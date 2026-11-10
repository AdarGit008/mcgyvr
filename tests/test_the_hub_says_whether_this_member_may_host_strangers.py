"""The hub says whether this member may host strangers, and the rig prints it.

A member's rigs serve strangers (the general pool's ``anyone``, riders on their
units) only after a hub admin approves that member once. The hub tells the rig
in the hello's ack (:data:`mcgyvr.hubwire.HOSTING_APPROVED_FIELD`, a boolean):
the agent reads it, keeps it in its state, and ``mcgyvr rig status`` and
``mcgyvr rig share`` say "approved to host" or "waiting for admin approval".
An older hub that does not carry it sends none, and then the rig says nothing
of it; a value of another type is refused.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from tests import rig_schema
from tests.rigagents import Clock, Hub, Report, _agent, _frame

FIELD = hubwire.HOSTING_APPROVED_FIELD


def _ack(**body: Any) -> Any:
    from mcgyvr.rig import protocol

    raw = _frame("ack", "h1", rig_id="r-1", **body)
    return protocol.read_ack(protocol.decode(raw))


# --- read_ack ----------------------------------------------------------------------


def test_read_ack_carries_the_hosting_approval_when_the_hub_says() -> None:
    assert _ack(**{FIELD: True}).hosting_approved is True
    assert _ack(**{FIELD: False}).hosting_approved is False
    # An older hub leaves it out, and the agent then says nothing of it.
    assert _ack().hosting_approved is None


@pytest.mark.parametrize("bad", [1, 0, "true", [], {}])
def test_read_ack_refuses_a_hosting_approval_that_is_not_a_boolean(bad: Any) -> None:
    from mcgyvr.rig.protocol import ProtocolError

    with pytest.raises(ProtocolError) as caught:
        _ack(**{FIELD: bad})
    assert FIELD in str(caught.value)


# --- the shipped schema ------------------------------------------------------------


def test_the_acks_hosting_approval_is_an_optional_boolean_in_the_schema() -> None:
    body = rig_schema.load(rig_schema.PROTOCOL)["$defs"]["AckBody"]
    field = body["properties"][FIELD]
    assert {"type": "boolean"} in field["anyOf"]
    assert {"type": "null"} in field["anyOf"]
    assert FIELD not in body.get("required", [])


@pytest.mark.parametrize("approved", [True, False])
def test_an_ack_carrying_the_hosting_approval_the_shipped_schema_takes(
    approved: bool,
) -> None:
    schema = rig_schema.load(rig_schema.PROTOCOL)
    rig_schema.validate({"rig_id": "rig-1", FIELD: approved}, schema, "#/$defs/AckBody")


# --- the agent's state -------------------------------------------------------------


def test_the_state_round_trips_the_hosting_approval(tmp_path: Path) -> None:
    from mcgyvr.rig import state

    for approved in (True, False, None):
        written = state.State(
            hub="https://hub.example.com",
            pid=os.getpid(),
            connected=True,
            rig_id="r-1",
            heartbeat_s=15,
            last_ack_at=1.0,
            written_at=1.0,
            hosting_approved=approved,
        )
        state.write(written)
        assert state.read() == written


def test_a_state_file_from_before_the_field_reads_as_none(tmp_path: Path) -> None:
    from mcgyvr.rig import state

    # A file written before hosting_approved existed has no such key.
    old = {
        "hub": "https://hub.example.com",
        "pid": os.getpid(),
        "connected": True,
        "rig_id": "r-1",
        "heartbeat_s": 15,
        "last_ack_at": 1.0,
        "written_at": 1.0,
    }
    state.path().parent.mkdir(parents=True, exist_ok=True)
    state.path().write_text(json.dumps(old), encoding="utf-8")
    read = state.read()
    assert read is not None and read.hosting_approved is None


def test_a_state_file_with_a_non_boolean_hosting_approval_is_refused() -> None:
    from mcgyvr.rig import state

    bad = {
        "hub": "https://hub.example.com",
        "pid": os.getpid(),
        "connected": True,
        "rig_id": "r-1",
        "heartbeat_s": 15,
        "last_ack_at": 1.0,
        "written_at": 1.0,
        "hosting_approved": "yes",
    }
    state.path().parent.mkdir(parents=True, exist_ok=True)
    state.path().write_text(json.dumps(bad), encoding="utf-8")
    assert state.read() is None


# --- the agent threads it to its status --------------------------------------------


def test_the_agent_keeps_the_hosting_approval_each_hello_was_acked_with() -> None:
    class Approving(Hub):
        def answer(self, message: dict[str, Any], channel: Any) -> list[Any]:
            out = super().answer(message, channel)
            if message["type"] != "hello":
                return out
            ack = json.loads(out[0])
            ack["body"][FIELD] = True
            return [json.dumps(ack), *out[1:]]

    seen: list[Any] = []
    agent, _ = _agent(
        [Approving(interval=15, beats=1)],
        Clock(),
        report=Report(),
        on_status=seen.append,
    )
    agent.run()
    acked = [s for s in seen if s.connected]
    assert acked and acked[-1].hosting_approved is True


# --- what status and share print ---------------------------------------------------


@pytest.fixture
def _dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCGYVR_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MCGYVR_DATA", str(tmp_path / "data"))


def _write_state(approved: bool | None) -> None:
    from mcgyvr.rig import state

    state.write(
        state.State(
            hub="https://hub.example.com",
            pid=os.getpid(),
            connected=True,
            rig_id="r-1",
            heartbeat_s=15,
            last_ack_at=1.0,
            written_at=1.0,
            hosting_approved=approved,
        )
    )


@pytest.mark.parametrize(
    ("approved", "line"),
    [(True, "approved to host"), (False, "waiting for admin approval")],
)
def test_share_says_whether_the_member_may_host_strangers(
    _dirs: None,
    capsys: pytest.CaptureFixture[str],
    approved: bool,
    line: str,
) -> None:
    from mcgyvr import cli

    _write_state(approved)
    assert cli.main(["rig", "share", "--off"]) == 0
    said = capsys.readouterr().out
    assert f"hosting: {line}" in said


def test_share_says_nothing_of_hosting_when_no_ack_has_arrived(
    _dirs: None, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr import cli

    # No state file at all: the agent has heard nothing from a hub yet.
    assert cli.main(["rig", "share", "--off"]) == 0
    assert "hosting:" not in capsys.readouterr().out
