"""A sealed ride is opened by the host's agent and answered sealed.

The host's agent makes one seal key per run (:class:`mcgyvr.seal.HostKey`) and
names it on every unit it advertises (``unit_advert``'s ``seal``). A ride whose
body carries a sealed envelope (as the hub forwards one: the unit's model, the
stream flag, the hub's cap on ``max_tokens`` and the envelope) is opened with
that key, held to the fields the hub passes a unit, posted to the unit in
clear, and its answer sent back sealed: a stream event by event, any other
answer whole. A ride the agent cannot open ends ``bad_seal`` and reaches no
unit. An agent with no key, and a ride in clear, are as before.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import seal, whole
from tests.relays import (
    RIDE_MODEL,
    RIDE_PROMPT,
    SERVED,
    Host,
    Unit,
    _host,
    _runner_serve,
)
from tests.relays import _ride_body as _clear_body

CAP = 64


def _forwarded(key: seal.UnitKey, *, stream: bool) -> tuple[bytes, seal.AnswerOpener]:
    """The body the hub relays for a sealed ride, and the rider's opener."""
    asked = whole.asking(
        {
            "model": "hitchhike@" + "b" * 32,
            "messages": [{"role": "user", "content": RIDE_PROMPT}],
            "max_tokens": 5000,
            "grammar": "root ::= x",
        }
    )
    sealed, opener = seal.seal_request(asked, key)
    body: dict[str, Any] = {
        "model": RIDE_MODEL,
        "stream": stream,
        "max_tokens": CAP,
        "sealed": sealed["sealed"],
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    return json.dumps(body).encode(), opener


@pytest.fixture
def key() -> seal.HostKey:
    return seal.HostKey()


@pytest.fixture
def host(tmp_path: Path, key: seal.HostKey) -> Iterator[Host]:
    made = _host(tmp_path, key=key)
    yield made
    made.unit.release.set()
    made.relays.cancel_all()
    assert made.unit.server is not None
    made.unit.server.shutdown()


@pytest.fixture
def streaming(tmp_path: Path, key: seal.HostKey) -> Iterator[tuple[Host, Unit]]:
    unit = Unit()
    unit.server = _runner_serve(unit)
    port = unit.server.server_address[1]
    made = _host(tmp_path, key=key, address=f"http://127.0.0.1:{port}/v1")
    yield made, unit
    made.relays.cancel_all()
    unit.server.shutdown()
    assert made.unit.server is not None
    made.unit.server.shutdown()


def test_every_unit_advertised_names_the_agents_key_and_an_agent_with_none_names_none(
    host: Host, key: seal.HostKey, tmp_path: Path
) -> None:
    (advert,) = host.box.of_type("unit_advert")
    assert [u["seal"] for u in advert["body"]["units"]] == [key.unit_key.wire()]

    plain = _host(tmp_path / "plain")
    (old,) = plain.box.of_type("unit_advert")
    assert all("seal" not in u for u in old["body"]["units"])
    assert plain.unit.server is not None
    plain.unit.server.shutdown()


def test_a_sealed_ride_reaches_the_unit_opened_and_held_to_what_the_hub_passes(
    host: Host, key: seal.HostKey
) -> None:
    body, opener = _forwarded(key.unit_key, stream=False)
    assert RIDE_PROMPT.encode() not in body

    host.ride(body)

    assert host.ended() == {"request_id": "q1", "outcome": "complete"}
    ((path, seen),) = host.unit.seen
    assert path == "/v1/chat/completions"
    sent = json.loads(seen)
    assert sent["messages"] == [{"role": "user", "content": RIDE_PROMPT}]
    assert sent["model"] == RIDE_MODEL  # the unit's own, as the hub named it
    assert sent["max_tokens"] == CAP  # the hub's cap holds over the rider's 5000
    assert "grammar" not in sent and "sealed" not in sent

    (response,) = host.box.of_type("relay_response")
    assert response["body"]["content_type"] == whole.JSON_TYPE
    answer = host.answer()
    assert b'"ok"' not in answer
    assert set(json.loads(answer)) == {"model", "sealed"}
    opened = json.loads(opener.body(answer))
    assert opened["model"] == SERVED
    assert opened["choices"][0]["message"]["content"] == "ok"
    assert all(RIDE_PROMPT not in json.dumps(f) for f in host.box.frames)


def test_a_sealed_stream_goes_back_event_by_event_and_assembles_for_the_rider(
    streaming: tuple[Host, Unit], key: seal.HostKey
) -> None:
    host, unit = streaming
    body, opener = _forwarded(key.unit_key, stream=True)

    host.ride(body, stream=True)

    assert host.ended() == {"request_id": "q1", "outcome": "complete"}
    (seen,) = unit.seen
    assert seen["body"]["stream"] is True
    assert seen["body"]["messages"][0]["content"] == RIDE_PROMPT
    (response,) = host.box.of_type("relay_response")
    assert whole.media(response["body"]["content_type"]) == whole.EVENT_STREAM
    raw = host.answer() + b"\n\n"
    assert b"Hello" not in raw and b"world" not in raw
    clear = [
        json.loads(e[6:]) for e in raw.split(b"\n\n") if e and e != b"data: [DONE]"
    ]
    assert clear[-1]["usage"]["completion_tokens"] == 7  # counted in clear
    assert all(RIDE_PROMPT not in json.dumps(f) for f in host.box.frames)

    assembled = whole.Whole()
    assembled.feed(opener.feed(raw) + opener.end())
    answer = assembled.answer()
    assert answer is not None
    document = json.loads(answer[2])
    assert document["choices"][0]["message"]["content"] == "Hello, world"


def test_a_sealed_ride_the_agent_cannot_open_ends_bad_seal_and_reaches_no_unit(
    host: Host, key: seal.HostKey
) -> None:
    stranger = seal.HostKey().unit_key
    body, _ = _forwarded(stranger, stream=False)
    host.ride(body)
    assert host.ended() == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "bad_seal",
    }

    body, _ = _forwarded(key.unit_key, stream=False)
    tampered = json.loads(body)
    ct = tampered["sealed"]["ct"]
    tampered["sealed"]["ct"] = ("B" if ct[0] == "A" else "A") + ct[1:]
    host.ride(json.dumps(tampered).encode(), request_id="q2")
    assert host.ended("q2")["error_code"] == "bad_seal"
    assert host.unit.seen == []


def test_an_agent_with_no_key_refuses_a_sealed_ride_and_rides_a_clear_one_as_before(
    tmp_path: Path, key: seal.HostKey
) -> None:
    plain = _host(tmp_path)
    try:
        body, _ = _forwarded(key.unit_key, stream=False)
        plain.ride(body)
        assert plain.ended()["error_code"] == "bad_seal"
        plain.ride(_clear_body(), request_id="q2")
        assert plain.ended("q2") == {"request_id": "q2", "outcome": "complete"}
        ((_, seen),) = plain.unit.seen
        assert json.loads(seen)["messages"][0]["content"] == RIDE_PROMPT
    finally:
        plain.relays.cancel_all()
        assert plain.unit.server is not None
        plain.unit.server.shutdown()
