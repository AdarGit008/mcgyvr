"""A link is timed on a rig through the door, and the timer is bounded.

Promise: ``python -m mcgyvr.serving.run link --host H`` is the door's fourth
fixed sequence. It checks what it was asked before anything reaches the rig --
two different cards by index, or an IPv4 address and a port -- then ships the
one timer (``mcgyvr/serving/linktime.py``) to the rig on stdin as ``python3 -``
and prints its one line of JSON. Nothing is leased and nothing is filed.

The timer itself imports the standard library alone and holds itself to its
bounds: a sink takes one connection and no more bytes than a reading needs,
every payload is small, and what it could not do is said as JSON with a
non-zero exit. Its network half is exercised here over loopback; its card half
is never run (no test touches a card).
"""

from __future__ import annotations

import ast
import ctypes
import json
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.serving import linktime, run
from tests import onedoor

REPO = Path(__file__).resolve().parent.parent
TIMER = REPO / "src" / "mcgyvr" / "serving" / "linktime.py"


# The door.


def link_door(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        str(root / onedoor.DOOR_REL),
        "link",
        "--host",
        "box-a.example",
    ]
    return subprocess.run(
        [*argv, *args],
        cwd=root,
        env=onedoor.door_env(root),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_the_link_run_is_one_fixed_gate_and_the_timer_is_on_the_manifest() -> None:
    assert [entry.script for entry in run.LINK_SEQUENCE] == ["link-01-time.py"]
    assert TIMER in run.READERS


def test_a_peer_timing_ships_the_timer_on_stdin_and_prints_its_answer(
    tmp_path: Path,
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    stubs = onedoor.stubs_dir(root)
    said = {"transfers": [[65536, 0.0001], [1048576, 0.0002]]}
    (stubs / "linktime.json").write_text(json.dumps(said) + "\n", encoding="utf-8")
    ran = link_door(root, "--peer", "0", "1")
    assert ran.returncode == 0, ran.stderr
    assert json.loads(ran.stdout.strip().splitlines()[-1]) == said
    command = (stubs / "linktime-cmd.txt").read_text(encoding="utf-8").strip()
    assert command == "python3 - mcgyvr-linktime peer 0 1"
    shipped = (stubs / "linktime-source.txt").read_text(encoding="utf-8")
    assert shipped == TIMER.read_text(encoding="utf-8")
    # Nothing is filed and nothing is leased.
    assert onedoor.written_under_records(root) == []
    assert onedoor.read_lease(root) is None


@pytest.mark.parametrize(
    ("args", "why"),
    [
        (("--peer", "0", "0"), "two cards"),
        (("--peer", "0", "x"), "index"),
        (("--sink", "box-b.example", "50151"), "IPv4"),
        (("--send", "192.0.2.20", "80"), "port"),
    ],
)
def test_what_cannot_be_timed_is_refused_before_the_rig_is_reached(
    tmp_path: Path, args: tuple[str, ...], why: str
) -> None:
    root = onedoor.fixture_repo(tmp_path)
    ran = link_door(root, *args)
    assert ran.returncode == 2
    assert why in ran.stderr
    assert onedoor.ssh_log(onedoor.stubs_dir(root)) == []


# The timer.


def test_the_timer_imports_the_standard_library_alone() -> None:
    tree = ast.parse(TIMER.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
    return port


def test_a_send_to_a_sink_times_every_payload_and_the_sink_ends() -> None:
    port = free_port()
    got: dict[str, Any] = {}

    def listen() -> None:
        got["received"] = linktime.sink("127.0.0.1", port)

    thread = threading.Thread(target=listen)
    thread.start()
    transfers = linktime.send("127.0.0.1", port)
    thread.join(timeout=30)
    assert not thread.is_alive()
    sizes = [size for size, _ in transfers]
    assert sizes == [
        size for size in linktime.NETWORK_PAYLOADS for _ in range(linktime.REPEATS)
    ]
    assert all(seconds > 0 for _, seconds in transfers)
    assert got["received"] == min(linktime.NETWORK_PAYLOADS) + sum(sizes)
    assert got["received"] <= linktime.SINK_MOST_BYTES


def test_a_sink_takes_no_more_than_a_reading_needs() -> None:
    port = free_port()
    failed: dict[str, str] = {}

    def listen() -> None:
        try:
            linktime.sink("127.0.0.1", port)
        except linktime.LinkTimeError as exc:
            failed["why"] = str(exc)

    thread = threading.Thread(target=listen)
    thread.start()
    with socket.create_connection(("127.0.0.1", port), timeout=10) as conn:
        conn.sendall((linktime.SINK_MOST_BYTES + 1).to_bytes(8, "big"))
        thread.join(timeout=30)
    assert "more than a reading needs" in failed["why"]


def test_the_peer_timer_says_so_when_the_machine_has_no_card_driver(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_driver(name: str) -> None:
        raise OSError(f"{name}: cannot open shared object file")

    monkeypatch.setattr(ctypes, "CDLL", no_driver)
    assert linktime.main([linktime.LINK_WORD, "peer", "0", "1"]) == 1
    said = json.loads(capsys.readouterr().out)
    assert "no CUDA driver" in said["error"]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["mcgyvr-linktime", "copy", "0", "1"],
        ["mcgyvr-linktime", "peer", "0", "0"],
        ["mcgyvr-linktime", "send", "box-b.example", "50151"],
        ["mcgyvr-linktime", "sink", "192.0.2.20", "99999"],
    ],
)
def test_what_the_timer_is_asked_wrongly_is_said_as_json(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert linktime.main(argv) == 1
    assert "error" in json.loads(capsys.readouterr().out)
