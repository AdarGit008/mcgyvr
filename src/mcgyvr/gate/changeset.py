"""Capture the working-tree changes of a git repository relative to a base commit.

The changes are staged into a private temporary index, so the user's real index
and checkout are left untouched. Each changed path becomes a `FileChange`
carrying its git status letter, the line numbers it adds, and whether it is
binary or a symlink, which lets callers consume only text they can analyse.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

# Well-known git object id of the empty tree. It is used as the base when the
# repository has no commits yet, so `git read-tree` still has a tree to start
# the temporary index from and every worktree file shows up as added.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class ChangeSetError(Exception):
    """Raised when the repository cannot be inspected or the change data is
    inconsistent."""


@dataclass(frozen=True)
class FileChange:
    """One changed path: its git status, added line numbers, and content kind."""

    path: str
    status: str  # Single status letter from `--name-status`, e.g. "A", "M" or "D".
    added_lines: frozenset[int]
    is_binary: bool
    #: True when the working-tree path is a symlink; never set for deletions.
    #: Git tracks symlinks as text and shows the target as an added line, but a
    #: target is not source code, so the flag keeps it out of text analysis.
    is_link: bool = False

    @property
    def is_deletion(self) -> bool:
        return self.status == "D"

    def added_line_numbers(self) -> tuple[int, ...]:
        """Added line numbers in the new file, sorted ascending."""
        return tuple(sorted(self.added_lines))


@dataclass(frozen=True)
class ChangeSet:
    """All changes of a repository against a base revision."""

    repo: Path
    base: str
    files: tuple[FileChange, ...]

    @classmethod
    def detect(cls, repo: str | os.PathLike[str], base: str = "HEAD") -> ChangeSet:
        """Collect the worktree changes of `repo` against `base` into a `ChangeSet`."""
        root = Path(repo)
        # Fail fast on directories that are not a repository instead of
        # returning an empty change set for them. This only probes for a
        # `.git` entry, so layouts without one are rejected as well.
        if not (root / ".git").exists():
            raise ChangeSetError(f"{root} is not a git repository")

        resolved = _resolve_base(root, base)
        with _TemporaryIndex() as index:
            env = {**os.environ, "GIT_INDEX_FILE": str(index)}
            # Fill the private index with the base tree, then stage the whole
            # worktree into it, so the diff against the base also covers
            # untracked files and the user's own index is never modified.
            # Both diffs below run against this index and pass `--no-renames`
            # so their per-file entries pair up; the patch uses `-U0` to keep
            # only added and removed lines.
            _git(root, "read-tree", resolved, env=env)
            _git(root, "add", "-A", env=env)
            inventory = _git(
                root,
                "diff",
                "--cached",
                "--no-renames",
                "--no-color",
                "-z",
                "--name-status",
                resolved,
                env=env,
            )
            patch = _git(
                root,
                "diff",
                "--cached",
                "--no-renames",
                "--no-color",
                "--no-ext-diff",
                "-U0",
                resolved,
                env=env,
            )

        statuses = _parse_name_status(inventory)
        hunks = _parse_added_lines(patch)
        if len(statuses) != len(hunks):
            # The two listings come from separate git calls and are paired by
            # position below. Unequal counts would attribute added lines to the
            # wrong path, so refuse rather than produce a wrong change set.
            raise ChangeSetError(
                "change inventory and patch disagree on file count "
                f"({len(statuses)} vs {len(hunks)}); refusing to guess"
            )

        files = tuple(
            FileChange(
                path=path,
                status=status,
                added_lines=frozenset(added),
                is_binary=is_binary,
                is_link=status != "D" and (root / path).is_symlink(),
            )
            for (status, path), (added, is_binary) in zip(statuses, hunks, strict=True)
        )
        return cls(repo=root, base=resolved, files=files)

    def __iter__(self) -> Iterator[FileChange]:
        return iter(self.files)

    def __bool__(self) -> bool:
        return bool(self.files)

    def paths(self) -> tuple[str, ...]:
        return tuple(f.path for f in self.files)

    def text_changes(self) -> tuple[FileChange, ...]:
        """Changes whose content can be read as text: not binary, deleted or a
        symlink."""
        return tuple(
            f
            for f in self.files
            if not f.is_binary and not f.is_deletion and not f.is_link
        )


def _resolve_base(root: Path, base: str) -> str:
    """Return `base` as given, or the empty tree id when `HEAD` does not exist yet."""
    if base != "HEAD":
        return base
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
        cwd=root,
        capture_output=True,
    )
    return "HEAD" if proc.returncode == 0 else _EMPTY_TREE


def _git(
    root: Path,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> bytes:
    """Run git in `root` and return its stdout, raising `ChangeSetError` on failure."""
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        env=dict(env) if env is not None else None,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise ChangeSetError(f"git {args[0]} failed: {detail}")
    return proc.stdout


class _TemporaryIndex:
    """Context manager owning a temporary directory that holds a scratch git index."""

    def __init__(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="mcgyvr-gate-")

    def __enter__(self) -> Path:
        return Path(self._dir.name) / "index"

    def __exit__(self, *exc: object) -> None:
        self._dir.cleanup()


def _parse_name_status(raw: bytes) -> list[tuple[str, str]]:
    """Turn NUL-separated `--name-status -z` output into (status letter, path) pairs."""
    tokens = raw.split(b"\x00")
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if not status:  # Empty token: end of the NUL-separated listing.
            break
        path = tokens[i + 1] if i + 1 < len(tokens) else b""
        pairs.append((status.decode("ascii", "replace")[0], _decode_path(path)))
        i += 2
    return pairs


def _parse_added_lines(patch: bytes) -> list[tuple[set[int], bool]]:
    """Split a unified diff into per-file (added line numbers, is_binary) pairs."""
    files: list[tuple[set[int], bool]] = []
    added: set[int] = set()
    is_binary = False
    new_ln = 0
    started = False

    def flush() -> None:
        nonlocal added, is_binary, started
        if started:
            files.append((added, is_binary))
        added = set()
        is_binary = False
        started = False

    for line in patch.split(b"\n"):
        if line.startswith(b"diff --git "):
            flush()
            started = True
        elif line.startswith(b"Binary files "):
            is_binary = True
        elif line.startswith(b"@@ "):
            new_ln = _hunk_new_start(line)
        elif line.startswith(b"+") and not line.startswith(b"+++ "):
            added.add(new_ln)
            new_ln += 1
        # Any other line (file headers, removed lines) adds no line number, and
        # removed lines do not advance the new-file line counter either.
    flush()
    return files


def _hunk_new_start(header: bytes) -> int:
    """Read the new-file start line from a `@@ -a,b +c,d @@` hunk header."""
    plus = header.split(b"+", 1)[1]
    field = plus.split(b" ", 1)[0].split(b",", 1)[0]
    return int(field)


def _decode_path(raw: bytes) -> str:
    """Decode a git path, keeping undecodable bytes as surrogate escapes."""
    return raw.decode("utf-8", "surrogateescape")


def read_added_text(change: FileChange, repo: Path) -> Mapping[int, str]:
    """Map each added line number of `change` to its current line text in `repo`."""
    if (
        change.is_binary
        or change.is_deletion
        or change.is_link
        or not change.added_lines
    ):
        return {}
    path = repo / change.path
    try:
        lines = path.read_text(encoding="utf-8", errors="surrogateescape").split("\n")
    except OSError:
        return {}
    result: dict[int, str] = {}
    for n in change.added_lines:
        if 1 <= n <= len(lines):
            result[n] = lines[n - 1]
    return result


def read_current_text(change: FileChange, repo: Path) -> str:
    """Read the current working-tree text of `change`, or empty when unavailable."""
    if change.is_binary or change.is_deletion or change.is_link:
        return ""
    try:
        return (repo / change.path).read_text(
            encoding="utf-8", errors="surrogateescape"
        )
    except OSError:
        return ""


def read_base_text(change: FileChange, changeset: ChangeSet) -> str:
    """Read the text of `change`'s path at the base revision, or empty when
    unavailable."""
    if change.is_binary or change.is_link:
        return ""
    return read_text_at(changeset.repo, changeset.base, change.path) or ""


def read_text_at(repo: Path, base: str, path: str) -> str | None:
    """Read `path` as it exists at `base`, or None when git cannot produce it."""
    try:
        raw = _git(repo, "show", f"{base}:{path}")
    except (ChangeSetError, OSError):
        return None
    return raw.decode("utf-8", "surrogateescape")
