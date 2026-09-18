"""A gate that raises is not the fault of the dispatch it was judging.

After a draw answers comes the whole of :func:`~mcgyvr.consensus._draw`'s
per-draw work — writing the bytes, calling the gate, binding the winner,
restoring the workspace. A driver that still named the draw that had *already
answered* as "the dispatch in flight" during that work would charge a gate that
raised on draw 0 of two to draw 0: the row of a dispatch that answered normally
corrected to ``outcome: error`` as though the endpoint had died, and the result
naming it as the attempt. A raise belongs to a dispatch only when it came out
of that dispatch, and not one line further.

The draws go out together and come back before any of them is gated, so
the gate's death on draw 0 finds both rows written: both answered, both are
accounted for, and the raise belongs to no dispatch — so the result names
none.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj
from tests._helpers import _orphans, _rows

TWO_DRAWS = "breadth:\n  draws: 2\n"


def test_the_gate_dying_on_draw_zero_is_not_draw_zeros_error(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Draw 0 answered and the gate then died: the dispatch is not the culprit."""
    import mcgyvr.drive as drive

    sent = lj.scripted(monkeypatch, lj.BAD_REPLY, lj.BAD_REPLY)

    def gate_dies(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("the acceptance runner died")

    monkeypatch.setattr(drive, "gate_workspace", gate_dies)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "mcgyvr.yaml", journal_dir=journal)
    lj.append_policy(config, TWO_DRAWS)
    contract = lj.make_contract(tmp_path / "impl.yaml")

    assert lj.main(lj.run_args(contract, repo, config)) == 1
    assert len(sent) == 2, "the draws went out together, before the gate died"

    rows = _rows(journal)
    assert [r.get("ok") for r in rows] == [True, True], (
        "both dispatches answered; it is the gate that died"
    )
    assert [r.get("outcome") for r in rows] == ["error", "error"], (
        "every row of the attempt is accounted for"
    )
    assert {r["detail"] for r in rows} == {
        "the attempt raised after draw 1 answered; no verdict was reached for this draw"
    }, rows
    assert _orphans(journal) == []

    result = json.loads(lj.result_path(capsys.readouterr().out).read_text())
    landed = result["attempts"][-1]
    assert landed["verdict"] == "error"
    assert landed["draw"] is None, (
        "the dispatch answered; charging the raise to it reports a dead "
        "endpoint that nobody saw"
    )
    assert landed["attempt_id"] is None, "there is no dispatch for the result to name"
    assert (landed["draws"], landed["rows"]) == (2, 2), (
        "two draws were asked for and both of them left a row"
    )
