"""A correction says how the work landed, and the reader shows it end to end.

:func:`mcgyvr.telemetry.correct` has existed since the journal was written and
nothing in the product called it, so every row read ``uncorrected`` forever —
including the rows of attempts the gate accepted and the operator committed.
A journal that cannot say whether a rung's answer was any good is a journal
that can be counted and never learned from, which is the whole reason the
text is kept beside the row.

Now ``mcgyvr run`` corrects. After the climb, every attempt row gets the
verdict the ladder gave it — ``passed``, ``failed`` — with the gate's finding
lines as the detail of a failure, so the journal answers *why* without the
gate being run again. Then the accepted attempt gets a second correction
saying how the work finally landed: ``committed`` with the commit on the
branch, or ``not_committed`` when the default left the change in the working
tree. ``fold`` is latest-wins in file order, so the folded outcome is the
landing and the raw lines keep the verdict underneath it.

And the reader is wired through: ``tools/live/index.py`` builds a table whose
``outcome`` column carries the folded word and whose ``session_file`` column
carries the transcript, and ``tools/live/review.py --outcome committed``
shows exactly the attempt that was, while ``--outcome uncorrected`` shows
none — the word on the screen is the word that selects it.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.telemetry import fold
from tests import livejournal as lj

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "tools" / "live" / "index.py"
REVIEW = REPO / "tools" / "live" / "review.py"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def _tool(tool: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tool), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=120,
    )


def test_an_accepted_uncommitted_attempt_folds_to_not_committed(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 0

    sink = journal / "claude-s1.jsonl"
    (row,) = fold(path=sink)
    assert row["outcome"] == "not_committed", row
    assert "src/pkg/messy.py" in row["detail"]
    # The raw lines keep the verdict under the landing: attempt, passed, landed.
    kinds = [
        (r["record_kind"], r.get("outcome"))
        for r in map(__import__("json").loads, sink.read_text().splitlines())
    ]
    assert kinds == [
        ("attempt", None),
        ("correction", "passed"),
        ("correction", "not_committed"),
    ], kinds


def test_a_committed_attempt_folds_to_committed_naming_the_commit(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config, "--commit")) == 0

    head = lj.git(repo, "rev-parse", "HEAD").strip()
    (row,) = fold(path=journal / "claude-s1.jsonl")
    assert row["outcome"] == "committed", row
    assert head[:12] in row["detail"], (head, row["detail"])


def test_a_rejected_attempt_folds_to_failed_with_the_findings_as_detail(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.BAD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    (row,) = fold(path=journal / "claude-s1.jsonl")
    assert row["outcome"] == "failed", row
    assert "acceptance" in row["detail"], row["detail"]


def test_the_index_and_the_review_show_the_landing_end_to_end(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")
    assert lj.main(lj.run_args(contract, repo, config, "--commit")) == 0
    transcript = home / ".claude" / "projects" / "-home-someone-somewhere" / "s1.jsonl"

    built = _tool(INDEX, str(journal))
    assert built.returncode == 0, built.stderr
    db = sqlite3.connect(journal / "index.sqlite")
    try:
        rows = db.execute(
            'SELECT outcome, session_file, task_type, latency_s FROM "attempts"'
        ).fetchall()
    finally:
        db.close()
    assert rows == [("committed", str(transcript), "function_implementation", 0.0)], (
        rows
    )

    shown = _tool(REVIEW, str(journal), "--outcome", "committed")
    assert shown.returncode == 0, shown.stderr
    assert "outcome=committed" in shown.stdout, shown.stdout
    assert f"session={transcript}" in shown.stdout, shown.stdout
    assert "1 of 1 attempts shown" in shown.stderr, shown.stderr

    none = _tool(REVIEW, str(journal), "--outcome", "uncorrected")
    assert none.returncode == 0, none.stderr
    assert "0 of 1 attempts shown" in none.stderr, none.stderr
    assert "===" not in none.stdout


def test_two_runs_of_one_contract_are_two_rows_with_their_own_landings(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session re-runs a contract exactly when the last run failed.

    Keyed without the run, the second run's row would share the first's id
    and ``fold`` would bind both corrections to the latest row, erasing the
    failure from the folded view — the one fact the feedback loop needs.
    """
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    lj.scripted(monkeypatch, lj.BAD_REPLY)
    assert lj.main(lj.run_args(contract, repo, config)) == 1
    lj.scripted(monkeypatch, lj.GOOD_REPLY)
    assert lj.main(lj.run_args(contract, repo, config)) == 0

    first, second = fold(path=journal / "claude-s1.jsonl")
    assert first["attempt_id"] != second["attempt_id"]
    assert first["outcome"] == "failed", first
    assert second["outcome"] == "not_committed", second


def test_an_attempt_that_raised_is_corrected_as_an_error_and_listed(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A dead socket is the common live failure; its row must not stay uncorrected."""
    import json

    import mcgyvr.drive as drive
    from mcgyvr.runner import RunnerError

    def dead(*_: object, **__: object) -> object:
        raise RunnerError("connection refused")

    monkeypatch.setattr(drive, "dispatch", dead)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    code = lj.main(lj.run_args(contract, repo, config))

    assert code == 1
    (row,) = fold(path=journal / "claude-s1.jsonl")
    assert row["ok"] is False
    assert row["outcome"] == "error", row
    assert "connection refused" in row["detail"]
    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "error"
    (attempt,) = result["attempts"]
    assert attempt["verdict"] == "error"
    assert attempt["attempt_id"] == row["attempt_id"]


def test_with_two_draws_the_verdict_lands_on_the_draw_it_is_about(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row per draw: the winner gets the verdict, the loser is failed."""
    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + "breadth:\n  draws: 2\n", encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 0

    rows = {r["attempt_id"]: r for r in fold(path=journal / "claude-s1.jsonl")}
    assert len(rows) == 2, sorted(rows)
    (loser,) = [r for k, r in rows.items() if "#" not in k]
    (winner,) = [r for k, r in rows.items() if k.endswith("#1")]
    assert loser["outcome"] == "failed", loser
    assert winner["outcome"] == "not_committed", winner
