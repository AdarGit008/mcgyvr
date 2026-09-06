"""Gate 1: no arm ever reaches the rig under a round that does not pin its tree.

An arm measured on a tree three commits past the pin must not land in the same
table as one measured on the pin (ADR-0018: every arm in a round runs against
one revision). That property used to be held by refusing the run, and on
2026-09-06 the owner ruled the other way: a round is a boundary in the record,
not a permission to work. So gate 1 (``01-round.py``) calls
``tools/bench/product.ensure_open()``, which draws the boundary the moved tree
needs and lets the run through — the same guarantee, taken from the operator's
hands.

What is asserted here is therefore the guarantee and not the refusal: whatever
the door does with a moved tree, ``RUN_ROUND`` names a round whose
``product_sha256`` is this tree's, and the round that was open keeps the digest
its own arms ran against.

The fixture pins the tree it builds (``tests/onedoor.py:pin``); ``unpin``
declares a digest the tree does not have. Both values reach the step as
``RUN_ROUND`` and ``RUN_PRODUCT_SHA256``, and from there the artifact's
``### ROUND`` stamp
(``test_an_artifact_names_the_run_and_the_round_that_produced_it``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import onedoor
from tests.onedoor import Scenario

PROBE = Scenario("alpha", "1-probe.sh")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repo = onedoor.fixture_repo(tmp_path)
    onedoor.add_step(repo, "alpha", "1-probe.sh", onedoor.probe_step(tmp_path / "e"))
    return repo


def test_a_moved_tree_runs_under_a_round_that_pins_it(
    root: Path, tmp_path: Path
) -> None:
    """The measured case: the tree moved, and the run must not be stopped for it.

    On 2026-09-06 this refusal stopped `serve up` and `serve down` outright, ten
    product files having moved since the open round was pinned. The boundary is
    now drawn by the door, so what has to hold is that the round the step is
    stamped with pins the tree the step actually ran on.
    """
    was_id = onedoor.pinned(root)[0]
    onedoor.unpin(root)
    stale = onedoor.pinned(root)[1]

    result = onedoor.door(root, PROBE)

    assert result.returncode == 0, (result.stdout, result.stderr)
    handed = onedoor.read_env_file(tmp_path / "e")
    opened_id, opened_digest = onedoor.pinned(root)
    assert handed["RUN_ROUND"] == opened_id != was_id, (
        f"the step was stamped {handed['RUN_ROUND']!r}; the door opened "
        f"{opened_id!r} and a stamp naming the round it left is a stamp that "
        "puts two revisions in one table"
    )
    assert handed["RUN_PRODUCT_SHA256"] == opened_digest != stale, handed
    assert (onedoor.envelope(root, "alpha") / "probe.tsv").is_file()


def test_the_round_that_was_open_keeps_its_own_pin(root: Path) -> None:
    """Appending, not re-pinning — the property the whole digest exists for.

    Rewriting the open round's digest would make one round span two revisions,
    which is the exact thing the refusal was protecting and the one thing
    drawing the boundary automatically must not cost.
    """
    onedoor.unpin(root)
    rounds_file = root / "tools" / "bench" / "rounds.json"
    before = json.loads(rounds_file.read_text(encoding="utf-8"))["rounds"]

    assert onedoor.door(root, PROBE).returncode == 0

    after = json.loads(rounds_file.read_text(encoding="utf-8"))["rounds"]
    assert len(after) == len(before) + 1, "one boundary was drawn, not several"
    assert after[:-1] == before, "an earlier round was rewritten, not kept"


def test_a_pinned_round_lets_the_run_proceed(root: Path, tmp_path: Path) -> None:
    result = onedoor.door(root, PROBE)
    assert result.returncode == 0, (result.stdout, result.stderr)
    handed = onedoor.read_env_file(tmp_path / "e")
    round_id, digest = onedoor.pinned(root)
    assert handed["RUN_ROUND"] == round_id == onedoor.ROUND_ID, handed
    assert handed["RUN_PRODUCT_SHA256"] == digest, handed
    assert (onedoor.envelope(root, "alpha") / "probe.tsv").is_file()
