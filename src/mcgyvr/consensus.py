""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mcgyvr.deliver import Accepted, DeliveryError
from mcgyvr.sandbox.tempdir import TempDirSandbox
from mcgyvr.scope import inside

if TYPE_CHECKING:  #
    from collections.abc import Callable

    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.sandbox import Sandbox


class ConsensusError(Exception):
    ""


class NoUsableDrawError(ConsensusError):
    ""


@dataclass(frozen=True)
class Unusable:
    ""

    reason: str


@dataclass(frozen=True)
class Consensus:
    ""

    draws: tuple[Accepted, ...]
    chosen: int
    gates: tuple[GateResult, ...]
    unusable: tuple[str, ...] = ()
    #
    #
    #
    #
    #
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
        ""
        return self.indices[self.chosen]

    @property
    def gate(self) -> GateResult:
        ""
        return self.gates[self.chosen]

    @property
    def winner(self) -> Accepted:
        ""
        return self.draws[self.chosen]

    @property
    def accepted(self) -> bool:
        ""
        return self.gate.accepted

    def __len__(self) -> int:
        ""
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
    ""
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
            #
            #
            #
            sandbox.drop_checkpoint()
    assert repo is not None  #
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
    ""
    drawn: list[Accepted] = []
    verdicts: list[GateResult] = []
    refused: list[str] = []
    dispatched: list[int] = []

    for index in range(n):
        content = sample(index)
        if isinstance(content, Unusable):
            #
            #
            #
            #
            refused.append(f"draw {index}: {content.reason}")
            continue
        data = _bytes_of(content, index)
        if isinstance(data, Unusable):
            #
            #
            #
            refused.append(f"draw {index}: {data.reason}")
            continue
        target = inside(space.workspace, contract.target)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            #
            #
            #
            #
            #
            #
            target.write_bytes(data)
            verdict = gate(space)
            #
            #
            #
            #
            #
            drawn.append(_bind(space.workspace, contract, verdict, index))
            verdicts.append(verdict)
            dispatched.append(index)
        finally:
            #
            #€”
            #is
            #wn
            #ce
            #
            if checkpoint is not None:
                space.restore_to(checkpoint)
            else:
                space.reset()

    if not verdicts:
        #
        #
        #
        raise NoUsableDrawError(
            f"none of the {n} draw(s) produced anything to gate â€” " + "; ".join(refused)
        )

    #
    #
    #
    #
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
    ""
    try:
        return Accepted.read(repo=workspace, contract=contract, result=verdict)
    except DeliveryError as exc:
        raise ConsensusError(
            f"draw {index} was judged but {contract.target} is not in the "
            f"workspace to bind that verdict to: {exc}"
        ) from exc


def _bytes_of(content: str, index: int) -> bytes | Unusable:
    ""
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
    ""
    return (
        int(result.accepted),
        -len(result.findings),
        -len(result.inconclusive),
    )
