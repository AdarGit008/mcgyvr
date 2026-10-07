"""Every board is read from its recorded answer, with its metric and its date.

Owner, 2026-10-07 (Rounds 4 and 5): one board per use case, each at a URL
agents can read and parse: LMArena text (chat), BFCL (agent), SWE-bench
Verified bash-only plus EvalPlus (coding), LMArena text_to_image (image) and
Open ASR (speech recognition). TTS has no public board.

Promises:

* Each board is read from the URL the knowledge layer names for it
  (:data:`mcgyvr.knowledge.record.BOARDS`), in the format it is served in, and
  a model it lists is scored with that board's metric, as a fact of that board
  on the date the board gives (or, when it gives none, the day it was read).
* LMArena is read page by page, and only its ``overall`` rows: the first row of
  another category ends the board.
* A board names a model by a Hugging Face link where it gives one, and by its
  name where it does not; either finds the model's repository, and a
  parenthesised mode (``(FC)``, ``(Prompt)``) is not part of the name.
* A board that does not answer is an error that names it.
* No board ranks TTS.

The answers are the ones recorded on 2026-10-07.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from mcgyvr.knowledge import boards, online
from mcgyvr.knowledge import record as kr
from mcgyvr.knowledge import store as ks
from tests.knowledge_online import Recorded

DAY = date(2026, 10, 7)


def _board(board_id: str) -> kr.Board:
    return next(b for b in kr.BOARDS if b.id == board_id)


def _score(board_id: str, model_id: str) -> kr.Score | None:
    board = _board(board_id)
    rows = boards.read(board, get=Recorded(), today=DAY)
    one = dataclasses.replace(ks.shipped()[0], model_id=model_id, scores=())
    scored = boards.scored(one, {board.id: rows}, today=DAY)
    return next(iter(scored.scores), None)


@pytest.mark.parametrize(
    ("board_id", "model_id", "value", "on"),
    [
        ("lmarena-text", "Qwen/Qwen3-30B-A3B-Instruct-2507", 1384.1, "2026-10-02"),
        ("bfcl", "Qwen/Qwen3-32B", 48.71, "2026-10-07"),
        (
            "swe-bench-verified-bash-only",
            "Qwen/Qwen3-Coder-480B-A35B-Instruct",
            55.4,
            "2025-08-02",
        ),
        ("evalplus", "Qwen/Qwen2.5-Coder-32B-Instruct", 87.2, "2026-10-07"),
        ("lmarena-text-to-image", "black-forest-labs/FLUX.2-dev", 1145.7, "2026-10-06"),
        ("open-asr", "nvidia/parakeet-tdt-0.6b-v2", 4.675, "2026-10-07"),
    ],
)
def test_a_listed_model_is_scored_with_the_boards_metric_and_date(
    board_id: str, model_id: str, value: float, on: str
) -> None:
    score = _score(board_id, model_id)
    assert score is not None
    assert score.board == board_id
    assert score.metric == _board(board_id).metric
    assert score.value.kind == "fact"
    assert score.value.source == f"board:{board_id}@{on}"
    assert score.value.read_at == DAY
    assert score.value.value == pytest.approx(value, abs=0.05)


def test_lmarena_is_read_page_by_page_and_only_its_overall_rows() -> None:
    server = Recorded()
    rows = boards.read(_board("lmarena-text"), get=server, today=DAY)
    assert len(server.asked) == 2, "the second page ends the overall board"
    assert all("&offset=" in url and "&length=" in url for url in server.urls())
    labels = {row.label for row in rows}
    assert "qwen3-32b" in labels and "claude-opus-5.5-high" in labels
    assert len(rows) == 6
    assert "claude-fable-5.1-max" not in labels, "listed under another category"


def test_a_mode_in_parentheses_is_not_part_of_the_name() -> None:
    assert boards.key("Qwen3-8B (FC)") == boards.key("Qwen/Qwen3-8B")
    assert boards.key("https://huggingface.co/Qwen/Qwen3-8B") == boards.key("qwen3-8b")


def test_a_board_that_does_not_answer_is_named() -> None:
    with pytest.raises(online.OnlineError, match="bfcl"):
        boards.read(_board("bfcl"), get=Recorded(bodies={}), today=DAY)


def test_no_board_ranks_tts() -> None:
    assert "tts" in kr.UNRANKED
    assert not [b for b in kr.BOARDS if b.ranks == "tts"]
    assert [b.id for b in boards.boards_for("media-gen")] == [
        "lmarena-text-to-image",
        "open-asr",
    ]
