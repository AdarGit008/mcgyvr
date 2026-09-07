"""The gate that decides acceptance runs the checks the product ships for it.

``Gate.run`` takes four judging inputs: the adapters, ``acceptance``,
``semantic`` and ``typecheck``. ``drive.gate_workspace`` — the one function both
tiers reach acceptance through — passes two of them. ``TypeCheck`` and
``SemanticCheck`` are constructed nowhere in ``src``; the only constructions in
the tree are in ``tests``. That is 1105 lines of type checking and 722 of
semantic checking, complete and tested, one keyword argument away from the only
place that decides whether work is accepted, with the ghostcall engine
force-included into every wheel to serve them.

What it costs is a guarantee. ``data/task-catalog.json`` states that a
``type_annotation`` contract means "the project's type checker accepts" the
result. The gate that accepts it never runs a type checker unless the contract
happened to declare one as an acceptance command — which is the operator doing
by hand what the type is supposed to mean.

**Asserted through ``gate_workspace``, not through a new function beside it.**
The whole finding is "the capability exists and nothing calls it"; a test that
required a fresh ``gate_typed_workspace`` could be satisfied by adding a second
entry point that the run does not use, leaving the defect exactly where it is.
So the verdict is taken from the function the run actually reaches.

**And the fixture declares a checker.** ``test_d17_typecheck_and_mutation.py::
test_a_repository_that_declares_no_checker_is_not_failed_for_the_absence`` holds
that a repository with no type checker is not failed for the absence, and
``gate/typecheck.py:238`` says the same. Demanding a rejection on the shared
``repo`` fixture — which declares nothing — would contradict both. A repository
that asked for a type checker is the case where the guarantee applies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.red_port.conftest import required

ANNOTATE = """
id: annotate-fetch
task_type: type_annotation
task: Add type annotations to fetch.
target: src/pkg/fetch.py
stop_conditions:
  - A helper's return type cannot be determined from its callers.
acceptance: ["python3 -c 'import sys; sys.exit(0)'"]
limits:
  max_output_tokens: 1024
scope:
  allow: ["src/pkg/**"]
"""

#: Annotated and wrong: ``url`` is declared ``int`` and returned as ``str``.
WRONG = "def fetch(url: int) -> str:\n    return url\n"

#: Annotated and right. The same call must accept this, or the gate is a wall.
RIGHT = "def fetch(url: str) -> str:\n    return url\n"


def _declare_mypy(repo: Path) -> None:
    """Give the repository a type checker of its own, and commit it.

    Committed, as ``test_d17`` does it, so the declaration is part of the base
    the change is measured against rather than something the change introduced.
    """
    from tests.red_port.conftest import git

    (repo / "pyproject.toml").write_text(
        '[tool.mypy]\npython_version = "3.12"\n', encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "declare a type checker")


def _verdict(repo: Path, source: str) -> Any:
    """The verdict the run itself reaches on a change to the target."""
    from mcgyvr.contract import loads
    from mcgyvr.drive import gate_workspace
    from mcgyvr.sandbox.base import open_sandbox

    _declare_mypy(repo)
    contract = loads(ANNOTATE)
    with open_sandbox(repo, mode="tempdir") as sandbox:
        target = Path(sandbox.workspace) / "src" / "pkg" / "fetch.py"
        target.write_text(source, encoding="utf-8")
        return gate_workspace(contract, sandbox)


def test_an_annotation_the_declared_checker_rejects_is_not_accepted(
    repo: Path,
) -> None:
    """The guarantee the catalog states, asserted as the run's own verdict.

    ``def fetch(url: int) -> str: return url`` is annotated, parses, formats and
    lints clean. It is also wrong, and this type is *defined* by the checker
    accepting.
    """
    result = _verdict(repo, WRONG)
    assert not result.accepted, (
        "a type_annotation change returning `int` where it declares `str` was "
        "accepted; the catalog guarantees the project's type checker accepts it"
    )
    assert any("fetch" in str(f) for f in result.findings), (
        f"the refusal must name what the checker found: {result.findings}"
    )


def test_an_annotation_the_declared_checker_accepts_is_accepted(repo: Path) -> None:
    """The direction that stops the fix from being "always refuse".

    Without this, a gate rung that rejected every ``type_annotation`` change
    would satisfy the test above and pass for a fix.
    """
    result = _verdict(repo, RIGHT)
    assert result.accepted, (
        f"a correct annotation must be accepted by the same call: "
        f"{result.findings} {result.environment_issues}"
    )


def test_the_semantic_check_reaches_the_same_verdict_path() -> None:
    """The second rung the docstring argues for, asserted separately.

    ``semantic`` is the other input ``Gate.run`` accepts and ``gate_workspace``
    does not pass. Stated on its own so that wiring the type checker alone does
    not read as having wired both.
    """
    required(
        "judge a change with the semantic check the gate already ships, from "
        "the function the run reaches acceptance through",
        _semantic_seam,
    )


def _semantic_seam() -> Any:
    """The seam that says the semantic rung is wired. Named, not designed.

    A port may express this as a parameter, a default, or a rung the gate builds
    for itself; what must be true is that a caller can tell the semantic check
    ran. ``GateResult`` already distinguishes a rung that could not say whether
    it ran (``inconclusive``), so that is where the answer belongs.
    """
    from mcgyvr.gate.runner import GateResult

    if "semantic" not in {f.name for f in GateResult.__dataclass_fields__.values()}:
        raise AttributeError(
            "GateResult carries no way to tell whether the semantic rung ran"
        )
    return GateResult
