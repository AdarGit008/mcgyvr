""

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

#
#
_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "mcgyvr",
    "GIT_AUTHOR_EMAIL": "sandbox@mcgyvr.invalid",
    "GIT_COMMITTER_NAME": "mcgyvr",
    "GIT_COMMITTER_EMAIL": "sandbox@mcgyvr.invalid",
}

#
#
#
_CREDENTIAL_NAME = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|_AUTH|APIKEY|SESSION)",
    re.IGNORECASE,
)

#
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


#
TIMEOUT_EXIT = -1

#��
#
#
#
#
#
#
#
#
DEFAULT_COMMAND_TIMEOUT_S = 900.0


def command_timeout(timeout: float | None) -> float:
    ""
    return DEFAULT_COMMAND_TIMEOUT_S if timeout is None else timeout


class SandboxError(Exception):
    ""


class NestedGitError(SandboxError):
    ""


def nested_git(root: Path) -> str | None:
    ""
    for here, dirs, files in os.walk(root):
        top = Path(here) == root
        for name in sorted([*dirs, *files]):
            if name.lower() == ".git" and not (top and name == ".git"):
                return (Path(here) / name).relative_to(root).as_posix()
        if top:
            dirs[:] = [d for d in dirs if d != ".git"]
    return None


def refuse_nested_git(root: Path) -> None:
    ""
    found = nested_git(root)
    if found is not None:
        raise NestedGitError(
            f"{found} is a git entry inside the workspace; host git would run "
            f"its config, so nothing more is done over this tree"
        )


@dataclass(frozen=True)
class CommandResult:
    ""

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
    ""

    tree: str
    ignored: frozenset[str]


@dataclass(frozen=True)
class Restored:
    ""

    removed: tuple[str, ...] = ()
    reverted: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.removed or self.reverted)

    def named(self, limit: int = 5) -> str:
        ""
        paths = sorted({*self.removed, *self.reverted})
        shown = ", ".join(paths[:limit])
        more = len(paths) - limit
        return f"{shown} (+{more} more)" if more > 0 else shown


def is_credential_var(name: str) -> bool:
    ""
    return name in _KNOWN_CREDENTIAL_VARS or bool(_CREDENTIAL_NAME.search(name))


def credential_env_names(env: Mapping[str, str]) -> frozenset[str]:
    ""
    return frozenset(name for name in env if is_credential_var(name))


def safe_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    ""
    env: dict[str, str] = {}
    for name, value in (extra or {}).items():
        if is_credential_var(name) or scrub(value) != value:
            continue  #
        env[name] = value
    return env


#
#
#
#
#al
#
#
#
_LIVE_REAPERS: dict[int, tuple[Callable[[], None], ...]] = {}


@cache
def _install_reaper() -> None:
    ""
    atexit.register(_reap_all)


def _reap_all() -> None:
    for reapers in list(_LIVE_REAPERS.values()):
        for reap in reapers:
            #
            #
            with contextlib.suppress(Exception):
                reap()


class Sandbox(ABC):
    ""

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

    #

    @property
    def workspace(self) -> Path:
        ""
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
            #
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
        ""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        _git(self.workspace, "reset", "--hard", self._base_commit)
        #
        _git(self.workspace, "clean", "-ffdx", *self._kept_args())

    def checkpoint(self) -> str:
        ""
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
        ""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        _git(self.workspace, "reset", "--hard", checkpoint)
        _git(self.workspace, "clean", "-ffd", *self._kept_args())

    def drop_checkpoint(self) -> None:
        ""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        refuse_nested_git(self.workspace)
        _git(self.workspace, "reset", "--mixed", self._base_commit)

    def snapshot(self) -> Snapshot:
        ""
        refuse_nested_git(self.workspace)
        return Snapshot(
            tree=_judged_tree(self.workspace),
            ignored=frozenset(_ignored_entries(self.workspace)),
        )

    def restore(self, snapshot: Snapshot) -> Restored:
        ""
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
            #
            for entry in removed:
                _prune_empty_parents(workspace, entry, existed)
        if reverted:
            _checkout_from(workspace, snapshot.tree, reverted)
        return Restored(tuple(removed), tuple(reverted))

    def changed_since_base(self, snapshot: Snapshot) -> frozenset[str]:
        ""
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
        ""
        if self._base_commit is None:
            raise SandboxError("sandbox is not open")
        return self._base_commit

    def source_base_commit(self) -> str:
        ""
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
        ""
        existing = _LIVE_REAPERS.get(id(self), ())
        _LIVE_REAPERS[id(self)] = (*existing, reaper)

    #

    @abstractmethod
    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        ""

    def host_path(self, reported: str) -> Path:
        ""
        return Path(reported)

    @abstractmethod
    def _start(self) -> None:
        ""

    def _kept(self) -> tuple[str, ...]:
        ""
        return ()

    def _kept_args(self) -> list[str]:
        #
        return [arg for name in self._kept() for arg in ("-e", f"/{name}")]

    @abstractmethod
    def _stop(self) -> None:
        ""


#


def _populate(
    source: Path, workspace: Path, base: str, *, left_out: list[str] | None = None
) -> tuple[str, str]:
    ""
    revision = _source_commit(source, base)
    if (source / ".git").exists() and _has_commit(source, base):
        _archive_into(source, workspace, base)
    else:
        #
        #
        #
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
    ""
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
    ""
    ref = base if base != "HEAD" else "HEAD^{commit}"
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
    )
    return proc.returncode == 0


def _archive_into(source: Path, workspace: Path, base: str) -> None:
    ""
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


#
#
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

#
#
_SECRET_DIRS = frozenset({".aws", ".gcloud", ".azure", ".ssh", ".gnupg", ".kube"})

#
#
#
_SECRET_UNDER = {
    ".docker": frozenset({"config.json"}),
    ".config": frozenset({"gcloud", "gh"}),
}

#
#
_LOGIN_RC = frozenset({".npmrc", ".pypirc", ".yarnrc", ".yarnrc.yml"})

_RC_LOGIN = re.compile(r"(auth|token|password|passwd|secret)\w*\s*[=:]", re.IGNORECASE)


def holds_a_secret(path: Path) -> bool:
    ""
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
    ""
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
    ""
    return (
        "The source is not a git repository, so it was copied whole except for "
        "files that hold secrets, which the task does not get: " + ", ".join(paths)
    )


def _git(
    root: Path,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> bytes:
    ""
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        env=dict(env) if env is not None else None,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise SandboxError(f"git {args[0]} failed in {root}: {detail}")
    return proc.stdout


#


def _judged_tree(workspace: Path) -> str:
    ""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-snap-") as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(workspace, "add", "-A", env=env)
        return _git(workspace, "write-tree", env=env).decode("ascii").strip()


def _ignored_entries(workspace: Path) -> set[str]:
    ""
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
    ""
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
    ""
    found: set[str] = set()
    for path in paths:
        parts = path.rstrip("/").split("/")
        depth = len(parts) if path.endswith("/") else len(parts) - 1
        found.update("/".join(parts[:end]) for end in range(1, depth + 1))
    return found


def _first_new(path: str, existed: set[str]) -> str:
    ""
    parts = path.split("/")
    for end in range(1, len(parts)):
        directory = "/".join(parts[:end])
        if directory not in existed:
            return f"{directory}/"
    return path


def _remove_entry(workspace: Path, entry: str) -> None:
    ""
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
    ""
    parts = entry.rstrip("/").split("/")[:-1]
    while parts and "/".join(parts) not in existed:
        with contextlib.suppress(OSError):  #
            (workspace.joinpath(*parts)).rmdir()
        parts.pop()


def _checkout_from(workspace: Path, tree: str, paths: Sequence[str]) -> None:
    ""
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
    ""
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
    ""
    pending = [root]
    while pending:
        here = pending.pop()
        with contextlib.suppress(OSError):
            if here.is_symlink() or not here.is_dir():
                continue
            here.chmod(stat.S_IRWXU)
            pending.extend(here.iterdir())


#


@dataclass(frozen=True)
class _SandboxChoice:
    ""

    mode: str
    notes: tuple[str, ...] = field(default_factory=tuple)


def choose_mode(
    configured: str, docker_available: bool, *, allow_fallback: bool = False
) -> _SandboxChoice:
    ""
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

#
#
NETWORKS = ("bridge", "none")


def check_network(network: str) -> str:
    ""
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
    ""
    check_network(network)
    if mode != "tempdir":
        #
        #
        #
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
    ""
    if cwd is None:
        return PurePosixPath(".")
    within = PurePosixPath(cwd)
    if within.is_absolute() or ".." in within.parts:
        raise SandboxError(f"a command runs inside the workspace, not at {cwd!r}")
    return within


def merge_env(*layers: Mapping[str, str] | None) -> dict[str, str]:
    ""
    merged: dict[str, str] = {}
    for layer in layers:
        merged.update(layer or {})
    return safe_env(merged)
