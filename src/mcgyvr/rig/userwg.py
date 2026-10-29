"""A Mac or Windows rig's pooled sessions, run natively through ``mcgyvr-wg``.

:class:`NativeHost` is the session host (:class:`mcgyvr.rig.session.SessionHost`)
of a rig lending with ``launcher: native`` on macOS or Windows. Where the
docker host runs a tunnel container, a worker and a head in containers, this
host runs one helper per session (:mod:`mcgyvr.rig.wghelper`) — userspace
WireGuard on a netstack, no TUN device and no admin rights — and the pinned
llama-server (:mod:`mcgyvr.serving.llamacpp`, fetched and verified by
:mod:`mcgyvr.serving.native`) as the helper's child, so the engine ends with
the helper and the helper with the agent.

The head listens on the loopback alone (:data:`mcgyvr.emit.LOOPBACK`, the
native units' rule, held by :func:`mcgyvr.emit.native_block`): the agent
relays the hub's requests to its API port, and the head reaches each of the
session's rpc devices only through a forward the helper opens on the loopback,
which accepts a connection only from the head's own process and dials only
that device, through the tunnel. A native rig lends no worker yet: the helper
serves no rpc server, so a worker is refused before anything starts.

Each process a session starts (the helper, and the head) is recorded by pid,
start time and program in a private folder, so a head left behind by a helper
that was killed outright, or by an agent that died, is ended by the next
teardown or sweep — only while its pid still has the recorded start time.

The session's own logic is the same as on Linux; only the parts differ. The
tunnel's hello names the loopback as its address, since nothing of the session
listens anywhere else on this host.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr import atomic, hostos
from mcgyvr.emit import LOOPBACK
from mcgyvr.rig import pooled, session, tunnel, udpwire, wghelper, wgpin
from mcgyvr.rig import sharing as sharing_module
from mcgyvr.serving import llamacpp, native
from mcgyvr.serving.release import ReleaseError
from mcgyvr.userdir import private_dir

#: What a native tunnel's hello names as its address and gateway.
HELLO_ADDRESS = f"{LOOPBACK}/32"
#: The device-name prefix llama.cpp gives each backend whose devices a native
#: head can name in the order the hub numbers its cards: CUDA, given exactly
#: the head's cards in PCI bus order, and Metal, one device. A Vulkan build
#: numbers devices in its own order, so its cards are not named.
DEVICE_PREFIX = {llamacpp.CUDA: "CUDA", llamacpp.METAL: "MTL"}
#: The environment the helper and the head keep of the agent's: what a program
#: needs to run and find its temporary folder, nothing of the agent's own
#: settings or secrets.
HELPER_ENV = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
)
#: The prefixes of the variables the head keeps beyond :data:`HELPER_ENV`:
#: the GPU runtimes' own settings.
ENGINE_ENV_PREFIXES = ("GGML_", "CUDA_", "VK_", "MTL_", "METAL_")
#: The bytes of a log read for its last lines.
LOG_TAIL_BYTES = 1 << 16
#: The folder, under the native units' state folder, a session's process
#: records are kept in.
RECORDS = "pooled"


@dataclass(frozen=True)
class Engine:
    """The pinned llama-server this machine runs, and the backend it was built for."""

    program: Path
    backend: str


def pinned_helper() -> list[str]:
    """The pinned helper program for this machine, fetched and verified on first use."""
    try:
        return [str(wgpin.helper(hostos.os_name(), native.machine_arch()))]
    except (ReleaseError, native.NativeError) as exc:
        raise pooled.PoolError(str(exc)) from exc


def pinned_engine() -> Engine:
    """The pinned llama-server build for this machine
    (:func:`mcgyvr.serving.native.pick`), fetched and verified on first use."""
    try:
        build = native.pick()
        folder = native.binaries(build)
    except native.NativeError as exc:
        raise pooled.PoolError(str(exc)) from exc
    return Engine(program=folder / hostos.exe(llamacpp.SERVER), backend=build.backend)


def helper_env(env: Mapping[str, str]) -> dict[str, str]:
    """The environment a helper starts with: :data:`HELPER_ENV` of ``env``, and
    the Go memory limit the tunnel container sets."""
    kept = {key: env[key] for key in HELPER_ENV if key in env}
    kept["GOMEMLIMIT"] = f"{pooled.TUNNEL_GO_MEMORY_MB}MiB"
    return kept


def engine_env(env: Mapping[str, str]) -> dict[str, str]:
    """The environment a head starts with, before its cards are named:
    :data:`HELPER_ENV` and the GPU runtimes' variables of ``env``, nothing else
    — a hub token, a cloud key or an operator's llama-server setting stays with
    the agent (the head serves other members' requests)."""
    return {
        key: value
        for key, value in env.items()
        if key in HELPER_ENV or key.startswith(ENGINE_ENV_PREFIXES)
    }


def records_dir() -> Path:
    """Where a native session's process records are kept: a private folder."""
    return native.state_dir() / RECORDS


def read_tail(path: Path, lines: int) -> str:
    """The last ``lines`` lines of a log, or nothing when it cannot be read."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - LOG_TAIL_BYTES))
            said = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(said.splitlines()[-lines:])


def head_block(
    name: str, argv: list[str], env: Mapping[str, str], cards: Sequence[int]
) -> dict[str, Any]:
    """The head's command and environment, held to a native unit's rules.

    The block a native unit is emitted as (:func:`mcgyvr.emit.native_block`)
    is the one place the bind rule lives: a native llama-server listens on
    :data:`mcgyvr.emit.LOOPBACK` alone, and a ``--host`` or ``LLAMA_ARG_HOST``
    naming anything else is refused. A refusal fails the head's start.
    """
    from mcgyvr.emit import EmitError
    from mcgyvr.emit import native_block as block

    try:
        return block(
            name,
            engine="llama.cpp",
            host=LOOPBACK,
            rpc=False,
            container=name,
            command=argv,
            env=env,
            cards=cards,
        )
    except EmitError as exc:
        raise pooled.PoolError(str(exc)) from exc


@dataclass(eq=False)
class _Run:
    """One session's helper and what it was asked to run."""

    session_id: str
    helper: wghelper.Helper
    api_port: int | None
    key: str | None = None
    head: bool = False
    forwards: list[int] = field(default_factory=list)

    @property
    def tunnel(self) -> str:
        return pooled.container_name(self.session_id, "tunnel")

    @property
    def head_name(self) -> str:
        return pooled.container_name(self.session_id, "head")


class NativeHost:
    """The parts of a rig's native pooled sessions: a helper each, and its head.

    ``helper`` gives the helper's argv and ``engine`` the llama-server build,
    both fetched and verified when the first session prepares (one fetch at a
    time) and kept; ``env`` is the agent's environment, of which the helper
    keeps :data:`HELPER_ENV` and the head :func:`engine_env`. Logs go where a
    native unit's do (:func:`mcgyvr.serving.native.log_path`), named by the
    part's container name, and each started process is recorded in
    ``records`` (:func:`records_dir`).
    """

    def __init__(
        self,
        *,
        agent_pid: int,
        helper: Callable[[], Sequence[str]] = pinned_helper,
        engine: Callable[[], Engine] = pinned_engine,
        env: Mapping[str, str] | None = None,
        log_path: Callable[[str], Path] = native.log_path,
        records: Callable[[], Path] = records_dir,
        reply_s: float = wghelper.REPLY_S,
    ) -> None:
        self._agent_pid = agent_pid
        self._helper = helper
        self._engine = engine
        self._env = dict(os.environ if env is None else env)
        self._log_path = log_path
        self._records = records
        self._reply_s = reply_s
        self._lock = threading.Lock()
        self._fetching = threading.Lock()
        self._runs: dict[str, _Run] = {}
        self._argv: list[str] | None = None
        self._found: Engine | None = None

    # Finding a session's run by a part's name.

    def _run_of(self, name: str) -> tuple[_Run, str] | None:
        with self._lock:
            for run in self._runs.values():
                if name == run.tunnel:
                    return run, "tunnel"
                if name == run.head_name:
                    return run, "head"
        return None

    def _session(self, session_id: str) -> _Run:
        with self._lock:
            found = self._runs.get(session_id)
        if found is None:
            raise pooled.PoolError(f"session {session_id} has no helper running")
        return found

    def _named(self, name: str) -> _Run:
        found = self._run_of(name)
        if found is None:
            raise pooled.PoolError(f"{name}: no helper runs it")
        return found[0]

    # The records of the processes a session started.

    def _record_path(self, name: str) -> Path:
        return self._records() / f"{name}.json"

    def _record(self, name: str, session_id: str, pid: int, program: str) -> None:
        folder = self._records()
        if private_dir(folder, make=True) is None:
            raise pooled.PoolError(
                f"{folder} is not this user's own folder; no process is recorded"
            )
        hostos.chmod_private(folder, directory=True)
        body = {
            "name": name,
            "session_id": session_id,
            "agent_pid": self._agent_pid,
            "pid": pid,
            "start": hostos.process_start_time(pid),
            "program": program,
        }
        atomic.write(folder / f"{name}.json", json.dumps(body, sort_keys=True) + "\n")

    def _recorded(self) -> list[dict[str, Any]]:
        try:
            files = sorted(self._records().glob("*.json"))
        except OSError:
            return []
        found = []
        for path in files:
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(body, dict) and isinstance(body.get("name"), str):
                found.append(body)
        return found

    def _end_recorded(self, name: str) -> None:
        """End the process recorded under ``name`` while its pid still has the
        recorded start time, its group with it, then forget the record."""
        path = self._record_path(name)
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        pid = native.matches(body)
        if pid is not None:
            hostos.end_pid(pid, force=True, group=True)
        with contextlib.suppress(OSError):
            path.unlink()

    # The tunnel.

    def tunnel_image(self) -> str:
        with self._fetching:
            if self._argv is None or self._found is None:
                argv = list(self._helper())
                found = self._engine()
                with self._lock:
                    self._argv, self._found = argv, found
        return f"{wgpin.PROGRAM}@{wgpin.TAG}"

    def start_tunnel(self, spec: pooled.TunnelSpec) -> None:
        with self._lock:
            argv = self._argv
        if argv is None:
            raise pooled.PoolError("the helper was not fetched before its start")
        run = _Run(
            session_id=spec.session_id,
            helper=wghelper.Helper(
                argv,
                log=self._log_path(pooled.container_name(spec.session_id, "tunnel")),
                env=helper_env(self._env),
                reply_s=self._reply_s,
            ),
            api_port=spec.api_port,
        )
        run.helper.start()
        assert run.helper.pid is not None
        self._record(run.tunnel, run.session_id, run.helper.pid, argv[0])
        with self._lock:
            self._runs[spec.session_id] = run
        run.key = run.helper.prepare(spec.listen_port, spec.publish, spec.lease_s)

    def tunnel_hello(self, name: str) -> pooled.TunnelHello | None:
        found = self._run_of(name)
        if found is None or found[0].key is None:
            return None
        return pooled.TunnelHello(
            public_key=found[0].key, address=HELLO_ADDRESS, gateway=LOOPBACK
        )

    def stun(
        self, name: str, port: int, token: str, servers: Sequence[tuple[str, int]]
    ) -> list[tuple[str, str, int]]:
        said = self._named(name).helper.stun(
            token, servers, udpwire.STUN_ATTEMPTS, session.STUN_WAIT_MS
        )
        return [(host, str(at), us) for host, at, us in said]

    def keep(
        self, name: str, port: int, token: str, servers: Sequence[tuple[str, int]]
    ) -> None:
        self._named(name).helper.keep(
            token, servers, session.KEEP_EVERY_S, session.KEEP_FOR_S
        )

    def tunnel_up(self, name: str, plan: tunnel.TunnelPlan) -> None:
        peers = []
        for peer in plan.peers:
            first = peer.candidates[0] if peer.candidates else None
            peers.append(
                wghelper.UpPeer(
                    key=peer.public_key,
                    host=str(first.host) if first else None,
                    port=first.port if first else 0,
                    keepalive=peer.keepalive_s,
                    allowed=tuple(str(net) for net in peer.allowed),
                )
            )
        self._named(name).helper.up(str(plan.address), pooled.TUNNEL_MTU, peers)

    def aim(self, name: str, port: int, aims: Sequence[session.Aim]) -> None:
        self._named(name).helper.aim(
            [
                wghelper.AimPeer(
                    key=one.key,
                    host=one.host,
                    port=one.port,
                    exact=one.exact,
                    moved=one.moved,
                )
                for one in aims
            ]
        )

    def peers(self, name: str, pokes: Sequence[str]) -> pooled.PeersSeen | None:
        return self._named(name).helper.peers(pokes)

    def ping(self, name: str, host: str) -> pooled.PingSeen:
        return self._named(name).helper.ping(
            host, pooled.TUNNEL_MTU - pooled.PING_HEADERS, pooled.FULL_PINGS
        )

    def transfer(
        self, name: str, pokes: Sequence[str]
    ) -> tuple[dict[str, int], dict[str, int]]:
        return self._named(name).helper.transfer(pokes)

    # The engines.

    def head_runtime(self, share: sharing_module.Sharing) -> str | None:
        return llamacpp.RUNTIME

    def head_bind(self, hello: pooled.TunnelHello) -> str:
        return LOOPBACK

    def local_device(self, number: int) -> str | None:
        with self._lock:
            found = self._found
        prefix = DEVICE_PREFIX.get(found.backend) if found is not None else None
        return f"{prefix}{number}" if prefix is not None else None

    def start_worker(self, spec: pooled.WorkerSpec) -> None:
        raise pooled.PoolError("a native rig runs no rpc worker")

    def open_worker(self, name: str, own: str, port: int, nets: Sequence[str]) -> None:
        raise pooled.PoolError("a native rig runs no rpc worker")

    def listening(self, name: str, own: str, port: int) -> bool:
        return False

    def open_head(
        self, name: str, own: str, gateway: str, pairs: Sequence[str]
    ) -> None:
        """Nothing to open: the helper's netstack listens on nothing it was not
        asked to, and the head's forwards are opened as it starts."""

    def start_head(self, spec: pooled.HeadSpec) -> None:
        run = self._session(spec.session_id)
        with self._lock:
            found = self._found
        if spec.bind != LOOPBACK:
            raise pooled.PoolError(
                f"a native head binds {LOOPBACK} alone, never {spec.bind}"
            )
        if run.api_port is None or found is None:
            raise pooled.PoolError("the session prepared no API port or build")
        local = []
        for device in spec.rpc:
            host, _, port = device.rpartition(":")
            forwarded = run.helper.forward("head", host, int(port))
            run.forwards.append(forwarded)
            local.append(f"{LOOPBACK}:{forwarded}")
        argv = pooled.head_server_args(
            spec,
            model=str(spec.models_dir / spec.model),
            port=run.api_port,
            rpc=local,
        )
        env = {
            **engine_env(self._env),
            **native.device_env(found.backend, spec.gpus),
        }
        block = head_block(run.head_name, argv, env, spec.gpus)
        pid = run.helper.spawn(
            "head",
            found.program,
            block["command"],
            block.get("environment", {}),
            found.program.parent,
            self._log_path(run.head_name),
        )
        self._record(run.head_name, run.session_id, pid, str(found.program))
        run.head = True

    # What any part is asked.

    def renew_lease(self, name: str) -> bool:
        found = self._run_of(name)
        if found is None:
            return False
        try:
            found[0].helper.lease()
        except pooled.PoolError:
            return False
        return True

    def logs(self, name: str, tail: int) -> str:
        return read_tail(self._log_path(name), tail)

    def state(self, name: str) -> str | None:
        found = self._run_of(name)
        if found is None:
            return None
        run, part = found
        if part == "tunnel":
            return "running" if run.helper.alive() else "exited"
        try:
            state, _ = run.helper.state("head")
        except pooled.PoolError:
            return None
        return None if state == "absent" else state

    def remove(self, names: Sequence[str]) -> None:
        """End the named parts: a head through its helper, a tunnel by its
        helper's teardown; then anything either left behind by its record (a
        head outlives a helper that had to be killed outright), and a part
        no live session holds (an earlier agent's) by its record alone."""
        for name in names:
            found = self._run_of(name)
            if found is None:
                self._end_recorded(name)
                continue
            run, part = found
            if part == "head":
                with contextlib.suppress(pooled.PoolError):
                    run.helper.kill("head")
                run.head = False
                run.forwards.clear()
                self._end_recorded(name)
                continue
            with self._lock:
                self._runs.pop(run.session_id, None)
            run.helper.teardown()
            self._end_recorded(run.head_name)
            self._end_recorded(name)

    def owned(self) -> list[pooled.Owned]:
        """The parts this host runs, heads before their tunnels, and the parts
        recorded by an agent that no longer runs them."""
        with self._lock:
            runs = list(self._runs.values())
        live: set[str] = set()
        found = []
        for run in runs:
            alive = run.helper.alive()
            parts = ([run.head_name] if run.head else []) + [run.tunnel]
            live.update((run.head_name, run.tunnel))
            found += [
                pooled.Owned(
                    name=name,
                    session_id=run.session_id,
                    agent_pid=self._agent_pid,
                    running=alive,
                )
                for name in parts
            ]
        for body in self._recorded():
            if body["name"] in live:
                continue
            agent = body.get("agent_pid")
            found.append(
                pooled.Owned(
                    name=body["name"],
                    session_id=str(body.get("session_id", "")),
                    agent_pid=agent if type(agent) is int else None,
                    running=native.matches(body) is not None,
                )
            )
        return found
