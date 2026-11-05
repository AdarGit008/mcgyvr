"""A sealed ride opens only with its unit's key, and its answer only in order.

The rider seals a chat request to the key a host's unit advertises
(:func:`mcgyvr.seal.seal_request`); the hub carries the envelope, and only the
agent holding that key opens it (:meth:`mcgyvr.seal.HostKey.open`). The agent
seals the answer event by event (:class:`mcgyvr.seal.AnswerSealer`) and the
rider opens it (:class:`mcgyvr.seal.AnswerOpener`):

* **In clear only what the hub routes and charges by.** The envelope carries
  the model, ``stream`` and ``stream_options``; each answer event its model and
  token counts. The prompt and the answer's text are never in clear.
* **One key opens it.** Another unit's key, a flipped byte of the request or of
  an event, an event moved, dropped or replayed, and a clear event slipped into
  a sealed answer are each refused.
* **The hub's own words still pass.** A clear error (a refusal, a stream cut)
  passes, and the model name the hub writes over the answer is the one read.
* **The unit is passed what the hub would pass.** The opened request is held
  to the hub's forwarded fields and its cap on ``max_tokens``.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from mcgyvr import hubwire, seal, whole

PROMPT = "the rider's sealed secret words"
ANSWERED = "the host's sealed answer"
RIDE = "hitchhike@" + "a" * 32


def _request(**more: Any) -> dict[str, Any]:
    return whole.asking(
        {"model": RIDE, "messages": [{"role": "user", "content": PROMPT}], **more}
    )


def _events() -> list[bytes]:
    def chunk(**fields: Any) -> bytes:
        return b"data: " + whole.dump({"id": "c1", "model": "host.gguf", **fields})

    return [
        chunk(choices=[{"index": 0, "delta": {"content": ANSWERED}}]),
        chunk(choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
        chunk(choices=[], usage={"prompt_tokens": 9, "completion_tokens": 4}),
        b"data: [DONE]",
    ]


def _stream(sealer: seal.AnswerSealer, events: list[bytes]) -> bytes:
    raw = b"".join(event + b"\n\n" for event in events)
    # fed in odd pieces, as a socket hands them over
    return b"".join(sealer.feed(raw[i : i + 7]) for i in range(0, len(raw), 7)) + (
        sealer.end()
    )


def _pair() -> tuple[seal.HostKey, dict[str, Any], seal.AnswerOpener]:
    host = seal.HostKey()
    sealed, opener = seal.seal_request(_request(), host.unit_key)
    return host, sealed, opener


# --- in clear only what the hub routes and charges by ------------------------------


def test_the_envelope_carries_the_prompt_only_sealed_and_names_the_key_it_is_for() -> (
    None
):
    host, sealed, _ = _pair()

    assert set(sealed) == {"model", "stream", "stream_options", "sealed"}
    assert set(sealed) <= hubwire.SEALED_CLEAR_FIELDS
    assert sealed["model"] == RIDE and sealed["stream"] is True
    envelope = sealed["sealed"]
    assert envelope["v"] == hubwire.SEAL_VERSION
    assert envelope["to"] == host.kid
    assert PROMPT not in json.dumps(sealed)
    assert hubwire.SEAL_PUBLIC_KEY.fullmatch(envelope["epk"])
    assert hubwire.SEAL_NONCE.fullmatch(envelope["nonce"])
    assert hubwire.SEAL_CIPHERTEXT.fullmatch(envelope["ct"])

    assert set(envelope) == set(hubwire.SEAL_ENVELOPE_FIELDS)
    body, _ = host.open(envelope)
    assert json.loads(body) == _request()


def test_a_unit_key_is_its_public_halfs_id_and_its_shape_is_the_wires() -> None:
    key = seal.HostKey().unit_key
    assert hubwire.SEAL_KEY_ID.fullmatch(key.kid)
    assert hubwire.SEAL_PUBLIC_KEY.fullmatch(key.pub)
    assert seal.SealKey.of(key.wire()) == key
    assert tuple(key.wire()) == hubwire.SEAL_KEY_FIELDS[:2]  # sig: not yet made
    assert seal.SealKey.of(key.wire() | {"sig": "A" * 86 + "=="}) == key
    other = seal.HostKey().unit_key
    with pytest.raises(ValueError, match="not the id of this key"):
        seal.SealKey(kid=key.kid, pub=other.pub)
    for wrong in ({"kid": key.kid}, {**key.wire(), "extra": 1}, "key", None):
        with pytest.raises(ValueError):
            seal.SealKey.of(wrong)


def test_every_answer_event_is_sealed_with_its_model_and_counts_in_clear() -> None:
    host, sealed, opener = _pair()
    _, sealer = host.open(sealed["sealed"])

    stream = _stream(sealer, _events())

    assert ANSWERED.encode() not in stream
    events = [e for e in stream.split(b"\n\n") if e]
    assert events[-1] == b"data: [DONE]"
    clear = [json.loads(e[len(b"data: ") :]) for e in events[:-1]]
    assert all(set(c) <= {"model", "usage", "sealed"} for c in clear)
    fields = set(hubwire.SEALED_ANSWER_ENVELOPE_FIELDS)
    assert all(set(c["sealed"]) == fields for c in clear)
    assert all(c["model"] == "host.gguf" for c in clear)
    assert clear[-1]["usage"] == {"prompt_tokens": 9, "completion_tokens": 4}

    assert opener.feed(stream) + opener.end() == b"".join(
        whole.dump(json.loads(e[6:])).join([b"data: ", b"\n\n"]) for e in _events()[:3]
    ) + (b"data: [DONE]\n\n")


def test_a_whole_answer_is_sealed_as_one_body_and_opens_as_it_was() -> None:
    host, sealed, opener = _pair()
    _, sealer = host.open(sealed["sealed"])
    answer = whole.dump(
        {
            "model": "host.gguf",
            "choices": [{"index": 0, "message": {"content": ANSWERED}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 4},
        }
    )

    body = sealer.body(answer)

    assert ANSWERED.encode() not in body
    document = json.loads(body)
    assert set(document) == {"model", "usage", "sealed"}
    assert opener.body(body) == answer


# --- one key opens it ---------------------------------------------------------------


def test_another_units_key_does_not_open_the_ride() -> None:
    _, sealed, _ = _pair()
    stranger = seal.HostKey()
    with pytest.raises(seal.SealError, match="another key"):
        stranger.open(sealed["sealed"])
    # nor when the envelope is readdressed to it: the agreed keys differ
    with pytest.raises(seal.SealError, match="does not open"):
        stranger.open(sealed["sealed"] | {"to": stranger.kid})


def _flip(text: str, at: int = 5) -> str:
    raw = bytearray(base64.b64decode(text))
    raw[at] ^= 1
    return base64.b64encode(bytes(raw)).decode()


@pytest.mark.parametrize("field", ["ct", "nonce", "epk"])
def test_a_request_altered_on_the_way_does_not_open(field: str) -> None:
    host, sealed, _ = _pair()
    envelope = dict(sealed["sealed"])
    envelope[field] = _flip(envelope[field])
    with pytest.raises(seal.SealError):
        host.open(envelope)


@pytest.mark.parametrize(
    "change",
    [
        {"v": 2},
        {"v": True},
        {"ct": "not base64!"},
        {"epk": "A" * 44},
        {"nonce": "short"},
    ],
)
def test_an_envelope_not_of_its_shape_is_refused(change: dict[str, Any]) -> None:
    host, sealed, _ = _pair()
    with pytest.raises(seal.SealError):
        host.open(sealed["sealed"] | change)
    with pytest.raises(seal.SealError):
        host.open({k: v for k, v in sealed["sealed"].items() if k != "nonce"})


def _sealed_events() -> tuple[list[bytes], seal.AnswerOpener]:
    host, sealed, opener = _pair()
    _, sealer = host.open(sealed["sealed"])
    stream = _stream(sealer, _events())
    return [e + b"\n\n" for e in stream.split(b"\n\n") if e], opener


def test_an_answer_event_altered_on_the_way_does_not_open() -> None:
    events, opener = _sealed_events()
    first = json.loads(events[0][6:])
    first["sealed"]["ct"] = _flip(first["sealed"]["ct"])
    with pytest.raises(seal.SealError, match="does not open"):
        opener.feed(b"data: " + whole.dump(first) + b"\n\n")


@pytest.mark.parametrize(
    "order",
    [[1, 0, 2, 3], [0, 2, 3], [0, 0, 1, 2, 3]],
    ids=["moved", "dropped", "replayed"],
)
def test_an_answer_event_out_of_its_place_does_not_open(order: list[int]) -> None:
    events, opener = _sealed_events()
    with pytest.raises(seal.SealError, match="in its place"):
        opener.feed(b"".join(events[i] for i in order))


def test_a_clear_event_slipped_into_a_sealed_answer_is_refused() -> None:
    events, opener = _sealed_events()
    forged = b'data: {"choices":[{"index":0,"delta":{"content":"forged"}}]}\n\n'
    with pytest.raises(seal.SealError, match="a clear event"):
        opener.feed(events[0] + forged)
    with pytest.raises(seal.SealError, match="a clear answer"):
        seal.AnswerOpener(b"\0" * 32).body(b'{"choices": []}')


def test_the_same_request_sent_twice_never_seals_two_answers_alike() -> None:
    """A hub may send one sealed request twice; the two answers share a key, so
    their nonces are random, never the counter repeated."""
    host, sealed, _ = _pair()
    _, first = host.open(sealed["sealed"])
    _, second = host.open(sealed["sealed"])
    one, two = _stream(first, _events()), _stream(second, _events())
    nonces = [
        json.loads(e[6:])["sealed"]["nonce"]
        for e in (one + two).split(b"\n\n")
        if e and e != b"data: [DONE]"
    ]
    assert len(set(nonces)) == len(nonces)


# --- the hub's own words still pass ----------------------------------------------


def test_a_clear_error_from_the_hub_passes_and_its_model_name_is_read() -> None:
    events, opener = _sealed_events()
    cut = b'data: {"error":{"code":"upstream_error","message":"cut"}}\n\n'
    assert opener.feed(cut) == cut
    refusal = b'{"error":{"code":"seal_key_unknown","message":"sync"}}'
    assert seal.AnswerOpener(b"\0" * 32).body(refusal) == refusal

    events, opener = _sealed_events()
    renamed = json.loads(events[0][6:]) | {"model": "as-asked"}
    opened = opener.feed(b"data: " + whole.dump(renamed) + b"\n\n")
    assert json.loads(opened[6:])["model"] == "as-asked"
    assert json.loads(opened[6:])["choices"][0]["delta"]["content"] == ANSWERED


# --- the unit is passed what the hub would pass -----------------------------------


def test_the_opened_request_is_held_to_the_hubs_forwarded_fields_and_cap() -> None:
    asked = _request(
        max_completion_tokens=5000,
        n=1,
        chat_template_kwargs={"enable_thinking": False, "unvetted": 1},
        top_logprobs=3,
        grammar="root ::= x",
        tools=[{"type": "function"}],
    )
    body = seal.unit_body(
        whole.dump(asked), model="host.gguf", max_tokens=256, stream=True
    )
    sent = json.loads(body)
    assert sent["model"] == "host.gguf"
    assert sent["max_tokens"] == 256
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    assert "grammar" not in sent and "top_logprobs" not in sent and "n" not in sent
    assert "max_completion_tokens" not in sent
    assert sent["stream_options"] == {"include_usage": True}
    assert set(sent) <= hubwire.FORWARDED_FIELDS
    assert sent["messages"] == [{"role": "user", "content": PROMPT}]

    small = seal.unit_body(
        whole.dump(_request(max_tokens=8)), model="m", max_tokens=256, stream=False
    )
    assert json.loads(small)["max_tokens"] == 8
    assert "stream_options" not in json.loads(small)
    for wrong in (b"[]", b"not json", whole.dump({"messages": []})):
        with pytest.raises(seal.SealError):
            seal.unit_body(wrong, model="m", max_tokens=1, stream=False)
    with pytest.raises(seal.SealError, match="more than one choice"):
        seal.unit_body(whole.dump(_request(n=2)), model="m", max_tokens=1, stream=False)
