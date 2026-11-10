"""X07 — a deterministic operation plans a tool on its own floor.

The deterministic family binds no rung — a rung's family is derived from whether its
*source* needs a credential, and a program has no source — so
:func:`~mcgyvr.route.plan` fills it from :func:`mcgyvr.deterministic.tool_steps`.
``format``, ``import_sort``, ``lint_fix`` and ``rename_symbol`` are operations a
tool does perfectly, for free, deterministically; a contract names one as
``task_type: code`` with ``operation:``.

**There is something to run.** Asserted through :func:`~mcgyvr.route.plan`, against
the real catalog, for every operation whose ``starts_on`` is the deterministic
family — read from the catalog rather than listed here, so an operation added to
the data file is covered on the day it is added. Asserted as a plan and not as an
execution because a plan is the thing mcgyvr can inspect before a token is spent,
and "the ladder's cheapest family is empty" is exactly the fact a plan is supposed
to be able to show.

The tests use the real routing code and no seam.
"""

from __future__ import annotations

from mcgyvr.catalog import catalog
from mcgyvr.config import Config, parse
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.ladder_map import UnitMap, unit_map
from mcgyvr.route import plan

# A keyless install: one local rung, no credential anywhere. The cheapest ladder
# a stranger can have, and the one where a deterministic tool is worth most.
KEYLESS = """\
units:
  local_qwen-7b:
    address: http://localhost:11434
    model: qwen2.5-coder:7b
    rig: workstation
    width: 2
ladder:
- local_qwen-7b
"""

DETERMINISTIC = tuple(o.name for o in catalog().operations if o.starts_on.rank == 0)


def _installed() -> tuple[Config, UnitMap]:
    config = parse(KEYLESS)
    return config, unit_map(config)


def _contract_of(operation: str) -> Contract:
    """The smallest valid contract naming ``operation``.

    Every deterministic operation's required evidence is structural, so none of them
    needs an acceptance command — which is itself part of why they belong on the
    cheapest family.
    """
    return load_contract(
        f"id: tidy-{operation.replace('_', '-')}\n"
        f"task_type: code\n"
        f"operation: {operation}\n"
        f"task: Tidy the package.\n"
        f"target: src/pkg/fetch.py\n"
        f"scope:\n"
        f'  allow: ["src/**"]\n'
    )


def test_a_deterministic_operation_has_something_to_run_on_its_own_floor() -> None:
    """The catalog's cheapest floor is a floor, not a label.

    Every operation is checked rather than one, because the emptiness is structural: a
    fix that special-cased ``format`` would leave the other three routed to nothing,
    and the catalog is data, so the set is read from it.
    """
    config, pool = _installed()
    assert DETERMINISTIC, (
        "no operation starts on the deterministic family, so this test asserts "
        "nothing — check data/task-catalog.json"
    )

    planned = {
        operation: plan(config, pool, _contract_of(operation))
        for operation in DETERMINISTIC
    }
    empty = {name: found.reason for name, found in planned.items() if not found.steps}

    assert not empty, (
        f"{len(empty)} of {len(DETERMINISTIC)} deterministic operations plan nothing "
        f"to run on their own floor, so each of them is a model call for work a tool "
        f"does for free: "
        + "; ".join(f"{name}: {reason}" for name, reason in empty.items())
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
