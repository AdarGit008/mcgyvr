""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from mcgyvr.catalog import Family, catalog

if TYPE_CHECKING:  #
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.deterministic import ToolStep
    from mcgyvr.local_pool import Rung, SourceMap


class RouteError(Exception):
    ""


class Verdict(StrEnum):
    ""

    PASSED = "passed"
    FAILED = "failed"
    DECLINED = "declined"


class Exhaustion(StrEnum):
    ""

    RUNGS_SPENT = "rungs_spent"
    ALL_DECLINED = "all_declined"
    NO_RUNG = "no_rung"
    WITHHELD = "withheld"


class Fanout(StrEnum):
    ""

    NONE = "none"
    IDLE = "idle"
    FULL = "full"


class Machine:
    ""

    __slots__ = ("_source",)

    def __init__(self, source: str) -> None:
        self._source = source

    def __repr__(self) -> str:
        return "<machine>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Machine):
            return NotImplemented
        return self._source == other._source

    def __hash__(self) -> int:
        return hash(self._source)

    def load(self, capacity: Capacity, rung: str | None = None) -> int | None:
        ""
        if self._source not in capacity.limits:
            return None
        return capacity.load(self._source, rung)

    def free(self, capacity: Capacity, rung: str | None = None) -> int | None:
        ""
        if self._source not in capacity.limits:
            return None
        return capacity.limit(self._source, rung) - capacity.load(self._source, rung)

    def server(self, capacity: Capacity) -> int | None:
        ""
        if self._source not in capacity.limits:
            return None
        return capacity.server_busy(self._source)

    def full(
        self, capacity: Capacity, rung: str | None, server: int | None
    ) -> bool | None:
        ""
        if self._source not in capacity.limits:
            return None
        return capacity.judge(self._source, rung, server).full

    def claim(self, capacity: Capacity, rung: str | None = None) -> None:
        ""
        if self._source in capacity.limits:
            capacity.reserve(self._source, rung)

    def release(self, capacity: Capacity, rung: str | None = None) -> None:
        ""
        capacity.release(self._source, rung)


@dataclass(frozen=True)
class Step:
    ""

    rung: Rung
    attempts: int
    machine: Machine | None = field(default=None, compare=False)


class Planned:
    ""

    steps: tuple[Step | ToolStep, ...]

    @property
    def climbable(self) -> tuple[Step, ...]:
        ""
        return tuple(step for step in self.steps if isinstance(step, Step))

    @property
    def programs(self) -> tuple[ToolStep, ...]:
        ""
        return tuple(step for step in self.steps if not isinstance(step, Step))

    @property
    def budget(self) -> int:
        ""
        return sum(step.attempts for step in self.steps)

    @property
    def climb_budget(self) -> int:
        ""
        return sum(step.attempts for step in self.climbable)


@dataclass(frozen=True)
class Plan(Planned):
    ""

    family: Family
    steps: tuple[Step | ToolStep, ...]
    reason: str = ""
    fanout: Fanout = Fanout.NONE

    def __bool__(self) -> bool:
        return bool(self.steps)

    def __len__(self) -> int:
        return len(self.steps)

    @property
    def rungs(self) -> tuple[str, ...]:
        ""
        return tuple(step.rung.name for step in self.steps if isinstance(step, Step))


@dataclass(frozen=True)
class Try:
    ""

    rung: Rung
    attempt: int
    of: int
    capacity: Capacity | None = None


@dataclass(frozen=True)
class Result:
    ""

    verdict: Verdict
    detail: str = ""
    #
    #
    #
    findings: tuple[str, ...] = ()
    #
    #
    #
    #
    #nd
    #
    #
    draw: int = 0
    draws: int = 1
    rows: int = 1

    #
    #
    #
    #
    #
    #
    @classmethod
    def passed(cls, detail: str = "", *, draws: int = 1) -> Result:
        return cls(verdict=Verdict.PASSED, detail=detail, draws=draws, rows=draws)

    @classmethod
    def failed(cls, detail: str = "", *, draws: int = 1) -> Result:
        return cls(verdict=Verdict.FAILED, detail=detail, draws=draws, rows=draws)

    @classmethod
    def declined(cls, detail: str = "", *, draws: int = 1) -> Result:
        #
        #
        #pt
        #
        #
        return cls(verdict=Verdict.DECLINED, detail=detail, draws=draws, rows=0)


@dataclass(frozen=True)
class Attempted:
    ""

    rung: str
    attempt: int
    verdict: Verdict
    detail: str = ""
    findings: tuple[str, ...] = ()
    #
    #
    #
    #
    #
    #t,
    #
    draw: int | None = 0
    #
    #
    #
    draws: int = 1
    #
    #
    #
    #
    rows: int = 1
    #
    #nd
    #d"
    #
    raised: bool = False


def attempted(rung: str, attempt: int, result: Result) -> Attempted:
    ""
    return Attempted(
        rung=rung,
        attempt=attempt,
        verdict=result.verdict,
        detail=result.detail,
        findings=result.findings,
        draw=result.draw,
        draws=result.draws,
        rows=result.rows,
    )


@dataclass(frozen=True)
class Accepted:
    ""

    family: Family
    rung: str
    history: tuple[Attempted, ...]

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class Exhausted:
    ""

    family: Family
    reason: Exhaustion
    history: tuple[Attempted, ...]
    detail: str = ""

    @property
    def ok(self) -> bool:
        return False

    @property
    def attempts_spent(self) -> int:
        ""
        return sum(1 for a in self.history if a.verdict is not Verdict.DECLINED)


#


def family_of(config: Config, rung: str) -> Family:
    ""
    lent = config.relief.get(rung)
    if lent is not None:
        return catalog().family_of(lent)
    name = config.ladder.get(rung)
    if name is None:
        offered = ", ".join(config.ladder.names) or "none"
        raise RouteError(f"no rung named {rung!r} in the ladder. Offered: {offered}")
    return catalog().family_of(config.units[name])


def by_family(config: Config, pool: SourceMap) -> Mapping[Family, tuple[Rung, ...]]:
    ""
    known = catalog()
    grouped: dict[Family, list[Rung]] = {f: [] for f in known.families}
    for rung in pool.rungs:
        grouped[family_of(config, rung.name)].append(rung)
    return {family: tuple(rungs) for family, rungs in grouped.items()}


def attempts_for(family: Family, configured: int, contract: Contract) -> int:
    ""
    if family.rank == 0:
        return 1
    return min(configured, contract.limits.attempts)


def plan(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    family: Family | None = None,
    capacity: Capacity | None = None,
) -> Plan:
    ""
    chosen = family if family is not None else contract.kind.starts_on
    rungs = by_family(config, pool).get(chosen)
    if rungs is None:  #
        raise RouteError(f"{chosen.name!r} is not a family of the loaded catalog")

    mode = fanout_of(config)

    if chosen.rank == 0:
        #
        #
        #
        #
        from mcgyvr.deterministic import tool_steps

        tools = tool_steps(contract)
        if tools:
            return Plan(family=chosen, steps=tools)

    if not rungs:
        return Plan(
            family=chosen,
            steps=(),
            reason=_why_empty(config, chosen, pool),
            fanout=mode,
        )

    machines = _machines(config, rungs)
    steps = tuple(
        Step(
            rung=rung,
            attempts=attempts_for(
                chosen, _configured_attempts(config, rung.name), contract
            ),
            machine=machines[rung.name],
        )
        for rung in rungs
    )
    return Plan(family=chosen, steps=steps, fanout=mode)


def fanout_of(config: Config) -> Fanout:
    ""
    declared = config.ladder.fanout
    try:
        return Fanout(declared)
    except ValueError as exc:
        offered = ", ".join(m.value for m in Fanout)
        raise RouteError(
            f"{declared!r} is not a fan-out mode. Offered: {offered}"
        ) from exc


def _configured_attempts(config: Config, rung: str) -> int:
    if config.ladder.get(rung) is None:
        #
        raise RouteError(f"no rung named {rung!r} in the ladder")
    attempts = config.get("attempts") or {}
    return int(attempts.get(rung, 1))


def draws_for(config: Config, rung: str) -> int:
    ""
    overrides = config.get("draws") or {}
    return int(overrides.get(rung, config.get("breadth.draws", 1)))


def _machines(config: Config, rungs: tuple[Rung, ...]) -> Mapping[str, Machine]:
    ""
    made: dict[str, Machine] = {}
    by_rung: dict[str, Machine] = {}
    for rung in rungs:
        if config.ladder.get(rung.name) is None:
            #
            raise RouteError(f"no rung named {rung.name!r} in the ladder")
        by_rung[rung.name] = made.setdefault(rung.name, Machine(rung.name))
    return by_rung


def _why_empty(config: Config, family: Family, pool: SourceMap) -> str:
    ""
    if family.rank == 0:
        return (
            "the deterministic family runs tools, not a model on a source, and no "
            "tool is bound for this contract's task type on this target. It binds "
            "no rung either, so there is no ladder entry to configure: what is "
            "missing is a program for the type, not a source for a rung."
        )
    mine = [s for s in pool.skipped if family_of(config, s.name) == family]
    if mine:
        why = "; ".join(f"{s.name}: {s.reason}" for s in mine)
        return (
            f"every rung of the {family.name!r} family was skipped ({why}), so "
            f"this is a configuration or availability problem rather than an "
            f"empty ladder."
        )
    return (
        f"no configured rung is in the {family.name!r} family — bind one to a "
        f"source that "
        + ("declares an api_key_env" if family.name == "api" else "needs no credential")
        + "."
    )


#


def _next_index(remaining: list[Step], mode: Fanout, capacity: Capacity) -> int:
    ""
    if mode is Fanout.NONE:
        return 0
    for index, step in enumerate(remaining):
        slots = (
            None
            if step.machine is None
            else step.machine.free(capacity, step.rung.name)
        )
        if slots is None:
            return 0
        if slots > 0:
            return index
    return 0


def _standing(remaining: list[Step], claimed: str | None) -> int | None:
    ""
    if claimed is None:
        return None
    for index, step in enumerate(remaining):
        if step.rung.name == claimed:
            return index
    return None


def _claim_next(
    remaining: list[Step],
    mode: Fanout,
    capacity: Capacity | None,
    claimed: str | None = None,
) -> Step:
    ""
    if capacity is None:
        return remaining.pop(0)
    with capacity.deciding():
        held = _standing(remaining, claimed)
        if held is not None:
            return remaining.pop(held)
        step = remaining.pop(_next_index(remaining, mode, capacity))
        if step.machine is not None:
            step.machine.claim(capacity, step.rung.name)
    return step


def _release(step: Step, capacity: Capacity | None) -> None:
    ""
    if step.machine is None or capacity is None:
        return
    step.machine.release(capacity, step.rung.name)


#


def climb(
    plan: Plan,
    attempt: Callable[[Try], Result],
    *,
    capacity: Capacity | None = None,
    permit: Callable[[Step, int], bool] | None = None,
    claimed: str | None = None,
) -> Accepted | Exhausted:
    ""
    history: list[Attempted] = []
    if not plan.steps:
        return Exhausted(
            family=plan.family,
            reason=Exhaustion.NO_RUNG,
            history=(),
            detail=plan.reason,
        )

    #'s
    #ic
    #
    #
    #
    #
    #
    #
    #
    steps = plan.climbable
    if plan.programs:
        named = ", ".join(sorted({step.tool.operation for step in plan.programs}))
        raise RouteError(
            f"the {plan.family.name!r} plan is a program, not a rung, so it is "
            f"not climbed: run it through `mcgyvr.deterministic` instead "
            f"({named})."
        )

    remaining = list(steps)
    #
    #
    #
    #`.
    choosing = plan.fanout
    #
    #ne
    #
    holding = claimed
    while remaining:
        step = _claim_next(remaining, choosing, capacity, holding)
        choosing = Fanout.NONE
        holding = None
        try:
            for number in range(1, step.attempts + 1):
                if permit is not None and not permit(step, number):
                    return Exhausted(
                        family=plan.family,
                        reason=Exhaustion.WITHHELD,
                        history=tuple(history),
                        detail=(
                            f"the climb stopped at {step.rung.name!r} attempt "
                            f"{number}: the caller's budget did not fund it."
                        ),
                    )
                result = attempt(
                    Try(
                        rung=step.rung,
                        attempt=number,
                        of=step.attempts,
                        capacity=capacity,
                    )
                )
                history.append(attempted(step.rung.name, number, result))
                if result.verdict is Verdict.PASSED:
                    return Accepted(
                        family=plan.family,
                        rung=step.rung.name,
                        history=tuple(history),
                    )
                if result.verdict is Verdict.DECLINED:
                    #
                    #
                    #
                    break
        finally:
            #or
            #ed
            #
            #
            _release(step, capacity)

    declined_only = all(a.verdict is Verdict.DECLINED for a in history)
    return Exhausted(
        family=plan.family,
        reason=Exhaustion.ALL_DECLINED if declined_only else Exhaustion.RUNGS_SPENT,
        history=tuple(history),
        detail=_exhausted_detail(plan, history, declined_only),
    )


def _exhausted_detail(plan: Plan, history: list[Attempted], declined_only: bool) -> str:
    ""
    tried = tuple(dict.fromkeys(a.rung for a in history))
    rungs = ", ".join(tried)
    if declined_only:
        return (
            f"every rung of the {plan.family.name!r} family declined this "
            f"contract ({rungs}); no attempt was spent."
        )
    spent = sum(1 for a in history if a.verdict is not Verdict.DECLINED)
    return (
        f"the {plan.family.name!r} family is spent: {spent} attempt(s) across "
        f"{rungs} and none produced an acceptable result."
    )
