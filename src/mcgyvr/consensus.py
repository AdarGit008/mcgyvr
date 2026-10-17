"""Best-of-N over gated draws in a sandbox.

:func:`best_of` asks a caller's sampler for ``n`` candidates, writes each one
at the contract's target inside a sandbox workspace, hands that workspace to
a caller's gate, and keeps the draw whose verdict ranks highest. A draw that
produced no candidate at all — a truncated reply, prose where a file was
asked for — is recorded as :class:`Unusable` and skipped instead of gated, so
one unreadable answer does not discard the verdicts the other draws paid for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.deliver import Accepted, DeliveryError
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.scope import inside

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable

    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.sandbox import Sandbox


class ConsensusError(Exception):
    """A best-of-N round could not be set up, or could not bind a verdict."""


class NoUsableDrawError(ConsensusError):
    """Every draw of the round was unusable, so there is nothing to gate."""


@dataclass(frozen=True)
class Unusable:
    """A draw that produced no candidate, and why.

    A sampler returns this instead of a string when it has nothing to write:
    a refused or truncated reply, a reply with no fenced file in it. The
    reason travels into :attr:`Consensus.unusable` with the draw's index in
    front of it, so a round in which every draw refused reports what went
    wrong with each instead of only that nothing arrived.
    """

    reason: str


@dataclass(frozen=True)
class Consensus:
    """One best-of-N round: the candidates it gated, and which one won.

    ``draws``, ``gates`` and ``chosen`` are parallel over the draws that
    produced a candidate. A refused draw is not a candidate, so it appears
    only in ``unusable`` and ``indices``; ``chosen`` therefore indexes the
    candidates, and :attr:`dispatched` maps it back to the draw the sampler
    was asked for.
    """

    draws: tuple[Accepted, ...]
    chosen: int
    gates: tuple[GateResult, ...]
    unusable: tuple[str, ...] = ()
    # Which dispatch each candidate came from, parallel to ``draws`` and
    # ``gates``: the sampler is called with a draw index while ``chosen``
    # counts candidates, and the two part company as soon as one draw is
    # refused. Empty means nothing was refused and the draws ran in order —
    # but a round that did refuse one must say so, or the index is a guess.
    indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.indices:
            if self.unusable:
                raise ConsensusError(
                    "a consensus with refused draws must say which dispatch "
                    "each candidate came from: `indices` is empty and "
                    f"{len(self.unusable)} draw(s) were unusable"
                )
            object.__setattr__(self, "indices", tuple(range(len(self.gates))))
        if len(self.indices) != len(self.gates):
            raise ConsensusError(
                f"{len(self.indices)} dispatch indices for {len(self.gates)} "
                "candidates: every candidate came from exactly one dispatch"
            )

    @property
    def dispatched(self) -> int:
        """The draw index the winning candidate came from."""
        return self.indices[self.chosen]

    @property
    def gate(self) -> GateResult:
        """The verdict the gate returned for the winning candidate."""
        return self.gates[self.chosen]

    @property
    def winner(self) -> Accepted:
        """The winning candidate, bound to the file the gate judged."""
        return self.draws[self.chosen]

    @property
    def accepted(self) -> bool:
        """Whether the winning candidate's verdict accepted the change."""
        return self.gate.accepted

    def __len__(self) -> int:
        """How many draws the round made, refused ones included."""
        return len(self.gates) + len(self.unusable)


def best_of(
    *,
    contract: Contract,
    sample: Callable[[int], str | Unusable],
    gate: Callable[[Sandbox], GateResult],
    n: int = 1,
    repo: Path | None = None,
    sandbox: Sandbox | None = None,
) -> Consensus:
    """Draw ``n`` candidates into a workspace, gate each, and keep the best.

    ``sample`` is called once per draw with the draw's index and returns the
    text of the file to write, or :class:`Unusable` when it has nothing to
    offer. ``gate`` is called with the sandbox once the candidate is on disk,
    because the gate judges the workspace's change rather than a string.

    Exactly one of ``sandbox`` and ``repo`` is required. A ``sandbox`` draws in
    the caller's own workspace: it is checkpointed before the first draw and
    restored to that checkpoint between draws, and the checkpoint is dropped
    before this returns. A ``repo`` is opened in a throwaway sandbox whose
    draws are reset to its base commit after each gate.

    Raises :class:`NoUsableDrawError` when no draw produced a candidate, and
    :class:`ConsensusError` when the arguments name no workspace or name two.
    """
    if n < 1:
        raise ConsensusError(f"a rung takes at least one draw; {n} were asked for")
    if sandbox is not None and repo is not None:
        raise ConsensusError(
            "pass `sandbox` or `repo`, not both: a sandbox is a workspace, so "
            "the `repo` beside it would be read by nothing"
        )
    if sandbox is None and repo is None:
        raise ConsensusError(
            "pass `sandbox` to draw in a caller's own workspace, or `repo` to "
            "draw in a fresh one opened from its HEAD"
        )
    if sandbox is not None:
        checkpoint = sandbox.checkpoint()
        try:
            return _draw(sandbox, contract, sample, gate, n, checkpoint=checkpoint)
        finally:
            # The checkpoint existed only to give the draws a clean start
            # and a place to go back to; dropping it leaves the caller's
            # history without a commit it never made, tree unchanged.
            sandbox.drop_checkpoint()
    assert repo is not None  # `sandbox` returned above, so `repo` was named
    with TempDirSandbox(repo) as staged:
        return _draw(staged, contract, sample, gate, n, checkpoint=None)


def _draw(
    space: Sandbox,
    contract: Contract,
    sample: Callable[[int], str | Unusable],
    gate: Callable[[Sandbox], GateResult],
    n: int,
    *,
    checkpoint: str | None,
) -> Consensus:
    """Run ``n`` draws in ``space`` and rank the verdicts of those that landed.

    Each candidate is written at the contract's target and handed to ``gate``
    in the workspace that now holds it; a draw the sampler or the encoding
    refused is recorded in ``unusable`` and never gated. The workspace is put
    back between draws — to ``checkpoint`` when the caller owns the sandbox,
    otherwise to the sandbox's base commit — so one candidate's file cannot be
    judged as part of the next one's change. Raises
    :class:`NoUsableDrawError` when no draw left anything for the gate.
    """
    drawn: list[Accepted] = []
    verdicts: list[GateResult] = []
    refused: list[str] = []
    dispatched: list[int] = []

    for index in range(n):
        content = sample(index)
        if isinstance(content, Unusable):
            # The sampler had nothing to offer: an unreadable reply, a
            # refusal, or text truncated at the ceiling. Nothing is written
            # and nothing is judged, so there is no verdict to rank — only a
            # reason, kept with its draw index for the round's report.
            refused.append(f"draw {index}: {content.reason}")
            continue
        data = _bytes_of(content, index)
        if isinstance(data, Unusable):
            # Text the workspace cannot hold as bytes. Recorded like a
            # refused draw rather than raised: writing it would end the round
            # and take the verdicts the earlier draws already earned with it.
            refused.append(f"draw {index}: {data.reason}")
            continue
        target = inside(space.workspace, contract.target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # The gate judges a tree, not a string, so the candidate has to
            # be on disk before it can be judged. `inside` has refused an
            # absolute target, one that walks out of the workspace and one
            # that crosses a symlink; the parent is created because a
            # contract may name a file in a directory the repo does not have.
            # The write replaces whatever is at the target already.
            target.write_bytes(data)
            verdict = gate(space)
            # Bind the verdict to the file that is on disk right now, before
            # the workspace is restored: `Accepted.read` reads the target
            # back out of the tree, so it has to run while the candidate is
            # still there. Verdict and draw index are appended together, in
            # candidate order, so `chosen` can be translated to a dispatch.
            drawn.append(_bind(space.workspace, contract, verdict, index))
            verdicts.append(verdict)
            dispatched.append(index)
        finally:
            # Put the workspace back before the next draw, so the next
            # candidate is judged on its own change and not on this one's
            # leftovers. A caller's sandbox returns to the checkpoint taken
            # before the first draw, which is the tree its draws start from; a
            # throwaway one resets to the commit it was opened at. This runs
            # whether the gate accepted, refused, or raised.
            if checkpoint is not None:
                space.restore_to(checkpoint)
            else:
                space.reset()

    if not verdicts:
        # Every draw refused, so there is no verdict to rank and no winner to
        # report: the round fails rather than picking one of nothing, and the
        # message carries each draw's own reason.
        raise NoUsableDrawError(
            f"none of the {n} draw(s) produced anything to gate — " + "; ".join(refused)
        )

    # Rank by `_score` and take the highest; `max` returns the first of equal
    # scores, so a tie goes to the earlier draw. The winner may still be a
    # candidate the gate turned down — the gate ran and said so — and the
    # caller reads that from `accepted` rather than having the round hide it.
    best = max(range(len(verdicts)), key=lambda index: _score(verdicts[index]))
    return Consensus(
        draws=tuple(drawn),
        chosen=best,
        gates=tuple(verdicts),
        unusable=tuple(refused),
        indices=tuple(dispatched),
    )


def _bind(
    workspace: Path, contract: Contract, verdict: GateResult, index: int
) -> Accepted:
    """Read the judged candidate back out of the workspace, with its verdict.

    ``Accepted.read`` is what carries the file's text, digest and findings,
    and it reads the tree the gate just judged, so it is called before the
    workspace is restored. A verdict with no file behind it means the gate
    did not leave the target where the contract names it: that is a fault in
    the round, not an unusable draw, so it raises instead of being skipped.
    """
    try:
        return Accepted.read(repo=workspace, contract=contract, result=verdict)
    except DeliveryError as exc:
        raise ConsensusError(
            f"draw {index} was judged but {contract.target} is not in the "
            f"workspace to bind that verdict to: {exc}"
        ) from exc


def _bytes_of(content: str, index: int) -> bytes | Unusable:
    """Encode a drawn file as the bytes that go into the workspace.

    ``surrogateescape`` is the codec the rest of the tree reads bytes back
    with, so text that came from a file round-trips unchanged. A lone
    surrogate outside the range that codec maps stands for no byte at all and
    has no UTF-8 encoding; it comes back as :class:`Unusable` rather than
    raised, so the draw is lost and the draws around it are not.
    """
    try:
        return content.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError as exc:
        return Unusable(
            f"cannot be written into the workspace: the character at "
            f"position {exc.start} is the lone surrogate "
            f"U+{ord(content[exc.start]):04X}, which has no UTF-8 encoding and "
            f"stands for no byte, so there is nothing for the gate to judge"
        )


def _score(result: GateResult) -> tuple[int, int, int]:
    """Score a verdict so a plain ``max`` prefers the better candidate.

    Acceptance dominates; among verdicts that agree on it, the fewer findings
    the better, and among those, the fewer inconclusive rungs. Both counts are
    negated because ``max`` picks the greatest tuple. ``inconclusive`` ranks
    last because a rung that could not run says less about a change than one
    that ran and found nothing wrong with it.
    """
    return (
        int(result.accepted),
        -len(result.findings),
        -len(result.inconclusive),
    )
