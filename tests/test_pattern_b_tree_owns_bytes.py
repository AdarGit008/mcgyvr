"""Pattern B — the tree owns the bytes, in the three levers that rewrite them.

Delivery takes an :class:`~mcgyvr.deliver.Accepted` minted off the tree, and no
verdict carries a ``value`` beside it. The three levers that rewrite or sample a
tree each hold the same rule in their own shape:

``cleanup``
    :func:`mcgyvr.cleanup.tidy` may rewrite an **accepted** change's bytes, and
    then :attr:`~mcgyvr.cleanup.Cleanup.regate` is true and the detail line says
    the gate wants re-running: the verdict was reached on the bytes that went
    in, and no rung has read the bytes that come out.

``consensus``
    :func:`mcgyvr.consensus.best_of` resets the workspace after every draw,
    including the winning one, so a losing draw leaks nowhere. The winner
    arrives as an :class:`~mcgyvr.deliver.Accepted`, minted in the draw's
    workspace before that reset.

``repair``
    :class:`mcgyvr.repair.RepairOutcome` carries the paths it changed and no
    ``content``: ``repair`` mutates the tree in place, and the tree is the copy.

The rule all three are measured against:

    The tree is the owner. Content never travels as a value, and one seam
    commits.

with the single exception the codebase already argues for:
:class:`~mcgyvr.deliver.Accepted`, where the bytes travel *bound* — minted off
the tree the verdict was reached in, carrying the digest that lets the far end
notice a substitution. Bound bytes are not a value channel. The last test here
is the guard that keeps the exception from widening into the rule again.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from mcgyvr.cleanup import tidy
from mcgyvr.consensus import best_of
from mcgyvr.contract import Contract, loads
from mcgyvr.deliver import Accepted
from mcgyvr.gate.findings import Finding
from mcgyvr.gate.runner import GateResult
from mcgyvr.repair import RepairOutcome
from mcgyvr.sandbox import Sandbox

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/pkg/**"]
limits:
  attempts: 5
"""

#: Valid Python that the gate accepts and the formatter still rewrites — the
#: case ``cleanup`` exists for, on the branch where nothing tells the caller the
#: verdict is now about different bytes.
LOOSE = "def fetch(url):\n    return  url\n"


@pytest.fixture
def contract() -> Contract:
    return loads(CONTRACT)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A one-commit repository holding ``contract.target``."""
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "fetch.py").write_text("def fetch(url):\n    return url\n")
    env = ["-c", "user.email=t@example.invalid", "-c", "user.name=Test"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), *env, "commit", "-qm", "base"],
        check=True,
        capture_output=True,
    )
    return root


def test_a_cleaned_acceptance_says_the_verdict_is_stale() -> None:
    """An accepted change the formatter rewrote says its verdict is stale.

    A rejected change gets re-run because the rejection has to be cleared; an
    accepted one would otherwise be carried forward under a verdict reached on
    the bytes the formatter replaced. So *any* rewrite makes the verdict stale,
    because the thing that makes a verdict true is the bytes it was
    computed over, and a gate run costs no tokens — which is the same argument
    this module already makes for cleaning instead of dispatching.
    """
    cleaned = tidy(content=LOOSE, result=GateResult(), target="src/pkg/fetch.py")

    assert cleaned.cleaned, "the fixture must be a file the formatter rewrites"
    assert cleaned.accepted, "and one the gate accepted, which is the open branch"
    assert cleaned.content != LOOSE, "the bytes carried forward are not the judged ones"
    assert cleaned.regate, (
        "the formatter replaced the bytes the gate reached its verdict on, so "
        "the verdict is about a file that no longer exists; a caller told "
        "`regate` is False will deliver bytes no rung has read"
    )
    assert "re-run" in cleaned.detail or "re-gate" in cleaned.detail, (
        f"the operator-facing line must say so too, and says {cleaned.detail!r}"
    )


def test_the_winning_draw_arrives_bound_to_the_tree_it_was_judged_in(
    repo: Path, contract: Contract
) -> None:
    """The winner arrives as an `Accepted`, minted before the draw's reset.

    Three draws, and the middle one is the only one the gate accepts, so the
    winner is neither the first nor the last — a run where "the tree happens to
    hold the right thing" cannot be true by accident. When ``best_of`` returns,
    the winning bytes are in no tree at all: every draw's workspace was reset,
    which is the invariant that keeps a losing draw from leaking and is right.

    So the channel is what binds the bytes, not the reset. The winner's verdict
    was reached in a workspace that still existed at the moment the gate spoke,
    which is exactly where :meth:`mcgyvr.deliver.Accepted.read` mints — so the
    binding can be taken there, per draw, before the reset that follows it.
    """
    draws = [
        "# draw 0\nvalue =  0\n",
        "# draw 1 winner\nvalue = 1\n",
        "# draw 2\nx=2\n",
    ]

    def sample(index: int) -> str:
        return draws[index]

    def gate(sandbox: Sandbox) -> GateResult:
        text = (sandbox.workspace / contract.target).read_text()
        if "winner" in text:
            return GateResult()
        return GateResult(
            findings=(
                Finding(
                    check="format", path=contract.target, line=1, message="reformat"
                ),
            )
        )

    picked = best_of(repo=repo, contract=contract, sample=sample, gate=gate, n=3)

    assert picked.chosen == 1, "the middle draw must be the winner for this to bite"
    assert picked.accepted

    bound = picked.winner
    assert isinstance(bound, Accepted), (
        "the winner must arrive bound to the bytes its verdict was reached on; "
        "a bare `str` is a claim about a tree that has already been reset"
    )
    assert bound.content == draws[1]
    assert bound.accepted
    assert bound.intact, "the digest must answer for the bytes beside it"


def test_repair_carries_no_second_copy_of_the_tree() -> None:
    """``RepairOutcome`` has no ``content``: repair writes the tree.

    ``repair`` mutates the tree in place, which makes the tree the owner by
    construction — there is no second place the bytes could be. A ``content``
    field would be the shape that lets a caller carry bytes past a gate.

    ``repaired`` is the claim that survives: which paths differ from what the
    worker left, which is what makes a second gate run worth a subprocess.
    """
    assert not hasattr(RepairOutcome(), "content"), (
        "a repair that writes the tree does not also hand back a copy of it; "
        "the paths in `repaired` say what changed and the tree says what it is"
    )


#: Types whose ``content`` field never sat beside a verdict, with the reason.
#: An entry here is an argument that no gate has spoken about these bytes yet,
#: so there is nothing for them to come apart from.
UNJUDGED_CONTENT = {
    # The model's reply, parsed out of its fence. It exists before any rung has
    # run; binding it to a verdict is what the rest of the pipeline is for.
    "mcgyvr.worker.reply.ParsedFile",
    # The config file `mcgyvr init` wrote or would write. No gate, no change
    # set, no repository — this is a rendering, reported so `--dry-run` can
    # print it.
    "mcgyvr.initialize.InitResult",
    # The transformer's output, and the one type here that *is* about judged
    # bytes: it is allowed because `regate` makes the staleness explicit and a
    # caller cannot carry these anywhere without running the gate again.
    "mcgyvr.cleanup.Cleanup",
}


def _dataclasses_with_content(root: Path) -> list[str]:
    """Every ``@dataclass`` under ``root`` with a field named ``content``."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        module = ".".join(path.relative_to(root.parent).with_suffix("").parts)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id == "content"
                for item in node.body
            ):
                continue
            fields = {
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            }
            if "digest" in fields:
                # Bound: the digest is what lets the far end notice that these
                # bytes are not the ones the verdict was reached on.
                continue
            found.append(f"{module}.{node.name}")
    return found


def test_no_new_type_carries_content_unbound() -> None:
    """The guard: bytes travel bound, or they travel from somewhere unjudged.

    :class:`mcgyvr.deliver.Accepted` is the exception the codebase argues for,
    and the argument is the ``digest`` field — bytes and verdict minted in one
    place off one tree, so a caller that swaps one can be caught. Any other
    dataclass carrying ``content`` is either pre-verdict (:data:`UNJUDGED_CONTENT`,
    with a reason each) or is a new value channel of the kind pattern B is
    about.

    Add an entry with its argument, or carry the bytes as an
    :class:`~mcgyvr.deliver.Accepted`. A fourth entry wants a reason; that is
    the intended cost.
    """
    src = Path(__file__).resolve().parent.parent / "src" / "mcgyvr"
    unbound = sorted(set(_dataclasses_with_content(src)) - UNJUDGED_CONTENT)
    assert unbound == [], (
        f"these carry file content beside no digest, so nothing downstream can "
        f"tell whether the bytes are still the ones a gate read: {unbound}"
    )
