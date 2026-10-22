"""An output cap is identity only when the contract states one.

A digest of ``dumps(contract)`` names a contract by what it says. A contract
that declares ``max_output_tokens`` carries that number as identity; one that
does not carries ``null``, and nothing is derived for it on load — no number
from ``data/task-catalog.json`` can re-key it. A
model-written ``code`` contract that states no cap is refused at dispatch
rather than sized
(``tests/test_a_code_contract_states_its_cap_or_is_refused_at_dispatch.py``),
so the loaded object carries ``None`` exactly as the emitted form does.
"""

from __future__ import annotations

from mcgyvr.contract import dumps, loads, parse

# A `code` contract that states no cap.
WITH_COMMANDS = """
id: fetch-retry
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["pytest -q"]
scope:
  allow: ["src/**/*.py"]
"""

DECLARED = WITH_COMMANDS + "limits:\n  max_output_tokens: 2048\n"


def test_an_unstated_cap_is_null_loaded_and_emitted() -> None:
    """Nothing is derived: the loaded object and the identity both say none."""
    contract = loads(WITH_COMMANDS)

    assert contract.limits.max_output_tokens is None
    assert '"max_output_tokens": null' in dumps(contract)


def test_a_declared_cap_is_part_of_the_identity() -> None:
    """A contract that *states* its cap states it in the emitted form too."""
    contract = loads(DECLARED)

    assert contract.limits.max_output_tokens == 2048
    assert '"max_output_tokens": 2048' in dumps(contract)


def test_the_round_trip_still_holds_for_both_shapes() -> None:
    """``parse(dumps(c)) == c``, stated or not."""
    assert parse(dumps(loads(WITH_COMMANDS))) == loads(WITH_COMMANDS)
    assert parse(dumps(loads(DECLARED))) == loads(DECLARED)
