"""The hub's messages reach one handler each, and the unknown are refused.

Every frame the hub sends goes through one dispatcher. Today it knows ``ack``
and ``error`` and hands them, read, to the session; a type it does not know is
answered with ``unsupported_type`` naming the frame, as the protocol asks, and
the channel stays open. A frame that is not well formed, or a known type whose
body is not, is answered with the protocol's code and reaches no handler. A
later command is one handler registered under its type: it gets the frame and
the session, and what it returns is the answer. A handler that fails is
answered as a failure, and the agent goes on.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests import rig_schema


class Session:
    def __init__(self) -> None:
        self.acks: list[Any] = []
        self.errors: list[Any] = []

    def on_ack(self, ack: Any) -> None:
        self.acks.append(ack)

    def on_error(self, error: Any) -> None:
        self.errors.append(error)


def _frame(**fields: Any) -> str:
    return json.dumps({"v": 1, **fields})


def _answer(reply: str | None) -> dict[str, Any]:
    assert reply is not None
    message: dict[str, Any] = json.loads(reply)
    rig_schema.validate(message, rig_schema.load(), "#/$defs/AgentMessage")
    return message


def test_an_ack_and_an_error_reach_the_session_read() -> None:
    from mcgyvr.rig import commands

    session = Session()
    dispatcher = commands.Dispatcher()
    ack = _frame(type="ack", id="a1", re="h1", body={"heartbeat_interval_s": 15})
    assert dispatcher.dispatch(ack, session) is None
    error = _frame(type="error", id="e1", re="h1", body={"code": "machine_mismatch"})
    assert dispatcher.dispatch(error, session) is None
    assert session.acks[0].heartbeat_interval_s == 15 and session.acks[0].re == "h1"
    assert session.errors[0].code == "machine_mismatch"
    assert dispatcher.known() == ("ack", "error")


@pytest.mark.parametrize("kind", ["start_worker", "relay_request", "stop", "x"])
def test_a_type_the_agent_does_not_know_is_answered_unsupported(kind: str) -> None:
    from mcgyvr.rig import commands

    session = Session()
    reply = commands.Dispatcher().dispatch(
        _frame(type=kind, id="c1", body={"model": "anything"}), session
    )
    answer = _answer(reply)
    assert answer["type"] == "error" and answer["re"] == "c1"
    assert answer["body"]["code"] == "unsupported_type"
    assert "anything" not in (reply or "")
    assert not session.acks and not session.errors


@pytest.mark.parametrize(
    ("raw", "code", "re"),
    [
        ("not json", "bad_message", None),
        (
            json.dumps({"v": 2, "type": "ack", "id": "a1", "re": "h"}),
            "unsupported_version",
            "a1",
        ),
        (json.dumps({"v": 1, "type": "Ack", "id": "a1"}), "bad_message", "a1"),
        (
            _frame(type="ack", id="a1", re="h1", body={"heartbeat_interval_s": "15"}),
            "bad_message",
            "a1",
        ),
        (_frame(type="ack", id="a1"), "bad_message", "a1"),
        (_frame(type="error", id="e1", body={}), "bad_message", "e1"),
        (b"\xff", "bad_message", None),
    ],
)
def test_a_frame_that_is_not_well_formed_is_answered_and_reaches_no_handler(
    raw: str | bytes, code: str, re: str | None
) -> None:
    from mcgyvr.rig import commands

    session = Session()
    answer = _answer(commands.Dispatcher().dispatch(raw, session))
    assert answer["body"]["code"] == code
    assert answer.get("re") == re
    assert not session.acks and not session.errors


def test_a_later_command_is_one_handler_under_its_type() -> None:
    from mcgyvr.rig import commands, protocol

    seen: list[Any] = []

    def start_worker(envelope: protocol.Envelope, session: Any) -> str:
        seen.append((envelope.type, envelope.id, dict(envelope.body), session))
        return protocol.error(
            protocol.new_id(), code="not_yet", message="", re=envelope.id
        )

    session = Session()
    dispatcher = commands.Dispatcher()
    dispatcher.register("start_worker", start_worker)
    assert dispatcher.known() == ("ack", "error", "start_worker")
    answer = _answer(
        dispatcher.dispatch(
            _frame(type="start_worker", id="c9", body={"n": 1}), session
        )
    )
    assert seen == [("start_worker", "c9", {"n": 1}, session)]
    assert answer["re"] == "c9"


def test_a_type_is_registered_once_and_only_as_a_type_tag() -> None:
    from mcgyvr.rig import commands

    dispatcher = commands.Dispatcher()
    with pytest.raises(ValueError):
        dispatcher.register("ack", lambda envelope, session: None)
    with pytest.raises(ValueError):
        dispatcher.register("Start-Worker", lambda envelope, session: None)


def test_a_handler_that_fails_is_answered_as_a_failure() -> None:
    from mcgyvr.rig import commands, protocol

    def broken(envelope: protocol.Envelope, session: Any) -> str | None:
        raise RuntimeError("secret detail")

    dispatcher = commands.Dispatcher()
    dispatcher.register("stop", broken)
    reply = dispatcher.dispatch(_frame(type="stop", id="c2"), Session())
    answer = _answer(reply)
    assert answer["body"]["code"] == "failed" and answer["re"] == "c2"
    assert "secret detail" not in (reply or "")
