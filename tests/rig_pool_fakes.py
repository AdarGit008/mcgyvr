"""Fakes for the rig agent's session tests: a daemon, a machine, and an outbox.

:class:`FakeDocker` stands where :class:`mcgyvr.sandbox.pooled.Pool` stands:
it records every call, keeps the containers a session started (by name, with
their labels), and answers the way a daemon would, with the knobs a test
turns (a tunnel that never says it is ready, a worker that exits, a port that
never listens). :func:`machine` is an invented machine of two cards of the
lent vendor and one of another, with one model on disk. Nothing here reaches
a daemon, a card, or the network.
"""

from __future__ import annotations

import itertools
import json
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests import rig_schema

KEY = "A" * 42 + "Q="
PEER_KEY = "B" * 42 + "g="
BRIDGE = "203.0.113.2/24"
GATEWAY = "203.0.113.1"
LAN_ADDRESS = "192.0.2.10"
PEER_ADDRESS = "192.0.2.20"
TUNNEL = "198.51.100.0/24"
SELF = "198.51.100.2"
PEER = "198.51.100.1"
MODEL = "model-q5.gguf"


@dataclass
class Container:
    argv: list[str]
    labels: dict[str, str]
    state: str = "running"


@dataclass
class FakeDocker:
    """A daemon that keeps what was started, and the knobs a test turns."""

    containers: dict[str, Container] = field(default_factory=dict)
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    scripts: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    leases: int = 0
    tunnel_ready: bool = True
    listening: bool = True
    exits_on_start: set[str] = field(default_factory=set)
    logs_said: str = "engine said: load failed\n"
    fail_script: str | None = None
    peer_silent: bool = False
    transfer_said: str | None = None
    peer_rx: int = 0
    #: The endpoints a WireGuard handshake completes at (None: every one), and
    #: where WireGuard ends up when a peer's NAT moved the port.
    answering: set[tuple[str, int]] | None = None
    roams: dict[tuple[str, int], tuple[str, int]] = field(default_factory=dict)
    aims: dict[str, tuple[str, int]] = field(default_factory=dict)
    shaken: dict[str, tuple[str, int]] = field(default_factory=dict)
    peers_said: str | None = None
    stun_said: str = "rtt 203.0.113.9 3478 1500\n"
    python: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def ensure_tunnel_image(self) -> str:
        self.calls.append(("image", ()))
        return "mcgyvr-tunnel:test"

    def start(self, argv: Sequence[str]) -> None:
        argv = list(argv)
        name = argv[argv.index("--name") + 1]
        labels = {}
        for i, word in enumerate(argv[:-1]):
            if word == "--label":
                key, _, value = argv[i + 1].partition("=")
                labels[key] = value
        with self.lock:
            self.calls.append(("run", (name,)))
            part = labels.get("mcgyvr.pool.part", "")
            state = "exited" if part in self.exits_on_start else "running"
            self.containers[name] = Container(argv=argv, labels=labels, state=state)

    def run_script(self, name: str, script: str, *args: str) -> str:
        from mcgyvr.sandbox import pooled

        with self.lock:
            self.scripts.append((name, script, args))
        if self.fail_script is not None and script == getattr(pooled, self.fail_script):
            from mcgyvr.sandbox.pooled import PoolError

            raise PoolError("docker exec failed (1): nft said no")
        if script == pooled.PING_SCRIPT:
            return "0.512\n"
        if script == pooled.TUNNEL_SCRIPT:
            self._aim(args[2:], 5, lambda a: True)
        if script == pooled.PATH_SCRIPT:
            self._aim(args[1:], 5, lambda a: a[4] == "1")
        if script == pooled.PEERS_SCRIPT:
            return self._peers()
        if script == pooled.TRANSFER_SCRIPT:
            if self.transfer_said is not None:
                return self.transfer_said
            with self.lock:
                if not self.peer_silent:
                    self.peer_rx += 148
                return f"{PEER_KEY}\t{self.peer_rx}\t4096\n"
        return "ok\n"

    def _aim(self, args: Sequence[str], width: int, aims: Any) -> None:
        with self.lock:
            for at in range(0, len(args) - width + 1, width):
                one = args[at : at + width]
                if one[1] != "-" and aims(one):
                    self.aims[one[0]] = (one[1], int(one[2]))

    def _peers(self) -> str:
        if self.peers_said is not None:
            return self.peers_said
        lines = ["now 1700000000"]
        with self.lock:
            for key, aim in self.aims.items():
                if key not in self.shaken and (
                    self.answering is None or aim in self.answering
                ):
                    self.shaken[key] = self.roams.get(aim, aim)
            for key in self.aims:
                lines.append(
                    f"handshake {key}\t{1700000000 if key in self.shaken else 0}"
                )
                host, port = self.shaken.get(key, self.aims[key])
                lines.append(f"endpoint {key}\t{host}:{port}")
        return "\n".join(lines) + "\n"

    def run_python(self, name: str, source: str, *args: str) -> str:
        with self.lock:
            self.python.append((name, "run", args))
        return self.stun_said

    def start_python(self, name: str, source: str, *args: str) -> None:
        with self.lock:
            self.python.append((name, "start", args))

    def try_script(self, name: str, script: str, *args: str) -> bool:
        with self.lock:
            self.scripts.append((name, script, args))
        return self.listening

    def renew_lease(self, name: str) -> bool:
        with self.lock:
            self.leases += 1
            return name in self.containers

    def logs(self, name: str, tail: int) -> str:
        if name.endswith("-tunnel"):
            if not self.tunnel_ready:
                return "starting\n"
            return f"public-key {KEY}\naddress {BRIDGE}\ngateway {GATEWAY}\nready\n"
        return self.logs_said

    def state(self, name: str) -> str | None:
        with self.lock:
            found = self.containers.get(name)
            return found.state if found else None

    def remove(self, names: Sequence[str]) -> None:
        with self.lock:
            self.calls.append(("rm", tuple(names)))
            for name in names:
                self.containers.pop(name, None)

    def owned(self) -> list[Any]:
        from mcgyvr.sandbox.pooled import Owned

        with self.lock:
            return [
                Owned(
                    name=name,
                    session_id=c.labels.get("mcgyvr.pool.session", ""),
                    agent_pid=int(c.labels.get("mcgyvr.pool.agent", "0") or 0),
                    running=c.state == "running",
                )
                for name, c in self.containers.items()
            ]

    def of_session(self, session_id: str) -> list[str]:
        with self.lock:
            return [
                name
                for name, c in self.containers.items()
                if c.labels.get("mcgyvr.pool.session") == session_id
            ]

    def runs(self) -> list[str]:
        return [args[0] for verb, args in self.calls if verb == "run"]


class Box:
    """An outbox that keeps every frame, each checked against the schema."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.open = True

    def put(self, frame: str, timeout: float | None = None) -> bool:
        message = json.loads(frame)
        rig_schema.validate(message, rig_schema.load(), "#/$defs/AgentMessage")
        if not self.open:
            return False
        with self.lock:
            self.frames.append(message)
        return True

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        with self.lock:
            return [f for f in self.frames if f["type"] == kind]


def report() -> Any:
    from mcgyvr.rig import hardware, protocol

    return hardware.Report(
        machine_id="mch-example",
        ram_total_mb=65536,
        ram_free_mb=60000,
        cards=(
            protocol.CardReport(
                index=0, name="Card A", vram_total_mb=8192, vram_free_mb=8000
            ),
            protocol.CardReport(
                index=1, name="Card A", vram_total_mb=8192, vram_free_mb=8000
            ),
            protocol.CardReport(
                index=2, name="Card B", vram_total_mb=4096, vram_free_mb=4000
            ),
        ),
        notes=(),
        sources=(("nvidia", 0), ("nvidia", 1), ("othervendor", 0)),
    )


def sharing(models: Path | None, **changes: Any) -> Any:
    from mcgyvr.rig import sharing as sharing_module

    settings: dict[str, Any] = {
        "enabled": True,
        "roles": ("head", "worker"),
        "image": "engine:rpc",
        "models_dir": str(models) if models else None,
        "endpoints": (LAN_ADDRESS,),
    }
    settings.update(changes)
    return sharing_module.Sharing(**settings)


def inventory(models: Path) -> Any:
    from mcgyvr.rig import inventory as inventory_module
    from mcgyvr.rig import protocol

    return inventory_module.Inventory(
        folder=models,
        models=(protocol.ModelInfo(name=MODEL, size_bytes=1024),),
        files={MODEL: f"dense/{MODEL}"},
    )


def interfaces() -> tuple[Any, ...]:
    import ipaddress

    return (
        ("eth0", ipaddress.IPv4Interface(f"{LAN_ADDRESS}/24")),
        ("lo", ipaddress.IPv4Interface("127.0.0.1/8")),
    )


def frame(kind: str, message_id: str = "c1", **body: Any) -> str:
    return json.dumps({"v": 1, "type": kind, "id": message_id, "body": body})


def tunnel_up_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "session_id": "s1",
        "address": f"{SELF}/24",
        "listen_port": 51820,
        "peers": [
            {
                "rig_id": "rig-peer",
                "public_key": PEER_KEY,
                "endpoints": [{"host": PEER_ADDRESS, "port": 51820, "kind": "lan"}],
                "allowed_ips": [f"{PEER}/32"],
            }
        ],
    }
    body.update(changes)
    return body


@dataclass
class Pool:
    docker: FakeDocker
    box: Box
    sessions: Any
    dispatcher: Any
    health: list[str]
    warmed: list[tuple[int, int]] = field(default_factory=list)
    warm_answers: list[bool] = field(default_factory=lambda: [True])
    warm_with: Any = None
    relay_port: int | None = 40001
    relayed: list[Any] = field(default_factory=list)

    def report(self, message_id: str = "t1") -> dict[str, Any]:
        """The tunnel_report answering tunnel_up ``message_id``, once sent."""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            found = [
                f
                for f in self.box.of_type("tunnel_report")
                if f.get("re") == message_id
            ]
            if found:
                return found[-1]
            time.sleep(0.005)
        raise AssertionError(f"no tunnel_report re {message_id} in {self.box.frames}")

    def up(self, message_id: str = "t1", **body: Any) -> dict[str, Any]:
        """Send tunnel_up; the tunnel_report that answers it."""
        answer = self.ask("tunnel_up", message_id, **body)
        assert answer is None, answer
        return self.report(message_id)

    def ask(
        self, kind: str, message_id: str = "c1", **body: Any
    ) -> dict[str, Any] | None:
        import json

        from tests import rig_schema

        reply = self.dispatcher.dispatch(frame(kind, message_id, **body), Stub())
        if reply is None:
            return None
        message: dict[str, Any] = json.loads(reply)
        rig_schema.validate(message, rig_schema.load(), "#/$defs/AgentMessage")
        return message

    def settle(self) -> None:
        assert self.sessions.settle(timeout=5.0)

    def wait_for(self, kind: str, state: str | None = None, count: int = 1) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            found = [
                f
                for f in self.box.of_type(kind)
                if state is None or f["body"].get("state") == state
            ]
            if len(found) >= count:
                return
            time.sleep(0.005)
        raise AssertionError(f"no {kind} {state or ''} in {self.box.frames}")


class Stub:
    def on_ack(self, ack: Any) -> None: ...

    def on_error(self, error: Any) -> None: ...


def make_pool(tmp_path: Path, **sharing_changes: Any) -> Pool:
    from mcgyvr.rig import commands
    from mcgyvr.rig import session as rs
    from mcgyvr.sandbox import pooled

    docker = FakeDocker()
    box = Box()
    health: list[str] = ["loading", "ok"]

    def head_health(port: int) -> str:
        return health.pop(0) if len(health) > 1 else health[0]

    made: list[Pool] = []

    def bind_relay(grant: Any) -> int | None:
        pool = made[0]
        pool.relayed.append(grant)
        return pool.relay_port

    def warm_up(port: int, ctx: int) -> bool:
        pool = made[0]
        pool.warmed.append((port, ctx))
        if pool.warm_with is not None:
            return bool(pool.warm_with(port, ctx))
        return pool.warm_answers[0]

    machine = rs.Machine(
        sharing=lambda: sharing(tmp_path, **sharing_changes),
        report=report,
        inventory=lambda: inventory(tmp_path),
        interfaces=interfaces,
        owner=pooled.Owner(uid=1000, gid=1000, agent_pid=os.getpid()),
        cache_dir=tmp_path / "cache",
        # a port of its own each time, as the machine's free_port gives one
        free_port=itertools.count(18080).__next__,
        head_health=head_health,
        warm_up=warm_up,
        bind_relay=bind_relay,
    )
    sessions = rs.Sessions(
        docker=docker, machine=machine, send=box.put, timing=rs.Timing.quick()
    )
    dispatcher = commands.Dispatcher()
    rs.register(dispatcher, sessions)
    made.append(Pool(docker, box, sessions, dispatcher, health))
    return made[0]


def prepared(pool: Pool, role: str = "worker") -> dict[str, Any]:
    assert pool.ask("session_prepare", "p1", session_id="s1", role=role) is None
    pool.wait_for("session_prepared")
    return pool.box.of_type("session_prepared")[0]
