"""§4 — a derived output cap is a runtime budget, not part of the contract's identity.

The pressure test's T1-E found that ``sha256(dumps(contract))`` — the pinned
instrument key ``tools/instruments.py`` joins recorded runs to their task set
by — depended on ``data/task-catalog.json``. ``output_cap`` derives the cap from
the task type's required evidence, and the derived number was written into the
emitted form, so flipping one ``needs_commands`` boolean re-keyed every pinned
contract of that type.

The fix is the one the port already applied to ``depends_on``: the *resolved*
value lives on the loaded object, the *declared* value lives in the serialised
form. A contract that declares ``max_output_tokens`` carries that number as
identity; a contract that does not carries ``null``, whatever the catalog later
says, and the loader re-derives the runtime budget on every parse.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.contract import dumps, loads, parse

FUNCTION_IMPL = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
"""

DOCSTRING = """
id: document
task_type: docstring
task: Document the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The helper's behaviour is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

DECLARED = FUNCTION_IMPL + "limits:\n  max_output_tokens: 2048\n"


def test_a_derived_cap_stays_on_the_loaded_object_and_not_in_the_emitted_form() -> None:
    """The runtime budget is derived; the identity carries the declaration only."""
    contract = loads(FUNCTION_IMPL)

    assert contract.limits.max_output_tokens == 1024, (
        "the loaded object must still carry the derived runtime cap"
    )
    assert '"max_output_tokens": null' in dumps(contract), (
        "a derived cap leaked into the emitted form, so the catalog still "
        "re-keys the identity"
    )


def test_a_declared_cap_is_part_of_the_identity() -> None:
    """A contract that *states* its cap states it in the emitted form too."""
    contract = loads(DECLARED)

    assert contract.limits.max_output_tokens == 2048
    assert '"max_output_tokens": 2048' in dumps(contract)


def test_the_round_trip_still_holds_for_both_shapes() -> None:
    """``parse(dumps(c)) == c``, derived or declared."""
    assert parse(dumps(loads(FUNCTION_IMPL))) == loads(FUNCTION_IMPL)
    assert parse(dumps(loads(DECLARED))) == loads(DECLARED)


def test_editing_the_catalog_does_not_move_the_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Flipping ``needs_commands`` changes the runtime cap, not the digest.

    Under the shipped catalog ``docstring`` derives 512. Flipping its
    ``no_semantic_change`` evidence to need a command would derive 1024 — and
    the emitted form must not move either way, because the cap was never
    declared.
    """
    import mcgyvr.catalog as catalog_module
    from mcgyvr.catalog import catalog as catalog_fn

    before = dumps(loads(DOCSTRING))

    raw: dict[str, Any] = json.loads(
        catalog_module.catalog_path().read_text(encoding="utf-8")
    )
    for evidence in raw["evidence_kinds"]:
        if evidence["name"] == "no_semantic_change":
            evidence["needs_commands"] = True
    path = tmp_path / "task-catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr("mcgyvr.catalog.catalog_path", lambda: path)
    catalog_fn.cache_clear()
    request.addfinalizer(catalog_fn.cache_clear)

    # The runtime cap moved — that is the catalog doing its job.
    assert loads(DOCSTRING).limits.max_output_tokens == 1024
    # The emitted form did not — that is identity no longer reading the catalog.
    assert dumps(loads(DOCSTRING)) == before
    assert (
        hashlib.sha256(dumps(loads(DOCSTRING)).encode()).hexdigest()
        == hashlib.sha256(before.encode()).hexdigest()
    )
