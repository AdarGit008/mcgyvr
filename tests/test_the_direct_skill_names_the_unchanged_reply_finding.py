"""/mcgyvr-direct names the finding an unchanged reply fails its draw with.

A reply that hands its target back exactly as HEAD holds it fails the draw
before the gate runs, as check `unchanged`, code `identical-to-base`; a user
who reads that finding in `attempts[].findings` looks it up in the skill's
Step 5. docgen spells the check and the code once, held here to the gate's.
"""

from __future__ import annotations

import inspect

from mcgyvr import docgen
from mcgyvr.drive import gate
from tests._paths import REPO

DIRECT_SKILL = REPO / "skills" / "mcgyvr-direct" / "SKILL.md"


def test_the_names_are_the_gates() -> None:
    assert docgen.UNCHANGED_CHECK == gate.UNCHANGED
    assert f'code="{docgen.UNCHANGED_CODE}"' in inspect.getsource(gate.unchanged_target)


def test_step_5_says_what_the_finding_means() -> None:
    text = " ".join(DIRECT_SKILL.read_text(encoding="utf-8").split())
    step = text[text.index("## Step 5") :]
    assert (
        f"check `{gate.UNCHANGED}`, code `{docgen.UNCHANGED_CODE}`, is a reply that "
        "handed its target back exactly as HEAD holds it"
    ) in step
    assert "fails before the gate runs and is never repaired" in step
