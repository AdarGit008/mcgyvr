"""D17 — the gate reads types when the repository asked for them, and knows which
hazards are wrong from which are merely unfashionable.

mcgyvr's gate runs syntax, structure, secrets, scope, lint, format, a semantic
resolution rung and the contract's acceptance commands. Two things it does not do.

**It never runs a type checker.** ``locate_type_check_command`` exists
(``src/mcgyvr/gate/adapters/python.py``) and is careful about the thing that is
easy to get wrong — it emits a command only for a repository that *declared* a
checker, in any of the files that checker reads its own configuration from, and it
appends no target because mypy's ``exclude`` does not apply to a file named on the
command line. Nothing in the gate calls it. So a worker can annotate a function
with a return type it does not return and the gate accepts.

That asymmetry is why both halves are asserted here and why both go through the
same seam. The half that says a repository declaring no checker is not failed for
the absence of one is **true today by accident**: there is no step, so there is
nothing to be absent. Asserting it against today's gate would be a green test that
holds nothing, and it would stay green through a port that shipped a checker run
unconditionally against every repository — which is precisely ADR-0006's mistake,
substituting mcgyvr's opinion for what the project wrote down. Routed through the
missing capability, it is RED now and it is a real constraint on the port.

**It has no hazard family with a severity.** ``_HazardVisitor`` collects three
language hazards and every one of them rejects. That is fine while the list is
mutable defaults, bare excepts and wildcard imports. It stops being fine the moment
the list grows a member that is a house-style preference, because then a change
that is *correct* is rejected for a fashion — and the cheapest possible fix, a
deterministic rewrite at zero model spend, is unreachable from a verdict that only
says "no".

So the split is the lever, and the two halves are asserted as one pair:

* A function that mutates the object its caller passed in is **correctness**. It
  changes state the caller still owns, the caller's next read is wrong, and no
  amount of reformatting makes it right. It rejects.
* ``from typing import List`` where ``list[int]`` is the pinned form is **style**.
  The code is correct. Rejecting it spends a whole attempt — a model call, a gate
  run, a rung of the ladder — to change six characters that a tool could change for
  nothing.

Asserting only the first would pass against a gate that rejected on both, which is
today's gate plus one more hazard and is the outcome this test exists to prevent.
So the style half asserts **both** that the change is accepted and that the hazard
was nonetheless reported, and it fails today whichever way the machine is set up.
Where ruff is installed, it *already* reports ``UP035``/``UP006`` — and every
``Finding`` rejects, so the change costs an attempt over six characters. Where ruff
is not installed, nothing reports it at all. Both are the same missing behavior seen
from two sides: there is no axis on which a finding can be said out loud without
also being fatal.

Those two run against the real :class:`~mcgyvr.gate.Gate` rather than through a
seam, because the surface they need already exists — ``findings`` reject and
``observations`` do not, and the semantic rung already lives on the second one. What
is missing is a hazard family that uses it.
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

    Deliberately untyped: how the step reaches a run is the port's decision, and a
    statically-checked call here would be this test choosing it. What the tests
    below assert is the :class:`~mcgyvr.gate.GateResult` that comes back.
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

    ADR-0006 put the choice of checker outside this project. A gate that ran one
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
    The pair is the behavior, and today's gate misses one half or the other
    depending on whether ruff is on the machine.
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
