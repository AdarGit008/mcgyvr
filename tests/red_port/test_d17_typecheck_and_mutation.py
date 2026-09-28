"""D17 — the gate reads types when the repository asked for them, and knows which
hazards are wrong from which are merely unfashionable.

**The gate runs the type checker a repository declared, and only that one**
(:class:`~mcgyvr.gate.typecheck.TypeCheck`, handed to ``Gate.run(typecheck=...)``).
A repository declaring no checker is not failed for the absence of one: a checker
run unconditionally against every repository would substitute mcgyvr's opinion for
what the project wrote down. Both halves go through the same seam.

**The hazard family is split by severity** (:mod:`mcgyvr.gate.typecheck`), and the
two halves are asserted as one pair:

* A function that mutates the object its caller passed in is **correctness**. It
  changes state the caller still owns, the caller's next read is wrong, and no
  amount of reformatting makes it right. It rejects.
* ``from typing import List`` where ``list[int]`` is the pinned form is **style**.
  The code is correct. Rejecting it spends a whole attempt — a model call, a gate
  run, a rung of the ladder — to change six characters that a tool could change for
  nothing.

Asserting only the first would pass against a gate that rejected on both, which is
the outcome this test exists to prevent. So the style half asserts **both** that the
change is accepted and that the hazard was nonetheless reported.

Those two run against the real :class:`~mcgyvr.gate.Gate`: ``findings`` reject and
``observations`` do not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcgyvr.gate import ChangeSet, Gate
from tests.red_port.conftest import git, required

TYPECHECK = "run the type checker a repository declared, over the lines a worker added"

MUTATES = """def merge_into(target, extra):
    target.append(extra)
    return target
"""

DEPRECATED_FORM = """from typing import List


def sizes(rows: List[int]) -> int:
    return len(rows)
"""

MISTYPED = """def count(rows: list[int]) -> int:
    return rows
"""


def _typecheck() -> Any:
    return required(
        TYPECHECK,
        lambda: __import__("mcgyvr.gate.typecheck", fromlist=["TypeCheck"]).TypeCheck,
    )


def _declare_mypy(repo: Path) -> None:
    """Give the repository a type checker of its own, and commit it.

    Committed rather than left in the tree so the declaration is part of the base
    the change is measured against — a worker that added the config file would be
    a different test.
    """
    (repo / "pyproject.toml").write_text(
        '[tool.mypy]\npython_version = "3.12"\n', encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "declare mypy")


def _worker_wrote(repo: Path, name: str, source: str) -> ChangeSet:
    """The change a worker left behind, as the gate sees it."""
    (repo / "src" / "pkg" / name).write_text(source, encoding="utf-8")
    return ChangeSet.detect(repo, git(repo, "rev-parse", "HEAD").strip())


def _typed_gate() -> Any:
    """The gate, with somewhere to hand a type-check step.

    Returned as ``Any``: the tests below assert the
    :class:`~mcgyvr.gate.GateResult` that comes back, not how the type-check
    step reaches the run.
    """
    return Gate()


def test_a_type_error_on_an_added_line_fails_the_gate_when_the_repo_declares_one(
    repo: Path,
) -> None:
    """The repository asked to be type-checked; the worker's line does not check."""
    _declare_mypy(repo)
    changed = _worker_wrote(repo, "count.py", MISTYPED)

    result = _typed_gate().run(changed, typecheck=_typecheck()(repo))

    assert not result.accepted, (
        "a function annotated `-> int` that returns its `list[int]` argument was "
        "accepted by a repository that declares mypy: the gate never asked"
    )
    assert any(f.path.endswith("count.py") for f in result.findings), (
        f"the change was rejected, but nothing points at the file that does not "
        f"type-check: {result.findings}"
    )


def test_a_repository_that_declares_no_checker_is_not_failed_for_the_absence(
    repo: Path,
) -> None:
    """No declaration, no verdict — and no complaint either.

    The choice of checker is the repository's, not this project's. A gate that ran one
    anyway would apply a bar the repository never agreed to, and a gate that
    recorded "no type checker" as an environment issue would degrade every install
    that never wanted one.
    """
    changed = _worker_wrote(repo, "count.py", MISTYPED)

    result = _typed_gate().run(changed, typecheck=_typecheck()(repo))

    assert result.accepted, (
        f"a repository that declares no type checker was failed anyway: "
        f"{result.findings}"
    )
    assert not any("type" in issue.lower() for issue in result.environment_issues), (
        f"the absence of a checker nobody asked for is reported as a degraded run: "
        f"{result.environment_issues}"
    )


def test_a_function_that_mutates_its_callers_argument_is_rejected(repo: Path) -> None:
    """In-place mutation of a parameter is a correctness fault, so it rejects.

    The caller still owns that object and its next read is wrong. This is the one
    hazard family that must reject, and it is asserted on the verdict rather than on
    the presence of a note, because a note that does not stop the change from
    landing has not prevented anything.
    """
    changed = _worker_wrote(repo, "merge.py", MUTATES)

    result = Gate().run(changed)

    assert not result.accepted, (
        "a function that appends to the list its caller passed in was accepted: "
        "the caller's object is changed under it, and no gate rung looked"
    )
    assert any(f.path.endswith("merge.py") for f in result.findings), (
        f"the change was rejected, but not for the mutation: {result.findings}"
    )


def test_a_deprecated_typing_form_is_reported_and_does_not_reject(repo: Path) -> None:
    """Style is said out loud and costs nothing — both halves, or neither is the point.

    Reporting alone is a gate that rejects correct code over six characters, which
    spends a model call and a rung of the ladder on work a formatter does for free.
    Accepting alone is a gate that never looked, and the operator learns nothing.
    The pair is the behavior.
    """
    changed = _worker_wrote(repo, "sizes.py", DEPRECATED_FORM)

    result = Gate().run(changed)

    assert result.accepted, (
        f"`from typing import List` is correct code in the wrong dialect and it "
        f"rejected the change: {result.findings}"
    )
    assert any(f.path.endswith("sizes.py") for f in result.observations), (
        "the deprecated typing form was neither reported nor rejected — the gate "
        "did not look, so there is no style half to distinguish from correctness"
    )
