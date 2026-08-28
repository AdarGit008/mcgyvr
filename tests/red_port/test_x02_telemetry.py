"""X02 — a run that records nothing is a run nobody can ask a question about afterwards.

mcgyvr measures a great deal and keeps none of it. A :class:`~mcgyvr.runner.Completion`
carries host-side latency, the backend's own token counts and the cap it was issued
under; a gate run carries findings, observations and the rungs that could not say; a
judgement carries the assurance the acceptance rests on. Every one of them is discarded
when the call returns. The word "telemetry" occurs in ``src/`` only inside docstrings —
always as a promise about what a number must never become — and no attempt is written
anywhere. So nothing about a run is answerable once it exits: not what it cost, not
which rung did the work, not whether climbing the ladder was worth it. Every
before/after claim about this port is downstream of this file.

Six statements, and three of them are about not losing data:

* **Exactly one record per attempt, including the attempt that raised.** The raising
  path is the one that matters and the one that gets forgotten, because it is reached
  by an exception rather than by a return: a sink written after the call site is
  written only when the call site was reached. A test that recorded a successful
  attempt would pass against a port that silently drops every failure — which is to
  say, against a port whose numbers describe only the runs that went well. It is held
  by two attempts, one of each kind, counted in the stream on disk.
* **A record names its rung and its model.** Two attempts that differ only in which
  model answered are otherwise identical rows, and a row that cannot say which is a
  measurement of nothing.
* **An unreported token count is absent, never zero.** mcgyvr already decided this
  twice in its own words (``runner.py:42`` and ``:648``): "a zero would average into
  telemetry as a real measurement of nothing". The rule survives a port only if
  something asserts it, because ``0`` is what a dataclass default and a
  ``dict.get(..., 0)`` both produce, and both look deliberate. Held in a pair: an
  unreported count never appears as ``0``, and a *reported* count is still carried —
  a port that simply drops all token fields would pass the first half alone.

Then the two that keep the store honest over time. Corrections about how the work
finally landed arrive after the attempt was written, and the cheap way to apply one is
to rewrite the line. That trades an append-only stream — the only shape several
orchestrators can write at once, and the only shape that survives a crash mid-write —
for an in-place edit. So the correction is asserted to arrive as its own record with
the attempt's original bytes untouched, and the fold is asserted to be latest-wins.
A correction naming no attempt is an authoring error, and dropping it silently turns a
visible mistake into missing data: it is asserted to survive the fold.

Last, the v2 constraint. The queue architecture has many orchestrators writing one
stream; a record that cannot say which orchestrator produced it makes that stream
unreadable the day the second one starts. That costs nothing to hold now and a
migration to hold later.

Nothing here dispatches. The attempt is a callable that returns a completion or
raises, because what telemetry must record is not a property of how the work was done.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.pool import Protocol
from mcgyvr.runner import Completion, StopReason
from tests.red_port.conftest import required

OBSERVE = (
    "record every attempt it runs — exactly once, whether the attempt "
    "returned or raised"
)
CORRECT = (
    "append how the work finally landed without rewriting the attempt's own record"
)
FOLD = "read attempt records back with their corrections folded in, latest wins"


def _observe() -> Any:
    return required(
        OBSERVE, lambda: __import__("mcgyvr.telemetry", fromlist=["observe"]).observe
    )


def _correct() -> Any:
    return required(
        CORRECT, lambda: __import__("mcgyvr.telemetry", fromlist=["correct"]).correct
    )


def _fold() -> Any:
    return required(
        FOLD, lambda: __import__("mcgyvr.telemetry", fromlist=["fold"]).fold
    )


def _completion(**overrides: Any) -> Completion:
    """A backend's answer in mcgyvr's own currency, so the record has real material."""
    fields: dict[str, Any] = {
        "text": "def fetch(url):\n    return url\n",
        "stop_reason": StopReason.COMPLETE,
        "raw_stop_reason": "stop",
        "model": "qwen2.5-coder:7b",
        "source": "workstation",
        "protocol": Protocol.OPENAI,
        "max_output_tokens": 1024,
        "latency_s": 1.5,
        "input_tokens": 812,
        "output_tokens": 96,
    }
    return Completion(**{**fields, **overrides})


def _boom() -> Completion:
    """An attempt that ends the way a dispatch against a dead endpoint ends."""
    raise RuntimeError("the endpoint closed the connection")


def _stream(sink: Path) -> list[dict[str, Any]]:
    """Every record the sink holds, in the order it was written.

    Read record by record rather than through the reader under test: the fold is one
    of the behaviors being asserted, and a reader that folded on the way in could hide
    a record that had been overwritten instead of appended.
    """
    return [json.loads(line) for line in sink.read_text().splitlines() if line.strip()]


def _says(record: dict[str, Any], value: object) -> bool:
    """Whether a record carries ``value`` at all, under whatever key the port chose.

    Key names are the port's to pick; what a record must carry is not.
    """
    return value in record.values()


def test_every_attempt_leaves_exactly_one_record_including_the_one_that_raised(
    tmp_path: Path,
) -> None:
    """Two attempts, one of which raised, leave two records — and the failure still "
    "raises."""
    observe = _observe()
    sink = tmp_path / "attempts.jsonl"
    answer = _completion()

    got = observe(
        lambda: answer,
        path=sink,
        attempt_id="a1",
        orchestrator="orch-a",
        rung="local/qwen",
    )
    with pytest.raises(RuntimeError):
        observe(
            _boom, path=sink, attempt_id="a2", orchestrator="orch-a", rung="api/big"
        )

    assert got is answer, "telemetry swallowed or replaced what the attempt produced"
    stream = _stream(sink)
    assert len(stream) == 2, f"two attempts left {len(stream)} records: {stream}"
    assert any(_says(r, "a1") for r in stream), (
        "the attempt that returned was not recorded"
    )
    assert any(_says(r, "a2") for r in stream), (
        "the attempt that raised was not recorded"
    )


def test_a_record_says_which_rung_and_which_model_produced_it(tmp_path: Path) -> None:
    """The two facts that make one row comparable with another."""
    observe = _observe()
    sink = tmp_path / "attempts.jsonl"

    observe(
        lambda: _completion(model="qwen2.5-coder:32b"),
        path=sink,
        attempt_id="a1",
        orchestrator="orch-a",
        rung="local/big",
    )

    record = _stream(sink)[0]
    assert _says(record, "local/big"), f"the record does not name the rung: {record}"
    assert _says(record, "qwen2.5-coder:32b"), (
        f"the record does not name the model: {record}"
    )


def test_a_token_count_the_backend_did_not_report_is_absent_rather_than_zero(
    tmp_path: Path,
) -> None:
    """mcgyvr's own rule, ported: an absent count never becomes a measurement of
    nothing.

    Held in a pair. The first half alone is passed by a port that carries no token
    fields at all, which loses the counts the backends *do* report; the second half
    alone is passed by a port that defaults them to ``0``, which is the failure the
    rule exists to prevent.
    """
    observe = _observe()
    sink = tmp_path / "attempts.jsonl"

    observe(
        lambda: _completion(input_tokens=None, output_tokens=None),
        path=sink,
        attempt_id="silent",
        orchestrator="orch-a",
        rung="local/qwen",
    )
    observe(
        lambda: _completion(input_tokens=812, output_tokens=96),
        path=sink,
        attempt_id="counted",
        orchestrator="orch-a",
        rung="local/qwen",
    )

    silent, counted = _stream(sink)
    zeroed = {
        key: value for key, value in silent.items() if "token" in key and value == 0
    }
    assert not zeroed, (
        f"a count the backend never reported was written as zero: {zeroed}"
    )
    assert _says(counted, 96), f"a count the backend did report is missing: {counted}"


def test_a_correction_is_appended_and_never_rewrites_the_attempts_own_record(
    tmp_path: Path,
) -> None:
    """How the work landed is learned later — and is added, not edited in.

    The bytes already on disk are compared before and after, because an in-place
    rewrite and an append are indistinguishable from the folded view, and only one of
    them survives two orchestrators writing at once or a crash mid-write.
    """
    observe, correct, fold = _observe(), _correct(), _fold()
    sink = tmp_path / "attempts.jsonl"
    observe(
        lambda: _completion(),
        path=sink,
        attempt_id="a1",
        orchestrator="orch-a",
        rung="local/qwen",
    )
    before = sink.read_bytes()

    correct(path=sink, attempt_id="a1", outcome="merged", detail="landed after review")

    after = sink.read_bytes()
    assert after.startswith(before), (
        "the attempt's own record was rewritten, not appended to"
    )
    assert len(_stream(sink)) == 2, (
        "the correction did not arrive as a record of its own"
    )
    folded = fold(path=sink)
    assert any(_says(record, "merged") for record in folded), (
        f"the correction is on disk but does not reach a reader: {folded}"
    )


def test_folding_is_latest_wins_per_attempt_and_keeps_an_unmatched_correction(
    tmp_path: Path,
) -> None:
    """One row per attempt with the newest correction standing, and no data thrown away.

    The orphan matters: a correction naming an attempt nobody logged is an authoring
    error, and a fold that drops it turns a visible mistake into a missing record.
    """
    observe, correct, fold = _observe(), _correct(), _fold()
    sink = tmp_path / "attempts.jsonl"
    observe(
        lambda: _completion(),
        path=sink,
        attempt_id="a1",
        orchestrator="orch-a",
        rung="local/qwen",
    )
    correct(path=sink, attempt_id="a1", outcome="merged", detail="landed after review")
    correct(
        path=sink,
        attempt_id="a1",
        outcome="reverted",
        detail="backed out an hour later",
    )
    correct(
        path=sink, attempt_id="ghost-1", outcome="merged", detail="names no attempt"
    )

    folded = fold(path=sink)
    mine = [record for record in folded if _says(record, "a1")]
    assert len(mine) == 1, f"folding left {len(mine)} rows for one attempt: {mine}"
    assert _says(mine[0], "reverted"), f"the newest correction did not win: {mine[0]}"
    assert not _says(mine[0], "merged"), (
        f"the superseded correction still stands: {mine[0]}"
    )
    assert any(_says(record, "ghost-1") for record in folded), (
        f"a correction naming no attempt was dropped instead of surfaced: {folded}"
    )


def test_a_record_names_the_orchestrator_that_wrote_it(tmp_path: Path) -> None:
    """v2 constraint — one stream, many writers, and every row says which one it came
    from.

    Not a nicety. The queue architecture round-robins over orchestrators against a
    single record stream; a store that cannot attribute a row is unreadable from the
    day the second orchestrator starts, and adding the field afterwards means every
    record written before it is unattributable forever.
    """
    observe = _observe()
    sink = tmp_path / "attempts.jsonl"

    observe(
        lambda: _completion(),
        path=sink,
        attempt_id="a1",
        orchestrator="orch-a",
        rung="local/qwen",
    )
    observe(
        lambda: _completion(),
        path=sink,
        attempt_id="a2",
        orchestrator="orch-b",
        rung="local/qwen",
    )

    first, second = _stream(sink)
    assert _says(first, "orch-a"), f"the record does not name its orchestrator: {first}"
    assert _says(second, "orch-b"), (
        f"the record does not name its orchestrator: {second}"
    )
