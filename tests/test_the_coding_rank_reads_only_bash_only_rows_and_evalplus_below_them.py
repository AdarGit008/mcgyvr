"""The coding rank reads only bash-only rows, and EvalPlus below them.

Owner, 2026-10-07 (Round 5): the coding board is "SWE-bench Verified
bash-only (`Mini:` rows) from raw.githubusercontent.com/SWE-bench/
swe-bench.github.io/master/data/leaderboards.json, plus EvalPlus for smaller
models; mcgyvr's own sample result is the final word." Plan section 4.4: the
bash-only rows run every model under the same minimal agent, so they compare
models rather than agents; sizes the bash-only rows do not list are ranked by
EvalPlus.

Promises:

* Of the SWE-bench file, only the Verified board's rows tagged ``Mini:`` are
  read. An agent's row on Verified, and every row on Lite, scores nothing,
  however high.
* A model with several bash-only rows is scored by its newest.
* A model on both boards ranks by its bash-only score. A model only EvalPlus
  lists ranks below every model with a bash-only score, whatever the two
  figures. A model on neither ranks last.
* Each score says its board, that board's metric, the board and date it was
  read from, and the day.

The answers are the ones recorded on 2026-10-07; the records are invented
around the model ids those answers name.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from mcgyvr.knowledge import boards
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks
from tests.knowledge_online import Recorded

DAY = date(2026, 10, 7)
SWE = "swe-bench-verified-bash-only"
EVALPLUS = "evalplus"

BIG_CODER = "Qwen/Qwen3-Coder-480B-A35B-Instruct"
MID_CODER = "Qwen/Qwen2.5-Coder-32B-Instruct"
SMALL_CODER = "deepseek-ai/deepseek-coder-6.7b-instruct"
AGENT_ONLY = "Qwen/Qwen3-Coder-30B-A3B-Instruct"


def _board(board_id: str) -> kr.Board:
    return next(b for b in kr.BOARDS if b.id == board_id)


def _rows(board_id: str) -> tuple[boards.Row, ...]:
    return boards.read(_board(board_id), get=Recorded(), today=DAY)


def _scored(model_id: str, size: int) -> kr.ModelRecord:
    """An invented record of ``model_id``, scored from the recorded boards."""
    shipped = ks.shipped()[0]
    one = dataclasses.replace(
        shipped,
        model_id=model_id,
        size_bytes=dataclasses.replace(shipped.size_bytes, value=size),
        scores=(),
    )
    read = {b.id: _rows(b.id) for b in boards.boards_for("coding")}
    return boards.scored(one, read, today=DAY)


def test_only_the_verified_boards_bash_only_rows_are_read() -> None:
    rows = _rows(SWE)
    assert {row.label for row in rows} == {
        "claude-4-5-opus",
        "gpt-5-mini-2025-08-07",
        "Qwen3-Coder-480B-A35B-Instruct",
        "Qwen2.5-Coder-32B-Instruct",
    }
    assert len(rows) == 5, "GPT 5 mini has two bash-only rows"


def test_an_agents_row_scores_nothing_and_the_bash_only_row_does() -> None:
    mid = _scored(MID_CODER, 20)
    (swe,) = [s for s in mid.scores if s.board == SWE]
    # Its agent rows on Verified say 47.0 and 38.0; its bash-only row 9.0.
    assert swe.value == kr.Number(9.0, "fact", f"board:{SWE}@2025-08-03", DAY)
    assert swe.metric == _board(SWE).metric
    agent_only = _scored(AGENT_ONLY, 20)
    assert [s.board for s in agent_only.scores if s.board == SWE] == []


def test_a_model_with_several_bash_only_rows_is_scored_by_its_newest() -> None:
    row = boards.best(
        _board(SWE), [r for r in _rows(SWE) if r.label == "gpt-5-mini-2025-08-07"]
    )
    assert row is not None
    assert (row.value, row.on) == (56.2, "2026-02-17")


def test_bash_only_ranks_first_then_evalplus_then_nothing() -> None:
    big = _scored(BIG_CODER, 300)
    mid = _scored(MID_CODER, 20)
    small = _scored(SMALL_CODER, 4)
    unranked = _scored(AGENT_ONLY, 18)
    # The small model's EvalPlus 71.3 is above the mid model's bash-only 9.0,
    # and still ranks below it: the two boards are not one scale.
    (small_score,) = small.scores
    assert (small_score.board, small_score.value.value) == (EVALPLUS, 71.3)
    assert [s.board for s in mid.scores] == [SWE, EVALPLUS]

    ranked = boards.rank("coding", [unranked, small, mid, big])
    assert [one.model_id for one in ranked] == [
        BIG_CODER,
        MID_CODER,
        SMALL_CODER,
        AGENT_ONLY,
    ]
