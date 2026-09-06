"""Every task type the schema offers has something that can execute it.

``task_type`` is a closed vocabulary: nine values, each with a guarantee in
``data/task-catalog.json``, each rendered into the shipped skill with a minimal
example a reader is told is "a shape that is known to validate".

``rename_symbol`` validates and cannot run. It is the sole member of
``deterministic._IN_PROCESS``, which yields a ``Tool`` with no argv; ``drive``
raises ``UnrunnableStepError`` on an empty argv, and ``cli._floor`` reports the
run as ``error``. Nothing anywhere implements the in-process rename — the word
appears in the codebase only in docstrings and in the example. Meanwhile the
catalog still guarantees "every reference the index resolved is renamed", and
``skills/mcgyvr/SKILL.md`` hands an orchestrator a ``rename_symbol`` contract to
copy.

So the one path an agent is most likely to take from the documentation — copy
the example, validate it, run it — spends a contract to arrive at ``error``.

What must be observably true: a task type in the vocabulary can be executed, or
it is not in the vocabulary. Which of the two ``rename_symbol`` becomes is the
port's choice; that validating a contract and running it agree is the
requirement.
"""

from __future__ import annotations

from typing import Any

CONTRACT = """
id: rename-fetch
task_type: {task_type}
task: Rename fetch_page to fetch_document in the module.
target: src/pkg/messy.py
scope:
  allow: ["src/pkg/**"]
"""


def _types() -> tuple[str, ...]:
    """The types a program executes. A model type is run by the ladder."""
    from mcgyvr.catalog import catalog

    return tuple(sorted(t.name for t in catalog().task_types if t.deterministic))


def _runnable(task_type: str) -> bool:
    """Whether anything in the product can carry out a contract of this type."""
    from mcgyvr.contract import loads
    from mcgyvr.deterministic import tool_steps

    contract = loads(CONTRACT.format(task_type=task_type))
    steps: Any = tool_steps(contract)
    if not steps:
        return False  # nothing on the floor binds, and the floor is where it starts
    return all(getattr(step, "argv", ()) for step in steps)


def test_no_task_type_validates_and_then_cannot_run() -> None:
    """The gap between `mcgyvr contract` saying yes and `mcgyvr run` erroring."""
    stranded = [name for name in _types() if not _runnable(name)]
    assert not stranded, (
        f"{', '.join(stranded)} validate as contracts and no executor exists; "
        "a run of one reaches `error` after the contract was accepted"
    )


def test_the_shipped_skill_offers_no_example_that_cannot_run() -> None:
    """The example an agent is told is safe to copy.

    The skill is generated from the schema, so an example surviving here is a
    schema that still offers the type — which is the same defect seen from the
    documentation end.
    """
    from pathlib import Path

    skill = Path.home() / ".claude" / "skills" / "mcgyvr" / "SKILL.md"
    if not skill.is_file():  # not installed in this checkout; the schema test stands
        return
    text = skill.read_text(encoding="utf-8")
    offered = [
        name
        for name in _types()
        if not _runnable(name) and f"task_type: {name}" in text
    ]
    assert not offered, (
        f"the skill hands an orchestrator a {', '.join(offered)} example to "
        "copy, and no executor exists for it"
    )
