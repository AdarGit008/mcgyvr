"""A ``code`` contract's evidence is derived from its own fields, not chosen.

Every change a model makes to a repository is one ``code`` type whose evidence
is computed from what the contract says, never from a type-selected bundle.

The rule, from the spec:

- always ``gate``;
- a non-empty ``demonstration`` adds ``failing_test_first``;
- a non-empty ``acceptance`` adds ``tests_pass``;
- ``no_semantic_change: true`` adds ``no_semantic_change``;
- ``type_check: true`` adds ``type_check``.

``no_semantic_change`` and ``type_check`` are optional contract fields that
default to false.
"""

from __future__ import annotations

from mcgyvr.catalog import catalog
from mcgyvr.contract import dumps, loads, parse


def _code(**extra: str) -> str:
    """A minimal ``code`` contract, with the given fields appended."""
    body = "\n".join(extra.values())
    return f"""
id: c
task_type: code
task: Do the thing.
target: src/pkg/fetch.py
stop_conditions: ["The intent is ambiguous."]
{body}
scope:
  allow: ["src/**"]
"""


def test_a_code_contract_always_carries_gate() -> None:
    contract = loads(_code())
    assert contract.evidence_names == ("gate",)


def test_a_demonstration_adds_failing_test_first() -> None:
    contract = loads(
        _code(demonstration='demonstration: ["pytest -q tests/test_defect.py"]')
    )
    assert "gate" in contract.evidence_names
    assert "failing_test_first" in contract.evidence_names
    assert "tests_pass" not in contract.evidence_names


def test_an_acceptance_adds_tests_pass() -> None:
    contract = loads(_code(acceptance='acceptance: ["pytest -q"]'))
    assert "gate" in contract.evidence_names
    assert "tests_pass" in contract.evidence_names
    assert "failing_test_first" not in contract.evidence_names


def test_no_semantic_change_flag_adds_no_semantic_change() -> None:
    contract = loads(_code(flag="no_semantic_change: true"))
    assert contract.no_semantic_change is True
    assert "no_semantic_change" in contract.evidence_names
    assert "gate" in contract.evidence_names


def test_type_check_flag_adds_type_check() -> None:
    contract = loads(_code(flag="type_check: true"))
    assert contract.type_check is True
    assert "type_check" in contract.evidence_names
    assert "gate" in contract.evidence_names


def test_the_two_flags_default_to_false() -> None:
    contract = loads(_code())
    assert contract.no_semantic_change is False
    assert contract.type_check is False
    assert "no_semantic_change" not in contract.evidence_names
    assert "type_check" not in contract.evidence_names


def test_the_full_derivation_is_ordered_and_complete() -> None:
    contract = loads(
        _code(
            acceptance='acceptance: ["pytest -q"]',
            demonstration='demonstration: ["pytest -q tests/test_defect.py"]',
            no_semantic_change="no_semantic_change: true",
            type_check="type_check: true",
        )
    )
    assert contract.evidence_names == (
        "gate",
        "failing_test_first",
        "tests_pass",
        "no_semantic_change",
        "type_check",
    )


def test_the_flags_round_trip_through_the_emitted_form() -> None:
    contract = loads(
        _code(
            no_semantic_change="no_semantic_change: true",
            type_check="type_check: true",
        )
    )
    assert parse(dumps(contract)) == contract
    assert "no_semantic_change" in dumps(contract)
    assert "type_check" in dumps(contract)


def test_a_false_flag_is_not_emitted() -> None:
    """False flags are the default; emitting them would re-key every contract."""
    assert "no_semantic_change" not in dumps(loads(_code()))
    assert "type_check" not in dumps(loads(_code()))


def test_code_is_the_only_local_coding_type() -> None:
    book = catalog()
    local_coding = [
        t.name
        for t in book.task_types
        if t.starts_on.name == "local" and t.use_case.name == "coding"
    ]
    assert local_coding == ["code"]


def test_the_code_type_marks_evidence_as_derived() -> None:
    code = catalog().require("code")
    assert code.evidence_derived is True
    assert code.evidence_names == ("gate",)
