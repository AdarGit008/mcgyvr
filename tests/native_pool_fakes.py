"""A native pooled session's test rig: an invented Mac, the fake helper, a fake head.

:func:`make_native_pool` is :func:`tests.rig_pool_fakes.make_pool` with the
session host a :class:`mcgyvr.rig.userwg.NativeHost` driving
``tests/fake_wg_helper.py`` (run by this interpreter) instead of a daemon, the
system seen as macOS, and the rig lending with ``launcher: native``. The
engine is ``tests/fake_native_head.py``, written out as an executable named
``llama-server``; a small echo server stands where a worker's rpc-server
would answer through the tunnel. Nothing here reaches a card, a daemon or a
network beyond the loopback.
"""

from __future__ import annotations

import itertools
import json
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes

HELPER = Path(__file__).with_name("fake_wg_helper.py")
HEAD = Path(__file__).with_name("fake_native_head.py")
#: The worker's rpc device on the session's tunnel, as the hub names it.
RPC_DEVICE = (fakes.PEER, 50052)


class Echo:
    """A loopback server that answers what it is sent, prefixed ``echo:``."""

    def __init__(self) -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.port: int = self.listener.getsockname()[1]
        self.heard: list[bytes] = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            with conn:
                got = b""
                while chunk := conn.recv(64):
                    got += chunk
                self.heard.append(got)
                conn.sendall(b"echo:" + got)

    def close(self) -> None:
        self.listener.close()


@dataclass
class NativePool:
    pool: fakes.Pool
    host: Any
    tmp: Path
    echo: Echo
    config: dict[str, Any] = field(default_factory=dict)

    def requests(self) -> list[dict[str, Any]]:
        """Every request the helpers were sent and every forward event, in order."""
        found = self.tmp / "helper-record.jsonl"
        if not found.exists():
            return []
        return [json.loads(line) for line in found.read_text().splitlines()]

    def verbs(self) -> list[str]:
        return [r["verb"] for r in self.requests() if "verb" in r]

    def head_said(self, timeout: float = 5.0) -> dict[str, Any]:
        target = self.tmp / "head-said.json"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if target.exists():
                try:
                    found: dict[str, Any] = json.loads(target.read_text())
                    return found
                except ValueError:
                    pass
            time.sleep(0.01)
        raise AssertionError("the head never said what it reached")


def write_engine(folder: Path) -> Path:
    """The fake head, written out as an executable ``llama-server``."""
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / "llama-server"
    program.write_text(
        f"#!{sys.executable} -I\n" + HEAD.read_text(encoding="utf-8"), encoding="utf-8"
    )
    program.chmod(0o700)
    return program


def as_native_system(monkeypatch: pytest.MonkeyPatch, system: str) -> None:
    """Make the rig see itself as a `system` machine with a helper pinned for it.

    Only the system's name is changed (``hostos.os_name``), which is what
    decides whether a rig's sessions run natively; every process call stays
    this machine's own, so the fake helper and the fake head really run, and
    their pids, start times and groups are real. What a Mac or Windows does
    with a detached start, a Job Object or a start time is ``hostos``'s own
    tests'."""
    from mcgyvr import hostos
    from mcgyvr.rig import wgpin

    monkeypatch.setattr(hostos, "os_name", lambda: system)
    monkeypatch.setattr(wgpin, "pinned_here", lambda: True)


def make_native_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend: str = "cuda",
    system: str = "windows",
    config: dict[str, Any] | None = None,
    with_host: bool = True,
    **sharing_changes: Any,
) -> NativePool:
    """A session table whose sessions run natively through the fake helper:
    by default an invented Windows box with two NVIDIA cards and a CUDA build."""
    from mcgyvr.rig import commands, pooled, userwg, wgpin
    from mcgyvr.rig import session as rs

    as_native_system(monkeypatch, system)
    echo = Echo()
    settings = {
        "version": wgpin.TAG,
        "record": str(tmp_path / "helper-record.jsonl"),
        "routes": {f"{RPC_DEVICE[0]}:{RPC_DEVICE[1]}": f"127.0.0.1:{echo.port}"},
        **(config or {}),
    }
    config_file = tmp_path / "helper-config.json"
    config_file.write_text(json.dumps(settings), encoding="utf-8")
    program = write_engine(tmp_path / "engine")
    logs = tmp_path / "logs"
    host = userwg.NativeHost(
        agent_pid=os.getpid(),
        helper=lambda: [sys.executable, "-I", str(HELPER), str(config_file)],
        engine=lambda: userwg.Engine(program=program, backend=backend),
        env={
            "PATH": os.environ.get("PATH", ""),
            "LLAMA_ARG_HOST": "0.0.0.0",
            "HF_TOKEN": "hf_not_for_the_head",
            "GGML_SCHED_MAX_COPIES": "1",
        },
        log_path=lambda name: logs / f"{name}.log",
        records=lambda: tmp_path / "records",
        reply_s=10.0,
    )
    box = fakes.Box()
    health: list[str] = ["loading", "ok"]

    def head_health(port: int) -> str:
        return health.pop(0) if len(health) > 1 else health[0]

    changes = {"launcher": "native", "image": None, **sharing_changes}
    machine = rs.Machine(
        sharing=lambda: fakes.sharing(tmp_path, **changes),
        report=fakes.report,
        inventory=lambda: fakes.inventory(tmp_path),
        interfaces=fakes.interfaces,
        owner=pooled.Owner(uid=1000, gid=1000, agent_pid=os.getpid()),
        cache_dir=None,
        free_port=itertools.count(18080).__next__,
        head_health=head_health,
        warm_up=lambda port, ctx: True,
        bind_relay=lambda grant: None,
    )
    docker = fakes.FakeDocker()
    sessions = rs.Sessions(
        docker=docker,
        machine=machine,
        send=box.put,
        timing=fakes.quick_timing(),
        native=host if with_host else None,
    )
    dispatcher = commands.Dispatcher()
    rs.register(dispatcher, sessions)
    pool = fakes.Pool(docker, box, sessions, dispatcher, health)
    return NativePool(pool=pool, host=host, tmp=tmp_path, echo=echo, config=settings)
