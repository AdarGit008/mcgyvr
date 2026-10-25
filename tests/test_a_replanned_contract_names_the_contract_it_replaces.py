"""A re-planned contract names the contract it replaces and its re-plan round.

The bound on re-planning is read from the contracts themselves: a contract
the orchestrator proposed in a spent one's place carries `replan.replaces`,
the spent contract's id, and `replan.round`, one more than the spent one's.
A contract nobody re-planned states neither, and writes neither back.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr.contract import ContractSchemaError, dumps, loads

BASE = {
    "id": "code-narrow",
    "task_type": "code",
    "task": "Rename rec_to_map to pairs_of; change nothing else.",
    "target": "pkg/codec.py",
    "scope": {"allow": ["pkg/codec.py"]},
    "stop_conditions": ["pairs_of is already defined"],
}


def a_document(**extra: object) -> str:
    return json.dumps({**BASE, **extra})


def test_the_lineage_round_trips() -> None:
    contract = loads(a_document(replan={"replaces": "code-rename", "round": 1}))

    assert (contract.replan.replaces, contract.replan.round) == ("code-rename", 1)
    assert json.loads(dumps(contract))["replan"] == {
        "replaces": "code-rename",
        "round": 1,
    }
    assert loads(dumps(contract)) == contract


def test_a_contract_nobody_replanned_states_no_lineage() -> None:
    contract = loads(a_document())

    assert (contract.replan.replaces, contract.replan.round) == ("", 0)
    assert "replan" not in json.loads(dumps(contract))


@pytest.mark.parametrize(
    ("lineage", "said"),
    [
        ({"replaces": "code-rename", "round": 0}, "round"),
        ({"round": 1}, "replaces"),
        ({"replaces": "code-narrow", "round": 1}, "own id"),
        ({"replaces": "not an id!", "round": 1}, "usable contract id"),
    ],
)
def test_a_lineage_that_names_nothing_it_could_replace_is_refused(
    lineage: dict[str, object], said: str
) -> None:
    with pytest.raises(ContractSchemaError, match=said):
        loads(a_document(replan=lineage))
