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

from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

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


def _runnable(task_type: str, repo: Path) -> bool:
    """Whether a contract of this type can actually be carried out.

    Asserted by running it, not by inspecting the step. ``argv`` being empty is
    how *today's* floor expresses "nothing to run", and an in-process executor —
    which the docstring above explicitly allows as a fix — would legitimately
    keep it empty. Probing the field would forbid one of the two permitted
    outcomes; running the contract forbids neither.
    """
    from mcgyvr.contract import loads
    from mcgyvr.deterministic import tool_steps
    from mcgyvr.drive import UnrunnableStepError, run_tool_step
    from mcgyvr.sandbox.base import open_sandbox

    contract = loads(CONTRACT.format(task_type=task_type))
    steps: Any = tool_steps(contract)
    if not steps:
        return False  # the floor is where this type starts and nothing binds
    try:
        with open_sandbox(repo, mode="tempdir") as sandbox:
            for step in steps:
                run_tool_step(step, sandbox)
    except UnrunnableStepError:
        return False
    except Exception:
        # A tool that is missing on this machine, or that refuses the fixture,
        # is not the failure under test: the type had an executor to reach.
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
    the committed skill still carries the example.
    """
    skill = REPO / "skills" / "mcgyvr" / "SKILL.md"
    assert skill.is_file(), f"{skill} is the shipped skill and must be readable"
    text = skill.read_text(encoding="utf-8")
    offered = [
        name
        for name in _types()
        if not _runnable(name, repo) and f"task_type: {name}" in text
    ]
    assert not offered, (
        f"the skill hands an orchestrator a {', '.join(offered)} example to "
        "copy, and no executor exists for it"
    )
