"""An attempt that raised owns every row it wrote, not only the row that raised.

Finding 8 settled the rule for the attempt whose draws all refused: *an attempt
accounts for every row it wrote*, because a suffixed row that never learns how
it landed is indistinguishable from a run that died before it could be
corrected, and breadth's whole justification is what its extra rows say.

The first repair of finding 7 reopened that hole on the other branch. It
corrected exactly one row of a raised attempt — the one it believed had raised
— while the non-raised branch went on correcting ``range(draws)``. With three
draws and a dispatch dying on the third, ``#0`` and ``#1`` were left ``ok:
true`` with no outcome, permanently.

``error`` is the word on all three, and it is chosen rather than fallen into.
``failed`` is a gate's verdict and no gate refused these draws: draw 0 and
draw 1 were gated, but the attempt they belong to reached no verdict, and
writing ``failed`` on them would report a judgement of the attempt that never
happened — the same coinage this repo already refuses for a draw that produced
nothing. What distinguishes the row that actually raised is not a different
word but the result's ``attempt_id``, which names it and only it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold
from tests import livejournal as lj

DRAWS = 3

BREADTH = f"breadth:\n  draws: {DRAWS}\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def _records(journal: Path) -> list[dict[str, Any]]:
    return [
        record for path in sorted(journal.glob("*.jsonl")) for record in fold(path=path)
    ]


def _rows(journal: Path) -> list[dict[str, Any]]:
    return sorted(
        (r for r in _records(journal) if r.get("record_kind") == ATTEMPT_KIND),
        key=lambda record: str(record["attempt_id"]),
    )


def _orphans(journal: Path) -> list[dict[str, Any]]:
    return [r for r in _records(journal) if r.get("record_kind") == CORRECTION_KIND]


def test_the_two_draws_before_the_raise_still_learn_how_they_landed(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Three draws, the third one's dispatch dies: three rows, three outcomes."""
    import mcgyvr.drive as drive
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, RunnerError, StopReason

    answers: list[str | None] = [lj.BAD_REPLY, lj.BAD_REPLY, None]

    def dies_on_the_third_draw(
        source_map: Any, rung: str, request: Any, **_: Any
    ) -> Any:
        reply = answers.pop(0)
        if reply is None:
            raise RunnerError("connection refused")
        return Completion(
            text=reply,
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:7b",
            source="workstation",
            protocol=Protocol.OLLAMA,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", dies_on_the_third_draw)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + BREADTH, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert answers == [], "all three draws were dispatched"

    rows = _rows(journal)
    assert len(rows) == DRAWS, sorted(r["attempt_id"] for r in rows)
    uncorrected = [r["attempt_id"] for r in rows if "outcome" not in r]
    assert not uncorrected, (
        f"{len(uncorrected)} of {DRAWS} rows the attempt wrote never learned how "
        f"they landed: {uncorrected}"
    )
    assert [r["outcome"] for r in rows] == ["error"] * DRAWS, (
        "the attempt raised and reached no verdict, so no row of it is `failed`"
    )
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert (landed["draw"], landed["draws"]) == (DRAWS - 1, DRAWS)
    assert landed["attempt_id"] == rows[-1]["attempt_id"], (
        "the row that raised is the one the result names"
    )
