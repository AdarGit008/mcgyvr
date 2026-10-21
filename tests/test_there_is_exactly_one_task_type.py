"""There is exactly one task type, and a deterministic operation is ``code``.

The vocabulary a contract names in ``task_type`` is ``code``. The deterministic
operations (``format``,
``import_sort``, ``lint_fix``, ``rename_symbol``) are not task types: a
contract asks for one as ``task_type: code`` with ``operation: <name>``, and
it still runs on the deterministic floor with no model, judged by the same
evidence it was judged by as a type of its own.

A name that used to be a task type is refused, and the refusal names the
spelling that replaced it — the one place an old name survives.
"""

from __future__ import annotations

import json

import pytest

from mcgyvr.catalog import catalog, catalog_path
from mcgyvr.contract import ContractSchemaError, dumps, loads, parse
from mcgyvr.deterministic import tool_for

ONE = ("code",)


def _code(operation: str, target: str = "src/pkg/messy.py", extra: str = "") -> str:
    return f"""
id: op
task_type: code
operation: {operation}
task: Do what the operation does.
target: {target}
{extra}
scope:
  allow: ["src/**"]
"""


def test_the_catalog_declares_exactly_the_one_task_type() -> None:
    assert tuple(t.name for t in catalog().task_types) == ONE


def test_the_catalog_keeps_no_list_of_removed_names() -> None:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    assert "excluded" not in raw
    assert not hasattr(catalog(), "excluded")


def test_every_operation_belongs_to_code_and_starts_on_the_floor() -> None:
    operations = catalog().operations
    assert {op.name for op in operations} == {
        "format",
        "import_sort",
        "lint_fix",
        "rename_symbol",
    }
    for op in operations:
        assert op.task_type == "code", op.name
        assert op.deterministic, op.name


def test_an_operation_is_not_a_task_type() -> None:
    assert catalog().get("format") is None
    assert catalog().operation("format") is not None


@pytest.mark.parametrize(
    ("operation", "evidence"),
    [
        ("format", ("gate", "tool_idempotent", "no_semantic_change")),
        ("import_sort", ("gate", "tool_idempotent", "no_semantic_change")),
        ("lint_fix", ("gate", "tool_idempotent")),
    ],
)
def test_a_code_contract_with_an_operation_runs_on_the_floor_with_its_evidence(
    operation: str, evidence: tuple[str, ...]
) -> None:
    contract = loads(_code(operation))
    assert contract.task_type == "code"
    assert contract.operation == operation
    assert contract.is_deterministic
    assert contract.kind.name == operation
    assert contract.evidence_names == evidence
    tool = tool_for(contract)
    assert tool is not None and tool.program == "ruff"


def test_a_rename_operation_carries_references_resolved() -> None:
    contract = loads(
        _code("rename_symbol", extra="rename:\n  from: fetch_page\n  to: fetch_doc")
    )
    assert contract.is_deterministic
    assert contract.evidence_names == (
        "gate",
        "references_resolved",
        "no_semantic_change",
    )
    tool = tool_for(contract)
    assert tool is not None and tool.program is None, "rename runs in-process"


def test_an_operation_contract_round_trips_and_names_its_operation() -> None:
    contract = loads(_code("format"))
    assert '"operation": "format"' in dumps(contract)
    assert parse(dumps(contract)) == contract


def test_a_contract_with_no_operation_does_not_emit_one() -> None:
    """A key every contract carried would re-key every contract ever emitted."""
    contract = loads(
        """
id: c
task_type: code
task: Do the thing.
target: src/pkg/fetch.py
stop_conditions: ["The intent is ambiguous."]
scope:
  allow: ["src/**"]
"""
    )
    assert contract.operation == ""
    assert "operation" not in dumps(contract)
    assert not contract.is_deterministic


def test_an_operation_may_take_a_pattern_target() -> None:
    contract = loads(_code("format", target="src/pkg/*.py"))
    assert contract.target == "src/pkg/*.py"


def test_an_unknown_operation_is_refused_naming_the_valid_ones() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(_code("tidy"))
    said = str(exc.value)
    assert said.startswith("operation:"), said
    assert "format" in said and "rename_symbol" in said, said


@pytest.mark.parametrize(
    ("old", "replacement"),
    [
        ("format", "'format' is now 'code' with operation: format"),
        ("import_sort", "'import_sort' is now 'code' with operation: import_sort"),
        ("lint_fix", "'lint_fix' is now 'code' with operation: lint_fix"),
        (
            "rename_symbol",
            "'rename_symbol' is now 'code' with operation: rename_symbol",
        ),
        ("function_implementation", "'function_implementation' is now 'code'"),
        ("bug_fix", "'bug_fix' is now 'code'"),
        ("docstring", "'docstring' is now 'code'"),
        ("type_annotation", "'type_annotation' is now 'code'"),
        ("test_scaffold", "'test_scaffold' is now 'code'"),
        ("chat", "'chat' is now the served endpoint, not a contract"),
        ("agent", "'agent' is now the served endpoint, not a contract"),
    ],
)
def test_a_contract_naming_an_old_type_is_told_the_replacement(
    old: str, replacement: str
) -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(
            f"""
id: c
task_type: {old}
task: Do the thing.
target: src/pkg/fetch.py
stop_conditions: ["The intent is ambiguous."]
scope:
  allow: ["src/**"]
"""
        )
    said = str(exc.value)
    assert said.startswith("task_type:"), said
    assert replacement in said, said


def test_a_name_that_never_was_a_type_lists_the_one() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(
            """
id: c
task_type: teleportation
task: Do the thing.
target: src/pkg/fetch.py
stop_conditions: ["The intent is ambiguous."]
scope:
  allow: ["src/**"]
"""
        )
    said = str(exc.value)
    assert said.endswith("Valid: code"), said
