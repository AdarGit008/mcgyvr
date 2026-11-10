"""A rider seals every request to a rung whose host names a key.

``mcgyvr rig rungs sync`` keeps the ``seal`` key the hub lists with a rung (the
host's agent advertises it) in ``relief.yaml``; every request to that rung is
then sealed to it (:func:`mcgyvr.runner.sealed_for`), and its answer opened as
it streams back, so the hub between carries neither the prompt nor the answer.

* **Sealed when keyed, clear when not.** A rung with a key is sent only the
  envelope's clear fields; one without (an older hub or agent) is sent as
  before.
* **The answer reads as a clear one would.** The opened stream assembles into
  the completion, under the name the hub wrote over it.
* **What does not open is no answer.** An answer altered on the way, or one the
  hub answers in clear, is a protocol error; a stale key's ``503
  seal_key_unknown`` is a full rung, passed over at no cost.
* **A sync keeps the key, and only a key of its shape.**

The hub and the host's agent are one loopback server here, holding the key.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import config, hubwire, runner, seal, whole
from mcgyvr.capacity import Capacity
from mcgyvr.config import ConfigError, parse
from mcgyvr.ladder_map import unit_map
from mcgyvr.rig import rungs
from mcgyvr.runner import (
    BackendError,
    ProtocolError,
    ReliefUnavailableError,
    Request,
    dispatch,
    sealed_for,
)
from tests.rungs import KEY, RIDE, RUNG_ID, error

PROMPT = "the rider's own secret prompt"
ANSWER = "the host's own secret answer"
SERVED = "coder-7b.gguf"


def _events() -> list[bytes]:
    def chunk(**fields: Any) -> bytes:
        event = {"id": "c1", "object": "chat.completion.chunk", "model": SERVED}
        return b"data: " + whole.dump(event | fields) + b"\n\n"

    return [
        chunk(
            choices=[{"index": 0, "delta": {"role": "assistant", "content": ANSWER}}]
        ),
        chunk(choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
        chunk(choices=[], usage={"prompt_tokens": 11, "completion_tokens": 5}),
    ]


@contextlib.contextmanager
def hosting(
    key: seal.HostKey, seen: list[bytes], mode: str = "sealed"
) -> Iterator[str]:
    """A loopback hub and host: opens what it is sent, answers it sealed.

    ``mode`` ``tampered`` flips a byte of one sealed event, ``clear`` answers
    in clear, ``stale`` refuses as a hub does a key no unit holds."""

    class _Hub(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append(body)
            if mode == "stale":
                status, refusal = error(503, "seal_key_unknown")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(refusal)))
                self.end_headers()
                self.wfile.write(refusal)
                return
            asked = json.loads(body)
            stream = b"".join(_events())
            if mode != "clear" and "sealed" in asked:
                _, sealer = key.open(asked["sealed"])
                stream = sealer.feed(stream) + sealer.end()
            if mode == "tampered":
                stream = stream.replace(b'"ct":"', b'"ct":"AAAA', 1)
            stream += b"data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(stream)))
            self.end_headers()
            self.wfile.write(stream)

        def log_message(self, *_: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Hub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def setup(address: str, key: seal.SealKey | None) -> str:
    sealed = "" if key is None else f"    seal: {json.dumps(key.wire())}\n"
    return (
        f"units:\n  local_fast:\n    address: {address}\n    model: qwen-3b\n"
        f"    width: 1\nladder: [local_fast]\nfanout: idle\nrelief:\n"
        f"  {RIDE}:\n    address: {address}\n    model: hitchhike@{RUNG_ID}\n"
        f"    api_key_env: HUB_KEY\n    width: 1\n    position: within\n"
        f"    served_model: {SERVED}\n"
        f"    busy_answers: {json.dumps(_busy())}\n" + sealed
    )


def _busy() -> list[dict[str, Any]]:
    return [{"status": s, "code": c} for s, c in hubwire.RUNG_BUSY]


@pytest.fixture(autouse=True)
def hub_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", KEY)


def ask(address: str, key: seal.SealKey | None, tmp_path: Path) -> Any:
    config = parse(setup(address, key))
    capacity = Capacity.of(config, root=tmp_path / "slots")
    request = Request(prompt=PROMPT, max_output_tokens=8)
    try:
        return dispatch(unit_map(config), RIDE, request, capacity=capacity)
    except Exception as exc:
        return exc


# --- sealed when keyed, clear when not; the answer reads as a clear one would --------


def test_a_keyed_rung_is_sent_only_the_envelope_and_reads_the_answer_it_holds(
    tmp_path: Path,
) -> None:
    key = seal.HostKey()
    seen: list[bytes] = []
    with hosting(key, seen) as address:
        completion = ask(address, key.unit_key, tmp_path)

    assert not isinstance(completion, Exception), completion
    assert completion.text == ANSWER
    assert completion.served_model == SERVED
    assert (completion.input_tokens, completion.output_tokens) == (11, 5)
    (sent,) = seen
    assert PROMPT.encode() not in sent
    asked = json.loads(sent)
    assert set(asked) <= hubwire.SEALED_CLEAR_FIELDS
    assert asked["model"] == f"hitchhike@{RUNG_ID}" and asked["stream"] is True
    assert asked["sealed"]["to"] == key.kid


def test_a_rung_with_no_key_is_asked_in_clear_as_before(tmp_path: Path) -> None:
    seen: list[bytes] = []
    with hosting(seal.HostKey(), seen) as address:
        completion = ask(address, None, tmp_path)

    assert not isinstance(completion, Exception), completion
    assert completion.text == ANSWER
    (sent,) = seen
    assert "sealed" not in json.loads(sent)
    assert PROMPT in json.loads(sent)["messages"][-1]["content"]


# --- what does not open is no answer ----------------------------------------------


@pytest.mark.parametrize("mode", ["tampered", "clear"])
def test_an_answer_that_does_not_open_is_a_protocol_error(
    tmp_path: Path, mode: str
) -> None:
    key = seal.HostKey()
    with hosting(key, [], mode) as address:
        outcome = ask(address, key.unit_key, tmp_path)

    assert isinstance(outcome, ProtocolError), outcome
    assert "does not open" in str(outcome)


def test_a_stale_key_is_a_full_rung_held_out_for_the_run_and_said_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The host's agent started again since the sync, so no unit holds the key
    the setup names: the rung is passed over at no cost, said once, and not
    asked again in this process, since the setup is read once."""
    key = seal.HostKey()
    seen: list[bytes] = []
    with hosting(key, seen, "stale") as address:
        outcome = ask(address, key.unit_key, tmp_path)
        again = ask(address, key.unit_key, tmp_path)

    assert isinstance(outcome, ReliefUnavailableError), outcome
    assert "seal_key_unknown" in str(outcome)
    assert isinstance(again, ReliefUnavailableError), again
    assert "held out" in str(again) and "mcgyvr rig rungs sync" in str(again)
    assert len(seen) == 1  # the second ask never left
    (note,) = [ln for ln in capsys.readouterr().err.splitlines() if "note:" in ln]
    assert "mcgyvr rig rungs sync" in note

    fresh = seal.HostKey()  # a sync writes the new key: the rung is asked again
    with hosting(fresh, seen) as address:
        assert ask(address, fresh.unit_key, tmp_path).text == ANSWER


def test_a_request_outside_the_bounds_is_refused_here_as_the_hub_would(
    tmp_path: Path,
) -> None:
    """The hub cannot check a sealed request, so the rider holds it to the
    bounds first: one outside them is the ``400 invalid_request`` the clear
    path would get, never sent, so the host's ``bad_seal`` (the backstop) cannot
    come back as a stale key and hold the rung out."""
    key = seal.HostKey()
    endpoint = unit_map(parse(setup("http://127.0.0.1:9/v1", key.unit_key))).bind(RIDE)
    asked = {"model": "m", "messages": [{"role": "user", "content": PROMPT}]}
    for outside in (
        {"temperature": 5},
        {"messages": [{"role": "evil", "content": PROMPT}]},
        {"logprobs": True, "top_logprobs": hubwire.CHAT_MAX_TOP_LOGPROBS + 1},
    ):
        with pytest.raises(BackendError) as refused:
            sealed_for(endpoint, asked | outside)
        assert (refused.value.status, refused.value.code) == hubwire.INVALID_REQUEST
        assert "outside the bounds" in str(refused.value)
    assert (RIDE, key.kid) not in runner._STALE_KEYS  # the rung is not held out
    sent, _ = sealed_for(endpoint, asked)  # in bounds: sealed as before
    assert PROMPT not in json.dumps(sent)


# --- a sync keeps the key, and only a key of its shape -------------------------------


def _listing(**more: Any) -> dict[str, Any]:
    rung = {
        "id": RUNG_ID,
        "host": "host",
        "address": "https://hub.example.org/v1",
        "model": f"hitchhike@{RUNG_ID}",
        "served_model": SERVED,
        "width": 1,
        "position": "within",
        "relief": True,
        **more,
    }
    return {"ride": True, "privacy": "p", "refresh_s": 60, "rungs": [rung]}


def test_a_sync_keeps_the_key_the_hub_lists_and_the_setup_loads_it() -> None:
    key = seal.HostKey().unit_key
    rides = rungs.read(_listing(seal=key.wire()), "https://hub.example.org")
    (ride,) = rides.rungs
    assert ride.seal == key

    text = rungs.render(rides, "HUB_KEY")
    assert yaml.safe_load(text)["relief"][ride.name]["seal"] == key.wire()
    unit = parse(
        "units:\n  own:\n    address: http://127.0.0.1:9\n    model: m\n"
        "ladder: [own]\n",
        relief_text=text,
    ).relief[ride.name]
    assert unit.seal == key

    # the relief.yaml block names the key's fields, less the signature not yet made
    assert tuple(f.name for f in config.SEAL_FIELDS) == hubwire.SEAL_KEY_FIELDS[:2]

    (old,) = rungs.read(_listing(), "https://hub.example.org").rungs
    assert old.seal is None
    text = rungs.render(rungs.Rides(True, "p", 60.0, (old,)), "HUB_KEY")
    assert "seal" not in yaml.safe_load(text)["relief"][old.name]


@pytest.mark.parametrize(
    "wrong",
    [
        {"kid": "0" * 32},
        {"kid": "0" * 32, "pub": "A" * 43 + "="},
        "a key",
    ],
    ids=["no pub", "not its id", "not an object"],
)
def test_a_listing_whose_key_is_not_of_its_shape_is_refused_whole(wrong: Any) -> None:
    with pytest.raises(rungs.HubAnswerError, match="seal"):
        rungs.read(_listing(seal=wrong), "https://hub.example.org")


def test_a_relief_yaml_whose_key_is_not_its_ids_does_not_load() -> None:
    key, other = seal.HostKey().unit_key, seal.HostKey().unit_key
    bad = setup("http://127.0.0.1:9/v1", None) + (
        f"    seal: {json.dumps({'kid': key.kid, 'pub': other.pub})}\n"
    )
    with pytest.raises(ConfigError, match="not the id of this key"):
        parse(bad)
