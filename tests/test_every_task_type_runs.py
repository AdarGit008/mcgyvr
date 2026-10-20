"""Every task type and deterministic operation the schema offers has something
that can execute it.

``task_type`` is a closed vocabulary of three task types (``code``, ``chat``,
``agent``), and ``operation`` names one of four deterministic
operations of ``code`` (``format``, ``import_sort``, ``lint_fix``,
``rename_symbol``), each with a guarantee in
``data/task-catalog.json``, each rendered into the shipped skill with a minimal
example a reader is told is "a shape that is known to validate" — rendered
into ``skills/mcgyvr/references/examples.md``, which the shipped skill points
at.

The path an agent is most likely to take from the documentation is: copy the
example, validate it, run it. ``rename_symbol`` is the sole member of
``deterministic.IN_PROCESS``: its step carries no argv and ``drive`` executes it
in process.

What must be observably true: an operation in the vocabulary can be executed,
or it is not in the vocabulary. Validating a contract and running it agree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests._paths import REPO

CONTRACT = """
id: rename-fetch
task_type: code
operation: {operation}
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
"""


def _types() -> tuple[str, ...]:
    """The operations a program executes. A model task type is run by the ladder."""
    from mcgyvr.catalog import catalog

    return tuple(sorted(o.name for o in catalog().operations if o.deterministic))


def _runnable(operation: str, repo: Path) -> bool:
    """Whether a contract naming this operation can actually be carried out.

    Asserted by running it, not by inspecting the step: an in-process step
    legitimately carries an empty ``argv``, so probing the field would say nothing.
    """
    from mcgyvr.contract import loads
    from mcgyvr.deterministic import tool_steps
    from mcgyvr.drive import UnrunnableStepError, run_tool_step
    from mcgyvr.sandbox.base import open_sandbox

    contract = loads(CONTRACT.format(operation=operation))
    steps: Any = tool_steps(contract)
    if not steps:
        return False  # the floor is where this operation starts and nothing binds
    try:
        with open_sandbox(repo, mode="tempdir") as sandbox:
            for step in steps:
                run_tool_step(step, sandbox)
    except UnrunnableStepError:
        return False
    except Exception:
        # A tool that is missing on this machine, or that refuses the fixture,
        # is not the failure under test: the operation had an executor to reach.
        return True
    return True


def test_no_task_type_validates_and_then_cannot_run(repo: Path) -> None:
    """The gap between `mcgyvr contract` saying yes and `mcgyvr run` erroring."""
    stranded = [name for name in _types() if not _runnable(name, repo)]
    assert not stranded, (
        f"{', '.join(stranded)} validate as contracts and no executor exists; "
        "a run of one reaches `error` after the contract was accepted"
    )


def test_the_shipped_skill_offers_no_example_that_cannot_run(repo: Path) -> None:
    """The example an agent is told is safe to copy.

    Read from the repository, not from ``~/.claude``. ``tests/conftest.py``
    repoints ``HOME`` at a fresh tmp dir for every test, so a check against the
    installed copy can never fail — it would return early on every run while
    the committed examples still carry the example.

    Read from ``references/examples.md``: ``SKILL.md`` carries no
    ``operation: {name}`` line, so a grep of it would match nothing for every name
    and pass while checking nothing.
    """
    examples = REPO / "skills" / "mcgyvr" / "references" / "examples.md"
    assert examples.is_file(), f"{examples} is the shipped examples file"
    text = examples.read_text(encoding="utf-8")
    assert text.count("```yaml") >= 1, f"{examples} carries no examples to check"
    offered = [
        name
        for name in _types()
        if not _runnable(name, repo) and f"operation: {name}" in text
    ]
    assert not offered, (
        f"the skill's examples hand an orchestrator a {', '.join(offered)} "
        "example to copy, and no executor exists for it"
    )
