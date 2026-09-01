"""X07 — the cheapest family on the ladder is a hole, and a missing tool must cost
something visible rather than nothing at all.

This is not a gap between mcgyvr and local-ai. It is a family the ladder declares,
that four task types are routed to by name, and that can never contain anything.
``route._why_empty`` says so in the code's own words: the deterministic family
"binds no rung: it is tools, not a model on a source. Its executor is the
deterministic tier (#81), which is not reached through the ladder." The reasoning is
sound — a rung's family is derived from whether its *source* needs a credential, and
a program has no source — but the consequence is that every ``starts_on:
deterministic`` type in ``data/task-catalog.json`` plans an empty family, and
:func:`~mcgyvr.escalate.escalate` skips it silently on its way to a model.

What that costs is exact and it is the reason this lever is worth its size:
``format``, ``import_sort``, ``lint_fix`` and ``rename_symbol`` are the four types a
tool does perfectly, for free, deterministically. Today each of them is a model
call. The floor the catalog wrote down is not being enforced downward; it is being
skipped.

Three statements, and the second and third are what stop the fix from being worse
than the hole:

* **There is something to run.** Asserted through :func:`~mcgyvr.route.plan`,
  against the real catalog, for every type whose ``starts_on`` is the deterministic
  family — read from the catalog rather than listed here, so a fifth type added to
  the data file is covered on the day it is added. Asserted as a plan and not as an
  execution because a plan is the thing mcgyvr can inspect before a token is spent,
  and "the ladder's cheapest family is empty" is exactly the fact a plan is supposed
  to be able to show.

* **A missing tool degrades rather than halts.** ``ruff`` not being installed is an
  ordinary state of an ordinary machine. It must not turn a ``format`` contract into
  a task that cannot run: the work is still doable, just dearly, and the next family
  up can do it. This is asserted as *where the work lands*, not as an absence of an
  exception, because a route that returned a family with nothing in it would also
  not raise.

* **The degradation is recorded.** A silent fallback is the failure mode that makes
  a missing dependency invisible: the contract still completes, the operator sees no
  error, and the only evidence is a model bill that is quietly larger than it should
  be. So the reason is asserted to name three things — the task type, the family it
  left and the family it landed in. A constant sentence can satisfy any one of them
  and not all three, which is the point of asserting all three.

The first test uses the real routing code and no seam: :func:`~mcgyvr.route.plan`
exists, answers, and answers "nothing". That is a behavior that is wrong rather than
a capability that is missing, and the honest way to say so is to assert against the
thing that is wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.pool import SourceMap, source_map
from mcgyvr.route import plan
from tests.red_port.conftest import required

ONWARD = (
    "route a deterministic task onward to the next family when its tool is not "
    "installed, recording what the missing dependency cost"
)

# A keyless install: one local rung, no credential anywhere. The cheapest ladder
# a stranger can have, and the one where a deterministic tool is worth most.
KEYLESS = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: ollama
    max_parallel: 2
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""

DETERMINISTIC = tuple(t.name for t in catalog().task_types if t.starts_on.rank == 0)


def _route() -> Any:
    return required(
        ONWARD,
        lambda: __import__("mcgyvr.deterministic", fromlist=["route"]).route,
    )


def _installed() -> tuple[Config, SourceMap]:
    config = parse(KEYLESS)
    return config, source_map(config)


def _contract_of(task_type: str) -> Contract:
    """The smallest valid contract of ``task_type``.

    Every deterministic type's required evidence is structural, so none of them
    needs an acceptance command — which is itself part of why they belong on the
    cheapest family.
    """
    return load_contract(
        f"id: tidy-{task_type.replace('_', '-')}\n"
        f"task_type: {task_type}\n"
        f"task: Tidy the package.\n"
        f"target: src/pkg/fetch.py\n"
        f"scope:\n"
        f'  allow: ["src/**"]\n'
    )


def test_a_deterministic_task_type_has_something_to_run_on_its_own_floor() -> None:
    """The catalog's cheapest floor is a floor, not a label.

    Every type is checked rather than one, because the emptiness is structural: a
    fix that special-cased ``format`` would leave the other three routed to nothing,
    and the catalog is data, so the set is read from it.
    """
    config, pool = _installed()
    assert DETERMINISTIC, (
        "no task type starts on the deterministic family, so this test asserts "
        "nothing — check data/task-catalog.json"
    )

    planned = {
        task_type: plan(config, pool, _contract_of(task_type))
        for task_type in DETERMINISTIC
    }
    empty = {name: found.reason for name, found in planned.items() if not found.steps}

    assert not empty, (
        f"{len(empty)} of {len(DETERMINISTIC)} deterministic task types plan nothing "
        f"to run on their own floor, so each of them is a model call for work a tool "
        f"does for free: "
        + "; ".join(f"{name}: {reason}" for name, reason in empty.items())
    )


def test_a_task_whose_tool_is_missing_routes_onward_instead_of_halting() -> None:
    """A machine without ruff can still get its file formatted, just dearly.

    Asserted on the family the work lands in. "It did not raise" would be satisfied
    by a route that landed nowhere, which is the halt this is about.
    """
    config, pool = _installed()
    contract = _contract_of(DETERMINISTIC[0])

    landed = _route()(config, pool, contract, installed=frozenset())

    family = getattr(landed, "family", None)
    assert family is not None and family.name != "deterministic", (
        f"a {contract.type.name!r} contract with no tool installed did not leave the "
        f"deterministic family: it landed on {family!r}, which has nothing to run it"
    )
    assert getattr(landed, "steps", ()), (
        f"the work moved to the {family.name!r} family and that family offers no "
        f"rung either, so the task still cannot run — this is a halt wearing a "
        f"different family's name"
    )


def test_the_cost_of_the_missing_dependency_is_recorded_rather_than_silent() -> None:
    """A fallback nobody can see is a bill nobody can explain.

    Three specifics are required of the reason, because any one of them alone is
    satisfiable by a fixed sentence: which contract degraded, which family it was
    supposed to run on, and which family is now paying for it.
    """
    config, pool = _installed()
    contract = _contract_of(DETERMINISTIC[0])

    landed = _route()(config, pool, contract, installed=frozenset())

    recorded = getattr(landed, "degradations", ())
    assert recorded, (
        f"a {contract.type.name!r} contract fell off its own floor and nothing was "
        f"recorded: the only trace of the missing tool is a larger model bill"
    )
    said = " ".join(str(entry) for entry in recorded)
    for expected in (contract.type.name, "deterministic", landed.family.name):
        assert expected in said, (
            f"the degradation does not name {expected!r}, so a reader cannot tell "
            f"what degraded, where it should have run, or what is paying for it "
            f"instead. It said: {said!r}"
        )


def test_a_degradation_that_lands_nowhere_does_not_claim_a_model_paid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing above the floor offers a rung; the record must say so, not lie."""
    monkeypatch.delenv("MCGYVR_TEST_KEY_THAT_IS_NOT_SET", raising=False)
    config = parse(
        """
version: 1
sources:
  vendor:
    base_url: https://api.example.com/v1
    api: openai
    max_parallel: 4
    api_key_env: MCGYVR_TEST_KEY_THAT_IS_NOT_SET
ladder:
  tiers:
    - name: api_big
      source: vendor
      model: vendor-large
"""
    )
    pool = source_map(config)
    contract = _contract_of(DETERMINISTIC[0])

    landed = _route()(config, pool, contract, installed=frozenset())

    degradations = getattr(landed, "degradations", ())
    assert degradations, "no degradation was recorded"
    recorded = degradations[0]
    said = str(recorded)
    assert "paid for with a model" not in said, (
        f"nothing above the floor can run the work, yet the degradation claims a "
        f"model is paying for it: {said!r}"
    )
    assert recorded.as_record().get("reason"), (
        f"the degradation carries no reason for landing nowhere: {said!r}"
    )


def test_planning_language_ownership_does_not_import_the_gate() -> None:
    """`_language_of` answers by extension; importing the gate is the defect."""
    import subprocess
    import sys

    code = (
        "import sys; "
        "from mcgyvr.deterministic import _language_of; "
        "assert _language_of('src/pkg/fetch.py') == 'python'; "
        "assert _language_of('src/pkg/app.tsx') == 'js/ts'; "
        "assert _language_of('README.md') is None; "
        "assert 'mcgyvr.gate' not in sys.modules, 'planning imported the gate package'"
    )
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)
