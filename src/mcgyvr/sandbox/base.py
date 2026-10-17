"""The sandbox contract: a throwaway git workspace per task, and the git
plumbing that fills it, judges it, restores it and takes it away again.

`Sandbox` is the abstract backend — a subclass supplies `run`, `_start` and
`_stop` — and everything the backends share lives here. The workspace is
populated from a source tree at a base revision and committed as its own git
base; checkpoints, snapshots and restores are expressed as git commits and tree
objects from there. Credentials are kept both out of a copied tree and out of
the environment a command is handed, every workspace is registered for removal
if its context manager is never exited, and `open_sandbox` picks the backend the
configuration asks for.
"""

from __future__ import annotations

import atexit
import contextlib
import fnmatch
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path, PurePosixPath
from typing import ClassVar

from mcgyvr.redact import scrub

_WORKSPACE_PREFIX = "mcgyvr-task-"

# The identity every commit inside a workspace is made under, so no host git
# configuration and no signing key have to be consulted.
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "mcgyvr",
    "GIT_AUTHOR_EMAIL": "sandbox@mcgyvr.invalid",
    "GIT_COMMITTER_NAME": "mcgyvr",
    "GIT_COMMITTER_EMAIL": "sandbox@mcgyvr.invalid",
}

# The shape of a variable name that names a credential: the word appearing
# anywhere in the name is enough, so `AWS_SECRET_ACCESS_KEY` and
# `SESSION_TOKEN` both match; `_KNOWN_CREDENTIAL_VARS` covers the names this
# pattern misses.
_CREDENTIAL_NAME = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_AUTH|APIKEY|SESSION)",
    re.IGNORECASE,
)

# Credentials whose names the pattern above would not catch, listed by name.
_KNOWN_CREDENTIAL_VARS = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    }
)


# The exit code a command is reported with when the sandbox killed it at the
# timeout: negative, so it cannot be mistaken for a status the command itself
# chose to exit with.
TIMEOUT_EXIT = -1

# The timeout a command gets when the caller names none, in seconds: a command
# that outlives it is killed and reported as timed out, with `TIMEOUT_EXIT` as
# its exit code. Fifteen minutes is long enough for a build or a test suite and
# short enough that a hung command still ends while the task can report it;
# both backends resolve a `None` timeout through `command_timeout`, so this one
# number governs each of them.
DEFAULT_COMMAND_TIMEOUT_S = 900.0


def command_timeout(timeout: float | None) -> float:
    """The timeout to give one command: `DEFAULT_COMMAND_TIMEOUT_S` when the
    caller names none, and otherwise the caller's value as given."""
    return DEFAULT_COMMAND_TIMEOUT_S if timeout is None else timeout


class SandboxError(Exception):
    """A sandbox could not do what was asked of it: a git command failed, the
    source could not be populated, or the workspace was used outside the context
    manager that creates it."""


class NestedGitError(SandboxError):
    """A `.git` entry was found below the workspace root. Host git would read the
    configuration of that repository, so work over this tree stops instead."""


def nested_git(root: Path) -> str | None:
    """The path, relative to `root`, of a `.git` entry below the workspace root,
    or `None` when there is none.

    The workspace's own `.git` at `root` is what makes it a repository and is
    skipped, as are the hidden entries beneath it. Names are visited in sorted
    order within each directory, so the reported entry is the first one met in a
    top-down walk.
    """
    for here, dirs, files in os.walk(root):
        top = Path(here) == root
        for name in sorted([*dirs, *files]):
            if name.lower() == ".git" and not (top and name == ".git"):
                return (Path(here) / name).relative_to(root).as_posix()
        if top:
            dirs[:] = [d for d in dirs if d != ".git"]
    return None


def refuse_nested_git(root: Path) -> None:
    """Raise `NestedGitError`, naming the entry, when the workspace holds a nested
    `.git`; say nothing when it does not."""
    found = nested_git(root)
    if found is not None:
        raise NestedGitError(
            f"{found} is a git entry inside the workspace; host git would run "
            f"its config, so nothing more is done over this tree"
        )


@dataclass(frozen=True)
class CommandResult:
    """What one command did: the argv it was given, the exit code, the captured
    `stdout` and `stderr`, and whether the sandbox killed it at the timeout."""

    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class Snapshot:
    """A workspace state to come back to: the git tree object standing for every
    tracked and non-ignored file, plus the ignored entries present at the time."""

    tree: str
    ignored: frozenset[str]


@dataclass(frozen=True)
class Restored:
    """What a restore changed: `removed` entries it deleted (directories ending in
    `/`) and `reverted` paths it took back from the snapshot."""

    removed: tuple[str, ...] = ()
    reverted: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.removed or self.reverted)

    def named(self, limit: int = 5) -> str:
        """The changed paths, deduplicated and sorted, in one line: the first
        `limit` of them, then how many more there are."""
        paths = sorted({*self.removed, *self.reverted})
        shown = ", ".join(paths[:limit])
        more = len(paths) - limit
        return f"{shown} (+{more} more)" if more > 0 else shown


def is_credential_var(name: str) -> bool:
    """Whether an environment variable name names a credential."""
    return name in _KNOWN_CREDENTIAL_VARS or bool(_CREDENTIAL_NAME.search(name))


def credential_env_names(env: Mapping[str, str]) -> frozenset[str]:
    """The names in `env` that `is_credential_var` calls credentials."""
    return frozenset(name for name in env if is_credential_var(name))


def safe_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """`extra` reduced to the entries that can be passed to a command.

    A name that looks like a credential is dropped, and so is any value the
    redactor would have to alter — that value is a secret whatever the variable
    is called.
    """
    env: dict[str, str] = {}
    for name, value in (extra or {}).items():
        if is_credential_var(name) or scrub(value) != value:
            continue  # a name or a value that holds a secret never reaches a command
        env[name] = value
    return env


# The open sandboxes, keyed by `id`, so that a workspace is still removed when
# its context manager is never exited: at interpreter exit the registrations
# are replayed. A value holds that sandbox's cleanup callables; the first
# removes the workspace and a backend may add more through `_register_reaper`.
# Keying by `id` rather than by the object keeps this mapping from holding a
# sandbox alive, and an entry is dropped as soon as its context exits.
_LIVE_REAPERS: dict[int, tuple[Callable[[], None], ...]] = {}


@cache
def _install_reaper() -> None:
    """Register `_reap_all` with `atexit`, once; later calls do nothing."""
    atexit.register(_reap_all)


def _reap_all() -> None:
    for reapers in list(_LIVE_REAPERS.values()):
        for reap in reapers:
            # Reaping is best effort and runs while the interpreter is going
            # down: one stubborn workspace must not keep the others from going.
            with contextlib.suppress(Exception):
                reap()


class Sandbox(ABC):
    """One task's isolation: a throwaway git workspace built from `source` at
    `base`, driven as a context manager.

    Entering the context creates a fresh temporary directory, populates it,
    commits it as the workspace's base and calls `_start`; leaving it calls
    `_stop` and removes the directory. From there the workspace is tracked with
    git: `checkpoint` and `restore_to` move along its own branch, while
    `snapshot` and `restore` judge the working tree without committing to it, and
    `reset` throws everything back to the base commit.

    A backend supplies `run`, `_start` and `_stop`, names the isolation it gives
    in `isolation`, and may list top-level workspace names it owns in `_kept` so
    that cleaning the workspace leaves them standing.
    """

    isolation: ClassVar[str]

    def __init__(
        self,
        source: str | os.PathLike[str],
        base: str = "HEAD",
        *,
        notes: Sequence[str] = (),
    ) -> None:
        self._source = Path(source)
        self._base = base
        self._workspace: Path | None = None
        self._base_commit: str | None = None
        self._source_commit: str = ""
        self.notes: tuple[str, ...] = tuple(notes)

    # The workspace exists only between `__enter__` and `__exit__`, and these
    # accessors refuse rather than pretend otherwise.

    @property
    def workspace(self) -> Path:
        """The temporary directory this sandbox works in."""
        if self._workspace is None:
            raise SandboxError("sandbox is not open — use it as a context manager")
        return self._workspace

    def __enter__(self) -> Sandbox:
        _install_reaper()
        self._workspace = Path(tempfile.mkdtemp(prefix=_WORKSPACE_PREFIX))
        _LIVE_REAPERS[id(self)] = (lambda: _remove_tree(self._workspace),)
        try:
            left_out: list[str] = []
            populated = _populate(
                self._source, self._workspace, self._base, left_out=left_out
            )
            self._base_commit, self._source_commit = populated
            if left_out:
                self.notes = (*self.notes, _left_out_note(left_out))
            self._start()
        except BaseException:
            # Setup failed part-way: take the workspace down again before the
            # error reaches the caller, so nothing stays on disk or registered.
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            self._stop()
        finally:
            _LIVE_REAPERS.pop(id(self), None)
            _remove_tree(self._workspace)
            self._workspace = None

    def reset(self) -> None:
        """Throw the workspace back to the base commit.

        Tracked changes are reverted and untracked and ignored files are removed,
        except the top-level entries `_kept` names. Checkpoints made since are no
        longer on the branch.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        _git(self.workspace, "reset", "--hard", self._base_commit)
        # `-x` takes ignored files too, so what an earlier run left behind is
        # not there for the next one to read.
        _git(self.workspace, "clean", "-ffdx", *self._kept_args())

    def checkpoint(self) -> str:
        """Commit the whole working tree, empty commits included, and return the
        new commit id — a point `restore_to` can bring the workspace back to."""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        refuse_nested_git(self.workspace)
        _git(self.workspace, "add", "-A")
        _git(
            self.workspace,
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "mcgyvr checkpoint",
            env={**os.environ, **_GIT_IDENTITY},
        )
        return _git(self.workspace, "rev-parse", "HEAD").decode("ascii").strip()

    def restore_to(self, checkpoint: str) -> None:
        """Put the workspace back on a commit `checkpoint` returned.

        `reset --hard` to it, then remove the untracked files left since; ignored
        files and the entries `_kept` names are left alone.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        _git(self.workspace, "reset", "--hard", checkpoint)
        _git(self.workspace, "clean", "-ffd", *self._kept_args())

    def drop_checkpoint(self) -> None:
        """Point the workspace branch back at the base commit and reset the index,
        leaving the working tree as it is, so the checkpoint commits in between
        are no longer part of what this workspace would deliver."""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        refuse_nested_git(self.workspace)
        _git(self.workspace, "reset", "--mixed", self._base_commit)

    def snapshot(self) -> Snapshot:
        """Record the workspace as it stands.

        The tree object covering its tracked and non-ignored files, plus the
        ignored entries present. A nested `.git` refuses the snapshot: nothing is
        judged over such a tree.
        """
        refuse_nested_git(self.workspace)
        return Snapshot(
            tree=_judged_tree(self.workspace),
            ignored=frozenset(_ignored_entries(self.workspace)),
        )

    def restore(self, snapshot: Snapshot) -> Restored:
        """Bring the workspace back to `snapshot`, without committing anything.

        Nested `.git` entries go, ignored entries the snapshot did not have go,
        paths added since go — taking any directory they brought into being with
        them — and paths changed or deleted since are checked out again. The
        top-level entries `_kept` names are left untouched. Returns what was
        removed and what was reverted.
        """
        workspace = self.workspace
        kept = set(self._kept())
        removed: list[str] = []
        while (entry := nested_git(workspace)) is not None:
            _remove_entry(workspace, entry)
            removed.append(entry)
        for entry in sorted(_ignored_entries(workspace) - snapshot.ignored):
            if entry.split("/", 1)[0] not in kept:
                _remove_entry(workspace, entry)
                removed.append(entry)
        added: list[str] = []
        reverted: list[str] = []
        for status, path in _tree_changes(workspace, snapshot.tree):
            (added if status == "A" else reverted).append(path)
        if added or removed:
            existed = _directories_of(
                [*_tree_paths(workspace, snapshot.tree), *snapshot.ignored]
            )
            for entry in sorted({_first_new(path, existed) for path in added}):
                if entry.split("/", 1)[0] not in kept:
                    _remove_entry(workspace, entry)
                    removed.append(entry)
            # Only directories the snapshot did not have are pruned, so a
            # directory the source legitimately has keeps standing even when it is
            # empty now.
            for entry in removed:
                _prune_empty_parents(workspace, entry, existed)
        if reverted:
            _checkout_from(workspace, snapshot.tree, reverted)
        return Restored(tuple(removed), tuple(reverted))

    def changed_since_base(self, snapshot: Snapshot) -> frozenset[str]:
        """The paths that differ between the base commit and `snapshot`'s tree,
        with no rename detection: a renamed path is reported under both names."""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        raw = _git(
            self.workspace,
            "diff-tree",
            "-r",
            "-z",
            "--no-renames",
            "--name-only",
            self._base_commit,
            snapshot.tree,
        )
        return frozenset(_nul_split(raw))

    def base_changeset_ref(self) -> str:
        """The commit in this workspace that `source` was populated at — the
        revision a delivery out of this workspace is compared against."""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        return self._base_commit

    def source_base_commit(self) -> str:
        """The commit in `source` that this workspace was built from.

        Raises when `source` names no committed revision — it is not a git
        repository, or nothing is committed yet — because delivery would then
        have no base to diff against, and a moving `HEAD` is not a substitute for
        one.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        if not self._source_commit:
            raise SandboxError(
                f"{self._source} names no revision this workspace was built from: "
                f"it is not a git repository, or it has nothing committed yet. "
                f"There is no base a delivery back into it could diff against, "
                f"and HEAD is not a substitute — it is a moving name"
            )
        return self._source_commit

    def _register_reaper(self, reaper: Callable[[], None]) -> None:
        """Add a cleanup callable to run at interpreter exit alongside the
        workspace removal, for whatever the backend brought up."""
        existing = _LIVE_REAPERS.get(id(self), ())
        _LIVE_REAPERS[id(self)] = (*existing, reaper)

    # What a backend supplies: `run` executes one command inside the isolation,
    # `_start` brings the isolation up once the workspace is populated, and
    # `_stop` takes it down again.

    @abstractmethod
    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run `command` inside the isolation, with no shell in between.

        `timeout` of `None` means `DEFAULT_COMMAND_TIMEOUT_S`; `env` is the whole
        environment the command gets; `cwd` is relative to the workspace. The
        result carries the exit code and the captured output, and a command that
        outlives its timeout is killed and reported as timed out with
        `TIMEOUT_EXIT` as its exit code.
        """

    def host_path(self, reported: str) -> Path:
        """Where a path the sandbox reported lives on this host. The base answer is
        the path itself: a workspace in a temporary directory is already on this
        host, which is what a backend with its own filesystem overrides."""
        return Path(reported)

    @abstractmethod
    def _start(self) -> None:
        """Bring the isolation up, once the workspace has been populated."""

    def _kept(self) -> tuple[str, ...]:
        """Top-level workspace names this backend owns, which cleaning the
        workspace must not touch."""
        return ()

    def _kept_args(self) -> list[str]:
        # `git clean` exclusions for those names, anchored at the workspace root.
        return [arg for name in self._kept() for arg in ("-e", f"/{name}")]

    @abstractmethod
    def _stop(self) -> None:
        """Take the isolation down; called on leaving, even when setup failed."""


# Building the workspace: get the source into it, note which source revision it
# came from, and commit the result as the workspace's own base.


def _populate(
    source: Path, workspace: Path, base: str, *, left_out: list[str] | None = None
) -> tuple[str, str]:
    """Fill `workspace` with `source` at `base`, and commit it as the base.

    A source that is a git repository with `base` committed is archived from that
    revision; anything else is copied file by file, minus `.git` and minus the
    files that hold secrets, whose relative paths are appended to `left_out`.

    Returns the workspace's base commit and the source revision, the latter `""`
    when the source names none.
    """
    revision = _source_commit(source, base)
    if (source / ".git").exists() and _has_commit(source, base):
        _archive_into(source, workspace, base)
    else:
        # There is no committed revision to archive, so the tree is copied as it
        # lies on disk — minus `.git`, which would bring the source's hooks and
        # config along, and minus anything that holds a secret.
        skipped = _copy_into(source, workspace)
        if left_out is not None:
            left_out.extend(skipped)

    _git(workspace, "init", "--quiet")
    _git(workspace, "add", "-A")
    _git(
        workspace,
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--quiet",
        "--allow-empty",
        "-m",
        "mcgyvr sandbox base",
        env={**os.environ, **_GIT_IDENTITY},
    )
    return _git(workspace, "rev-parse", "HEAD").decode("ascii").strip(), revision


def _source_commit(source: Path, base: str) -> str:
    """`base` resolved to a commit id in `source`, or `""` when it does not
    resolve: not a git repository, or nothing committed under that name."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "rev-parse",
            "--verify",
            "--quiet",
            f"{base}^{{commit}}",
        ],
        capture_output=True,
    )
    return (
        proc.stdout.decode("ascii", "replace").strip() if proc.returncode == 0 else ""
    )


def _has_commit(source: Path, base: str) -> bool:
    """Whether `base` names a commit in `source`, peeling a bare `HEAD` to the
    commit it points at."""
    ref = base if base != "HEAD" else "HEAD^{commit}"
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
    )
    return proc.returncode == 0


def _archive_into(source: Path, workspace: Path, base: str) -> None:
    """Extract the `git archive` of `source` at `base` into `workspace`, through
    the host `tar`; either step failing raises `SandboxError`."""
    archive = subprocess.run(
        ["git", "-C", str(source), "archive", "--format=tar", base],
        capture_output=True,
    )
    if archive.returncode != 0:
        detail = archive.stderr.decode("utf-8", "replace").strip()
        raise SandboxError(f"could not archive {source} at {base}: {detail}")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(workspace)],
        input=archive.stdout,
        capture_output=True,
    )
    if extract.returncode != 0:
        detail = extract.stderr.decode("utf-8", "replace").strip()
        raise SandboxError(f"could not extract archive into {workspace}: {detail}")


# A source that is not a git repository is copied rather than archived, so the
# files that hold secrets have to be recognised by name: these names are refused.
_SECRET_FILES = (
    ".env",
    ".env.*",
    ".envrc",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    ".netrc",
    "_netrc",
    ".git-credentials",
    ".pgpass",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
)

# Directories that hold credentials as a whole, refused whenever they are a
# directory.
_SECRET_DIRS = frozenset({".aws", ".gcloud", ".azure", ".ssh", ".gnupg", ".kube"})

# Directories where only named children hold credentials, the rest being
# ordinary configuration: `.docker/config.json` holds registry logins, and
# `.config/gcloud` and `.config/gh` hold theirs.
_SECRET_UNDER = {
    ".docker": frozenset({"config.json"}),
    ".config": frozenset({"gcloud", "gh"}),
}

# Login files that are only secret when they carry something: `holds_a_secret`
# reads them and looks for a token, password or auth entry.
_LOGIN_RC = frozenset({".npmrc", ".pypirc", ".yarnrc", ".yarnrc.yml"})

_RC_LOGIN = re.compile(r"(auth|token|password|passwd|secret)\w*\s*[=:]", re.IGNORECASE)


def holds_a_secret(path: Path) -> bool:
    """Whether `path` has to be kept out of the workspace.

    True for a secret directory, for a known secret child of a configuration
    directory, for a name matching `_SECRET_FILES`, and for a login file whose
    text holds a credential — one that cannot be read counts as holding one.
    """
    name = path.name
    if name in _SECRET_DIRS and path.is_dir():
        return True
    if name in _SECRET_UNDER.get(path.parent.name, frozenset()):
        return True
    if any(fnmatch.fnmatch(name, pattern) for pattern in _SECRET_FILES):
        return True
    if name in _LOGIN_RC and path.is_file():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return True  #
        return bool(_RC_LOGIN.search(text)) or scrub(text) != text
    return False


def _copy_into(source: Path, workspace: Path) -> tuple[str, ...]:
    """Copy `source` into `workspace`, leaving out every `.git` entry and every path
    `holds_a_secret` refuses.

    Returns the sorted relative paths left out; a tree that cannot be copied
    raises `SandboxError`.
    """
    skipped: list[str] = []

    def leave_out(directory: str, names: list[str]) -> set[str]:
        here = Path(directory)
        out = {".git"} & set(names)
        for name in names:
            if name not in out and holds_a_secret(here / name):
                out.add(name)
                skipped.append((here / name).relative_to(source).as_posix())
        return out

    try:
        shutil.copytree(source, workspace, dirs_exist_ok=True, ignore=leave_out)
    except OSError as exc:
        raise SandboxError(f"could not copy {source} into {workspace}: {exc}") from exc
    return tuple(sorted(skipped))


def _left_out_note(paths: Sequence[str]) -> str:
    """The note recording that the source was not a git repository and was copied
    whole, minus the secret-bearing paths the task therefore does not get."""
    return (
        "The source is not a git repository, so it was copied whole except for "
        "files that hold secrets, which the task does not get: " + ", ".join(paths)
    )


def _git(
    root: Path,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> bytes:
    """Run git in `root` with `args` and return its stdout.

    The output is captured, `env` replaces the environment when given, and a
    non-zero exit raises `SandboxError` carrying git's stderr.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        env=dict(env) if env is not None else None,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise SandboxError(f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout


# Judging a workspace: the tree object that stands for what it holds, the
# ignored entries git reports, and the diff between two such tree objects.


def _judged_tree(workspace: Path) -> str:
    """The tree object for the workspace as it stands.

    A throwaway index is filled with `git add -A`, so tracked and non-ignored
    files are all in and ignored files are all out, and the tree written from it
    names that state without touching the workspace's own index or history.
    """
    with tempfile.TemporaryDirectory(prefix="mcgyvr-snap-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(workspace, "add", "-A", env=env)
        return _git(workspace, "write-tree", env=env).decode("ascii").strip()


def _ignored_entries(workspace: Path) -> set[str]:
    """The ignored, untracked entries in the workspace, each directory collapsed to
    its path with a trailing slash."""
    raw = _git(
        workspace,
        "ls-files",
        "-z",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "--no-empty-directory",
    )
    return set(_nul_split(raw))


def _tree_changes(workspace: Path, before: str) -> list[tuple[str, str]]:
    """`(status, path)` pairs for what differs between tree `before` and the
    workspace now, with no rename detection; empty when the trees are equal."""
    after = _judged_tree(workspace)
    if after == before:
        return []
    raw = _git(
        workspace,
        "diff-tree",
        "-r",
        "-z",
        "--no-renames",
        "--name-status",
        before,
        after,
    )
    tokens = _nul_split(raw)
    return [(tokens[i][0], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]


def _tree_paths(workspace: Path, tree: str) -> list[str]:
    return _nul_split(_git(workspace, "ls-tree", "-r", "-z", "--name-only", tree))


def _directories_of(paths: Sequence[str]) -> set[str]:
    """Every directory path implied by `paths`: the ancestors of a file, and for an
    entry ending in `/` the directory itself as well."""
    found: set[str] = set()
    for path in paths:
        parts = path.rstrip("/").split("/")
        depth = len(parts) if path.endswith("/") else len(parts) - 1
        found.update("/".join(parts[:end]) for end in range(1, depth + 1))
    return found


def _first_new(path: str, existed: set[str]) -> str:
    """The shallowest ancestor directory of `path` that `existed` does not have, as
    a path ending in `/` — the entry to remove to take the whole new subtree with
    it — or `path` itself when every ancestor was already there."""
    parts = path.split("/")
    for end in range(1, len(parts)):
        directory = "/".join(parts[:end])
        if directory not in existed:
            return f"{directory}/"
    return path


def _remove_entry(workspace: Path, entry: str) -> None:
    """Delete `entry` from `workspace`: a file or symlink, or a directory with
    everything under it.

    A directory that resists removal is unlocked and tried once more, and
    `SandboxError` is raised if anything is still there afterwards.
    """
    path = workspace / entry.rstrip("/")
    if path.is_symlink() or path.is_file():
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():
            _unlock(path)
            shutil.rmtree(path, ignore_errors=True)
    if path.is_symlink() or path.exists():
        raise SandboxError(
            f"{entry} was left in the workspace and could not be removed"
        )


def _prune_empty_parents(workspace: Path, entry: str, existed: set[str]) -> None:
    """Remove the parent directories of a removed `entry` that are empty now,
    stopping at the first one that `existed` before the restore."""
    parts = entry.rstrip("/").split("/")[:-1]
    while parts and "/".join(parts) not in existed:
        with contextlib.suppress(OSError):  # not empty, or already gone: leave it
            (workspace.joinpath(*parts)).rmdir()
        parts.pop()


def _checkout_from(workspace: Path, tree: str, paths: Sequence[str]) -> None:
    """Write `paths` from tree `tree` back into `workspace` through a throwaway
    index, content and mode included; a failure raises `SandboxError`."""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-snap-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(workspace, "read-tree", tree, env=env)
        proc = subprocess.run(
            ["git", "-C", str(workspace), "checkout-index", "-f", "-z", "--stdin"],
            input=b"".join(p.encode("utf-8", "surrogateescape") + b"\0" for p in paths),
            capture_output=True,
            env=env,
        )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise SandboxError(f"git checkout-index failed in {workspace}: {detail}")


def _nul_split(raw: bytes) -> list[str]:
    return [t.decode("utf-8", "surrogateescape") for t in raw.split(b"\0") if t]


def _remove_tree(path: Path | None) -> None:
    """Remove the workspace directory, best effort: a tree that will not go is
    unlocked and tried again, and a survivor is reported on stderr rather than
    raised, since this runs while unwinding or at interpreter exit."""
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)
    if not path.exists():
        return
    _unlock(path)
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        print(f"mcgyvr: workspace {path} could not be removed", file=sys.stderr)


def _unlock(root: Path) -> None:
    """Give every directory under `root` owner read-write-search permission, so a
    tree a command made read-only can be removed; failures are ignored."""
    pending = [root]
    while pending:
        here = pending.pop()
        with contextlib.suppress(OSError):
            if here.is_symlink() or not here.is_dir():
                continue
            here.chmod(stat.S_IRWXU)
            pending.extend(here.iterdir())


# Choosing the backend: which mode a task runs in, and the caveats that come
# with it.


@dataclass(frozen=True)
class _SandboxChoice:
    """The mode chosen for a task, and the notes to attach to its sandbox
    explaining anything weaker about how it runs."""

    mode: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def choose_mode(
    configured: str, docker_available: bool, *, allow_fallback: bool = False
) -> _SandboxChoice:
    """The mode `configured` resolves to, given whether a Docker daemon answered.

    `tempdir` asked for by name resolves to `tempdir`, noted as the weaker mode.
    `docker` with no daemon raises unless `allow_fallback` lets the task fall back
    to `tempdir`, which is then noted as a fallback as well as a weaker mode.
    """
    if configured == "tempdir":
        return _SandboxChoice("tempdir", (_WEAKER_MODE_NOTE,))
    if not docker_available:
        if not allow_fallback:
            raise SandboxError(_NO_DAEMON_REFUSAL)
        return _SandboxChoice(
            "tempdir",
            (
                "Docker was requested but no daemon answered; "
                "`sandbox.allow_fallback` is on, so this task falls back to the "
                "temp-directory sandbox. " + _WEAKER_MODE_NOTE,
            ),
        )
    return _SandboxChoice("docker")


_NO_DAEMON_REFUSAL = (
    "`sandbox.mode` is `docker` and no Docker daemon answered, so the task is "
    "not run: falling back would run a contract's acceptance commands on this "
    "host instead of in a container. Start Docker, or choose the weaker mode "
    "by name — `sandbox.mode: tempdir`, or `--sandbox tempdir` for one run — "
    "or keep `docker` and set `sandbox.allow_fallback: true` to fall back to "
    "it whenever no daemon answers."
)

# The networks a task may be given. The container backend honours both; the
# tempdir backend runs on this host and cannot take the network away, so it
# refuses anything but `bridge`.
NETWORKS = ("bridge", "none")


def check_network(network: str) -> str:
    """`network` itself when it is one of `NETWORKS`, and a refusal otherwise."""
    if network not in NETWORKS:
        raise SandboxError(
            f"`sandbox.network: {network}` is not a network a task is given; "
            f"it is one of {', '.join(NETWORKS)}"
        )
    return network


_WEAKER_MODE_NOTE = (
    "This is the explicitly weaker mode: a contract's acceptance commands run "
    "without a shell, but each runs whatever program it names, on the host, "
    "not inside a container. Credentials are still kept out and each task "
    "still gets a throwaway git workspace, but process, network and resource "
    "isolation are the host's."
)


def open_sandbox(
    source: str | os.PathLike[str],
    *,
    mode: str = "docker",
    base: str = "HEAD",
    docker_available: bool | None = None,
    image: str | None = None,
    setup: Sequence[str] = (),
    endpoints: Sequence[str] = (),
    allow_fallback: bool = False,
    network: str = "bridge",
) -> Sandbox:
    """The backend the mode and configuration ask for, not yet entered.

    A mode that may start a container first refuses a daemon named through
    `DOCKER_HOST` or `DOCKER_CONTEXT`: a task's container must run on this
    machine's daemon. Docker availability is
    detected when the caller does not say, and `choose_mode` then decides between
    the two backends — refusing, or falling back when `allow_fallback` permits it,
    when `docker` was asked for and no daemon answered. The tempdir backend needs
    `network` to be `bridge`: it runs on this host and cannot take the network
    away.
    """
    check_network(network)
    if mode != "tempdir":
        # Whatever `mode` says, a daemon reached through `DOCKER_HOST` or
        # `DOCKER_CONTEXT` is not this machine's, and no container the product
        # starts may land there; that is refused before any mode is chosen.
        from mcgyvr.sandbox.image import foreign_daemon

        refusal = foreign_daemon()
        if refusal is not None:
            raise SandboxError(refusal)

    if docker_available is None:
        from mcgyvr.detect import detect_docker

        docker_available, _ = detect_docker()

    choice = choose_mode(mode, docker_available, allow_fallback=allow_fallback)

    if choice.mode == "docker":
        from mcgyvr.sandbox.docker import DockerSandbox

        return DockerSandbox(
            source,
            base=base,
            image=image,
            setup=tuple(setup),
            endpoints=tuple(endpoints),
            network=network,
            notes=choice.notes,
        )

    if network != "bridge":
        raise SandboxError(
            f"`sandbox.network: {network}` asks for a task with no network, and "
            f"this task would run in the temp-directory sandbox, on this host, "
            f"where mcgyvr cannot take the network away. Run it in a container "
            f"(`sandbox.mode: docker`, with a daemon that answers), or set "
            f"`sandbox.network: bridge`."
        )

    from mcgyvr.sandbox.tempdir import TempDirSandbox

    return TempDirSandbox(source, base=base, notes=choice.notes)


def workdir(cwd: str | None) -> PurePosixPath:
    """`cwd` as a path inside the workspace: `.` when none was given, and an
    absolute path or one that climbs out with `..` is refused."""
    if cwd is None:
        return PurePosixPath(".")
    within = PurePosixPath(cwd)
    if within.is_absolute() or ".." in within.parts:
        raise SandboxError(f"a command runs inside the workspace, not at {cwd!r}")
    return within


def merge_env(*layers: Mapping[str, str] | None) -> dict[str, str]:
    """`layers` merged in order, later layers winning, and the result reduced by
    `safe_env` to what a command may be handed."""
    merged: dict[str, str] = {}
    for layer in layers:
        merged.update(layer or {})
    return safe_env(merged)
