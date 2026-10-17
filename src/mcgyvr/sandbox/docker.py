""

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

#
#
#s.
HOST_ALIAS = "host.docker.internal"

#
CONTAINER_WORKSPACE = PurePosixPath("/workspace")

#
#
ENDPOINTS_ENV = "MCGYVR_ENDPOINTS"

#
#
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


@dataclass(frozen=True)
class Resources:
    ""

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
    ""
    parsed = urlparse(base_url)
    if parsed.hostname is None or parsed.hostname.lower() not in _LOOPBACK_HOSTS:
        return base_url
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse(parsed._replace(netloc=f"{HOST_ALIAS}{port}"))


def host_gateway_args(system: str) -> list[str]:
    ""
    if system == "Linux":
        return ["--add-host", f"{HOST_ALIAS}:host-gateway"]
    return []


class DockerSandbox(Sandbox):
    ""

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

    #

    def _start(self) -> None:
        self._image_tag = self._resolve_image()
        #
        #
        #
        if self._image_override is None:
            self._seeded = seeded_folders(self._image_tag, self._runner)
        self._container = f"mcgyvr-task-{uuid.uuid4().hex[:12]}"
        #
        #
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
            #
            #
            raise SandboxError(
                f"could not start task container: {result.stderr.strip()}"
            )

    def _stop(self) -> None:
        self._reap_container()

    def _reap_container(self) -> None:
        ""
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
            env=merge_env(env),  #
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
        ""
        return self._seeded

    def host_path(self, reported: str) -> Path:
        ""
        printed = PurePosixPath(reported)
        try:
            within = printed.relative_to(CONTAINER_WORKSPACE)
        except ValueError:
            return Path(reported)
        return self.workspace.joinpath(*within.parts)

    def _end_leftovers(self, name: str, timed_out: bool) -> None:
        ""
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
        ""
        listed = self._runner(["top", name, "-o", "pid"], None)
        if not listed.ok:
            return True  #
        rows = [line for line in listed.stdout.splitlines()[1:] if line.strip()]
        return len(rows) > 1

    #

    def _resolve_image(self) -> str:
        ""
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
        ""
        return self._network != "none"

    def _container_env(self) -> dict[str, str]:
        ""
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


#


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
    ""
    args = [
        "run",
        "--detach",
        "--name",
        name,
        "--workdir",
        "/workspace",
        "--volume",
        f"{workspace}:/workspace",
        #
        #
        #
        "--volume",
        f"{workspace}/.git:/workspace/.git:ro",
        *(
            token
            for folder in seeded
            for token in ("--volume", str(CONTAINER_WORKSPACE / folder))
        ),
        *resources.run_args(),
        #
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
    ""
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
    ""
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
    ""
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
