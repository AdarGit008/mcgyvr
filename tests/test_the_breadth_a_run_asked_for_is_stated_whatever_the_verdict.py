"""``draws`` is the breadth the attempt was configured for, on every entry.

The field meant two different quantities depending on the verdict a reader had
to check first. A judged entry carried ``breadth.draws``; a raised entry
carried how many rows the attempt had written. So a run configured for two
draws that raised after one reported ``draws: 1`` and was indistinguishable, in
the result file, from a run configured for one — and the field a reader would
use to say "breadth was spent here" quietly under-reported every raise.

Two quantities need two fields. ``draws`` is what was asked for and never
changes meaning; ``rows`` is how many draws left a journal row, which is what a
caller correcting the journal iterates and what an operator reads as "how far
the attempt actually got". Their difference is the interesting number and it
was not expressible at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.escalate import DispatchRaisedError, Judgement, Outcome, escalate
from mcgyvr.route import Try
from mcgyvr.runner import RunnerError
from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold
from tests import livejournal as lj
from tests.test_escalate import KEYLESS, contract, halted, mapped

TWO_DRAWS = "breadth:\n  draws: 2\n"


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


def _entry(cause: BaseException) -> Any:
    """The one history entry of a climb whose only attempt raised ``cause``."""

    def attempt(this: Try) -> Judgement:
        raise cause

    config, pool = mapped(KEYLESS)
    result = halted(escalate(config, pool, contract(), attempt))
    assert result.outcome is Outcome.ERROR
    (entry,) = result.history
    return entry


def test_the_entry_keeps_the_breadth_and_the_rows_apart() -> None:
    """Three asked for, one row written: the entry says both numbers."""
    entry = _entry(
        DispatchRaisedError(RunnerError("connection refused"), draws=3, rows=1, draw=0)
    )

    assert (entry.draw, entry.draws, entry.rows) == (0, 3, 1), (
        "`draws` is the breadth asked for and `rows` is what was written; "
        "collapsing them reports a three-draw run as a one-draw run"
    )


def test_a_driver_that_says_nothing_asked_for_nothing_and_wrote_nothing() -> None:
    """No claim from the raise site is no breadth and no rows, not draw 0 of 1."""
    entry = _entry(RuntimeError("nothing was built"))

    assert (entry.draw, entry.draws, entry.rows) == (None, 0, 0)


def test_a_run_that_raised_before_dispatching_still_says_it_asked_for_two(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing was dispatched, and the breadth it would have spent is still stated."""
    import mcgyvr.drive as drive

    def no_prompt(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the prompt could not be built")

    monkeypatch.setattr(drive, "build_prompt", no_prompt)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert _rows(journal) == [] and _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert (landed["draw"], landed["draws"], landed["rows"]) == (None, 2, 0)


def test_a_judged_attempt_says_the_same_number_twice(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every draw of a judged attempt left a row, so the two numbers agree."""
    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "failed"
    assert (landed["draws"], landed["rows"]) == (2, 2)
