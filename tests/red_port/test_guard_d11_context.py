"""D11 — a dependency is stated, or it is refused. It is never described.

GREEN by design. The thing being ported over assembles context by sending
dependency *file bodies*, which is cheaper to write and strictly worse: it
spends the budget on lines the worker will not change, and when a dependency
cannot be located it degrades into an approximation nobody can tell from a fact.
mcgyvr's answer is ADR-0007 — the decomposer names a symbol, the index states
what it looks like, and if the index cannot state it the unit of work does not
get emitted.

``tests/test_orchestrator_decompose.py`` already holds the two halves separately:
that a dep's ``signature`` equals the index's text, and that an unknown symbol
becomes a refusal. Both would survive the regression this file exists to stop.
A port that kept the ``signature`` field, filled it correctly, and *also* pasted
the dependency's source into the prompt would pass every one of them — the field
would still be right, and nothing asserts what the worker actually receives.

So the level here is the prompt:

* **The body is asserted absent from what the worker is handed**, end to end,
  decompose through render. The dependency file carries a marker inside its
  function body that appears nowhere in its declaration, so "the signature
  arrived" and "only the signature arrived" are two different assertions and
  both are made. The target's own content *is* inlined and must be — that is
  the file being changed — so the absent-text check is aimed at the dependency
  file alone, which is the only thing that makes it meaningful.
* **The refusal covers the cases that are not a typo.** The existing tests refuse
  an unknown symbol and an import. This one refuses a file the index does not
  hold and a file the parser could not read — the two ways a real repository
  produces a symbol that exists to a human and not to the index. Those are
  exactly the cases where "describe it approximately" is tempting, and the
  assertion is that nothing was emitted at all rather than that something
  hedged was.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from mcgyvr.orchestrator.decompose import (
    DepRef,
    Proposal,
    RecordedProposer,
    decompose,
)
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.worker.prompt import build_prompt

BODY_MARKER = "MARKER_ONLY_IN_THE_DEPENDENCY_BODY"

DEPENDENCY = f'''\
def paginate(items: list[int], size: int = 10) -> list[int]:
    """Return one page of items."""
    {BODY_MARKER} = size
    return items[:size]
'''

TARGET = """\
from pagination import paginate


def listing(items):
    return items
"""

PROPOSAL = Proposal(
    task_type="docstring",
    task="Document listing() and say how it pages its items.",
    target="listing.py",
    deps=(DepRef(path="pagination.py", symbol="paginate", note="page with this"),),
    stop_conditions=("The pager's contract is ambiguous.",),
)


def _git(root: Path, *args: str) -> None:
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {done.stderr.strip()}")


@pytest.fixture
def index(tmp_path: Path) -> Index:
    """A repository where one file's function is another file's dependency."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pagination.py").write_text(DEPENDENCY)
    (root / "listing.py").write_text(TARGET)
    # Unparseable on purpose: a real repository has one, and a symbol inside it
    # is exactly the dependency that tempts an approximation.
    (root / "broken.py").write_text("def paginate(:\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "test")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return build_index(root)


def test_a_dependency_reaches_the_worker_as_a_signature_and_not_as_a_body(
    index: Index,
) -> None:
    """What the worker is handed carries the declaration and none of the source.

    Three assertions and they are not the same one. The signature is present, so
    the dependency was actually communicated. The body marker is absent from the
    dependency's own signature, so the extractor did not simply slice too much.
    And the marker is absent from the *whole rendered prompt*, which is the only
    place a body could be smuggled back in — a second section, a re-read, an
    "for reference" block — while every field-level assertion still passed.

    The target's own content is asserted present alongside, because a prompt that
    had lost that too would satisfy the absence check while being useless.
    """
    result = decompose(
        index, "the listing pager", propose=RecordedProposer((PROPOSAL,))
    )

    assert result.refusals == (), f"unexpectedly refused: {result.refusals}"
    (built,) = result.contracts
    (dep,) = built.deps
    assert dep.path == "pagination.py"
    assert "def paginate(" in dep.signature, (
        f"no declaration was stated: {dep.signature!r}"
    )
    assert BODY_MARKER not in dep.signature, (
        "the dependency's body rode along in the signature"
    )

    prompt = build_prompt(built)

    assert "signatures only" in prompt.user, (
        "the worker was not told these are signatures"
    )
    assert dep.signature.splitlines()[0] in prompt.user, (
        "the signature never reached the worker"
    )
    assert BODY_MARKER not in prompt.user, "the dependency's body reached the worker"
    assert "return items[:size]" not in prompt.user, (
        "the dependency's source reached the worker"
    )
    assert "def listing(items):" in prompt.user, (
        "sanity: the target's own content is still sent"
    )


@pytest.mark.parametrize(
    ("dep", "why"),
    [
        (
            DepRef(path="nowhere.py", symbol="paginate"),
            "a file the index does not hold",
        ),
        (
            DepRef(path="broken.py", symbol="paginate"),
            "a file the parser could not read",
        ),
    ],
)
def test_a_dependency_whose_signature_cannot_be_stated_is_refused(
    index: Index, dep: DepRef, why: str
) -> None:
    """Nothing is emitted, and nothing hedged is emitted either.

    Both cases name a symbol a human would say exists — one in a path that is not
    indexed, one in a file that is in the tree but did not parse. Neither is a
    typo, and both are where an approximation would be produced by a system that
    had one to fall back on.

    Asserted on the emptiness of ``contracts`` rather than on the refusal alone:
    a port that emitted the contract *and* recorded a note would leave the refusal
    list looking right while the weaker behaviour shipped. The reason is checked
    to name the symbol, so a reader of the refusal can act on it.
    """
    proposal = replace(PROPOSAL, deps=(dep,))

    result = decompose(
        index, "the listing pager", propose=RecordedProposer((proposal,))
    )

    assert result.contracts == (), f"a contract was emitted for {why}"
    (refusal,) = result.refusals
    assert "signature" in refusal.reason, (
        f"the refusal does not say why: {refusal.reason!r}"
    )
    assert "paginate" in refusal.reason, "the refusal does not name the dependency"
