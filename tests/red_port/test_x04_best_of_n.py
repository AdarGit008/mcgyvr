"""X04 — several samples for one attempt, ranked by what the gate actually found.

mcgyvr dispatches once per attempt and escalates on failure. That is the right shape
when the next rung is genuinely better, and the wrong one when the cheap rung is
*almost* right: a 7B asked the same question three times produces three different
answers, and the ladder as it stands throws two of them away unseen and pays for a
larger model instead. Sampling is the cheapest thing on this list — the prompt is
already built, the context is already assembled, the slot is already held.

It is also the easiest thing to get dangerously wrong, and three of these four
statements are about that.

*Each sample is gated independently* is asserted by making the gate's verdict depend on
what is in the working tree when it runs, and then arranging for exactly one of three
samples to satisfy it. The result must carry three verdicts in the shape ``False, True,
False``. A test that asserted only "three samples were produced" would pass against an
implementation that generated three and gated the first, which is the failure that
makes best-of-N look like it works while costing three times as much for nothing.

*The delivered sample is the one with the best gate result* is asserted against a
sample that says it is correct. The rejected candidate carries a comment claiming it
passes every test; the accepted one carries no claim at all and merely works. Selection
by anything the model wrote — a confidence line, a self-assessment, a "// verified"
— is selection by the thing under test, and it is exactly what a model that has learned
to sound right will exploit. The gate ran the change; the model only described it.

*The samples that were not chosen leave nothing behind* is the invariant that makes the
whole thing safe to run at all. Each sample has to be written into a tree to be gated,
so N-1 of them are written and must be gone: the tree is asserted clean, at the same
commit, holding the same bytes it started with, and — the assertion that catches the
rest — no marker from any sample survives anywhere under the repository. A best-of-N
that leaks a rejected sample into the tree corrupts the change that *is* delivered,
and D22's delivery would commit it without ever knowing it was there. Note what is
*not* asserted: that the winner was written. Selection and delivery are separate, as
D22 has it, and a selector that committed would have taken the delivery decision away
from the code that owns it.

*Requesting one sample behaves exactly as today* is the compatibility statement, and it
is asserted with the count left unspecified rather than passed as ``1`` — the default
is the part that must not change. Every existing caller asks for one attempt's worth of
work, and this lever is only worth having if it costs them nothing.

Nothing here dispatches. Samples are supplied and the gate is supplied, for the reason
:func:`mcgyvr.escalate.escalate` takes ``attempt``: the ranking rule is assertable
without a model, and a test that needed one could not run.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcgyvr.gate import Finding, GateResult
from mcgyvr.sandbox import Sandbox
from tests.red_port.conftest import git, required

BEHAVIOR = (
    "gate several samples of one attempt independently and deliver the one the gate "
    "ranked best, leaving the rejected ones nowhere in the tree"
)

TARGET = "src/pkg/fetch.py"

# The one that says it is right and is not, and the one that says nothing and is.
BOASTFUL = (
    "def fetch(url):\n"
    "    # verified: this passes every test in the suite\n"
    "    return url\n"
)
WORKING = "def fetch(url):\n    return url.strip()\n"


def _best_of() -> Any:
    """N samples for one attempt, ranked by gate result.

    Placeholder path. What must survive the port is what is asserted about the result:
    one verdict per sample, the winner chosen by those verdicts, and a clean tree.
    """
    return required(
        BEHAVIOR,
        lambda: __import__("mcgyvr.consensus", fromlist=["best_of"]).best_of,
    )


def _marked(index: int) -> str:
    """A sample distinguishable from every other sample, by content alone."""
    return f"def fetch(url):\n    # sample-{index}\n    return url\n"


def _gate_on_tree(wanted: str) -> Callable[[Sandbox], GateResult]:
    """A gate whose verdict depends on what is in the tree, not on what it was told.

    This is the whole reason the samples are written before they are judged: a gate
    that read its argument instead of the workspace could be satisfied by an
    implementation that never applied anything, and "what actually happened when the
    change was run" would go unasserted.
    """

    def gate(sandbox: Sandbox) -> GateResult:
        text = (sandbox.workspace / TARGET).read_text()
        if wanted in text:
            return GateResult()
        return GateResult(
            findings=(
                Finding(
                    check="acceptance",
                    path=TARGET,
                    message="the declared demonstration did not pass",
                ),
            )
        )

    return gate


def test_every_sample_of_one_attempt_is_gated_on_its_own(
    repo: Path, contract: Any
) -> None:
    """Three samples, three verdicts, and only the middle one passes.

    The shape of the verdict list is asserted rather than its length, because a length
    assertion passes against an implementation that generates N and judges one — which
    costs N and buys nothing.
    """
    result = _best_of()(
        repo=repo,
        contract=contract,
        n=3,
        sample=_marked,
        gate=_gate_on_tree("sample-1"),
    )

    verdicts = [gate.accepted for gate in result.gates]
    assert verdicts == [False, True, False], (
        f"each sample must be judged on what it did; got {verdicts}"
    )
    assert result.winner.content == _marked(1)
    assert result.winner.accepted and result.winner.intact, (
        "the winner arrives bound to the verdict reached on it, so a caller "
        "reading these bytes is reading what the middle gate run read"
    )


def test_the_winner_is_chosen_by_the_gate_and_not_by_the_model(
    repo: Path, contract: Any
) -> None:
    """A sample that claims to be correct loses to one that merely is.

    The claim is inside the candidate's own text, which is the only place a model can
    put one. Any selection rule that reads it — a confidence marker, a self-report, a
    "verified" comment — is ranking the description instead of the result.
    """
    samples = (BOASTFUL, WORKING)

    result = _best_of()(
        repo=repo,
        contract=contract,
        n=2,
        sample=lambda index: samples[index],
        gate=_gate_on_tree("strip"),
    )

    assert result.winner.content == WORKING, (
        "the sample that announced its own correctness was preferred to the one that "
        "passed the gate"
    )
    assert result.winner.accepted, (
        "and the verdict bound to the winning bytes is the accepting one, not the "
        "boast's"
    )
    assert sum(gate.accepted for gate in result.gates) == 1


def test_the_samples_that_lost_leave_nothing_in_the_tree(
    repo: Path, contract: Any
) -> None:
    """N-1 samples were written somewhere to be judged, and all of them are gone.

    Asserted on the bytes, the status, the HEAD and — the one the others miss — on
    every rejected sample's own marker being absent from the whole repository. A
    leaked sample is not a cosmetic problem: D22's delivery would commit it as part of
    the change that won.
    """
    before = (repo / TARGET).read_text()
    head = git(repo, "rev-parse", "HEAD").strip()

    _best_of()(
        repo=repo,
        contract=contract,
        n=3,
        sample=_marked,
        gate=_gate_on_tree("sample-1"),
    )

    assert (repo / TARGET).read_text() == before, "a sample was left in the target file"
    assert git(repo, "status", "--porcelain").strip() == "", "tree left dirty"
    assert git(repo, "rev-parse", "HEAD").strip() == head, (
        "selection committed something"
    )

    everything = "".join(
        path.read_text(errors="ignore") for path in repo.rglob("*") if path.is_file()
    )
    for index in range(3):
        assert f"sample-{index}" not in everything, (
            f"sample-{index} survived selection somewhere in the repository"
        )


def test_asking_for_one_sample_is_what_mcgyvr_does_today(
    repo: Path, contract: Any
) -> None:
    """The default is one sample, one verdict, and the sample is the answer.

    ``n`` is deliberately not passed. Every caller that exists today asks for one
    attempt's worth of work, and a lever that changed what they get by default is a
    lever that has to be adopted rather than one that can be turned on.
    """
    result = _best_of()(
        repo=repo,
        contract=contract,
        sample=lambda index: WORKING,
        gate=_gate_on_tree("strip"),
    )

    assert len(result.gates) == 1, f"the default asked for {len(result.gates)} samples"
    assert result.gates[0].accepted
    assert result.winner.content == WORKING
    assert result.winner is result.draws[0], (
        "one draw makes it the winner, and the binding is that draw's"
    )
