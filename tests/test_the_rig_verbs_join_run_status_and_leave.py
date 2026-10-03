"""``mcgyvr rig`` joins a hub, runs the agent, says where it stands, and leaves.

``join`` takes the hub's address and the rig token the hub showed, keeps the
token (:mod:`mcgyvr.rig.credentials`) and runs the agent in the foreground;
``run`` runs it again from what is kept; ``status`` says what is kept, what
the agent last heard and what this machine reads as, never the token's secret;
``leave`` forgets the token here. A token is never sent in clear past this
machine: a hub reached over the network must be ``https://``. A machine joined
to one hub is not joined to another until it leaves. Joined to a hub that acks
its hello and its heartbeats and then revokes the rig, the agent says hello
with the machine's report, beats, and ends saying the rig was revoked.
"""

from __future__ import annotations

import io
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from tests import rig_schema
from tests.machine_shapes import shapes
from tests.machinereader import machine_read_text
from tests.rig_fake_hub import Peer, Server

TOKEN = "mhr_0123456789abcdef_" + "s" * 43
SECRET = "s" * 43


def cli(*argv: str) -> int:
    from mcgyvr.cli import main

    return main(list(argv))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "config-folder"
    monkeypatch.setenv("MCGYVR_HOME", str(folder))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data-folder"))
    return folder


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Stands in for the agent: records what it would run against."""
    from mcgyvr.rig import verbs

    runs: list[Any] = []

    def fake(kept: Any) -> int:
        runs.append(kept)
        return 0

    monkeypatch.setattr(verbs, "run_agent", fake)
    return runs


@pytest.mark.parametrize(
    ("hub", "agent_url"),
    [
        ("https://hub.example.com", "wss://hub.example.com/api/v1/agent"),
        ("https://hub.example.com/", "wss://hub.example.com/api/v1/agent"),
        ("https://hub.example.com/base", "wss://hub.example.com/base/api/v1/agent"),
        ("http://127.0.0.1:8765", "ws://127.0.0.1:8765/api/v1/agent"),
        ("http://localhost:8765", "ws://localhost:8765/api/v1/agent"),
        ("http://[::1]:8765", "ws://[::1]:8765/api/v1/agent"),
        ("wss://hub.example.com/api/v1/agent", "wss://hub.example.com/api/v1/agent"),
    ],
)
def test_a_hubs_address_names_its_agent_channel(hub: str, agent_url: str) -> None:
    from mcgyvr.rig import verbs

    assert verbs.agent_url(hub) == agent_url


@pytest.mark.parametrize(
    "hub",
    ["http://hub.example.com", "ws://hub.example.com", "http://192.0.2.10:8000"],
)
def test_a_token_is_never_sent_in_clear_past_this_machine(
    home: Path, ran: list[Any], hub: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    assert cli("rig", "join", hub, "--token", TOKEN) == Exit.REFUSED
    assert "https://" in capsys.readouterr().err
    assert not home.exists() or not any(home.iterdir())
    assert not ran


@pytest.mark.parametrize(
    "hub",
    [
        "ftp://hub.example.com",
        "https://user:pw@hub.example.com",
        "https://",
        "nonsense",
    ],
)
def test_an_address_that_is_not_a_hubs_is_a_usage_error(
    home: Path, ran: list[Any], hub: str
) -> None:
    from mcgyvr.exits import Exit

    assert cli("rig", "join", hub, "--token", TOKEN) == Exit.USAGE
    assert not ran


def test_join_keeps_the_token_and_runs_the_agent(
    home: Path, ran: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import credentials

    assert cli("rig", "join", "https://hub.example.com", "--token", TOKEN) == 0
    kept = credentials.load()
    assert kept == credentials.Credentials(hub="https://hub.example.com", token=TOKEN)
    assert ran == [kept]
    assert stat.S_IMODE(credentials.path().stat().st_mode) == 0o600
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert "mhr_0123456789abcdef" in out.out + out.err


def test_join_reads_the_token_from_stdin_when_asked(
    home: Path, ran: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.rig import credentials

    monkeypatch.setattr(sys, "stdin", io.StringIO(TOKEN + "\n"))
    assert cli("rig", "join", "https://hub.example.com", "--token", "-") == 0
    kept = credentials.load()
    assert kept is not None and kept.token == TOKEN


def test_a_token_that_could_not_be_sent_is_a_usage_error(
    home: Path, ran: list[Any]
) -> None:
    from mcgyvr.exits import Exit

    assert cli("rig", "join", "https://hub.example.com", "--token", "a b") == Exit.USAGE
    assert not ran


def test_a_machine_joined_to_one_hub_must_leave_before_joining_another(
    home: Path, ran: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit
    from mcgyvr.rig import credentials

    assert cli("rig", "join", "https://hub.example.com", "--token", TOKEN) == 0
    assert cli("rig", "join", "https://hub.example.com", "--token", TOKEN) == 0
    other = "mhr_fedcba9876543210_" + "t" * 43
    capsys.readouterr()
    assert cli("rig", "join", "https://other.example.com", "--token", other) == (
        Exit.REFUSED
    )
    assert "mcgyvr rig leave" in capsys.readouterr().err
    kept = credentials.load()
    assert kept is not None and kept.token == TOKEN
    assert len(ran) == 2


def test_run_runs_from_what_is_kept_and_says_how_to_join_when_nothing_is(
    home: Path, ran: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli("rig", "run") == 1
    assert "mcgyvr rig join" in capsys.readouterr().err
    cli("rig", "join", "https://hub.example.com", "--token", TOKEN)
    assert cli("rig", "run") == 0
    assert len(ran) == 2


def test_status_says_what_is_kept_and_never_the_secret(
    home: Path,
    ran: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import hardware, state

    assert cli("rig", "status") == 1
    assert "not joined" in capsys.readouterr().out
    cli("rig", "join", "https://hub.example.com", "--token", TOKEN)
    machine = next(m for m in shapes() if not m.cards)
    text = machine_read_text(machine, tmp_path / "reader")
    monkeypatch.setattr(hardware, "run_reader", lambda: text)
    state.write(
        state.State(
            hub="https://hub.example.com",
            pid=os.getpid(),
            connected=True,
            rig_id="r-example",
            heartbeat_s=15,
            last_ack_at=1.0,
            written_at=1.0,
        )
    )
    capsys.readouterr()
    assert cli("rig", "status") == 0
    out = capsys.readouterr().out
    assert "https://hub.example.com" in out
    assert "mhr_0123456789abcdef" in out and SECRET not in out
    assert "r-example" in out
    assert "mch-" in out and "0 cards" in out


def test_leave_forgets_the_token_and_says_the_rig_stays_on_the_hub(
    home: Path, ran: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.rig import credentials

    cli("rig", "join", "https://hub.example.com", "--token", TOKEN)
    capsys.readouterr()
    assert cli("rig", "leave") == 0
    assert credentials.load() is None
    assert "hub" in capsys.readouterr().out
    assert cli("rig", "leave") == 0


def test_rig_alone_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exited:
        cli("rig")
    assert exited.value.code == 2


def test_joined_to_a_hub_the_agent_says_hello_beats_and_ends_when_revoked(
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from mcgyvr.exits import Exit
    from mcgyvr.fleet import machine as reader
    from mcgyvr.rig import hardware

    shape = next(m for m in shapes() if m.cards and all(c.total_mib for c in m.cards))
    text = machine_read_text(shape, tmp_path / "reader")
    monkeypatch.setattr(hardware, "run_reader", lambda: text)
    seen: list[dict[str, Any]] = []

    def hub(peer: Peer) -> None:
        peer.handshake()
        assert peer.headers["authorization"] == f"Bearer {TOKEN}"
        hello = json.loads(peer.recv_text())
        seen.append(hello)
        peer.send_text(
            json.dumps(
                {
                    "v": 1,
                    "type": "ack",
                    "id": "a1",
                    "re": hello["id"],
                    "body": {"rig_id": "r-example", "heartbeat_interval_s": 1},
                }
            )
        )
        beat = json.loads(peer.recv_text())
        seen.append(beat)
        peer.send_text(
            json.dumps({"v": 1, "type": "ack", "id": "a2", "re": beat["id"]})
        )
        peer.send_text(
            json.dumps(
                {"v": 1, "type": "error", "id": "e1", "body": {"code": "revoked"}}
            )
        )
        peer.send_close(4001, "revoked")
        peer.recv_frame()

    with Server(hub) as server:
        url = f"http://127.0.0.1:{server.port}"
        assert cli("rig", "join", url, "--token", TOKEN) == Exit.ERROR
    assert not server.failures, server.failures
    schema = rig_schema.load()
    hello, beat = seen
    rig_schema.validate(hello, schema, "#/$defs/Hello")
    rig_schema.validate(beat, schema, "#/$defs/Heartbeat")
    assert hello["body"]["machine_id"] == reader.short_id(reader.parse(text))
    assert len(hello["body"]["cards"]) == len(shape.cards)
    err = capsys.readouterr().err
    assert "revoked" in err and SECRET not in err
