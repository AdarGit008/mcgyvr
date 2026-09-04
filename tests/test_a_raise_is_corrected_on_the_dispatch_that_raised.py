"""A raised attempt is corrected on the dispatch that raised, or on nothing.

``escalate`` synthesises the raised attempt's history entry itself, and it
used to synthesise it with the defaults ``draw=0, draws=1`` — the shape of an
attempt that drew once. ``_report_climb`` believed them, so under
``breadth.draws > 1`` it corrected blind:

* draw 0 was drawn and gated and draw 1's dispatch died, and the ``error``
  landed on row ``#0`` — the dispatch that answered — while ``#1``, the one
  that raised, stayed uncorrected and the result named ``#0`` as the attempt;
* a raise before the first dispatch — a sandbox reset, ``pool.bind``,
  ``build_prompt`` — writes no row at all, and a correction was appended for
  one anyway. :func:`~mcgyvr.telemetry.fold` returns it as an orphan and the
  live view drops it, which is a correction that exists nowhere a reader
  looks.

Both are driven through ``mcgyvr run`` with ``drive.dispatch`` scripted,
because what is asserted is the row a real run finally leaves behind.
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
    """Every folded record of the run, whatever the writer's file was named."""
    return [
        record for path in sorted(journal.glob("*.jsonl")) for record in fold(path=path)
    ]


def _rows(journal: Path) -> list[dict[str, Any]]:
    """The attempt rows, in id order — so a draw sorts after the attempt it is of."""
    return sorted(
        (r for r in _records(journal) if r.get("record_kind") == ATTEMPT_KIND),
        key=lambda record: str(record["attempt_id"]),
    )


def _orphans(journal: Path) -> list[dict[str, Any]]:
    """The corrections `fold` could not bind: one naming a row nobody wrote."""
    return [r for r in _records(journal) if r.get("record_kind") == CORRECTION_KIND]


def _config(tmp_path: Path, journal: Path, *, extra: str = "") -> Path:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(
        lj.LADDER + extra + f"journal:\n  dir: {journal}\n", encoding="utf-8"
    )
    return path


def test_the_error_lands_on_the_draw_whose_dispatch_raised(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two draws, the second one's dispatch dies: ``#1`` is the row corrected."""
    import mcgyvr.drive as drive
    from mcgyvr.pool import Protocol
    from mcgyvr.runner import Completion, RunnerError, StopReason

    answers: list[str | None] = [lj.BAD_REPLY, None]

    def dies_on_the_second_draw(
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

    monkeypatch.setattr(drive, "dispatch", dies_on_the_second_draw)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = _config(tmp_path, journal, extra=TWO_DRAWS)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert answers == [], "both draws were dispatched"

    first, second = _rows(journal)
    assert second["attempt_id"] == f"{first['attempt_id']}#1", (first, second)
    assert second.get("outcome") == "error", "the raise is corrected onto its own row"
    # Not "no outcome": the draw that answered is still a row this attempt
    # wrote, and an attempt accounts for every row it wrote (finding 8). It
    # carries `error` too — the attempt reached no verdict, so nothing here is
    # `failed` — and what says the raise is *this* row's is `attempt_id` below.
    assert first.get("outcome") == "error", "the draw that answered is accounted for"
    assert first["detail"] == (
        "the attempt raised on draw 1; no verdict was reached for this draw"
    ), first
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "error"
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert landed["attempt_id"] == second["attempt_id"], "the result names the dispatch"
    assert (landed["draw"], landed["draws"]) == (1, 2)


def test_a_raise_before_the_first_dispatch_corrects_nothing(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing was dispatched, so there is no row and no correction to make."""
    import mcgyvr.drive as drive

    def no_prompt(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the prompt could not be built")

    monkeypatch.setattr(drive, "build_prompt", no_prompt)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = _config(tmp_path, journal)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1

    assert _rows(journal) == [], "no dispatch was made, so no row was written"
    assert _orphans(journal) == [], "a correction was appended for a row nobody wrote"

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    assert result["outcome"] == "error"
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert landed["attempt_id"] is None, "there is no row for the result to name"
