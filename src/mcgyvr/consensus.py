"""Best-of-N: several draws for one attempt, ranked by what the gate found (#119).

mcgyvr dispatches once per attempt and escalates on failure. That is the right
shape when the next rung is genuinely better, and the wrong one when the cheap
rung is *almost* right: a 7B asked the same question three times gives three
different answers, and the ladder as it stands throws two of them away unseen
and pays for a larger model instead. Breadth is the cheapest thing on the list
— the prompt is built, the context is assembled, the slot is held — and what it
spends is wall clock, not the expensive tokens ADR-0001's north star counts.

**ADR-0008 is the standing decision and most of it stands here.** Its case was
against *consensus*: no functional majority voting over execution fingerprints,
no generated test inputs, no ranking on a signal the gate does not own. That is
kept exactly. The gate is the only scorer (ADR-0029), draws are judged in the
order they were drawn, and a tie goes to the earliest — so where the gate cannot
tell two candidates apart, "the first candidate to pass the gate" is still what
wins, which is ADR-0008's rule unchanged.

**What this changes is the early exit, and the change is deliberate.** ADR-0008
has the rung stop at the first accepted draw. Every draw is gated here instead,
for the reason the ADR itself gives when it names the measurement that would
settle breadth: "given that a gate-passing candidate exists among N, at what
index does it first appear?" A run that stops at the first accept answers that
only for the draws before the winner; one verdict per draw answers it outright,
and the vector it leaves is what turns "three draws cost three gate runs and
bought nothing" into a fact rather than a suspicion. The price is gate runs —
wall clock against ``budgets.task_timeout_s`` — and no tokens at all. It is an
amendment to ADR-0008 and wants recording as one.

**Selection is not delivery.** The winner is returned, never written: the
workspace each draw was judged in is reset after it and torn down at the end, so
a rejected draw leaves nothing anywhere. That is the invariant that makes
breadth safe to run at all — every draw has to be written into a tree to be
gated, and a leaked one would be committed by delivery (#D22) as part of the
change that won. A caller that wants the winner in a tree applies it, and can
read :attr:`Consensus.accepted` first to see whether it should.

**Nothing here dispatches, and nothing here executes.** Draws are supplied and
so is the gate, for the same reason :func:`~mcgyvr.route.climb` takes an attempt
function: the ranking rule is then assertable without a model, and a module that
needed one could not be tested. Where a gate runs the contract's own commands
they must run in a sandbox (ADR-0005), which is why a caller that already holds
one passes it in — the draws are staged in the workspace its attempt is already
using, against the base it is already diffing.

**The default is one draw**, which is what every caller gets today: one draw,
one verdict, and the draw is the answer. A lever whose whole benefit is "fewer
crossings into the API family" cannot be evaluated before the telemetry that
counts crossings exists, so breadth above one stays something a caller asks for
rather than something it is given.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.sandbox.tempdir import TempDirSandbox

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.sandbox import Sandbox


class ConsensusError(Exception):
    """A best-of run could not be made from the inputs given."""


@dataclass(frozen=True)
class Consensus:
    """What N draws of one attempt came to: every verdict, and the winner.

    ``gates`` holds one result per draw, in the order drawn — the record that
    makes "N draws bought nothing" checkable afterwards — and ``chosen`` indexes
    into it, so the winner's verdict is never carried apart from the losers'.
    """

    content: str
    chosen: int
    gates: tuple[GateResult, ...]

    @property
    def gate(self) -> GateResult:
        """The winning draw's verdict."""
        return self.gates[self.chosen]

    @property
    def accepted(self) -> bool:
        """Whether the winner passed at all.

        ``False`` is the honest answer that the best of N was still not good
        enough, and it is what a caller checks before delivering: the content
        is always the best draw, which is not the same as an acceptable one.
        """
        return self.gate.accepted

    def __len__(self) -> int:
        return len(self.gates)


def best_of(
    *,
    repo: Path,
    contract: Contract,
    sample: Callable[[int], str],
    gate: Callable[[Path], GateResult],
    n: int = 1,
    sandbox: Sandbox | None = None,
) -> Consensus:
    """Draw ``n`` candidates for one attempt, gate each on its own, return the best.

    ``sample(index)`` is the text of one draw for ``contract.target`` — a whole
    file, which is what ``output_schema: whole_file`` means and what a
    model-executed contract's target always is (a pattern target is refused at
    load for every type a model runs). It is called once per draw, in order, and
    an exception it raises is not caught: a draw that could not be made is not a
    verdict, and swallowing it into a rejection would report the rung as having
    tried.

    ``gate(workspace)`` judges the draw that is currently in the tree. It is
    handed the workspace rather than the text on purpose — what is being ranked
    is what the change *did*, and a gate that could only read what it was told
    would be satisfied by an implementation that never applied anything.

    ``sandbox`` is the workspace to draw in. A caller mid-attempt already holds
    one and should pass it; without one an ephemeral temp-directory workspace is
    opened on ``repo``, populated from its ``HEAD`` and removed afterwards.
    Either way the workspace is reset after every draw, so the caller's tree —
    and the next draw — see nothing of the last one.
    """
    if n < 1:
        raise ConsensusError(f"a rung takes at least one draw; {n} were asked for")
    if sandbox is not None:
        return _draw(sandbox, contract, sample, gate, n)
    with TempDirSandbox(repo) as staged:
        return _draw(staged, contract, sample, gate, n)


def _draw(
    space: Sandbox,
    contract: Contract,
    sample: Callable[[int], str],
    gate: Callable[[Path], GateResult],
    n: int,
) -> Consensus:
    """Write each draw into ``space``, judge it, and undo it before the next."""
    drawn: list[str] = []
    verdicts: list[GateResult] = []

    for index in range(n):
        content = sample(index)
        target = space.workspace / contract.target
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # `write_bytes` under `surrogateescape`, the same way
            # :func:`mcgyvr.pending.stash` stores accepted work: `write_text`
            # encodes with the platform's preferences under `strict` and
            # translates line endings, so the draw the gate judged would not be
            # the draw returned as the winner. A verdict about a file nobody
            # kept is the one thing this ranking cannot survive.
            target.write_bytes(_bytes_of(content, index))
            verdicts.append(gate(space.workspace))
        finally:
            # In `finally` rather than after the verdict: a gate that raises
            # must not leave one draw's bytes in the workspace the next draw —
            # or the caller's own attempt, when the sandbox is theirs — is
            # judged in. `Sandbox.reset` is what makes N draws cost one
            # workspace and N-1 resets (ADR-0008).
            space.reset()
        drawn.append(content)

    # `max` keeps the first of equal keys, so a tie goes to the earliest draw:
    # where the gate cannot separate two candidates, the one drawn first wins.
    best = max(range(n), key=lambda index: _score(verdicts[index]))
    return Consensus(content=drawn[best], chosen=best, gates=tuple(verdicts))


def _bytes_of(content: str, index: int) -> bytes:
    """One draw as the bytes that go in the workspace, or this module's error.

    The other half of the ``pending.stash`` model the comment above cites: the
    convention is ``surrogateescape``, which round-trips *bytes* a decode could
    not read (U+DC80..U+DCFF), and a **lone** surrogate is not one of those. It
    is a legal JSON escape, so ``\ud800`` survives ``json.loads`` into a
    completion and reaches here as ordinary draw text — and ``stash`` was fixed
    to answer that with its own error rather than a codec exception, for the
    reason that applies here unchanged: a caller catching :class:`ConsensusError`
    has decided what to do about a draw it cannot use, and a bare
    ``UnicodeEncodeError`` out of a ranking function is not a decision it can
    make.

    A refusal rather than a rejection, because there is no verdict to record: no
    file was written, so no gate ran, so the draw is not a candidate that scored
    badly — it is a candidate that does not exist.
    """
    try:
        return content.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError as exc:
        raise ConsensusError(
            f"draw {index} cannot be written into the workspace: the character at "
            f"position {exc.start} is the lone surrogate "
            f"U+{ord(content[exc.start]):04X}, which has no UTF-8 encoding and "
            f"stands for no byte, so there is nothing for the gate to judge"
        ) from exc


def _score(result: GateResult) -> tuple[int, int, int]:
    """How well one draw did, higher first — the gate's verdict and nothing else.

    ``accepted`` is what decides. The two counts only order the draws the gate
    rejected, so that "best of N" still means something when none of them passed
    and the caller reporting the failure has the closest one to report.

    Observations are deliberately not scored. They are findings a rung reported
    without rejecting on (the semantic rung, #123, whose non-blocking status is
    a measured choice), and letting them pick the winner would promote a
    non-blocking check into a selector — a policy flip nobody decided.
    """
    return (
        int(result.accepted),
        -len(result.findings),
        -len(result.inconclusive),
    )
