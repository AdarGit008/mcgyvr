"""The contract is public API an agent authors, so these tests hold it to the
three things #14 makes acceptance criteria — every rejection names the field
and the fix, a glob-scoped contract for a model-tier task type is rejected at
load, and a contract the orchestrator emits is one the loader accepts — plus
the self-contradictions that would otherwise surface mid-task, after a rung had
already been spent.

The worker/orchestrator field split (#94) is tested through
:meth:`Contract.worker_view`, because "orchestrator-only fields never reach the
worker prompt" is only true if there is no other accessor that leaks them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.contract import (
    SCHEMA_VERSION,
    TASK_TYPES,
    Contract,
    ContractFileError,
    ContractSchemaError,
    dumps,
    load,
    loads,
    parse,
)

MINIMAL = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
scope:
  allow: ["src/**/*.py"]
"""

DETERMINISTIC = """
id: tidy
task_type: format
task: Reformat the package.
target: src/pkg/fetch.py
scope:
  allow: ["src/**"]
"""

FULL = """
version: 1
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
interface: "def fetch(url: str, *, retries: int = 3) -> Response"
deps:
  - path: src/pkg/backoff.py
    signature: "def delay(attempt: int) -> float"
    note: Use this for the wait between attempts.
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
  - The change would need to touch a file outside the target.
output_schema: whole_file
context:
  max_input_tokens: 8000
scope:
  allow: ["src/**/*.py"]
  forbid: ["src/pkg/generated/**"]
acceptance:
  - pytest -q
risk: high
verification:
  policy: model
limits:
  max_output_tokens: 2048
  attempts: 3
"""


_MINIMAL_SCOPE = 'scope:\n  allow: ["src/**/*.py"]'


def with_scope(allow: str, forbid: str | None = None) -> str:
    """MINIMAL with its scope block replaced — appending a second would (rightly)
    trip the duplicate-key guard."""
    block = f"scope:\n  allow: {allow}"
    if forbid is not None:
        block += f"\n  forbid: {forbid}"
    return MINIMAL.replace(_MINIMAL_SCOPE, block)


# --- acceptance: a contract the orchestrator emits is one the API accepts ---


def test_minimal_contract_round_trips() -> None:
    contract = loads(MINIMAL)
    assert parse(dumps(contract)) == contract


def test_fully_populated_contract_round_trips() -> None:
    contract = loads(FULL)
    assert parse(dumps(contract)) == contract


def test_round_trip_preserves_every_field() -> None:
    """Not just equal objects — every declared value survives the emitted form."""
    contract = parse(dumps(loads(FULL)))
    assert contract.id == "fetch-retry"
    assert contract.task_type == "function_implementation"
    assert contract.interface.startswith("def fetch(")
    assert [d.path for d in contract.deps] == ["src/pkg/backoff.py"]
    assert contract.deps[0].signature == "def delay(attempt: int) -> float"
    assert contract.deps[0].note == "Use this for the wait between attempts."
    assert len(contract.stop_conditions) == 2
    assert contract.max_input_tokens == 8000
    assert contract.scope.allow == ("src/**/*.py",)
    assert contract.scope.forbid == ("src/pkg/generated/**",)
    assert contract.acceptance == ("pytest -q",)
    assert contract.risk == "high"
    assert contract.verification.policy == "model"
    assert contract.limits.max_output_tokens == 2048
    assert contract.limits.attempts == 3


def test_json_is_accepted_as_well_as_yaml() -> None:
    """Direct mode is an agent writing JSON; YAML is a superset, so both load."""
    assert parse(dumps(loads(MINIMAL))) == loads(MINIMAL)


def test_defaults_are_applied() -> None:
    contract = loads(MINIMAL)
    assert contract.version == SCHEMA_VERSION
    assert contract.interface == ""
    assert contract.deps == ()
    assert contract.output_schema == "whole_file"
    assert contract.max_input_tokens == 4096
    assert contract.risk == "medium"
    assert contract.verification.policy == "gate_only"
    assert contract.limits.max_output_tokens == 1024
    assert contract.limits.attempts == 2
    assert contract.scope.forbid == ()


# --- acceptance: a glob target on a model-tier type is rejected -------------


def test_glob_target_is_rejected_for_a_model_task_type() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(MINIMAL.replace("target: src/pkg/fetch.py", 'target: "src/**/*.py"'))
    message = str(exc.value)
    assert message.startswith("target:")
    assert "one destination" in message
    assert "format" in message  # names the types that *can* take a pattern


@pytest.mark.parametrize(
    "pattern", ["src/*.py", "src/**", "src/f?tch.py", "src/[ab].py"]
)
def test_every_glob_metacharacter_is_caught(pattern: str) -> None:
    with pytest.raises(ContractSchemaError, match=r"^target:"):
        loads(MINIMAL.replace("target: src/pkg/fetch.py", f'target: "{pattern}"'))


def test_glob_target_is_allowed_for_a_deterministic_task_type() -> None:
    contract = loads(
        DETERMINISTIC.replace("target: src/pkg/fetch.py", 'target: "src/**"')
    )
    assert contract.target == "src/**"
    assert contract.is_deterministic


def test_literal_target_is_allowed_for_a_model_task_type() -> None:
    assert loads(MINIMAL).target == "src/pkg/fetch.py"


# --- acceptance: every rejection names the field and the fix ----------------


@pytest.mark.parametrize(
    ("document", "field"),
    [
        (MINIMAL.replace("id: fetch-retry", "id: 'not a valid id'"), "id:"),
        (
            MINIMAL.replace("task_type: function_implementation", "task_type: nope"),
            "task_type:",
        ),
        (
            MINIMAL.replace(
                "task: Add retry with backoff to the fetch helper.", "task: ''"
            ),
            "task:",
        ),
        (MINIMAL + "\ncontext:\n  max_input_tokens: 0\n", "context.max_input_tokens:"),
        (
            MINIMAL + "\ncontext:\n  max_input_tokens: half\n",
            "context.max_input_tokens:",
        ),
        (MINIMAL + "\nrisk: catastrophic\n", "risk:"),
        (MINIMAL + "\noutput_schema: freeform\n", "output_schema:"),
        (MINIMAL + "\nverification:\n  policy: vibes\n", "verification.policy:"),
        (MINIMAL + "\nlimits:\n  attempts: 0\n", "limits.attempts:"),
        (MINIMAL + "\nacceptance: pytest -q\n", "acceptance:"),
        (
            MINIMAL.replace('allow: ["src/**/*.py"]', 'allow: ["/etc/passwd"]'),
            "scope.allow.0:",
        ),
        (
            MINIMAL.replace('allow: ["src/**/*.py"]', 'allow: ["../outside/**"]'),
            "scope.allow.0:",
        ),
        (MINIMAL + "\ndeps:\n  - signature: 'def f()'\n", "deps.0.path:"),
        (MINIMAL + "\ndeps:\n  - path: a.py\n", "deps.0.signature:"),
    ],
)
def test_every_rejection_names_its_field(document: str, field: str) -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(document)
    message = str(exc.value)
    assert message.startswith(field), f"expected a message naming {field}: {message}"
    # And it says something beyond the complaint — what a valid value is.
    assert len(message) > len(field) + 20


def test_a_missing_required_key_names_it_and_explains_it() -> None:
    without_target = "\n".join(
        line for line in MINIMAL.splitlines() if not line.startswith("target:")
    )
    with pytest.raises(ContractSchemaError) as exc:
        loads(without_target)
    message = str(exc.value)
    assert message.startswith("target:")
    assert "required key is not set" in message
    assert "e.g. src/pkg/fetch.py" in message  # the hint says what to write


def test_unknown_key_is_rejected_and_lists_the_valid_ones() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(MINIMAL + "\nretries: 3\n")
    message = str(exc.value)
    assert "unknown key 'retries'" in message
    assert "task_type" in message  # the valid set is shown


def test_unknown_nested_key_names_its_block() -> None:
    document = MINIMAL.replace(
        _MINIMAL_SCOPE, "scope:\n  allow: ['src/**']\n  deny: ['b.py']"
    )
    with pytest.raises(ContractSchemaError, match=r"^scope: unknown key 'deny'"):
        loads(document)


def test_duplicate_key_is_rejected() -> None:
    with pytest.raises(ContractSchemaError, match="duplicate key"):
        loads(MINIMAL + "\nrisk: low\nrisk: high\n")


def test_empty_contract_is_rejected_with_what_it_needs() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads("")
    assert "id, task_type, task, target and scope.allow" in str(exc.value)


def test_unreadable_yaml_is_a_file_error_not_a_schema_error() -> None:
    with pytest.raises(ContractFileError, match="not valid YAML or JSON"):
        loads("id: [unclosed")


def test_a_future_schema_version_is_rejected() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(MINIMAL.replace("id:", f"version: {SCHEMA_VERSION + 1}\nid:"))
    assert str(exc.value).startswith("version:")
    assert f"reads version {SCHEMA_VERSION}" in str(exc.value)


# --- self-contradiction, rejected at load rather than mid-task -------------


def test_a_pattern_both_allowed_and_forbidden_is_rejected() -> None:
    """The worked example from local-ai: forbid always wins, so allow is dead."""
    with pytest.raises(ContractSchemaError) as exc:
        loads(with_scope('["src/**"]', '["src/**"]'))
    message = str(exc.value)
    assert message.startswith("scope.forbid:")
    assert "both allowed and forbidden" in message


def test_a_target_its_own_scope_forbids_is_rejected() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(with_scope('["src/**"]', '["src/pkg/fetch.py"]'))
    assert str(exc.value).startswith("target:")
    assert "forbidden by this contract's own scope" in str(exc.value)


def test_a_target_outside_allowed_scope_is_rejected() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(MINIMAL.replace('allow: ["src/**/*.py"]', 'allow: ["docs/**"]'))
    assert str(exc.value).startswith("target:")
    assert "outside scope.allow" in str(exc.value)


def test_an_empty_allow_list_is_rejected() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(MINIMAL.replace('allow: ["src/**/*.py"]', "allow: []"))
    message = str(exc.value)
    assert message.startswith("scope.allow:")
    assert "permits nothing" in message


def test_a_model_task_type_without_stop_conditions_is_rejected() -> None:
    without = MINIMAL.replace(
        "stop_conditions:\n  - The retry policy is not stated anywhere in the repo.\n",
        "",
    )
    with pytest.raises(ContractSchemaError) as exc:
        loads(without)
    message = str(exc.value)
    assert message.startswith("stop_conditions:")
    assert "will guess" in message


def test_a_deterministic_task_type_needs_no_stop_conditions() -> None:
    """A tool cannot guess, so the requirement would be ceremony."""
    assert loads(DETERMINISTIC).stop_conditions == ()


def test_a_duplicated_dependency_is_rejected() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(
            MINIMAL
            + "\ndeps:\n"
            + "  - path: a.py\n    signature: 'def f()'\n"
            + "  - path: a.py\n    signature: 'def g()'\n"
        )
    assert str(exc.value).startswith("deps.1.path:")


def test_an_output_cap_larger_than_the_prompt_budget_is_rejected() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        loads(
            MINIMAL
            + "\ncontext:\n  max_input_tokens: 1000\n"
            + "\nlimits:\n  max_output_tokens: 4000\n"
        )
    message = str(exc.value)
    assert message.startswith("limits.max_output_tokens:")
    assert "exceeds context.max_input_tokens" in message


# --- the worker / orchestrator split (#94) ---------------------------------

ORCHESTRATOR_ONLY = ("risk", "verification", "acceptance", "limits", "scope")


def test_worker_view_excludes_every_orchestrator_only_field() -> None:
    view = loads(FULL).worker_view()
    for key in ORCHESTRATOR_ONLY:
        assert key not in view, f"{key} must not reach the worker prompt"


def test_worker_view_carries_what_the_worker_needs() -> None:
    view = loads(FULL).worker_view()
    assert view["task"].startswith("Add retry")
    assert view["target"] == "src/pkg/fetch.py"
    assert view["interface"].startswith("def fetch(")
    assert view["deps"][0]["signature"] == "def delay(attempt: int) -> float"
    assert len(view["stop_conditions"]) == 2
    assert view["output_schema"] == "whole_file"
    assert view["context"]["max_input_tokens"] == 8000


def test_no_orchestrator_value_leaks_into_the_serialized_worker_view() -> None:
    """Not just absent keys — the values themselves must not appear anywhere."""
    import json

    rendered = json.dumps(loads(FULL).worker_view())
    assert "pytest -q" not in rendered  # acceptance command
    assert "high" not in rendered  # risk
    assert "generated" not in rendered  # a forbid pattern
    assert "2048" not in rendered  # the output cap


# --- the scope object the gate will use ------------------------------------


def test_scope_is_the_canonical_matcher() -> None:
    scope = loads(FULL).scope
    assert scope.permits("src/pkg/fetch.py")
    assert not scope.permits("src/pkg/generated/api.py")  # forbid wins
    assert not scope.permits("docs/readme.md")
    assert scope.violations(["src/pkg/fetch.py", "docs/x.md"]) == ("docs/x.md",)


# --- the task-type seed ----------------------------------------------------


def test_every_declared_task_type_loads() -> None:
    for kind in TASK_TYPES:
        document = f"""
id: t
task_type: {kind.name}
task: Do the thing.
target: src/pkg/fetch.py
stop_conditions: ["An unknown."]
scope:
  allow: ["src/**"]
"""
        contract = loads(document)
        assert contract.type is kind
        assert contract.is_deterministic == kind.deterministic


def test_every_task_type_is_documented() -> None:
    """A type nobody can explain is one nobody can choose correctly."""
    for kind in TASK_TYPES:
        assert kind.doc.strip()
        assert kind.name.islower()


# --- loading from a file ---------------------------------------------------


def test_load_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "contract.yaml"
    path.write_text(MINIMAL)
    assert load(path).id == "fetch-retry"


def test_load_names_the_path_it_could_not_read(tmp_path: Path) -> None:
    with pytest.raises(ContractFileError, match="cannot be read"):
        load(tmp_path / "absent.yaml")


def test_a_file_error_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("id: [unclosed")
    with pytest.raises(ContractFileError, match=str(path)):
        load(path)


def test_contract_is_immutable() -> None:
    contract = loads(MINIMAL)
    with pytest.raises(AttributeError):
        contract.id = "other"  # type: ignore[misc]


def test_contracts_compare_by_value() -> None:
    assert loads(MINIMAL) == loads(MINIMAL)
    assert isinstance(loads(MINIMAL), Contract)
