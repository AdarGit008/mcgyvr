"""The container sandbox: one task, one container, torn down after.

This is the strong mode. A task runs in a container built from an image that
already carries the repository's dependencies (:mod:`mcgyvr.sandbox.image`),
so an acceptance command fails because the worker was wrong rather than
because an import was missing. The workspace is bind-mounted from the host,
so the git repository the base class populated is the one the container sees
at ``/workspace`` and the one the gate reads back — the two modes share that
machinery and differ only in *where* :meth:`run` executes.

The container lifecycle (#27) holds three guarantees:

- **Nothing survives.** The container is force-removed on success, failure and
  interrupt — by ``__exit__`` for the normal and interrupted paths, and by the
  process-exit reaper the base class installs for a hard crash. Removal is by
  a name minted per task, so a reaper can reap a container even after the
  Python object holding it is gone.
- **A runaway cannot take the host down.** Memory, CPU and PID ceilings bound
  the container; a command that exceeds the wall-clock ceiling has its
  container killed rather than being waited on.
- **Every attempt starts clean.** :meth:`reset` (inherited) restores the git
  base in the shared workspace, so a failed attempt leaves no trace in the
  next.

And two connectivity invariants that pull opposite ways (#31):

- **The container reaches configured worker endpoints.** A ``localhost``
  endpoint on the host is not ``localhost`` inside a container; it is
  translated to ``host.docker.internal``, and on Linux — where that name is
  not automatic — a ``host-gateway`` mapping is added so it resolves. The
  translated endpoints are handed in as a plain, credential-free variable.
- **No credential reaches the container.** The environment is built from
  nothing and vetted (:func:`~mcgyvr.sandbox.base.safe_env`), so a container's
  environment satisfies ``credential_env_names(env) == frozenset()`` by
  construction — the red-failing security invariant in ``SECURITY.md``.
"""

from __future__ import annotations

import os
import platform as platform_module
import subprocess
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse, urlunparse

from mcgyvr.sandbox.base import CommandResult, Sandbox, SandboxError, merge_env
from mcgyvr.sandbox.image import (
    DockerRunner,
    ImageError,
    ensure_image,
    subprocess_runner,
)
from mcgyvr.sandbox.stack import detect_stack

# The name Docker Desktop resolves to the host, and the name we map by hand on
# Linux. One name across platforms is what keeps everything above the sandbox
# from caring which OS it is on — the portability trap #31 names.
HOST_ALIAS = "host.docker.internal"

# A benign, credential-free variable carrying where the container can reach
# workers. Named so it cannot match the credential filter.
ENDPOINTS_ENV = "MCGYVR_ENDPOINTS"

# Loopback hosts on the host machine that mean "the host" and must be
# rewritten to reach it from inside a container.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

_TIMEOUT_EXIT = -1  # exit code for a command the wall-clock ceiling killed


@dataclass(frozen=True)
class Resources:
    """Ceilings that stop a runaway command taking the host down (#27).

    Strings for ``memory``/``cpus`` because that is Docker's own vocabulary
    (``2g``, ``0.5``); passed through untouched so the meaning is Docker's,
    not a re-interpretation of it.
    """

    memory: str = "2g"
    cpus: str = "2"
    pids: int = 512

    def run_args(self) -> list[str]:
        return [
            "--memory",
            self.memory,
            "--cpus",
            self.cpus,
            "--pids-limit",
            str(self.pids),
        ]


def translate_endpoint(base_url: str) -> str:
    """Rewrite a host-loopback endpoint so a container can reach it.

    A ``localhost`` URL means the container itself from inside a container, not
    the host; it is rewritten to :data:`HOST_ALIAS`, which resolves to the host
    on every platform (natively on Docker Desktop, via
    :func:`host_gateway_args` on Linux). A non-loopback host — another machine,
    a container network name — is already reachable and is left untouched.
    """
    parsed = urlparse(base_url)
    if parsed.hostname is None or parsed.hostname.lower() not in _LOOPBACK_HOSTS:
        return base_url
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{userinfo}{HOST_ALIAS}{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def host_gateway_args(system: str) -> list[str]:
    """The run flags that make :data:`HOST_ALIAS` resolve on this platform.

    Docker Desktop (macOS, Windows) resolves it natively, so nothing is
    needed. On Linux it is not automatic and is mapped to the special
    ``host-gateway`` value, which Docker resolves to the host's gateway IP.
    """
    if system == "Linux":
        return ["--add-host", f"{HOST_ALIAS}:host-gateway"]
    return []


class DockerSandbox(Sandbox):
    """Run a task in its own container, built from the repository's own image."""

    isolation: ClassVar[str] = "container"

    def __init__(
        self,
        source: str | os.PathLike[str],
        base: str = "HEAD",
        *,
        image: str | None = None,
        setup: Sequence[str] = (),
        endpoints: Sequence[str] = (),
        resources: Resources | None = None,
        notes: Sequence[str] = (),
        runner: DockerRunner = subprocess_runner,
        system: str | None = None,
    ) -> None:
        super().__init__(source, base, notes=notes)
        self._image_override = image
        self._setup = tuple(setup)
        self._endpoints = tuple(endpoints)
        self._resources = resources or Resources()
        self._runner = runner
        self._system = system or platform_module.system()
        self._container: str | None = None
        self._image_tag: str | None = None

    # -- lifecycle --------------------------------------------------------

    def _start(self) -> None:
        self._image_tag = self._resolve_image()
        self._container = f"mcgyvr-task-{uuid.uuid4().hex[:12]}"
        # Register a reaper before the container exists, so even a crash during
        # `docker run` reaps by name once the daemon has the container.
        self._register_reaper(self._reap_container)

        env = self._container_env()
        args = _run_args(
            name=self._container,
            image=self._image_tag,
            workspace=self.workspace,
            resources=self._resources,
            gateway=host_gateway_args(self._system),
            user=_host_user(),
            env=env,
        )
        result = self._runner(args, None)
        if not result.ok:
            self._container = None
            raise SandboxError(
                f"could not start task container: {result.stderr.strip()}"
            )

    def _stop(self) -> None:
        self._reap_container()

    def _reap_container(self) -> None:
        """Force-remove the container. Idempotent — safe as a crash reaper too.

        Force-remove kills a still-running container and removes it in one
        step, so teardown never depends on the command having exited.
        """
        if self._container is None:
            return
        self._runner(["rm", "--force", self._container], None)
        self._container = None

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if self._container is None:
            raise SandboxError("container is not running — use as a context manager")
        argv = tuple(command)
        exec_args = _exec_args(
            name=self._container,
            command=argv,
            env=merge_env(env),  # per-command extras, vetted; base env is ambient
        )
        result = _docker_exec(exec_args, timeout)
        if result.timed_out:
            # A command past the wall-clock ceiling is not waited on; its
            # container is killed so nothing keeps running behind the verdict.
            self._runner(["kill", self._container], None)
        return CommandResult(
            command=argv,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
        )

    # -- image + env ------------------------------------------------------

    def _resolve_image(self) -> str:
        """The image to run: an explicit override, or the built per-repo image."""
        if self._image_override is not None:
            return self._image_override
        stack = detect_stack(self._source)
        if not stack.detected:
            raise SandboxError(
                "; ".join(stack.notes)
                or "the repository's stack could not be detected and no "
                "`sandbox.image` override is set"
            )
        try:
            return ensure_image(
                stack, self._source, self._setup, runner=self._runner
            ).tag
        except ImageError as exc:
            raise SandboxError(str(exc)) from exc

    def _container_env(self) -> dict[str, str]:
        """The container's ambient environment: minimal, endpoint-bearing, keyless.

        Built from nothing, so no host variable — least of all a credential —
        can leak in. ``HOME`` points at the writable workspace; the translated
        worker endpoints ride in a benign variable.
        """
        base: dict[str, str] = {"HOME": "/workspace"}
        reachable = [translate_endpoint(url) for url in self._endpoints]
        if reachable:
            base[ENDPOINTS_ENV] = ",".join(reachable)
        return merge_env(base)


# --- pure argv builders (the tested surface) -----------------------------


def _run_args(
    *,
    name: str,
    image: str,
    workspace: Path,
    resources: Resources,
    gateway: Sequence[str],
    user: str | None,
    env: Mapping[str, str],
) -> list[str]:
    """Build the ``docker run`` argv for a detached, long-lived task container.

    The container is kept alive with ``sleep infinity`` and driven by
    ``docker exec``; that keeps one container per task while letting the gate
    run many commands in it. The workspace is bind-mounted so host git and the
    container see one tree.
    """
    args = [
        "run",
        "--detach",
        "--name",
        name,
        "--workdir",
        "/workspace",
        "--volume",
        f"{workspace}:/workspace",
        *resources.run_args(),
        *gateway,
    ]
    if user is not None:
        args += ["--user", user]
    for key, value in sorted(env.items()):
        args += ["--env", f"{key}={value}"]
    args += [image, "sleep", "infinity"]
    return args


def _exec_args(
    *,
    name: str,
    command: Sequence[str],
    env: Mapping[str, str],
) -> list[str]:
    """Build the ``docker exec`` argv running one command in the container."""
    args = ["exec", "--workdir", "/workspace"]
    for key, value in sorted(env.items()):
        args += ["--env", f"{key}={value}"]
    args.append(name)
    args += list(command)
    return args


@dataclass(frozen=True)
class _ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


def _docker_exec(exec_args: Sequence[str], timeout: float | None) -> _ExecResult:
    """Run ``docker exec …`` on the host, capturing output under a timeout."""
    try:
        done = subprocess.run(
            ["docker", *exec_args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return _ExecResult(
            exit_code=_TIMEOUT_EXIT,
            stdout=_as_text(expired.stdout),
            stderr=_as_text(expired.stderr),
            timed_out=True,
        )
    except FileNotFoundError:
        return _ExecResult(127, "", "docker is not on PATH", False)
    return _ExecResult(done.returncode, done.stdout, done.stderr, False)


def _host_user() -> str | None:
    """``uid:gid`` on POSIX, so bind-mounted files stay host-owned; else None.

    Running the container as the host user keeps files the container writes
    into the shared workspace readable and removable by the host — the gate
    reads them and teardown removes them without a permission fight. Windows
    has no ``getuid``; there Docker Desktop handles ownership and this returns
    None.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:
        return None
    return f"{getuid()}:{getgid()}"


def _as_text(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", "replace")
    return stream
