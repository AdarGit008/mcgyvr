"""The sandbox interface both modes implement, and everything they share.

Two modes exist — a container (:mod:`mcgyvr.sandbox.docker`) and a temp
directory (:mod:`mcgyvr.sandbox.tempdir`) — and #30 requires that nothing
above them cares which is in use and that they share their test suite rather
than having two. So the seam between them is kept as small as it can be:

**everything except where a command runs lives here.** The workspace is a
throwaway directory with a fresh git repository, populated from the target
repository and committed once as the *base*. The gate judges the worker's
change as a real diff against that base, and :meth:`Sandbox.reset` restores
it between attempts. That workspace, its git repository, and its teardown are
identical in both modes; only :meth:`Sandbox.run` differs — on the host for a
temp directory, inside a container for Docker.

Two invariants are enforced here rather than trusted to each mode:

1. **Nothing survives a finished task.** The workspace is removed on success,
   on failure and on interrupt, by a context manager whose ``__exit__`` runs
   even when the body raises ``KeyboardInterrupt`` — and, as a backstop for
   an interpreter exit with a sandbox still open, by an ``atexit`` reaper that
   reaps whatever is still registered. The reaper does not run on
   ``os._exit``, a fatal signal or an interpreter crash.
2. **No credential reaches a task.** The environment a command runs in is
   built from an explicit allowlist, never inherited from the host, and any
   caller-supplied variable whose name looks like a credential is dropped
   before it can enter. ``SECURITY.md`` makes this a red-failing invariant,
   so :func:`credential_env_names` is the check a test asserts against.
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

# Identity used for the base commit. Deliberately not the host user's: the
# sandbox's git history is scaffolding the gate reads, never authorship.
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "mcgyvr",
    "GIT_AUTHOR_EMAIL": "sandbox@mcgyvr.invalid",
    "GIT_COMMITTER_NAME": "mcgyvr",
    "GIT_COMMITTER_EMAIL": "sandbox@mcgyvr.invalid",
}

# A variable name that looks like a secret. Broad on purpose: this guards a
# security invariant, so a false positive (dropping a harmless var) is the
# safe direction and a false negative is not.
_CREDENTIAL_NAME = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_AUTH|APIKEY|SESSION)",
    re.IGNORECASE,
)

# Provider variables that do not match the shape above but still hold keys.
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


#: The exit code reported for a command the wall-clock ceiling killed.
TIMEOUT_EXIT = -1

#: The ceiling a sandbox command runs under when nothing else supplies one —
#: no caller ceiling and no ``task_timeout_s`` in config. A command with no
#: bound at all hangs a task forever, so the sandbox carries its own. It is a
#: default, not a measurement: the same 900s the config schema defaults
#: ``task_timeout_s`` to, chosen so a configured install and an unconfigured
#: one behave alike. The bounds on the docker CLI calls beneath a command are
#: :data:`~mcgyvr.sandbox.image.DOCKER_CALL_TIMEOUT_S` and
#: :data:`~mcgyvr.sandbox.image.DOCKER_BUILD_TIMEOUT_S`, and are defaults in
#: the same sense.
DEFAULT_COMMAND_TIMEOUT_S = 900.0


def command_timeout(timeout: float | None) -> float:
    """The ceiling one command runs under: the caller's, or the built-in one.

    Both modes run this over what they were handed, so ``run(..., timeout=None)``
    is a command with the default ceiling rather than an unbounded one.
    """
    return DEFAULT_COMMAND_TIMEOUT_S if timeout is None else timeout


class SandboxError(Exception):
    """A sandbox could not be created, populated, or torn down."""


class NestedGitError(SandboxError):
    """A ``.git`` entry below the workspace root, which host git would enter."""


def nested_git(root: Path) -> str | None:
    """The first ``.git`` entry below ``root``, as a relative path, or ``None``.

    Host git over a tree holding a nested repository runs a child git inside
    it, and that child runs the nested repository's own ``core.fsmonitor`` and
    filter drivers. The top-level ``.git`` is the host's and is mounted
    read-only into a container; any other one was written by a command, so no
    host git is run over a tree that holds one. Directory or file (a
    ``gitdir:`` pointer), in any case. Symlinks are not followed.
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
    """Raise :class:`NestedGitError` naming the entry when ``root`` holds one."""
    found = nested_git(root)
    if found is not None:
        raise NestedGitError(
            f"{found} is a git entry inside the workspace; host git would run "
            f"its config, so nothing more is done over this tree"
        )


@dataclass(frozen=True)
class CommandResult:
    """The outcome of one command run inside a sandbox.

    ``timed_out`` is distinct from a non-zero ``exit_code``: a command the
    contract's wall-clock ceiling killed is not the same as one that ran and
    failed, and #38's acceptance logic needs to tell them apart.
    """

    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def is_credential_var(name: str) -> bool:
    """Whether an environment variable name looks like it holds a secret."""
    return name in _KNOWN_CREDENTIAL_VARS or bool(_CREDENTIAL_NAME.search(name))


def credential_env_names(env: Mapping[str, str]) -> frozenset[str]:
    """The credential-shaped names in ``env`` — empty is the required state.

    A task container's environment must satisfy ``credential_env_names(env)
    == frozenset()``. This is the exact assertion ``SECURITY.md`` calls for,
    factored out so the same check guards construction and the test.
    """
    return frozenset(name for name in env if is_credential_var(name))


def safe_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a task environment from nothing, adding only vetted extras.

    The base is empty — the host environment is never inherited — so a
    credential can only appear if a caller passes one, and this drops those
    before they enter. Everything a runtime needs on top of the image's own
    defaults (a working directory, a locale) is set by the mode, not here.
    A value holding a URL with ``user:password@`` in it is a credential under
    any name (an index, database or proxy URL), and is dropped the same way.
    """
    env: dict[str, str] = {}
    for name, value in (extra or {}).items():
        if is_credential_var(name) or scrub(value) != value:
            continue  # a caller mistake must not become a leak
        env[name] = value
    return env


# --- process-exit reaper -------------------------------------------------
#
# The context manager is the primary teardown path and covers interrupt,
# because a `with` unwinds on KeyboardInterrupt. This registry is the
# backstop for the case the context manager cannot cover — a normal
# interpreter exit with a sandbox still registered. It does not run on
# `os._exit`, a fatal signal or an interpreter crash. Each mode registers a
# cheap idempotent callable.
_LIVE_REAPERS: dict[int, tuple[Callable[[], None], ...]] = {}


@cache
def _install_reaper() -> None:
    """Register the exit reaper, once per process.

    Memoised rather than latched behind a module flag. The registry above has
    to be process-wide — there is one process exit to hook — but the *flag* did
    not have to be rebindable, and "no global mutable state" is checkable
    only if the exceptions are zero: a guard that allows one legitimate
    ``global`` allows the next one that claims to be legitimate.
    """
    atexit.register(_reap_all)


def _reap_all() -> None:
    for reapers in list(_LIVE_REAPERS.values()):
        for reap in reapers:
            # A reaper must never raise on exit: a failed cleanup of one
            # resource must not block cleanup of the next.
            with contextlib.suppress(Exception):
                reap()


class Sandbox(ABC):
    """One task's isolated workspace. Use as a context manager.

    Populating the workspace, its git base commit, resetting it, and tearing
    it down are shared; a subclass supplies only how a command runs and any
    mode-specific setup/teardown around the workspace (a container's create
    and remove). ``isolation`` names the strength of the mode for the user,
    and ``notes`` carry anything that had to be surfaced once at open.
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

    # -- lifecycle --------------------------------------------------------

    @property
    def workspace(self) -> Path:
        """The host path of the workspace. Valid only inside the context."""
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
            # A failure mid-open must not leave a half-built sandbox behind.
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
        """Discard everything since the base commit, so the next attempt is clean.

        A failed attempt leaves no trace in the next (#27): tracked edits are
        reverted and untracked files — including ignored ones a command may
        have written — are removed. Runs on the host workspace, which both
        modes share.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        _git(self.workspace, "reset", "--hard", self._base_commit)
        # `-ff` removes nested repositories too; neither command runs their config.
        _git(self.workspace, "clean", "-ffdx", *self._kept_args())

    def checkpoint(self) -> str:
        """Commit the workspace's current state and return the commit to restore to.

        A snapshot for a caller that is about to write and reset and wants to
        come back to exactly this state — a best-of draw loop, say. Paired with
        :meth:`drop_checkpoint`, which returns ``HEAD`` to the base once the
        caller is done, leaving the working tree where it was.
        """
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
        """Return the workspace to a :meth:`checkpoint` snapshot, dropping the rest.

        Everything since the snapshot — tracked edits, new files, deletions —
        is discarded. Ignored files are deliberately left alone: the snapshot
        does not commit them (``git add -A`` honours ``.gitignore``), so a
        caller's ignored files are part of the state to preserve, not draw
        by-product to sweep.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        _git(self.workspace, "reset", "--hard", checkpoint)
        _git(self.workspace, "clean", "-ffd", *self._kept_args())

    def drop_checkpoint(self) -> None:
        """Return ``HEAD`` to the base commit, keeping the working tree as it is.

        The reverse of :meth:`checkpoint`: the snapshot commit is left for git to
        collect, ``HEAD`` moves back to the base, and the working tree — the
        caller's state, restored by :meth:`restore_to` — stays put as uncommitted
        changes again.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        refuse_nested_git(self.workspace)
        _git(self.workspace, "reset", "--mixed", self._base_commit)

    def base_changeset_ref(self) -> str:
        """The base ref the gate diffs the worker's change against.

        A commit in the *workspace's* own repository — the one ``git init``
        made here — and therefore meaningful only inside this workspace. It is
        not a revision of the source repository and resolves nowhere else, so it
        is not what :func:`mcgyvr.deliver.deliver` diffs against; that wants
        :meth:`source_base_commit`.
        """
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        return self._base_commit

    def source_base_commit(self) -> str:
        """The revision of the *source* repository this workspace was built from.

        The same question ``base`` asked at construction, answered as a
        concrete commit: it is the revision the worker started from, and it is
        the one value here that means anything back in the repository a
        delivery commits into. :meth:`base_changeset_ref` is its
        workspace-local twin and the two are never equal — a delivery handed
        the wrong one fails to resolve its base.

        Raises when the source could name no commit — a non-git directory, or a
        repository with nothing committed yet. Both are populated by copying, and
        neither has a revision for a caller to diff against, so there is no
        answer to give. Delivery refuses an empty base by name, and this
        refuses to produce one.
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
        """Add a teardown callback the process-exit reaper runs on a hard crash.

        A mode registers whatever it stood up (a container) so it is reaped
        even when a crash skips ``__exit__``. Reapers must be idempotent and
        must not raise. The workspace already registers itself in ``__enter__``.
        """
        existing = _LIVE_REAPERS.get(id(self), ())
        _LIVE_REAPERS[id(self)] = (*existing, reaper)

    # -- mode seam --------------------------------------------------------

    @abstractmethod
    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        """Run one command in the sandbox and capture its result.

        ``env`` is additive and vetted: it is layered onto the mode's minimal
        environment through :func:`safe_env`, so no credential can enter even
        if a caller forwards one.

        ``timeout`` is a ceiling in seconds; ``None`` asks for the built-in
        :data:`DEFAULT_COMMAND_TIMEOUT_S` rather than for no ceiling at all.
        Nothing a sandbox runs is unbounded.

        ``cwd`` is a directory inside the workspace, relative to it, to run
        in; ``None`` is the workspace itself (:func:`workdir`).
        """

    def host_path(self, reported: str) -> Path:
        """A path a command printed, as the host reads it.

        The workspace is the same directory on both sides in the temp-directory
        mode; the container mode sees it at another path and overrides this.
        """
        return Path(reported)

    @abstractmethod
    def _start(self) -> None:
        """Mode-specific setup after the workspace exists (create a container)."""

    def _kept(self) -> tuple[str, ...]:
        """Top-level workspace entries a clean must leave: the mode's own.

        None by default. The container mode names the mount points of the
        dependency volumes it keeps visible (see
        :class:`~mcgyvr.sandbox.docker.DockerSandbox`).
        """
        return ()

    def _kept_args(self) -> list[str]:
        # `-e` holds under `-x` too: it is the one ignore rule `-x` keeps.
        return [arg for name in self._kept() for arg in ("-e", f"/{name}")]

    @abstractmethod
    def _stop(self) -> None:
        """Mode-specific teardown before the workspace is removed. Idempotent."""


# --- workspace population (shared, host-side git) ------------------------


def _populate(
    source: Path, workspace: Path, base: str, *, left_out: list[str] | None = None
) -> tuple[str, str]:
    """Fill ``workspace`` from ``source``, commit it, and name both bases.

    When ``source`` is a git repository the base tree is taken with
    ``git archive`` — exactly the tracked content of ``base``, no ``.git``,
    no untracked heavyweight directories (``node_modules``, ``.venv``) that a
    copy would drag in. A non-git source is copied whole minus the files that
    hold secrets (:func:`_copy_into`), whose paths are appended to
    ``left_out``. Either way the
    workspace then gets its own fresh git repository with a single base
    commit, which is what makes the worker's change a real diff and
    :meth:`Sandbox.reset` possible.

    Two commits come back because they answer two different questions and
    conflating them raises: the workspace's own base commit, which the gate
    diffs against here, and the source revision that workspace was built from,
    which is what a delivery back in the source repository can diff against. The
    second is ``""`` when the source has no commit to name.
    """
    revision = _source_commit(source, base)
    if (source / ".git").exists() and _has_commit(source, base):
        _archive_into(source, workspace, base)
    else:
        # A non-git source, or a git repo with no commit yet to archive, is
        # copied minus its secrets; the fresh git repository below becomes its
        # base.
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
    """``base`` as a concrete commit in ``source``, or ``""`` if it names none.

    Resolved at open rather than left as the caller's string, because ``HEAD``
    is a moving name: a delivery diffing against ``HEAD`` after the run is
    diffing against wherever the branch has got to, which is not where the
    worker started.
    """
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
    """Whether ``base`` resolves to a commit in ``source``.

    A freshly ``git init``'d repository has none; there is nothing to archive,
    so population copies the working tree instead. When ``base`` is not
    ``HEAD`` it names a specific ref the caller asserts exists.
    """
    ref = base if base != "HEAD" else "HEAD^{commit}"
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
    )
    return proc.returncode == 0


def _archive_into(source: Path, workspace: Path, base: str) -> None:
    """Extract ``base``'s tracked tree from a git ``source`` into ``workspace``."""
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


#: File names a non-git source is copied without, whatever they hold: each is a
#: place a secret is kept. A pattern is matched against the name alone.
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

#: Directories a non-git source is copied without: cloud and remote-login
#: credential folders.
_SECRET_DIRS = frozenset({".aws", ".gcloud", ".azure", ".ssh", ".gnupg", ".kube"})

#: Credential files that live inside a folder that is otherwise harmless, keyed
#: by the folder's name: ``.docker/config.json`` holds registry logins,
#: ``.config/gcloud`` and ``.config/gh`` hold cloud and GitHub tokens.
_SECRET_UNDER = {
    ".docker": frozenset({"config.json"}),
    ".config": frozenset({"gcloud", "gh"}),
}

#: Package-manager settings files that are copied unless they hold a login: a
#: registry URL is configuration, a token beside it is a secret.
_LOGIN_RC = frozenset({".npmrc", ".pypirc", ".yarnrc", ".yarnrc.yml"})

_RC_LOGIN = re.compile(r"(auth|token|password|passwd|secret)\w*\s*[=:]", re.IGNORECASE)


def _holds_a_secret(path: Path) -> bool:
    """Whether a non-git copy leaves ``path`` behind, by its name or its login."""
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
            return True  # unread is not known clean
        return bool(_RC_LOGIN.search(text)) or scrub(text) != text
    return False


def _copy_into(source: Path, workspace: Path) -> tuple[str, ...]:
    """Copy a non-git ``source`` into ``workspace``, minus VCS metadata and secrets.

    A git source brings its tracked files only, so an ignored ``.env`` stays
    behind on its own. A non-git source has no ignore rules to say what is
    whose, so what is left behind is decided by name: dotenv files, keys and
    certificates, ``.netrc``, cloud and SSH credential folders, a registry
    login, and a package-manager settings file that carries a token. The
    paths left behind come back, relative to ``source``, so the run can say
    which files its task does not have.
    """
    skipped: list[str] = []

    def leave_out(directory: str, names: list[str]) -> set[str]:
        here = Path(directory)
        out = {".git"} & set(names)
        for name in names:
            if name not in out and _holds_a_secret(here / name):
                out.add(name)
                skipped.append((here / name).relative_to(source).as_posix())
        return out

    try:
        shutil.copytree(source, workspace, dirs_exist_ok=True, ignore=leave_out)
    except OSError as exc:
        raise SandboxError(f"could not copy {source} into {workspace}: {exc}") from exc
    return tuple(sorted(skipped))


def _left_out_note(paths: Sequence[str]) -> str:
    """The note a sandbox carries when its non-git copy left secrets behind."""
    return (
        "The source is not a git repository, so it was copied whole except for "
        "files that hold secrets, which the task does not get: " + ", ".join(paths)
    )


def _git(
    root: Path,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> bytes:
    """Run a git command in ``root``, raising :class:`SandboxError` on failure."""
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        env=dict(env) if env is not None else None,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise SandboxError(f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout


def _remove_tree(path: Path | None) -> None:
    """Remove a workspace, tolerating a partially-created or already-gone one.

    A command runs as the host user and can take the permissions off a
    directory it made, so a tree that will not go is given them back and
    removed again. One that still survives is named on stderr rather than left
    behind in silence.
    """
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
    """Give the owner full access to every directory under ``root``.

    Symlinks are not followed, so nothing outside the tree is touched.
    """
    pending = [root]
    while pending:
        here = pending.pop()
        with contextlib.suppress(OSError):
            if here.is_symlink() or not here.is_dir():
                continue
            here.chmod(stat.S_IRWXU)
            pending.extend(here.iterdir())


# --- factory -------------------------------------------------------------


@dataclass(frozen=True)
class _SandboxChoice:
    """Which mode was chosen and why — used to surface the weaker mode once."""

    mode: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def choose_mode(
    configured: str, docker_available: bool, *, allow_fallback: bool = False
) -> _SandboxChoice:
    """Resolve the effective sandbox mode from config and Docker availability.

    ``docker`` configured without a daemon is refused (:class:`SandboxError`):
    falling back puts a contract's acceptance commands on the host, and that is
    for the user to choose ahead of time, not to read about in a note after the
    run started. The refusal names both ways on: ``tempdir`` by name, or
    ``allow_fallback`` (``sandbox.allow_fallback``), which falls back and says
    so once. ``tempdir`` configured is an explicit choice and carries the same
    weaker-mode note.
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

#: Where a task container is attached: Docker's own default network, or none.
#: The names are Docker's, passed to ``--network`` untouched.
NETWORKS = ("bridge", "none")


def check_network(network: str) -> str:
    """``network`` if a task can be given it, else :class:`SandboxError` by name."""
    if network not in NETWORKS:
        raise SandboxError(
            f"`sandbox.network: {network}` is not a network a task is given; "
            f"it is one of {', '.join(NETWORKS)}"
        )
    return network


_WEAKER_MODE_NOTE = (
    "This is the explicitly weaker mode: acceptance commands are arbitrary "
    "shell from a contract and run on the host, not inside a container. "
    "Credentials are still kept out and each task still gets a throwaway git "
    "workspace, but process, network and resource isolation are the host's."
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
    """Construct the sandbox a task should run in, not yet entered.

    ``mode`` comes from ``sandbox.mode`` in config; ``image``/``setup``,
    ``allow_fallback`` and ``network`` from the rest of the ``sandbox`` block.
    ``docker`` with no daemon is refused unless ``allow_fallback`` is set
    (:func:`choose_mode`). ``network="none"`` is kept by a container and
    refused by the temp-directory mode, which runs commands on the host and
    cannot take the network away — chosen by name or reached by the fallback,
    it is not claimed and then not kept. ``endpoints`` are the configured worker
    ``base_url``s the container must be able to reach; loopback ones are
    translated to the host alias by the Docker mode, and they are passed only
    there — the temp-directory mode already runs on the host. Docker
    availability is detected here unless the caller supplies it (tests, and
    callers that already probed). The returned sandbox carries ``notes`` naming
    the weaker mode when one is in force — the caller surfaces them once at open.
    """
    check_network(network)
    if mode != "tempdir":
        # Before the daemon is even probed: a `docker info` under DOCKER_HOST
        # would go wherever the variable points, a rig included, and the
        # sandbox runs on this machine's daemon or nowhere.
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
    """``cwd`` as a path under the workspace, refused if it would leave it.

    Both modes resolve a command's working directory through this, so a
    caller's ``cwd`` means the same place in each and never one outside.
    """
    if cwd is None:
        return PurePosixPath(".")
    within = PurePosixPath(cwd)
    if within.is_absolute() or ".." in within.parts:
        raise SandboxError(f"a command runs inside the workspace, not at {cwd!r}")
    return within


def merge_env(*layers: Mapping[str, str] | None) -> dict[str, str]:
    """Combine env layers left-to-right, vetting the whole result.

    Used by both modes to fold their minimal base env together with a
    caller's extras through the same credential filter.
    """
    merged: dict[str, str] = {}
    for layer in layers:
        merged.update(layer or {})
    return safe_env(merged)
