"""A typed decision is streamed from its unit like every other dispatch.

A decision asks a unit for one token and its ``top_logprobs``. It goes down
the same wire as a generation (:func:`mcgyvr.runner._post_json`), and since
every dispatch now asks its unit for a stream behind the scenes so a hang-up
reaches the unit at its next write, a decision does too, the same way: the
body asks for the stream and its counts (:func:`mcgyvr.whole.asking`), the
whole answer is assembled from it, and the decision reads its probabilities
from the assembled answer exactly as it read them from the unit's answer not
streamed (the token's ``logprobs.content`` entry, with its ``top_logprobs``,
is carried by the stream's one token event and assembled under the choice).
A decision runs under the thread's :class:`~mcgyvr.runner.Hangup` and the
dispatch deadline as any dispatch does. The rig agent's own warm-up request
is not a dispatch and is not touched.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from mcgyvr import decision as decision_module
from mcgyvr.decision import BoolAnswer, Noul, classify
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import Hangup, HungUpError
from tests.test_the_runner_streams_from_every_unit_and_hangs_up_when_the_asker_has_gone import (  # noqa: E501
    Unit,
    _serve,
)

TOP = [
    {"token": "Yes", "logprob": -0.1, "bytes": [89, 101, 115]},
    {"token": "No", "logprob": -2.3, "bytes": [78, 111]},
]
TOKEN = {"token": "Yes", "logprob": -0.1, "bytes": [89, 101, 115], "top_logprobs": TOP}


@pytest.fixture
def unit() -> Iterator[Unit]:
    built = Unit(pieces=["Yes"], logprobs=[TOKEN])
    built.server = _serve(built)
    yield built
    built.server.shutdown()


def _endpoint(unit: Unit) -> Endpoint:
    return Endpoint(
        source="jev",
        base_url=unit.endpoint.base_url,
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def test_a_decision_asks_its_unit_for_a_stream_and_reads_the_token_it_assembles(
    unit: Unit,
) -> None:
    decided = classify(_endpoint(unit), "m", {"file": "x"}, {"done": Noul("done?")})
    (seen,) = unit.seen
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["body"]["max_tokens"] == 1
    assert seen["body"]["logprobs"] is True
    assert seen["headers"]["accept"] == "text/event-stream"
    answer = decided.answers["done"]
    expected = decision_module.answer_for(Noul("done?"), tuple(TOP))
    assert isinstance(answer, BoolAnswer) and isinstance(expected, BoolAnswer)
    assert answer.probability_true == pytest.approx(expected.probability_true)
    assert answer.probability_true > 0.85


def test_the_probabilities_read_from_the_stream_are_those_of_the_whole_answer(
    unit: Unit,
) -> None:
    """The unit's own answer not streamed, read by the same reader, gives the
    same top_logprobs: nothing of the token's entry is lost in assembly."""
    whole = unit.whole()
    whole["choices"][0]["logprobs"] = {"content": [TOKEN]}
    from_whole = decision_module._top_logprobs(whole)
    decided = classify(_endpoint(unit), "m", {}, {"q": Noul("q?")})
    answer, expected = (
        decided.answers["q"],
        decision_module.answer_for(Noul("q?"), from_whole),
    )
    assert isinstance(answer, BoolAnswer) and isinstance(expected, BoolAnswer)
    assert answer.probability_true == pytest.approx(expected.probability_true)


def test_a_decision_runs_under_the_threads_hangup_like_every_dispatch(
    unit: Unit,
) -> None:
    hangup = Hangup()
    hangup.hang_up()
    with hangup, pytest.raises(HungUpError):
        classify(_endpoint(unit), "m", {}, {"q": Noul("q?")})
    assert unit.seen == []


def test_the_stubbed_wire_sees_the_stream_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def fake_post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append(payload)
        return {
            "choices": [{"index": 0, "message": {}, "logprobs": {"content": [TOKEN]}}]
        }

    monkeypatch.setattr(decision_module, "_post_json", fake_post)
    classify(
        Endpoint(
            source="local",
            base_url="http://localhost:8080",
            protocol=Protocol.OPENAI,
            max_parallel=1,
            credential_env=None,
        ),
        "m",
        {},
        {"q": Noul("q?")},
    )
    assert sent[0]["stream"] is True
    assert sent[0]["stream_options"] == {"include_usage": True}
    assert json.dumps(sent[0])  # a body, as the wire sends it


def test_a_decision_on_a_thread_is_the_threads_own(unit: Unit) -> None:
    """A Hangup on another thread does not reach a decision on this one."""
    other = Hangup()
    other.hang_up()
    outcome: dict[str, Any] = {}

    def run() -> None:
        with other:
            pass  # entered and left on this thread; the decision runs outside

        outcome["decided"] = classify(_endpoint(unit), "m", {}, {"q": Noul("q?")})

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=10.0)
    assert "decided" in outcome
