"""A rule in ``okf/must-read/touching-rigs.md`` that became a gate says which one.

Three of that file's rules are now code checks the door runs
(``src/mcgyvr/serving/gate-scripts/``, ``run.py``'s SEQUENCE): prove
reachability is gate 2 (the live rig
compared with its declaration); ``img=`` on every srv1 row is gate 3 (a tag
resolved once to a digest, which is what the driver receives); kill what you
started is gate 7 (the trap that finds the run's containers gone and the rig
unchanged). A rule that is enforced by code and still reads as advice sends
the reader to do by hand what the door already refuses — or, worse, to do it
around the door. No new prose file: the pointer goes beside the rule, as
``→ gate N``, the way the file already points at evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DOC = Path(__file__).resolve().parent.parent / "okf" / "must-read" / "touching-rigs.md"

#: (a phrase that identifies the rule's paragraph, the pointer owed beside it)
RULES = (
    ("Prove reachability", "→ gate 2"),
    ("Record `img=`", "→ gate 3"),
    ("Kill what you started", "→ gate 7"),
)


@pytest.mark.parametrize(("rule", "gate"), RULES)
def test_the_rule_points_at_its_gate(rule: str, gate: str) -> None:
    paragraphs = DOC.read_text(encoding="utf-8").split("\n\n")
    holding = [p for p in paragraphs if rule in p]
    assert len(holding) == 1, (
        f"{rule!r} identifies {len(holding)} paragraph(s) of {DOC.name}, not one"
    )
    assert gate in holding[0], (
        f"the rule {rule!r} is now a code check and its paragraph does not say "
        f"{gate!r}:\n{holding[0]}"
    )
