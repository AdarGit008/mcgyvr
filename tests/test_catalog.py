"""Tests for the decomposition catalog (#15).

The three things #15 makes acceptance criteria are tested directly:

* every entry states its guarantee and its starting rung,
* no entry exists that no configured ladder can serve,
* the catalog is data, not code branches — adding a type does not require a
  code change.

The third is the one that decays quietly, so it is tested behaviourally
(``test_a_new_task_type_needs_no_code_change``) rather than only by reading the
source: a spelling check can be satisfied by a file that still branches, but a
type invented entirely in a temp file cannot load unless the code really is
generic over the vocabulary.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import (
    Catalog,
    CatalogError,
    catalog,
    catalog_path,
    load,
)
from mcgyvr.cli import main
from mcgyvr.config import Config, Ladder, Source, Tier
from mcgyvr.contract import ContractSchemaError, loads, task_type

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "mcgyvr"


@pytest.fixture
def shipped() -> Catalog:
    return catalog()


def _config(*tiers: tuple[str, bool]) -> Config:
    """A config whose ladder holds one rung per (name, requires_credential)."""
    sources = {
        name: Source(
            name=name,
            base_url="http://localhost:1",
            api="openai",
            max_parallel=1,
            api_key_env="SOME_KEY" if keyed else None,
        )
        for name, keyed in tiers
    }
    return Config(
        path=None,
        data={},
        sources=sources,
        ladder=Ladder(
            tiers=tuple(Tier(name=f"{n}_m", source=n, model="m") for n, _ in tiers)
        ),
    )


# --- acceptance: every entry states its guarantee and its starting rung -----


def test_every_entry_states_a_guarantee(shipped: Catalog) -> None:
    for kind in shipped.task_types:
        assert kind.guarantee.strip(), f"{kind.name} has no guarantee"
        # A guarantee is a sentence a caller is owed, not a restated name.
        assert len(kind.guarantee.split()) > 5, f"{kind.name}'s guarantee is a label"


def test_every_entry_states_where_it_starts(shipped: Catalog) -> None:
    families = {f.name for f in shipped.families}
    for kind in shipped.task_types:
        assert kind.starts_on.name in families


def test_every_entry_states_its_required_evidence(shipped: Catalog) -> None:
    for kind in shipped.task_types:
        assert kind.required_evidence, f"{kind.name} requires no evidence"
        # The gate is the floor under every type, not one option among several.
        assert "gate" in kind.evidence_names, f"{kind.name} does not carry the gate"


def test_every_entry_is_documented_and_warranted(shipped: Catalog) -> None:
    """A type nobody can explain is one nobody can choose correctly."""
    for kind in shipped.task_types:
        assert kind.doc.strip()
        assert kind.warrant.strip(), f"{kind.name} says nothing about why it is here"
        assert kind.name.islower()


def test_evidence_baseline_routes_each_kind_to_the_slot_that_can_satisfy_it(
    shipped: Catalog,
) -> None:
    """#183: the demonstrating evidence expects a baseline *failure*, so it
    cannot share a slot with the regression evidence — and the split is data
    on the kind, not a name known to any consumer."""
    by_name = {e.name: e for e in shipped.evidence_kinds}
    assert by_name["failing_test_first"].baseline == "fail"
    assert by_name["tests_pass"].baseline == "pass"
    for kind in shipped.evidence_kinds:
        if not kind.needs_commands:
            assert kind.baseline == "pass"  # the default; no baseline run exists


def test_the_command_needing_properties_split_by_baseline(shipped: Catalog) -> None:
    bug_fix = shipped.require("bug_fix")
    assert bug_fix.needs_demonstration_commands  # failing_test_first
    # Its guarantee promises the demonstration and nothing else, so no
    # pass-at-baseline command is required of it (#183).
    assert not bug_fix.needs_acceptance_commands
    implementation = shipped.require("function_implementation")
    assert implementation.needs_acceptance_commands  # tests_pass
    assert not implementation.needs_demonstration_commands


def test_deterministic_is_derived_from_the_family_not_declared(
    shipped: Catalog,
) -> None:
    """The two cannot disagree, because there is only one of them."""
    for kind in shipped.task_types:
        assert kind.deterministic == (kind.starts_on.name == "deterministic")


def test_the_deterministic_family_is_the_cheapest(shipped: Catalog) -> None:
    assert shipped.families[0].name == "deterministic"
    assert [f.rank for f in shipped.families] == list(range(len(shipped.families)))


# --- acceptance: no entry exists that no configured ladder can serve --------


def test_a_local_only_ladder_serves_every_entry(shipped: Catalog) -> None:
    """The keyless install is a supported configuration, not a degraded one."""
    keyless = _config(("local", False))
    assert shipped.unservable(keyless) == ()


def test_an_api_only_ladder_serves_every_entry(shipped: Catalog) -> None:
    """A starting family is a floor: a dearer rung satisfies a cheaper one."""
    assert shipped.unservable(_config(("remote", True))) == ()


def test_a_ladder_with_no_rungs_serves_only_the_deterministic_types(
    shipped: Catalog,
) -> None:
    """Tools need no binding; everything else does."""
    bare = _config()
    servable = {t.name for t in shipped.servable(bare)}
    assert servable == {t.name for t in shipped.task_types if t.deterministic}
    assert {t.name for t in shipped.unservable(bare)} == {
        t.name for t in shipped.task_types if not t.deterministic
    }


def test_unservable_names_the_types_rather_than_returning_a_count(
    shipped: Catalog,
) -> None:
    """The honest answer to 'this install cannot do that' is which, by name."""
    for kind in shipped.unservable(_config()):
        assert kind.name
        assert kind.guarantee


# --- acceptance: the catalog is data, not code branches ---------------------


def test_a_new_task_type_needs_no_code_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The criterion, tested the only way that cannot rot: invent one.

    `sql_migration` exists nowhere in this repository. If any code branched on
    the vocabulary it would have no branch to take, and this would fail.
    """
    raw: dict[str, Any] = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["task_types"].append(
        {
            "name": "sql_migration",
            "starts_on": "api",
            "guarantee": "A migration is written and the schema check passes.",
            "required_evidence": ["gate", "tests_pass"],
            "warrant": "invented by a test",
            "doc": "Invented by a test.",
        }
    )
    path = tmp_path / "task-catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr("mcgyvr.catalog._CACHED", load(path))

    kind = task_type("sql_migration")
    assert kind.starts_on.name == "api"
    assert not kind.deterministic
    assert kind.needs_acceptance_commands

    contract = loads(
        """
id: add-index
task_type: sql_migration
task: Add an index on the events table.
target: migrations/0007.sql
stop_conditions: ["The target dialect is not stated."]
acceptance: ["make migrate-check"]
scope:
  allow: ["migrations/**"]
"""
    )
    assert contract.type.name == "sql_migration"
    assert contract.is_deterministic is False

    # And it is genuinely unservable on a keyless ladder, by the same rule that
    # governs every shipped entry — no special case was needed for it either.
    unservable = {t.name for t in load(path).unservable(_config(("local", False)))}
    assert unservable == {"sql_migration"}


def test_no_consumer_of_the_vocabulary_names_a_task_type(shipped: Catalog) -> None:
    """No string literal in the catalog's consumers equals a task type name.

    Scoped to the modules that read the vocabulary. The gate is deliberately
    excluded: its `"format"` is a check label in its own vocabulary and `ruff
    format` is a subcommand argument, so scanning it would assert a coincidence
    of spelling rather than a property of the design.
    """
    names = set(shipped.names)
    consumers = ("catalog.py", "contract.py", "cli.py")
    offenders = [
        f"{module}:{node.lineno} {node.value!r}"
        for module in consumers
        for node in ast.walk(ast.parse((SOURCE_ROOT / module).read_text("utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value in names
    ]
    assert not offenders, f"task types named in code: {offenders}"


def test_the_catalog_file_is_the_only_definition() -> None:
    """No module reconstructs the vocabulary as a Python literal."""
    for path in SOURCE_ROOT.rglob("*.py"):
        text = path.read_text("utf-8")
        assert "TASK_TYPES = (" not in text, f"{path} redeclares the vocabulary"


# --- excluded entries -------------------------------------------------------


def test_exclusions_are_recorded_with_a_reason(shipped: Catalog) -> None:
    """Removals are kept, not deleted — the reason is the point of keeping them."""
    assert shipped.excluded
    for gone in shipped.excluded:
        assert len(gone.reason.split()) > 8, f"{gone.name}'s removal is unexplained"


def test_the_inherited_vocabulary_was_actually_validated(shipped: Catalog) -> None:
    """Every inherited name is either carried or explicitly removed.

    The issue's open question was which inherited types survive. An inherited
    name that is neither in the catalog nor in `excluded` was not answered, just
    dropped.
    """
    inherited = {
        "formatting": "format",
        "import sorting": "import_sort",
        "simple rename": "rename_symbol",
        "comment addition": "comment_addition",
        "string literal edit": "string_literal_edit",
        "function implementation": "function_implementation",
        "type annotation": "type_annotation",
        "simple bug fix": "simple_bug_fix",
        "docstring": "docstring",
        "test scaffold": "test_scaffold",
        "config edit": "config_edit",
        "lint fix": "lint_fix",
        "bug fix": "bug_fix",
        "multi-file refactor": "multi_file_refactor",
        "algorithm implementation": "algorithm_implementation",
        "complex bug fix": "complex_bug_fix",
        "interface design": "interface_design",
    }
    for prose, name in inherited.items():
        decided = shipped.get(name) is not None or shipped.excluded_entry(name)
        assert decided, f"inherited type {prose!r} was neither carried nor removed"


def test_a_removed_type_is_rejected_with_the_reason_it_was_removed() -> None:
    """The next person to reach for it finds out why, not just that."""
    with pytest.raises(ContractSchemaError) as exc:
        task_type("multi_file_refactor")
    message = str(exc.value)
    assert "task_type:" in message
    assert "single-file" in message or "one file" in message


def test_a_superseded_type_names_its_replacement() -> None:
    with pytest.raises(ContractSchemaError) as exc:
        task_type("complex_bug_fix")
    assert "'bug_fix'" in str(exc.value)


def test_an_unknown_type_lists_the_vocabulary(shipped: Catalog) -> None:
    with pytest.raises(ContractSchemaError) as exc:
        task_type("teleportation")
    message = str(exc.value)
    for name in shipped.names:
        assert name in message


# --- loader rejections ------------------------------------------------------


def _write(tmp_path: Path, **overrides: Any) -> Path:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw.update(overrides)
    path = tmp_path / "task-catalog.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_an_unreadable_catalog_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="cannot read"):
        load(tmp_path / "absent.json")


def test_malformed_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "task-catalog.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogError, match="not valid JSON"):
        load(path)


def test_a_future_schema_version_is_rejected(tmp_path: Path) -> None:
    """Read under the wrong rules is worse than not read at all."""
    with pytest.raises(CatalogError, match="schema_version"):
        load(_write(tmp_path, schema_version=99))


def test_an_undeclared_starting_family_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["task_types"][0]["starts_on"] = "quantum"
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="not a declared family"):
        load(path)


def test_an_undeclared_evidence_kind_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["task_types"][0]["required_evidence"] = ["vibes"]
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="not a declared evidence kind"):
        load(path)


def test_an_unknown_evidence_baseline_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["evidence_kinds"][0]["baseline"] = "maybe"
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="not 'pass' or 'fail'"):
        load(path)


def test_a_fail_baseline_without_commands_is_rejected(tmp_path: Path) -> None:
    """A structural check has no baseline run whose outcome could be expected."""
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    structural = next(e for e in raw["evidence_kinds"] if not e.get("needs_commands"))
    structural["baseline"] = "fail"
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match=r"without\s+needs_commands"):
        load(path)


def test_a_duplicated_task_type_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["task_types"].append(dict(raw["task_types"][0]))
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="more than once"):
        load(path)


def test_an_entry_missing_its_guarantee_is_rejected(tmp_path: Path) -> None:
    """The guarantee is not optional prose; it is what the entry is for."""
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["task_types"][0].pop("guarantee")
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="guarantee"):
        load(path)


def test_a_type_that_is_both_carried_and_excluded_is_rejected(tmp_path: Path) -> None:
    """A type is in the vocabulary or it is not."""
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["excluded"].append({"name": raw["task_types"][0]["name"], "reason": "x" * 60})
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="also a declared task type"):
        load(path)


def test_superseded_by_must_name_a_carried_type(tmp_path: Path) -> None:
    raw = json.loads(catalog_path().read_text(encoding="utf-8"))
    raw["excluded"][0]["superseded_by"] = "nonexistent"
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="not a declared task type"):
        load(path)


def test_an_empty_catalog_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="no task types"):
        load(_write(tmp_path, task_types=[]))


def test_the_catalog_is_loaded_once() -> None:
    assert catalog() is catalog()


# --- the CLI ----------------------------------------------------------------


def _keyless_config(tmp_path: Path) -> Path:
    path = tmp_path / "mcgyvr.yaml"
    path.write_text(
        """
version: 1
sources:
  local:
    base_url: http://localhost:11434
    api: ollama
ladder:
  tiers:
    - name: local_qwen2.5-coder-7b
      source: local
      model: qwen2.5-coder:7b
""",
        encoding="utf-8",
    )
    return path


def test_cli_lists_every_type_with_its_guarantee(
    capsys: pytest.CaptureFixture[str], shipped: Catalog
) -> None:
    assert main(["catalog"]) == 0
    out = capsys.readouterr().out
    for kind in shipped.task_types:
        assert kind.name in out
        assert kind.starts_on.name in out
        assert kind.guarantee in out


def test_cli_shows_one_type_in_full(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["catalog", "bug_fix"]) == 0
    out = capsys.readouterr().out
    assert "failing_test_first" in out
    assert "guarantee:" in out
    assert "warrant:" in out


def test_cli_explains_a_removed_type_rather_than_calling_it_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["catalog", "interface_design"]) == 1
    err = capsys.readouterr().err
    assert "not in the vocabulary" in err
    assert "acceptance evidence" in err


def test_cli_rejects_an_unknown_type_by_listing_the_vocabulary(
    capsys: pytest.CaptureFixture[str], shipped: Catalog
) -> None:
    assert main(["catalog", "teleportation"]) == 1
    err = capsys.readouterr().err
    for name in shipped.names:
        assert name in err


def test_cli_resolves_against_a_configured_ladder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _keyless_config(tmp_path)
    assert main(["catalog", "--against", str(config)]) == 0
    out = capsys.readouterr().out
    assert "Every type is servable" in out


def test_cli_shows_the_removals_and_their_reasons(
    capsys: pytest.CaptureFixture[str], shipped: Catalog
) -> None:
    assert main(["catalog", "--excluded"]) == 0
    out = capsys.readouterr().out
    for gone in shipped.excluded:
        assert gone.name in out


def test_cli_reports_a_broken_config_rather_than_ignoring_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "mcgyvr.yaml"
    broken.write_text("sources: {}\n", encoding="utf-8")
    assert main(["catalog", "--against", str(broken)]) == 1
    assert "error:" in capsys.readouterr().err
