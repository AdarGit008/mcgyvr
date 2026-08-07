"""Offline invariants over #167's Python arm — the control for CLM-0012's null.

CLM-0012 measured the JS/TS bundle flat and had to scope the finding, because
one control could not be run: CLM-0004's own Python ladder against a reachable
rig. Two readings fit the data and they have opposite consequences. Under
*language*, ``prompts/python.md`` keeps its evidence and only the JS/TS port is
unsupported. Under *serving stack*, CLM-0004 does not describe the stack mcgyvr
dispatches on and the Python bundle's standing is no better than the JS/TS one.

The arm that separates them is CLM-0004's twenty tasks, recovered from local-ai
and ported to mcgyvr contracts, run through the same rig the JS/TS sweep used.
What is checkable without a worker is whether that port is honest, and these are
the ways it could quietly not be:

* **The tasks could drift from the ones that were measured.** The acceptance
  scripts and reference solutions are copied from the vendored instrument, so a
  digest holds them to it. A task set that had been *rewritten* would still look
  like a replication and would not be one, which is the failure #167 says is
  worse than not running the control at all.
* **The composition could stop matching the JS/TS arm's.** A rate compared
  across arms is only about language if the mix it averages over is the same.
* **c2 could stop being the shipped bundle.** Here that equality runs the
  opposite way from the JS/TS arm's — ``prompts/python.md`` was derived *from*
  the measured ``c2.md``, not the other way round — so the file this arm uses as
  a condition is the vendored one, and this asserts the shipped prompt still
  equals it.

The rig's ``--selftest`` runs every reference against its own acceptance and is
the precondition for a sweep. It needs no worker; neither does anything here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import types
from pathlib import Path

from mcgyvr.contract import Contract, load
from mcgyvr.worker.bundle import bundle_for

REPO = Path(__file__).resolve().parent.parent
BUNDLE_TOOLS = REPO / "tools" / "bundle"
TASKS = BUNDLE_TOOLS / "python" / "tasks"
EVIDENCE = REPO / "records" / "evidence" / "local-ai-2026-08-02"
CONDITIONS = EVIDENCE / "data" / "context_exp" / "bundles"
INSTRUMENT = EVIDENCE / "instrument"
SHIPPED = REPO / "src" / "mcgyvr" / "prompts" / "python.md"

# Identical to the JS/TS arm's, and that is the point rather than a coincidence.
# Both sets are the same twenty intents — 8 function implementations, 5 bug
# fixes, 3 refactors, 2 type annotations, 2 edge-case hardenings — mapped onto
# mcgyvr's catalog by the same rule, because `refactor` and `edge_case` are not
# in `data/task-catalog.json`. A rate from one arm is comparable with a rate
# from the other only while this holds.
COMPOSITION = {
    "function_implementation": 11,
    "bug_fix": 7,
    "type_annotation": 2,
}


def _by_path(name: str, path: Path) -> types.ModuleType:
    """Import a module by path — neither ``tools/`` nor the evidence is a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _measure() -> types.ModuleType:
    return _by_path("bundle_measure_py_arm", BUNDLE_TOOLS / "measure.py")


def _recovered() -> list[dict[str, str]]:
    """The vendored task set the port was written from."""
    tasks = _by_path("context_tasks_vendored", INSTRUMENT / "context_tasks.py").TASKS
    assert isinstance(tasks, list)
    return tasks


def _task_dirs() -> list[Path]:
    return sorted(d for d in TASKS.iterdir() if d.is_dir())


def _contracts() -> list[Contract]:
    return [load(d / "contract.yaml") for d in _task_dirs()]


def _condition(name: str) -> str:
    return (CONDITIONS / f"{name}.md").read_text(encoding="utf-8")


# --- the port is the measured task set -----------------------------------


def test_the_task_set_is_twenty_tasks() -> None:
    """CLM-0004's n. A different one would not be comparable with its rates."""
    assert len(_task_dirs()) == 20


def test_the_task_ids_are_the_recovered_ones() -> None:
    """Same ids, so a row here lines up with a row in the vendored results."""
    assert [d.name for d in _task_dirs()] == [t["id"] for t in _recovered()]


def test_acceptance_and_reference_are_the_recovered_ones_byte_for_byte() -> None:
    """The half of the port that must not be authored, held to a digest.

    A contract had to be rewritten — mcgyvr renders its own user message from
    structured fields and will not take a pre-rendered one — but the acceptance
    script and the reference solution are what decide whether a cell passes.
    If those were re-authored, the arm would be a new instrument wearing
    CLM-0004's task ids, and its agreement or disagreement with the JS/TS arm
    would mean nothing.
    """
    recovered = {t["id"]: t for t in _recovered()}
    for directory in _task_dirs():
        original = recovered[directory.name]
        for filename, key in (("accept.py", "accept"), ("reference.py", "reference")):
            ported = (directory / filename).read_bytes()
            expected = original[key].encode("utf-8")
            assert hashlib.sha256(ported).hexdigest() == (
                hashlib.sha256(expected).hexdigest()
            ), f"{directory.name}/{filename} is not the recovered {key}"


def test_every_task_ships_a_contract_a_reference_and_an_acceptance_script() -> None:
    for directory in _task_dirs():
        assert (directory / "contract.yaml").is_file(), directory.name
        assert (directory / "reference.py").is_file(), directory.name
        assert (directory / "accept.py").is_file(), directory.name


def test_every_contract_loads_through_the_real_loader() -> None:
    """A contract this project would reject is not one it could dispatch."""
    assert len(_contracts()) == 20


def test_every_task_selects_the_python_bundle() -> None:
    """The arm is about the Python bundle; a target must reach it."""
    for contract in _contracts():
        selected = bundle_for(contract.target)
        assert selected is not None, contract.id
        assert selected.language == "python", contract.id


def test_every_task_declares_a_runnable_acceptance_command() -> None:
    """Acceptance is the contract's, executed — so it has to be there to run.

    The bug-fix tasks carry their command in ``demonstration`` because it fails
    on the task's base by design (#183); every other task carries it in
    ``acceptance``. Both lists are executed, so what matters is that the union
    is non-empty and that the split follows the type.
    """
    for contract in _contracts():
        commands = (*contract.demonstration, *contract.acceptance)
        assert commands, contract.id
        assert all(command == "python accept.py" for command in commands), contract.id
        expects_baseline_failure = contract.type.needs_demonstration_commands
        assert bool(contract.demonstration) == expects_baseline_failure, contract.id


def test_the_composition_matches_the_jsts_arm() -> None:
    """Same mix on both arms, so a difference between them is about language."""
    counts: dict[str, int] = {}
    for contract in _contracts():
        counts[contract.task_type] = counts.get(contract.task_type, 0) + 1
    assert counts == COMPOSITION


def test_the_recovered_intents_map_onto_that_composition() -> None:
    """The mapping is recorded rather than hidden inside a total.

    ``refactor`` and ``edge_case`` are local-ai vocabulary and are not in
    ``data/task-catalog.json``, so those intents are carried by the catalog
    types that own them — exactly as the JS/TS arm did it. A slice by intent
    and a slice by task type are both true and are not the same slice.
    """
    intents: dict[str, int] = {}
    for task in _recovered():
        intents[task["type"]] = intents.get(task["type"], 0) + 1
    assert intents == {
        "function_impl": 8,
        "bug_fix": 5,
        "refactor": 3,
        "type_annotation": 2,
        "edge_case": 2,
    }
    functions = intents["function_impl"] + intents["refactor"]
    assert functions == COMPOSITION["function_implementation"]
    assert intents["bug_fix"] + intents["edge_case"] == COMPOSITION["bug_fix"]
    assert intents["type_annotation"] == COMPOSITION["type_annotation"]


def test_no_task_is_measured_as_unmeasurable() -> None:
    """No contract may declare an output schema the reply parser cannot read."""
    for contract in _contracts():
        assert contract.output_schema == "whole_file", contract.id


# --- the ladder ----------------------------------------------------------


def test_the_ladder_is_nested() -> None:
    """Each condition opens with the one below it, so size is the only variable."""
    c1, c2, c3 = _condition("c1"), _condition("c2"), _condition("c3")
    assert c2.startswith(c1)
    assert c3.startswith(c2)


def test_the_conditions_are_the_vendored_files_not_a_copy() -> None:
    """The arm reads the measured bundles directly, so there is nothing to drift."""
    measure = _measure()
    assert measure.PYTHON.conditions == CONDITIONS


def test_c2_is_the_shipped_bundle_byte_for_byte() -> None:
    """The rig refuses to dispatch otherwise; this says so without a worker."""
    measure = _measure()
    measure.check_c2_is_the_shipped_bundle(measure.PYTHON)

    shipped = bundle_for("solution.py")
    assert shipped is not None
    assert shipped.text.encode("utf-8") == (CONDITIONS / "c2.md").read_bytes()


def test_c0_is_the_absence_of_a_system_prompt() -> None:
    """CLM-0004's c0 is "none — contract only", not an empty file."""
    measure = _measure()
    assert measure.condition_text("c0", measure.PYTHON) == ""


# --- the two arms differ in what Language names, and nothing else ---------


def test_the_arms_share_the_sampler_the_cap_and_the_remediation_round() -> None:
    """One instrument, two task sets. Anything else would be a third variable.

    The sampler, the output cap, the acceptance timeout and the ladder are
    module-level in the rig rather than per-arm, so this is really an assertion
    that they have not been made per-arm in some later edit — which is the
    change that would let the two arms diverge without anyone deciding to.
    """
    measure = _measure()
    for arm in (measure.JSTS, measure.PYTHON):
        assert not hasattr(arm, "temperature")
        assert not hasattr(arm, "max_output_tokens")
    assert measure.TEMPERATURE == 0.0
    assert measure.MAX_OUTPUT_TOKENS == 768
    assert measure.LADDER == ("c0", "c1", "c2", "c3")


def test_the_default_arm_is_still_the_one_144_measured() -> None:
    """Every command line already written down keeps meaning what it meant."""
    measure = _measure()
    assert measure.DEFAULT_LANGUAGE is measure.JSTS
