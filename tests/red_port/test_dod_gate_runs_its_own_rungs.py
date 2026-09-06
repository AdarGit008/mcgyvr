"""The gate that decides acceptance runs the checks the product ships for it.

``Gate.run`` takes four judging inputs: the adapters, ``acceptance``,
``semantic`` and ``typecheck``. ``drive.gate_workspace`` — the one function both
tiers reach acceptance through — passes two of them. ``TypeCheck`` and
``SemanticCheck`` are constructed nowhere in ``src``; the only constructions in
the tree are in ``tests``.

That is 1105 lines of type checking and 722 of semantic checking, complete and
tested, one keyword argument away from the only place that decides whether work
is accepted. The ghostcall engine is force-included into every wheel to serve
them.

What it costs is a guarantee. ``data/task-catalog.json`` states that a
``type_annotation`` contract means "the project's type checker accepts" the
result. The gate that accepts it never runs a type checker unless the contract
happened to declare one as an acceptance command — which is the operator doing by
hand what the type is supposed to mean.

What must be observably true: a change of a type whose guarantee names a checker
is judged by that checker, without the contract having to ask. Where the object
is built is the port's choice; that the verdict reflects it is the requirement.
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

#: Annotated, and wrong: ``url`` is declared ``int`` and returned as ``str``.
WRONG = "def fetch(url: int) -> str:\n    return url\n"


def _verdict(repo: Path) -> Any:
    """The gate's verdict on a change the type checker rejects."""
    from mcgyvr.contract import loads
    from mcgyvr.sandbox.base import open_sandbox

    contract = loads(ANNOTATE)
    judge = required(
        "judge a change with the type checker the task type's own guarantee "
        "names, without the contract having to declare it",
        lambda: (
            __import__(
                "mcgyvr.drive", fromlist=["gate_typed_workspace"]
            ).gate_typed_workspace
        ),
    )
    with open_sandbox(repo, mode="tempdir") as sandbox:
        target = Path(sandbox.workspace) / "src" / "pkg" / "fetch.py"
        target.write_text(WRONG, encoding="utf-8")
        return judge(contract, sandbox)


def test_a_type_annotation_the_checker_rejects_is_not_accepted(repo: Path) -> None:
    """The guarantee the catalog states, asserted as a verdict.

    ``def fetch(url: int) -> str: return url`` is annotated, parses, formats and
    lints. It is also wrong, and the type is defined by the checker accepting.
    """
    result = _verdict(repo)
    assert not result.passed, (
        "a type_annotation change returning `int` where it declares `str` was "
        "accepted; the catalog guarantees the project's type checker accepts it"
    )
    assert any("fetch" in str(f) for f in result.findings), (
        f"the refusal must name what the checker found: {result.findings}"
    )
