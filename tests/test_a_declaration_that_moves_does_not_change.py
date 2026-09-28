"""``hosts.json`` lives beside the door, in one place.

``tools/runs/hosts.json`` carries a ``rig`` block per host: gate 2 of the door
compares the live ``rig_snapshot`` field by field with that declaration, and
the declaration belongs where the one reader of it lives. No second copy exists
at ``tools/bench/serving/configs/hosts.json``, and
``tests/test_declared_host_state.py``'s checks read the same path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests import test_declared_host_state as declared_host_state

REPO = Path(__file__).resolve().parent.parent
NEW = REPO / "tools" / "runs" / "hosts.json"
OLD = REPO / "tools" / "bench" / "serving" / "configs" / "hosts.json"

#: Two blocks described a daemon that is not in the product; their values are
#: in ``mcgyvr-lab/archive/forensic-ollama/``. The file records the removal in
#: place rather than dropping the keys, which is what lets the check below tell
#: a deliberate removal from a block that fell out in a merge.
REMOVAL_KEY = "_removed_2026_09_06"


def _new() -> dict[str, Any]:
    document = json.loads(NEW.read_text(encoding="utf-8"))
    assert isinstance(document, dict), "the declaration is not a JSON object"
    return document


def test_the_declaration_lives_beside_the_door_and_nowhere_else() -> None:
    assert NEW.is_file(), f"{NEW.relative_to(REPO)} does not exist"
    assert not OLD.exists(), (
        f"{OLD.relative_to(REPO)} still exists; two declarations is the drift "
        "the declaration was filed to stop"
    )


def test_the_blocks_the_move_carried_record_their_own_removal() -> None:
    """A removal that is stated is a different thing from a block that vanished.

    The two blocks were taken out on purpose: each key is present, carries the
    removal note, and the note points at where the values went. A block that
    simply disappeared fails this.
    """
    document = _new()
    for block in ("residency", "engine"):
        assert block in document, (
            f"{block!r} is gone from the declaration entirely; a removal is "
            "recorded in place so a reader can tell it from a merge accident"
        )
        note = document[block].get(REMOVAL_KEY, "")
        assert note.strip(), f"{block!r} was emptied without saying why"
        assert "archive/forensic-ollama/" in note, (
            f"{block!r}'s removal note does not say where the values went"
        )


def test_no_setting_survived_the_removal_unstated() -> None:
    """The half a removal note cannot cover on its own.

    A note saying "these were removed" beside a key that is still declared
    would read as removed and behave as declared. So the two blocks carry
    nothing but documentation keys.
    """
    document = _new()
    for block in ("residency", "engine"):
        live = {k for k in document[block] if not k.startswith("_")}
        assert not live, (
            f"{block!r} says it was removed and still declares {sorted(live)}"
        )


def test_the_sibling_checks_read_the_declaration_at_its_new_path() -> None:
    assert declared_host_state.DECLARATION == NEW, (
        f"tests/test_declared_host_state.py reads {declared_host_state.DECLARATION}"
    )
    assert declared_host_state.declaration()["residency"] == _new()["residency"]
