"""A raise that happened after the draws is on no dispatch of the attempt.

The first repair of finding 7 read the raising draw off the journal: count the
attempt's rows and take the last one, "the dispatch in flight". That sentence
is false for every raise that happens *after* ``best_of`` has returned — the
verifier dying, ``cleanup`` raising, ``_bind``'s ``ConsensusError``, a gate that
raises — and those are the raises that reach the widest part of the code. Both
draws answered, both rows say ``ok: true``, and the ``error`` was pinned on the
last of them: a dispatch that answered normally, and not even the one whose
content won.

What is true is that the attempt raised and no dispatch of it did. Every row it
wrote is corrected — the attempt reached no verdict, so no row of it may keep
``ok: true`` and no outcome — and the result names no dispatch, because there
is no dispatch to name.

All three of the raises the paragraph above names are driven here and not only
the verifier: ``judge`` is the raise that plainly happens after ``best_of``
returns, while the gate and ``_bind`` raise *inside* the draw loop, on the last
draw, after its dispatch answered and its row went down. Those two are what the
second repair got wrong — it cleared "the dispatch in flight" only on entry to
``sample`` and after ``best_of`` returned, so everything between a dispatch
answering and the next draw beginning was still charged to the dispatch that
had answered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.telemetry import ATTEMPT_KIND, CORRECTION_KIND, fold
from tests import livejournal as lj

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


def test_a_judge_that_dies_is_not_charged_to_the_last_draw(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two draws answered, ``judge`` raised: neither dispatch is the culprit."""
    import mcgyvr.drive as drive

    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)

    def judge_dies(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the verifier died after the draws")

    monkeypatch.setattr(drive, "judge", judge_dies)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    first, second = _rows(journal)
    assert second["attempt_id"] == f"{first['attempt_id']}#1", (first, second)
    assert first.get("ok") is True and second.get("ok") is True, "both answered"
    assert [r.get("outcome") for r in (first, second)] == ["error", "error"], (
        "the attempt raised, so every row it wrote says so"
    )
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert (landed["draws"], landed["rows"]) == (2, 2), (
        "both draws were dispatched and both left a row"
    )
    assert landed["draw"] is None, (
        "no dispatch raised: the raise came after the draws, and naming one "
        "pins it on a dispatch that answered"
    )
    assert landed["attempt_id"] is None, "there is no dispatch for the result to name"


def _dies_on_the_last_draw(
    monkeypatch: pytest.MonkeyPatch, module: Any, name: str
) -> None:
    """Let ``module.name`` through once, then raise: the second draw is the last."""
    real = getattr(module, name)
    calls = 0

    def dies_the_second_time(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError(f"{name} died on the last draw")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, dies_the_second_time)


@pytest.mark.parametrize("where", ["gate", "bind"])
def test_a_raise_past_the_last_dispatch_is_on_no_dispatch(
    where: str,
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The gate and ``_bind`` run after a dispatch answered, and are not its fault."""
    import mcgyvr.consensus as consensus
    import mcgyvr.drive as drive

    lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    if where == "gate":
        _dies_on_the_last_draw(monkeypatch, drive, "gate_workspace")
    else:
        _dies_on_the_last_draw(monkeypatch, consensus, "_bind")
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    config.write_text(config.read_text() + TWO_DRAWS, encoding="utf-8")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    first, second = _rows(journal)
    assert second["attempt_id"] == f"{first['attempt_id']}#1", (first, second)
    assert first.get("ok") is True and second.get("ok") is True, "both answered"
    assert [r.get("outcome") for r in (first, second)] == ["error", "error"]
    said = (
        "the attempt raised after draw 1 answered; no verdict was reached for this draw"
    )
    assert [r.get("detail") for r in (first, second)] == [said, said], (first, second)
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert (landed["draw"], landed["draws"], landed["rows"]) == (None, 2, 2)
    assert landed["attempt_id"] is None, "there is no dispatch for the result to name"
