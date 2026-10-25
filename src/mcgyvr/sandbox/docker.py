"""A sandbox whose commands run inside a Docker container.

The task's workspace is bind-mounted at `/workspace`, with `.git` read-only
over it, and the container is started detached on `sleep infinity`, so every
command is a `docker exec`. Credential-looking environment variables are
dropped before the container is given an environment, a loopback endpoint URL
is rewritten to `host.docker.internal` so the container can reach the service
behind it, and a command that times out or leaves processes running costs the
container a kill and a start, so nothing of it is left behind.
"""

from __future__ import annotations

import os
import platform as platform_module
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import ClassVar
from urllib.parse import urlparse, urlunparse

from mcgyvr.sandbox.base import (
    TIMEOUT_EXIT,
    CommandResult,
    Sandbox,
    SandboxError,
    check_network,
    command_timeout,
    merge_env,
    workdir,
)
from mcgyvr.sandbox.image import (
    DockerRunner,
    ImageError,
    ensure_image,
    foreign_daemon,
    seeded_folders,
    subprocess_runner,
)
from mcgyvr.sandbox.stack import detect_stack

# The name a container uses to reach a service listening on this machine.
# Docker Desktop resolves it on its own; on Linux `host_gateway_args` adds the
# extra-host entry that makes it resolve to the host's gateway.
HOST_ALIAS = "host.docker.internal"

#: Where the task's workspace is mounted inside the container. Container-side
#: paths under it map back onto the host workspace in `host_path`.
CONTAINER_WORKSPACE = PurePosixPath("/workspace")

# Carries the task's endpoint URLs into the container as one comma-separated
# value, set only when the container has a network to reach them over.
ENDPOINTS_ENV = "MCGYVR_ENDPOINTS"

# Hostnames that mean this machine. An endpoint named with one of them is
# rewritten to `HOST_ALIAS`, because inside the container it is not a loopback.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


@dataclass(frozen=True)
class Resources:
    """The memory, CPU and process caps a task container is given.

    `run_args` renders them as the `docker run` flags that impose them.
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
    """Point a loopback endpoint at the host, for a container to reach it.

    `base_url` comes back unchanged unless its hostname is one of
    `_LOOPBACK_HOSTS`; otherwise the host, with its port when it has one, is
    replaced by `HOST_ALIAS` and scheme and path are kept.
    """
    parsed = urlparse(base_url)
    if parsed.hostname is None or parsed.hostname.lower() not in _LOOPBACK_HOSTS:
        return base_url
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse(parsed._replace(netloc=f"{HOST_ALIAS}{port}"))


def host_gateway_args(system: str) -> list[str]:
    """The `docker run` flags that let a container resolve `HOST_ALIAS`.

    Linux maps that name to nothing by default, so it gets an explicit
    `host-gateway` entry; a platform whose Docker already resolves it, as
    Docker Desktop does, gets no flags.
    """
    if system == "Linux":
        return ["--add-host", f"{HOST_ALIAS}:host-gateway"]
    return []


class DockerSandbox(Sandbox):
    """A sandbox whose commands run in a detached container over the workspace.

    `_start` creates the container with the workspace mounted at `/workspace`
    and `_stop` removes it, so an instance is usable only inside `with`.
    """

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
        network: str = "bridge",
        notes: Sequence[str] = (),
        runner: DockerRunner = subprocess_runner,
        system: str | None = None,
    ) -> None:
        super().__init__(source, base, notes=notes)
        self._network = check_network(network)
        self._image_override = image
        self._setup = tuple(setup)
        self._endpoints = tuple(endpoints)
        self._resources = resources or Resources()
        self._runner = runner
        self._system = system or platform_module.system()
        self._container: str | None = None
        self._image_tag: str | None = None
        self._dead: str | None = None
        self._seeded: tuple[str, ...] = ()

    # The container's lifetime: started with the workspace mounted, stopped
    # with it, and reaped on interpreter exit as well.

    def _start(self) -> None:
        self._image_tag = self._resolve_image()
        # A built image carries the repository's installed dependency folders;
        # a volume of its own over each non-empty one keeps the image's copy
        # visible past the workspace mount. An override image is taken as it is.
        if self._image_override is None:
            self._seeded = seeded_folders(self._image_tag, self._runner)
        self._container = f"mcgyvr-task-{uuid.uuid4().hex[:12]}"
        # Reaping is registered with the exit hook too, so the container is
        # removed even when the sandbox is never closed and `_stop` never runs.
        self._register_reaper(self._reap_container)

        env = self._container_env()
        args = _run_args(
            name=self._container,
            image=self._image_tag,
            workspace=self.workspace,
            resources=self._resources,
            network=self._network,
            gateway=host_gateway_args(self._system) if self._reaches_out else [],
            user=_host_user(),
            env=env,
            seeded=self._seeded,
        )
        result = self._runner(args, None)
        if not result.ok:
            # A `docker run` that failed means there is no container to run in:
            # say what docker said, rather than hand back a sandbox that cannot.
            raise SandboxError(
                f"could not start task container: {result.stderr.strip()}"
            )

    def _stop(self) -> None:
        self._reap_container()

    def _reap_container(self) -> None:
        """Force the container and its volumes away, and forget its name.

        A container that is already gone is not an error; any other failure is
        reported on stderr, since this runs while the sandbox is being torn
        down and has nothing left to raise into.
        """
        if self._container is None:
            return
        removed = self._runner(["rm", "--force", "--volumes", self._container], None)
        if not removed.ok and "No such container" not in removed.stderr:
            print(
                f"mcgyvr: task container {self._container} could not be removed: "
                f"{removed.stderr.strip()}",
                file=sys.stderr,
            )
        self._container = None

    def run(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        if self._container is None:
            raise SandboxError("container is not running — use as a context manager")
        if self._dead is not None:
            raise SandboxError(self._dead)
        argv = tuple(command)
        exec_args = _exec_args(
            name=self._container,
            command=argv,
            env=merge_env(env),  # credential-looking values are dropped
            workdir=str(CONTAINER_WORKSPACE / workdir(cwd)),
        )
        result = _docker_exec(exec_args, command_timeout(timeout))
        self._end_leftovers(self._container, result.timed_out)
        return CommandResult(
            command=argv,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            timed_out=result.timed_out,
        )

    def _kept(self) -> tuple[str, ...]:
        """The seeded folders that a reset or a restore must leave alone.

        The container sees the image's copy of each of them, so what the host
        holds at that path is not workspace content for a clean or a checkout.
        """
        return self._seeded

    @property
    def roots(self) -> tuple[str, ...]:
        """The host's spellings of the workspace, and the container's mount."""
        return (*super().roots, str(CONTAINER_WORKSPACE))

    def host_path(self, reported: str) -> Path:
        """Map a path the container printed to where it lives on the host.

        A path under `/workspace` is taken as relative to the workspace mount;
        anything else is returned as the string has it.
        """
        printed = PurePosixPath(reported)
        try:
            within = printed.relative_to(CONTAINER_WORKSPACE)
        except ValueError:
            return Path(reported)
        return self.workspace.joinpath(*within.parts)

    def _end_leftovers(self, name: str, timed_out: bool) -> None:
        """Put the container back to a bare keepalive after a command.

        A command that ran out of time, or one that left processes running
        beside the keepalive, costs the container a kill and a start; a restart
        that fails marks the sandbox dead, so later `run`s raise instead of
        executing into a container that is no longer what was started.
        """
        if not timed_out and not self._runs_more_than_its_keepalive(name):
            return
        self._runner(["kill", name], None)
        started = self._runner(["start", name], None)
        if not started.ok:
            self._dead = (
                f"task container {name} could not be started again "
                f"after a command was ended: {started.stderr.strip()}"
            )

    def _runs_more_than_its_keepalive(self, name: str) -> bool:
        """Whether the container has processes beside `sleep infinity`.

        `docker top` lists one row per process, header first, and the container
        holds nothing but that keepalive between commands, so a second row is
        what a command left running. An unreadable process list counts as
        leftovers.
        """
        listed = self._runner(["top", name, "-o", "pid"], None)
        if not listed.ok:
            return True  # cannot tell, so assume leftovers
        rows = [line for line in listed.stdout.splitlines()[1:] if line.strip()]
        return len(rows) > 1

    # What the container is given before it starts: its image, whether it has a
    # network, and the environment it and its commands run with.

    def _resolve_image(self) -> str:
        """The tag of the image the task container runs.

        The override when one is set; otherwise the cached or freshly built
        image for the stack detected in the source. A stack that is not
        detected, and a build that fails, are raised as a `SandboxError`.
        """
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

    @property
    def _reaches_out(self) -> bool:
        """Whether the container is given a network to reach anything over."""
        return self._network != "none"

    def _container_env(self) -> dict[str, str]:
        """The environment the container is started with.

        `HOME` and the XDG directories point inside the workspace and at `/tmp`
        of the container, and the endpoint list rides along as one value when
        the container has a network to reach those endpoints over.
        """
        base: dict[str, str] = {
            "HOME": "/workspace",
            "XDG_CACHE_HOME": "/tmp/cache",
            "XDG_CONFIG_HOME": "/tmp/config",
            "XDG_DATA_HOME": "/tmp/data",
        }
        reachable = [translate_endpoint(url) for url in self._endpoints]
        if reachable and self._reaches_out:
            base[ENDPOINTS_ENV] = ",".join(reachable)
        return merge_env(base)


# The docker command lines, plus the helpers that build and run them.


def _run_args(
    *,
    name: str,
    image: str,
    workspace: Path,
    resources: Resources,
    gateway: Sequence[str],
    user: str | None,
    env: Mapping[str, str],
    network: str = "bridge",
    seeded: Sequence[str] = (),
) -> list[str]:
    """The `docker run` arguments for a detached container that just idles.

    The workspace is mounted at `/workspace` with `.git` read-only over it,
    seeded folders get a volume each, resources and the environment are
    applied, and the command is `sleep infinity`, for `docker exec` to have a
    container to run in.
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
        # `.git` is mounted read-only over the workspace mount, so a command
        # can read the history but cannot write the commits that snapshot and
        # restore the tree.
        "--volume",
        f"{workspace}/.git:/workspace/.git:ro",
        *(
            token
            for folder in seeded
            for token in ("--volume", str(CONTAINER_WORKSPACE / folder))
        ),
        *resources.run_args(),
        # bridge is docker's default, so only another network is named.
        *(["--network", network] if network != "bridge" else []),
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
    workdir: str = "/workspace",
) -> list[str]:
    """The `docker exec` arguments for one command in the running container.

    The workdir is a path inside the container, and the environment is applied
    as sorted `--env` pairs before the container's name and the command.
    """
    args = ["exec", "--workdir", workdir]
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
    """Run one `docker exec` from the host and report what it produced.

    A daemon refused as foreign is raised rather than run, a timeout comes back
    as `TIMEOUT_EXIT` with `timed_out` set, and a host with no docker on its
    PATH as exit 127.
    """
    refusal = foreign_daemon()
    if refusal is not None:
        raise SandboxError(refusal)
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
            exit_code=TIMEOUT_EXIT,
            stdout=_as_text(expired.stdout),
            stderr=_as_text(expired.stderr),
            timed_out=True,
        )
    except FileNotFoundError:
        return _ExecResult(127, "", "docker is not on PATH", False)
    return _ExecResult(done.returncode, done.stdout, done.stderr, False)


def _host_user() -> str | None:
    """The host user as `uid:gid`, so files written into the mount are theirs.

    A platform without `getuid` and `getgid` returns nothing, and the container
    then runs as its image says.
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
