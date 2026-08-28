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
   even when the body raises ``KeyboardInterrupt`` — and, as a backstop for a
   hard crash that skips ``__exit__``, by a process-exit reaper that reaps
   whatever is still registered.
2. **No credential reaches a task.** The environment a command runs in is
   built from an explicit allowlist, never inherited from the host, and any
   caller-supplied variable whose name looks like a credential is dropped
   before it can enter. ``SECURITY.md`` makes this a red-failing invariant,
   so :func:`credential_env_names` is the check a test asserts against.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

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


class SandboxError(Exception):
    """A sandbox could not be created, populated, or torn down."""


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
    """
    env: dict[str, str] = {}
    for name, value in (extra or {}).items():
        if is_credential_var(name):
            continue  # a caller mistake must not become a leak
        env[name] = value
    return env


# --- process-exit reaper -------------------------------------------------
#
# The context manager is the primary teardown path and covers interrupt,
# because a `with` unwinds on KeyboardInterrupt. This registry is the
# backstop for the case the context manager cannot cover — a hard crash or
# os._exit — where atexit still runs registered reapers over whatever is
# live. Each mode registers a cheap idempotent callable.
_LIVE_REAPERS: dict[int, tuple[Callable[[], None], ...]] = {}
_reaper_installed = False


def _install_reaper() -> None:
    global _reaper_installed
    if not _reaper_installed:
        atexit.register(_reap_all)
        _reaper_installed = True


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
            populated = _populate(self._source, self._workspace, self._base)
            self._base_commit, self._source_commit = populated
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
        _git(self.workspace, "clean", "-fdx")

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

        The same question ``base`` asked at construction, answered as a concrete
        commit: it is the revision the worker started from, and it is the one
        value here that means anything back in the repository a delivery commits
        into. :meth:`base_changeset_ref` is its workspace-local twin and the two
        are never equal — a delivery handed the wrong one fails to resolve its
        base, which is how this came to be exposed at all.

        Raises when the source could name no commit — a non-git directory, or a
        repository with nothing committed yet. Both are populated by copying, and
        neither has a revision for a caller to diff against, so there is no
        answer to give. It used to answer ``""``, and that turned out to be the
        worse half of B7: ``deliver`` softened a falsy base to ``HEAD``, so the
        one value meaning *there is no base* selected the one base that is a
        moving name, and a delivery committed against wherever the branch had
        got to. The two ends are fixed together — delivery refuses an empty base
        by name, and this refuses to produce one.
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
    ) -> CommandResult:
        """Run one command in the sandbox and capture its result.

        ``env`` is additive and vetted: it is layered onto the mode's minimal
        environment through :func:`safe_env`, so no credential can enter even
        if a caller forwards one.
        """

    @abstractmethod
    def _start(self) -> None:
        """Mode-specific setup after the workspace exists (create a container)."""

    @abstractmethod
    def _stop(self) -> None:
        """Mode-specific teardown before the workspace is removed. Idempotent."""


# --- workspace population (shared, host-side git) ------------------------


def _populate(source: Path, workspace: Path, base: str) -> tuple[str, str]:
    """Fill ``workspace`` from ``source``, commit it, and name both bases.

    When ``source`` is a git repository the base tree is taken with
    ``git archive`` — exactly the tracked content of ``base``, no ``.git``,
    no untracked heavyweight directories (``node_modules``, ``.venv``) that a
    copy would drag in. A non-git source is copied wholesale. Either way the
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
        # copied wholesale; the fresh git repository below becomes its base.
        _copy_into(source, workspace)

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


def _copy_into(source: Path, workspace: Path) -> None:
    """Copy a non-git ``source`` tree into ``workspace``, skipping VCS metadata."""
    try:
        shutil.copytree(
            source,
            workspace,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git"),
        )
    except OSError as exc:
        raise SandboxError(f"could not copy {source} into {workspace}: {exc}") from exc


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
    """Remove a workspace, tolerating a partially-created or already-gone one."""
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)


# --- factory -------------------------------------------------------------


@dataclass(frozen=True)
class _SandboxChoice:
    """Which mode was chosen and why — used to surface the weaker mode once."""

    mode: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def choose_mode(configured: str, docker_available: bool) -> _SandboxChoice:
    """Resolve the effective sandbox mode from config and Docker availability.

    ``docker`` configured without a daemon does not fail — it falls back to
    the temp directory and says so once, because locking a user out for the
    lack of Docker is the opposite of the intent (ADR-0001 §5). ``tempdir``
    configured is an explicit choice and carries the same weaker-mode note.
    """
    if configured == "tempdir":
        return _SandboxChoice("tempdir", (_WEAKER_MODE_NOTE,))
    if not docker_available:
        return _SandboxChoice(
            "tempdir",
            (
                "Docker was requested but no daemon answered; falling back to "
                "the temp-directory sandbox. " + _WEAKER_MODE_NOTE,
            ),
        )
    return _SandboxChoice("docker")


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
) -> Sandbox:
    """Construct the sandbox a task should run in, not yet entered.

    ``mode`` comes from ``sandbox.mode`` in config; ``image``/``setup`` from
    the rest of the ``sandbox`` block. ``endpoints`` are the configured worker
    ``base_url``s the container must be able to reach; loopback ones are
    translated to the host alias by the Docker mode, and they are passed only
    there — the temp-directory mode already runs on the host. Docker
    availability is detected here unless the caller supplies it (tests, and
    callers that already probed). The returned sandbox carries ``notes`` naming
    the weaker mode when one is in force — the caller surfaces them once at open.
    """
    if docker_available is None:
        from mcgyvr.detect import detect_docker

        docker_available, _ = detect_docker()

    choice = choose_mode(mode, docker_available)

    if choice.mode == "docker":
        from mcgyvr.sandbox.docker import DockerSandbox

        return DockerSandbox(
            source,
            base=base,
            image=image,
            setup=tuple(setup),
            endpoints=tuple(endpoints),
            notes=choice.notes,
        )

    from mcgyvr.sandbox.tempdir import TempDirSandbox

    return TempDirSandbox(source, base=base, notes=choice.notes)


def merge_env(*layers: Mapping[str, str] | None) -> dict[str, str]:
    """Combine env layers left-to-right, vetting the whole result.

    Used by both modes to fold their minimal base env together with a
    caller's extras through the same credential filter.
    """
    merged: dict[str, str] = {}
    for layer in layers:
        merged.update(layer or {})
    return safe_env(merged)
