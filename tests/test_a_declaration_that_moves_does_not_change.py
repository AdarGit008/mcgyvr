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

#: ``residency`` as ``tools/bench/serving/configs/hosts.json`` declared it on
#: 2026-08-22 (commit 70294f0e), copied here rather than read from the old
#: path, because the old path is what goes away.
RESIDENCY: dict[str, Any] = {
    "_doc": (
        "The three ollama settings that decide whether a model stays on the card "
        "and whether a second may join it — which is exactly what the co-residency "
        "cells measure. The owner's rule is `no limits: the hardware is the limit; "
        "if it breaks, we fix mcgyvr`, so two of the three are `0` (no cap) and the "
        "third disables the clock. Declaring `no cap` is NOT the same as leaving "
        "the engine to choose: srv2's old values were whatever 0.32.5 picked, "
        "recorded nowhere, under a different engine version from srv1's. Value "
        "strings are compared literally against the unit's `Environment=` line, "
        "which is how a survey reports them."
    ),
    "OLLAMA_NUM_PARALLEL": {
        "value": "0",
        "why": (
            "no cap on slots — the hardware is the limit (owner, 2026-08-22). srv1 "
            "previously declared `2`, which split its context 8192x2 while srv2 "
            "ran 4096x1; that split is K2 and K7."
        ),
    },
    "OLLAMA_MAX_LOADED_MODELS": {
        "value": "0",
        "why": (
            "no cap on co-resident models (owner, 2026-08-22). srv1 previously "
            "declared `3`; srv2 declared nothing and the engine chose `0`."
        ),
    },
    "OLLAMA_KEEP_ALIVE": {
        "value": "-1",
        "why": (
            "nothing is evicted by a clock (owner, 2026-08-22). Resolves to "
            "`2562047h47m16.854775807s` — max int64 — on both rigs. srv1 previously "
            "declared `5m`; srv2 declared nothing and the engine chose `5m0s`."
        ),
    },
}

ENGINE_BUILD = "0.32.15"


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


def test_the_residency_block_is_what_was_declared_on_2026_08_22() -> None:
    assert _new()["residency"] == RESIDENCY


def test_the_engine_build_is_what_was_declared_on_2026_08_22() -> None:
    assert _new()["engine"]["ollama"]["build"] == ENGINE_BUILD


def test_the_sibling_checks_read_the_declaration_at_its_new_path() -> None:
    assert declared_host_state.DECLARATION == NEW, (
        f"tests/test_declared_host_state.py reads {declared_host_state.DECLARATION}"
    )
    assert declared_host_state.declaration()["residency"] == RESIDENCY
