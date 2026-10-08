"""The public leaderboards, read: one score per model, with its board and date.

Owner, 2026-10-07 (Rounds 4 and 5): one board per use case, each at a URL an
agent can read and parse. The boards and their URLs are
:data:`mcgyvr.knowledge.record.BOARDS`; this module reads them.

* :func:`read` fetches one board and answers its rows: the name a row gives a
  model (a Hugging Face link where it gives one), the board's figure, and the
  date the board gives that row, or the day it was read when it gives none.
* :func:`scored` matches a record's model id to those rows and gives it one
  :class:`~mcgyvr.knowledge.record.Score` per board that lists it: a fact of
  that board, sourced ``board:<board>@<date>``.
* :func:`rank` orders records for a use case by its boards, in the order
  :func:`boards_for` gives them.

**Coding** is ruled apart (Round 5). SWE-bench is read only from its Verified
board's ``Mini:`` rows (bash-only: every model under the same minimal agent,
so the rows compare models and not agents), and EvalPlus ranks the models
those rows do not list. A model with a bash-only score ranks above every model
with only an EvalPlus score, whatever the two figures: they are two scales.
mcgyvr's own sample has the last word; a board only orders the candidates.

A model is found on a board by its repository's name with case, punctuation
and a parenthesised mode (``(FC)``, ``(Prompt)``) left out (:func:`key`).
Where a row lists one model more than once, its newest row counts, then its
best figure.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from mcgyvr.knowledge import online
from mcgyvr.knowledge.record import BOARD, BOARDS, Board, ModelRecord, Number, Score

#: The parts of a use case each board may rank: media-gen is an image model
#: and a voice, and the voice's recognition is what a board ranks.
PARTS: Mapping[str, tuple[str, ...]] = {
    "chat": ("chat",),
    "agent": ("agent",),
    "coding": ("coding",),
    "media-gen": ("image", "asr"),
}
#: Rows asked of the Hub's dataset viewer per page, and the most pages read:
#: its own ceiling per page, and more pages than the text board has rows.
PAGE_ROWS = 100
MAX_PAGES = 50
#: The one category of an LMArena board that ranks every model.
OVERALL = "overall"
#: The SWE-bench board that is read, and the tags of the rows that count.
SWE_VERIFIED = "Verified"
BASH_ONLY_TAG = "Mini:"
MODEL_TAG = "Model:"
#: The EvalPlus figure a score carries.
EVALPLUS_FIGURE = "humaneval+"

_HF_LINK = re.compile(r"huggingface\.co/([^/\s?#]+/[^/\s?#]+)")
_MODE = re.compile(r"\s*\([^)]*\)")
_NOT_NAME = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True)
class Row:
    """One model's figure on a board: ``label`` as the board names it, ``on``
    the date the board gives (``YYYY-MM-DD``)."""

    label: str
    value: float
    on: str


def key(name: str) -> str:
    """What a model is matched on: the repository name, lower case, with no
    punctuation and no parenthesised mode."""
    linked = _HF_LINK.search(name)
    text = linked[1] if linked else name
    text = _MODE.sub("", text).strip().rsplit("/", 1)[-1]
    return _NOT_NAME.sub("", text.lower())


def boards_for(use_case: str | None) -> tuple[Board, ...]:
    """The boards that rank ``use_case``, in the order they rank it."""
    parts = PARTS.get(use_case or "", ())
    return tuple(board for part in parts for board in BOARDS if board.ranks == part)


def _number(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip().rstrip("%"))
        except ValueError:
            return None
    return None


def _label(link: Any, name: str) -> str:
    """A Hugging Face repository the row links to, or the row's own name."""
    if isinstance(link, str):
        linked = _HF_LINK.search(link)
        if linked:
            return linked[1]
    return name


def _lmarena(board: Board, get: online.Get | None) -> list[Row]:
    rows: list[Row] = []
    for page in range(MAX_PAGES):
        url = f"{board.url}&offset={page * PAGE_ROWS}&length={PAGE_ROWS}"
        answer = online.get_json(get, url)
        listed = answer.get("rows") if isinstance(answer, dict) else None
        if not isinstance(listed, list):
            raise online.OnlineError(f"{board.id}: {url} answered no rows")
        if not listed:
            return rows
        for item in listed:
            row = item.get("row") if isinstance(item, dict) else None
            if not isinstance(row, dict):
                continue
            if row.get("category") != OVERALL:
                return rows
            value = _number(row.get("rating"))
            name = row.get("model_name")
            on = row.get("leaderboard_publish_date")
            if value is not None and isinstance(name, str) and isinstance(on, str):
                rows.append(Row(name, value, on))
    return rows


def _csv(board: Board, get: online.Get | None) -> list[dict[str, str]]:
    text = online.get_text(get, board.url)
    return list(csv.DictReader(io.StringIO(text)))


def _bfcl(board: Board, get: online.Get | None, today: str) -> list[Row]:
    rows: list[Row] = []
    for row in _csv(board, get):
        value = _number(row.get("Overall Acc"))
        name = row.get("Model") or ""
        if value is not None and name:
            rows.append(Row(_label(row.get("Model Link"), name), value, today))
    return rows


def _open_asr(board: Board, get: online.Get | None, today: str) -> list[Row]:
    rows: list[Row] = []
    for row in _csv(board, get):
        value = _number(row.get("avg"))
        name = row.get("model") or ""
        if value is not None and name:
            rows.append(Row(name, value, today))
    return rows


def _swe_bash_only(board: Board, get: online.Get | None) -> list[Row]:
    answer = online.get_json(get, board.url)
    listed = answer.get("leaderboards") if isinstance(answer, dict) else None
    if not isinstance(listed, list):
        raise online.OnlineError(f"{board.id}: {board.url} answered no leaderboards")
    rows: list[Row] = []
    for leaderboard in listed:
        if not isinstance(leaderboard, dict) or leaderboard.get("name") != SWE_VERIFIED:
            continue
        for result in leaderboard.get("results") or ():
            tags = [t for t in result.get("tags") or () if isinstance(t, str)]
            if not any(t.startswith(BASH_ONLY_TAG) for t in tags):
                continue
            model = next(
                (
                    t.removeprefix(MODEL_TAG).strip()
                    for t in tags
                    if t.startswith(MODEL_TAG)
                ),
                "",
            )
            value = _number(result.get("resolved"))
            on = result.get("date")
            if model and value is not None and isinstance(on, str):
                rows.append(Row(_label(model, model), value, on))
    return rows


def _evalplus(board: Board, get: online.Get | None, today: str) -> list[Row]:
    answer = online.get_json(get, board.url)
    if not isinstance(answer, dict):
        raise online.OnlineError(f"{board.id}: {board.url} answered no results object")
    rows: list[Row] = []
    for name, entry in answer.items():
        if not isinstance(entry, dict):
            continue
        figures = entry.get("pass@1")
        value = (
            _number(figures.get(EVALPLUS_FIGURE)) if isinstance(figures, dict) else None
        )
        if value is not None:
            rows.append(Row(_label(entry.get("link"), name), value, today))
    return rows


def read(
    board: Board, *, get: online.Get | None = None, today: date
) -> tuple[Row, ...]:
    """``board``'s rows, read now. A board that does not answer, or answers
    what it does not publish, raises :class:`mcgyvr.knowledge.online.OnlineError`
    naming it."""
    day = today.isoformat()
    try:
        if board.id in ("lmarena-text", "lmarena-text-to-image"):
            rows = _lmarena(board, get)
        elif board.id == "bfcl":
            rows = _bfcl(board, get, day)
        elif board.id == "swe-bench-verified-bash-only":
            rows = _swe_bash_only(board, get)
        elif board.id == "evalplus":
            rows = _evalplus(board, get, day)
        elif board.id == "open-asr":
            rows = _open_asr(board, get, day)
        else:
            raise online.OnlineError(f"{board.id}: no reader for this board")
    except online.NoNetworkError:
        raise
    except online.OnlineError as exc:
        message = str(exc)
        raise online.OnlineError(
            message if message.startswith(board.id) else f"{board.id}: {message}"
        ) from exc
    return tuple(rows)


def best(board: Board, rows: Sequence[Row]) -> Row | None:
    """Of one model's rows, the one that counts: the newest, then the best."""
    if not rows:
        return None
    sign = 1 if board.better == "higher" else -1
    return max(rows, key=lambda row: (row.on, sign * row.value))


def scored(
    one: ModelRecord, read: Mapping[str, Sequence[Row]], *, today: date
) -> ModelRecord:
    """``one`` with a score from each board of ``read`` that lists it.

    A board ``read`` holds replaces what ``one`` said of it; the scores of
    boards it does not hold are kept.
    """
    boards = {board.id: board for board in BOARDS}
    wanted = key(one.model_id)
    fresh: list[Score] = []
    for board_id, rows in read.items():
        board = boards[board_id]
        row = best(board, [r for r in rows if key(r.label) == wanted])
        if row is None:
            continue
        fresh.append(
            Score(
                board=board.id,
                metric=board.metric,
                value=Number(row.value, "fact", f"{BOARD}:{board.id}@{row.on}", today),
            )
        )
    kept = tuple(score for score in one.scores if score.board not in read)
    return replace(one, scores=(*kept, *fresh))


def rank(use_case: str | None, records: Sequence[ModelRecord]) -> list[ModelRecord]:
    """``records`` best first for ``use_case``.

    By the first of :func:`boards_for` that scores a record, then that
    board's figure, then the smaller file; a record no board of the use case
    scores comes last.
    """
    order = boards_for(use_case)

    def place(one: ModelRecord) -> tuple[int, float, int, str]:
        for tier, board in enumerate(order):
            score = next((s for s in one.scores if s.board == board.id), None)
            if score is not None:
                sign = -1 if board.better == "higher" else 1
                return (
                    tier,
                    sign * float(score.value.value),
                    one.total_bytes,
                    one.model_id,
                )
        return (len(order), 0.0, one.total_bytes, one.model_id)

    return sorted(records, key=place)
