"""An ungated task type for tests of the classifier's choice mechanics.

The shipped catalog has only `code`, whose proposal also carries a reply cap
the classifier states from the chosen target's size
(test_the_classifier_states_a_code_contracts_reply_cap.py). The choice
mechanics are shown with a kind that judges no change and states no cap
instead, so a test of them compares only the fields that were chosen: built
here as a `TaskType` for a vocabulary handed in directly, or invented into a
copy of the catalog when a contract must load against it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import TaskType, catalog, catalog_path

NAME = "agent"
DOC = (
    "Answer a prompt in plain prose from the repository files the contract "
    "names as its sources, ungated."
)


def ungated() -> TaskType:
    """The ungated kind, for a vocabulary handed to the proposer directly."""
    return replace(
        catalog().require("code"),
        name=NAME,
        required_evidence=(),
        evidence_derived=False,
        doc=DOC,
    )


def invent_ungated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> TaskType:
    """Invent the ungated kind into a copy of the catalog and load that copy.

    The invented entry is `code`'s with no evidence and its own doc, so it
    equals `ungated()`, and a lookup of the kind by name finds it.

    Repointing the loader and clearing the memo is the supported way to swap
    the shipped catalog (test_catalog.py); the memo is cleared again when the
    test ends.
    """
    raw: dict[str, Any] = json.loads(catalog_path().read_text(encoding="utf-8"))
    (code,) = (entry for entry in raw["task_types"] if entry["name"] == "code")
    entry = {key: value for key, value in code.items() if key != "evidence_derived"}
    raw["task_types"].append(
        entry | {"name": NAME, "required_evidence": [], "doc": DOC}
    )
    path = tmp_path / "task-catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr("mcgyvr.catalog.catalog_path", lambda: path)
    catalog.cache_clear()
    request.addfinalizer(catalog.cache_clear)
    return catalog().require(NAME)
