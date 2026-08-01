"""Detect the worker's change once, and share it.

Every gate check needs the same two facts: which files changed, and which
lines the worker *added*. Deriving that per check is the difference between a
constant and a linear number of subprocesses — local-ai measured 3 spawns
against 51 for a 25-file change once this was shared. So the whole change is
computed here, in a fixed number of git invocations regardless of how many
files moved, and threaded into every check.

The change is computed against a *base* tree — the state of the repository
before the worker ran. A worker in a sandbox leaves a mix of modified tracked
files, brand-new untracked files, and deletions; all three have to be seen as
one change with correct added-line attribution. Rather than special-case each,
we stage the working tree into a **throwaway index** seeded from the base and
diff that against the base. One code path covers tracked edits, untracked
additions and deletions, and it does not touch the repository's real index or
working tree.

Paths are read from git's ``-z`` machine output, so a filename with spaces,
quotes or non-ASCII characters is never quoted and can never cause a check to
silently skip a file (the failure mode this module exists to prevent).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

# The well-known SHA-1 of git's empty tree. Diffing against it turns "every
# line is new" into the same code path as any other base, which is what a
# repository with no commit yet needs.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class ChangeSetError(Exception):
    """The change could not be computed (git failed, or the repo is unusable)."""


@dataclass(frozen=True)
class FileChange:
    """One path the worker touched, and the lines it added there.

    ``added_lines`` are 1-based line numbers in the *new* version of the file.
    A deletion adds nothing; a binary change cannot be attributed by line, so
    both carry an empty set. Checks that scan added text therefore iterate
    ``added_lines`` and are automatically inert on deletes and binaries.
    """

    path: str
    status: str  # single-letter git status: A, M, D, T (renames are split)
    added_lines: frozenset[int]
    is_binary: bool

    @property
    def is_deletion(self) -> bool:
        return self.status == "D"

    def added_line_numbers(self) -> tuple[int, ...]:
        """Added line numbers in ascending order."""
        return tuple(sorted(self.added_lines))


@dataclass(frozen=True)
class ChangeSet:
    """The worker's whole change against a base, computed once.

    Construct with :meth:`detect`. Instances are immutable and safe to thread
    into every check.
    """

    repo: Path
    base: str
    files: tuple[FileChange, ...]

    @classmethod
    def detect(cls, repo: str | os.PathLike[str], base: str = "HEAD") -> ChangeSet:
        """Compute the change in ``repo`` against ``base`` (default ``HEAD``).

        ``base`` is any tree-ish naming the pre-worker state. When it is
        ``HEAD`` and the repository has no commit yet, the empty tree is used
        so a first-ever change is attributed as wholly added rather than
        failing to resolve.
        """
        root = Path(repo)
        # `.git` is a directory in a primary checkout and a file in a linked
        # worktree; either satisfies us. A subdirectory is never passed here —
        # the gate always addresses a repository root.
        if not (root / ".git").exists():
            raise ChangeSetError(f"{root} is not a git repository")

        resolved = _resolve_base(root, base)
        with _TemporaryIndex() as index:
            env = {**os.environ, "GIT_INDEX_FILE": str(index)}
            # Seed the throwaway index with the base tree, then stage the whole
            # working tree over it. What remains different from the base is
            # exactly the worker's change — modifications, additions (formerly
            # untracked) and deletions alike. `add -A` honours .gitignore, so a
            # change to an ignored path is excluded, matching what delivery
            # could actually commit.
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
            # The two diffs are the same diff rendered two ways, so they list
            # the same files in the same order. A mismatch means our parser
            # lost a file — surface it rather than silently misattribute.
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

    def with_additions(self) -> tuple[FileChange, ...]:
        """Files that gained at least one line — where added-line checks run."""
        return tuple(f for f in self.files if f.added_lines)

    def text_changes(self) -> tuple[FileChange, ...]:
        """Non-binary, non-deleted changes — the scannable surface."""
        return tuple(f for f in self.files if not f.is_binary and not f.is_deletion)


def _resolve_base(root: Path, base: str) -> str:
    """Return a tree-ish that exists, falling back to the empty tree.

    Only ``HEAD`` is softened — an explicit base that does not resolve is a
    caller error worth failing on.
    """
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
    """Run a git command, returning raw stdout bytes.

    Bytes, not text: git path output is only reliably decoded once we have
    split on NUL, and some content is not UTF-8.
    """
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
    """A throwaway git index file, removed on exit.

    A plain NamedTemporaryFile would hand git an existing empty file, which it
    reads as a valid empty index — usable, but we want a path git creates
    itself. We reserve a name in a temp dir and let git populate it.
    """

    def __init__(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="mcgyvr-gate-")

    def __enter__(self) -> Path:
        return Path(self._dir.name) / "index"

    def __exit__(self, *exc: object) -> None:
        self._dir.cleanup()


def _parse_name_status(raw: bytes) -> list[tuple[str, str]]:
    """Parse ``--name-status -z`` into ``(status, path)`` pairs.

    With ``--no-renames`` every record is ``STATUS\\0PATH\\0``; there are no
    two-path rename/copy records to disambiguate. ``-z`` means paths are
    verbatim — never quoted — so a space or non-ASCII byte in a name is
    carried through intact.
    """
    tokens = raw.split(b"\x00")
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if not status:  # trailing NUL leaves an empty final token
            break
        path = tokens[i + 1] if i + 1 < len(tokens) else b""
        pairs.append((status.decode("ascii", "replace")[0], _decode_path(path)))
        i += 2
    return pairs


def _parse_added_lines(patch: bytes) -> list[tuple[set[int], bool]]:
    """Per file, the set of added new-file line numbers and whether it is binary.

    Returned in patch order, which is the same order as ``--name-status`` above,
    so the two are zipped positionally. This sidesteps re-parsing the possibly
    quoted path out of the patch header only to match it back to the inventory.

    ``-U0`` means hunks carry no context lines: every ``+`` line is an addition,
    and its number is read straight off the hunk header's new-file start.
    """
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
        # '-' lines and the '---'/'+++' headers do not advance the new-file
        # counter; with -U0 there are no ' ' context lines to consider.
    flush()
    return files


def _hunk_new_start(header: bytes) -> int:
    """Extract the new-file start line from ``@@ -a,b +c,d @@``.

    ``+c`` may omit the count (``+c`` means ``+c,1``). A hunk that only deletes
    is written ``+c,0``; it produces no ``+`` lines, so its start is never used.
    """
    plus = header.split(b"+", 1)[1]
    field = plus.split(b" ", 1)[0].split(b",", 1)[0]
    return int(field)


def _decode_path(raw: bytes) -> str:
    """Decode a git path to str, preserving forward slashes.

    ``surrogateescape`` keeps a non-UTF-8 byte sequence round-trippable rather
    than raising, so an oddly encoded filename still appears in the change set
    (and can be flagged) instead of aborting the whole gate run.
    """
    return raw.decode("utf-8", "surrogateescape")


def read_added_text(change: FileChange, repo: Path) -> Mapping[int, str]:
    """The text of each added line, keyed by line number.

    A convenience for checks that scan added content (secrets, structural
    forms). Reads the current on-disk file — the worker's output — and returns
    only the lines :class:`ChangeSet` attributed to the worker. Binary and
    deleted files yield nothing.
    """
    if change.is_binary or change.is_deletion or not change.added_lines:
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
