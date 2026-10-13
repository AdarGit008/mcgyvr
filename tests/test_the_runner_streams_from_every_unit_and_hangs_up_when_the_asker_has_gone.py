"""The runner streams from every unit, and hangs up when whoever asked has gone.

A unit notices that whoever asked has gone only when it writes to them, and an
answer not streamed is written once, at its end: a dispatch left mid-answer
(a timeout, Ctrl-C, a facade client that closed its connection) had the slot
decode the rest for nobody. So the runner now asks every unit for a stream
(``stream`` and ``stream_options.include_usage`` on the body, ``Accept:
text/event-stream``) and assembles the whole answer itself with the
product-core piece (:mod:`mcgyvr.whole`), so the completion is what the unit's
answer not streamed would have given: the same text, stop reason, counts and
the unit's own ``timings``. What is held here:

* the completion assembled from the stream equals the one read from the
  unit's whole answer, field for field;
* ``timeout_s`` bounds the whole dispatch, not each token: a stream slower
  than it ends at the deadline, as a transport failure, and the unit sees the
  hang-up at once;
* a :class:`~mcgyvr.runner.Hangup` held by whoever asked ends the dispatches
  made under it at once (the unit's next write fails), the dispatch raises
  :class:`~mcgyvr.runner.HungUpError`, and a dispatch made under it afterwards
  reaches no unit; :func:`~mcgyvr.runner.hang_up_all` does the same for every
  dispatch of the process (Ctrl-C);
* a unit that answers anything but a 200 stream is read as before: an error
  status is :class:`~mcgyvr.runner.BackendError` with its body, a whole JSON
  answer is parsed as it comes, an error event mid-stream is the status it
  says, and a stream that ends without its answer is a transport failure.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from mcgyvr import runner as runner_module
from mcgyvr.runner import (
    BackendError,
    Hangup,
    HungUpError,
    ProtocolError,
    Request,
    StopReason,
    TransportError,
    hang_up_all,
    runner_for,
)
from mcgyvr.whole import MAX_EVENT_BYTES
from tests.relays import MODEL, Unit
from tests.relays import _runner_serve as _serve


@pytest.fixture
def unit() -> Iterator[Unit]:
    built = Unit()
    built.server = _serve(built)
    yield built
    built.server.shutdown()


ASK = Request(prompt="hi", max_output_tokens=300, timeout_s=5.0)


def _generate(unit: Unit, request: Request = ASK) -> Any:
    return runner_for(unit.endpoint).generate(MODEL, request)


def _in_thread(
    unit: Unit, request: Request = ASK
) -> tuple[threading.Thread, dict[str, Any]]:
    """A dispatch on a thread of its own; its outcome, once it has one."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["done"] = _generate(unit, request)
        except Exception as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


# -- the stream is asked, the whole is assembled -------------------------------


def test_every_dispatch_asks_the_unit_for_a_stream_and_its_counts(unit: Unit) -> None:
    _generate(unit)
    (seen,) = unit.seen
    assert seen["path"] == "/v1/chat/completions"
    assert seen["body"]["stream"] is True
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert seen["headers"]["accept"] == "text/event-stream"
    assert seen["headers"]["content-type"] == "application/json"
    assert unit.seen_event("answered")


def test_the_completion_is_what_the_units_whole_answer_would_have_given(
    unit: Unit,
) -> None:
    """Field for field: what the parser reads from the assembled answer is
    what it reads from the answer the unit writes a request not streamed."""
    done = _generate(unit)
    assert done.text == "Hello, world"
    assert done.stop_reason is StopReason.COMPLETE
    assert done.raw_stop_reason == "stop"
    assert done.served_model == MODEL
    assert (done.input_tokens, done.output_tokens) == (23, 7)
    assert done.decode_tok_s == pytest.approx(56.726)
    assert done.prefill_tok_s == pytest.approx(390.625)
    assert (done.draft_n, done.draft_n_accepted) == (4, 3)
    assert done.complete is True

    parsed = runner_for(unit.endpoint)._parse(unit.whole())
    assert parsed.text == done.text
    assert parsed.raw_stop_reason == done.raw_stop_reason
    assert (parsed.input_tokens, parsed.output_tokens) == (
        done.input_tokens,
        done.output_tokens,
    )
    assert parsed.decode_tok_s == done.decode_tok_s
    assert parsed.prefill_tok_s == done.prefill_tok_s


def test_a_reply_cut_by_the_cap_and_one_with_no_counts_read_as_before(
    unit: Unit,
) -> None:
    unit.finish_reason = "length"
    unit.usage = None
    unit.timings = None
    done = _generate(unit)
    assert done.stop_reason is StopReason.TRUNCATED
    assert done.truncated is True
    assert done.output_tokens is None
    assert done.decode_tok_s is None


# -- the deadline ----------------------------------------------------------------


def test_the_timeout_bounds_the_whole_dispatch_and_the_unit_sees_the_hang_up(
    unit: Unit,
) -> None:
    """Each token comes well inside the timeout; the answer does not."""
    unit.pieces = ["x"] * 200
    unit.pace_s = 0.02
    started = time.monotonic()
    with pytest.raises(TransportError, match=r"within 0\.3s"):
        _generate(unit, Request(prompt="hi", max_output_tokens=300, timeout_s=0.3))
    assert time.monotonic() - started < 2.0
    assert unit.seen_event("hung up")
    assert unit.decoded() < 60, unit.decoded()
    assert "answered" not in unit.events


# -- whoever asked has gone ------------------------------------------------------


def test_a_hangup_ends_the_dispatches_made_under_it_and_the_unit_stops_at_once(
    unit: Unit,
) -> None:
    unit.pieces = ["x"] * 400
    unit.pace_s = 0.02
    hangup = Hangup()
    outcome: dict[str, Any] = {}

    def run() -> None:
        with hangup:
            try:
                outcome["done"] = _generate(unit)
            except Exception as exc:
                outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert unit.seen_event("decoded")
    time.sleep(0.1)  # a few tokens in
    hangup.hang_up()
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert isinstance(outcome.get("error"), HungUpError)
    assert isinstance(outcome["error"], TransportError)  # the climb's one kind
    assert unit.seen_event("hung up")
    decoded = unit.decoded()
    assert decoded < 20, decoded  # a token or two past the leave, not the answer
    assert "answered" not in unit.events
    assert hangup.hung_up is True


def test_a_dispatch_made_under_a_hangup_that_was_hung_up_reaches_no_unit(
    unit: Unit,
) -> None:
    hangup = Hangup()
    hangup.hang_up()
    with hangup, pytest.raises(HungUpError):
        _generate(unit)
    assert unit.seen == []


def test_a_hangup_is_the_threads_own_and_leaves_other_dispatches_be(unit: Unit) -> None:
    """A hangup ends what was asked under it, on its thread; a dispatch on
    another thread, under no hangup, runs to its end."""
    unit.pieces = ["x"] * 20
    unit.pace_s = 0.02
    thread, outcome = _in_thread(unit)
    assert unit.seen_event("decoded")
    Hangup().hang_up()  # nothing was asked under this one
    with Hangup() as other:
        other.hang_up()
    thread.join(timeout=5.0)
    assert "done" in outcome
    assert outcome["done"].text == "x" * 20


def test_hang_up_all_ends_every_dispatch_of_the_process_at_once(
    unit: Unit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C: every dispatch in flight is hung up on, and none is made after."""
    monkeypatch.setattr(runner_module, "_every", Hangup())  # this process's, reset
    unit.pieces = ["x"] * 400
    unit.pace_s = 0.02
    first, one = _in_thread(unit)
    second, two = _in_thread(unit)
    assert unit.seen_event("decoded")
    time.sleep(0.1)
    hang_up_all()
    first.join(timeout=5.0)
    second.join(timeout=5.0)
    assert isinstance(one.get("error"), HungUpError)
    assert isinstance(two.get("error"), HungUpError)
    assert unit.seen_event("hung up", count=2)
    assert unit.decoded() < 40, unit.decoded()
    with pytest.raises(HungUpError):
        _generate(unit)
    assert len(unit.seen) == 2


# -- anything but a 200 stream is read as before -----------------------------------


def test_a_unit_that_refuses_the_request_is_a_backend_error_with_its_body(
    unit: Unit,
) -> None:
    unit.status = 400
    unit.refused = b'{"error":{"code":400,"message":"bad request","type":"invalid"}}'
    with pytest.raises(BackendError, match="HTTP 400") as caught:
        _generate(unit)
    assert caught.value.status == 400
    assert "bad request" in str(caught.value)


def test_a_unit_that_answers_a_whole_json_body_is_read_as_it_comes(unit: Unit) -> None:
    """An engine that ignores ``stream`` answers whole; the answer is parsed as
    it comes, as PR #597's relay passes it through."""
    unit.whole_json = True
    done = _generate(unit)
    assert done.text == "Hello, world"
    assert done.output_tokens == 7
    assert unit.seen_event("answered")


def test_an_error_event_mid_stream_is_the_status_it_says(unit: Unit) -> None:
    unit.error = {"code": 503, "message": "slot unavailable", "type": "unavailable"}
    with pytest.raises(BackendError, match="HTTP 503") as caught:
        _generate(unit)
    assert caught.value.status == 503
    assert "slot unavailable" in str(caught.value)


def test_a_stream_that_ends_without_its_answer_is_a_transport_failure(
    unit: Unit,
) -> None:
    unit.pieces = ["x"] * 50
    unit.cut_after = 3
    with pytest.raises(TransportError, match="ended before its answer"):
        _generate(unit)
    assert unit.seen_event("died")


def test_a_stream_that_is_no_chat_completions_is_a_protocol_error(unit: Unit) -> None:
    """One event held longer than any of a chat completion's, its end not in
    sight: a server that speaks no stream."""
    unit.pieces = ["y" * (3 * MAX_EVENT_BYTES)]
    with pytest.raises(ProtocolError, match="not a chat completion"):
        _generate(unit)
