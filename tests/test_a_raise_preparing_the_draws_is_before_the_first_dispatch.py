"""A raise preparing the draws is a raise before the first dispatch.

This file used to pin the window *between* two draws: ``drive._as_sent`` ran
per draw, after ``pool.bind`` and before ``observe``, so a raise there on
draw 1 left draw 0's row standing and ``rows: 1, draw: null`` had to be told
as "after draw 0 answered" rather than "after its draws".

That window is gone, and deliberately. The draws of one attempt are
dispatched together, so what every draw shares — the endpoint that serves it
and the prompt as the runner sends it — is read once, before any draw goes
out. A raise there is now what it is: before the first dispatch, no row
written, nothing to correct and nothing to name. The "after draw ``rows - 1``
answered" sentence still stands for the raises that come after the draws (a
gate, a cleanup, a verifier), and is pinned where those happen.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj
from tests._helpers import _orphans, _rows

TWO_DRAWS = "breadth:\n  draws: 2\n"


def test_a_prompt_that_cannot_be_read_back_stops_the_attempt_before_any_draw(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The prompt is rendered once for both draws, and neither was dispatched."""
    import mcgyvr.drive as drive

    sent = lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)
    built = 0

    def dies_preparing_the_draws(prompt: Any) -> Any:
        nonlocal built
        built += 1
        raise RuntimeError("the prompt could not be read back")

    monkeypatch.setattr(drive, "_as_sent", dies_preparing_the_draws)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    lj.append_policy(config, TWO_DRAWS)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert (built, len(sent)) == (1, 0), (
        "the prompt is read once for the attempt, and no draw went out after it raised"
    )

    assert _rows(journal) == [], "no dispatch was made, so no row was written"
    assert _orphans(journal) == [], "and nothing was corrected for a row nobody wrote"

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert landed["attempt_id"] is None, "there is no dispatch for the result to name"
    assert (landed["draw"], landed["draws"], landed["rows"]) == (None, 2, 0), (
        "the breadth it asked for is stated; the rows it wrote are none"
    )
