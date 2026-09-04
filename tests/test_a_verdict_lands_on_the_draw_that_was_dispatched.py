"""A verdict lands on the draw that was dispatched, not on the draw that was ranked.

``best_of`` keeps the draws that produced a candidate in ``gates``/``draws``
and the ones that produced nothing in ``unusable``, so ``chosen`` indexes the
*candidates*. The journal was keyed by the *dispatch* index — one row per
``send(draw)`` — and ``worker_attempt`` handed ``chosen`` straight to the
journal as the draw the verdict was about. With draws=2 and an unreadable
first reply, the winner is candidate 0 and dispatch 1: the row nobody could
parse was corrected ``passed`` and then ``committed``, and the row that was
actually accepted was corrected as a losing draw.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.consensus import Consensus, Unusable, best_of
from mcgyvr.contract import load
from mcgyvr.gate import GateResult
from mcgyvr.telemetry import fold
from tests import livejournal as lj

#: No fence, no JSON: `parse_reply` refuses it and the draw is `Unusable`.
UNREADABLE_REPLY = "I would rather not."


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    return tmp_path / "home"


def test_a_consensus_names_the_dispatch_index_of_its_winner(tmp_path: Path) -> None:
    repo = lj.make_repo(tmp_path / "repo")
    contract = load(lj.make_contract(tmp_path / "impl.yaml"))

    def sample(index: int) -> str | Unusable:
        return Unusable("no fence") if index == 0 else "VALUE = 1\n"

    picked = best_of(
        contract=contract,
        sample=sample,
        gate=lambda space: GateResult(),
        n=2,
        repo=repo,
    )

    assert picked.chosen == 0, "the winner is the only candidate"
    assert picked.dispatched == 1, "and it was the second dispatch"
    assert len(picked) == 2


def test_a_consensus_with_no_refusals_dispatched_what_it_chose() -> None:
    from tests.test_fix_outcomes_and_argv import _bound

    picked = Consensus(
        draws=(_bound("x = 1\n", accepted=False), _bound("y = 1\n", accepted=True)),
        chosen=1,
        gates=(GateResult(findings=()), GateResult()),
    )
    assert picked.dispatched == 1


def test_the_journal_corrects_the_accepted_dispatch_and_not_the_unreadable_one(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lj.scripted(monkeypatch, UNREADABLE_REPLY, lj.GOOD_REPLY)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + "breadth:\n  draws: 2\n", encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 0

    rows = {r["attempt_id"]: r for r in fold(path=journal / "claude-s1.jsonl")}
    assert len(rows) == 2, sorted(rows)
    (unreadable,) = [r for k, r in rows.items() if "#" not in k]
    (winner,) = [r for k, r in rows.items() if k.endswith("#1")]
    assert winner["outcome"] == "not_committed", winner
    assert unreadable["outcome"] == "failed", unreadable
    assert "draw 1" in unreadable["detail"], unreadable["detail"]

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    (attempt,) = result["attempts"]
    assert attempt["draw"] == 1
    assert attempt["draws"] == 2
    assert attempt["attempt_id"].endswith("#1"), attempt["attempt_id"]
