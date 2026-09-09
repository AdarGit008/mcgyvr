"""``hosts.json`` moved beside the door, and said the same thing after the move.

``tools/bench/serving/configs/hosts.json`` was filed on 2026-08-22 to close the
K9 gap: the settings that decide residency were set live on both rigs and
nothing in the repository stated them. It now grows a ``rig`` block per host
and moves to ``tools/runs/hosts.json``, because gate 2 of the door compares the
live ``rig_snapshot`` field by field with a declaration (BRIEF.md gate 2), and
the declaration belongs where the one reader of it lives.

A move is the moment a value gets retyped. The residency block below is the
old file's, verbatim, so the move is held to the declaration it carried — and
``tests/test_declared_host_state.py``'s checks are held to the new path, not
left pointing at a file that no longer exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests import test_declared_host_state as declared_host_state

REPO = Path(__file__).resolve().parent.parent
NEW = REPO / "tools" / "runs" / "hosts.json"
OLD = REPO / "tools" / "bench" / "serving" / "configs" / "hosts.json"

#: The two blocks the move carried, as they stood, are no longer in the file.
#: They described a daemon that was removed from the product and masked on srv2
#: on 2026-09-06; both are in ``archive/forensic-ollama/``, verbatim, with the
#: owner's `no limits` rule that chose their values. The file records the
#: removal in place rather than dropping the keys, which is what lets the check
#: below tell a deliberate removal from a block that fell out in a merge.
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

    This file exists because a move is the moment a value gets retyped, and it
    held the two blocks to what they said before the move. They are gone now,
    with the engine they described — so what it can still hold is that they were
    taken out on purpose: each key is still present, carries the removal note,
    and the note points at where the values went. A block that simply
    disappeared would fail this exactly as a retyped one used to.
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
