""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr import decision
from mcgyvr.local_pool import Rung

if TYPE_CHECKING:  #
    from collections.abc import Callable, Mapping, Sequence

    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap

#
INSTRUCTIONS = (
    "Is this task hard enough that the smarter resident rung should be woken "
    "to try it, instead of the fast resident model or the API?"
)


class Cooling(Protocol):
    ""

    def unavailable(self, endpoints: Sequence[Any]) -> Mapping[str, str]: ...


class FleetManagerError(Exception):
    ""


@dataclass(frozen=True)
class Difficulty:
    ""

    wake: bool
    probability_true: float
    confidence: float


def judge(
    pool: SourceMap,
    rung: str,
    state: Mapping[str, Any],
    *,
    timeout_s: float | None = None,
) -> Difficulty:
    ""
    if pool.get(rung) is None:
        raise FleetManagerError(f"no rung named {rung!r} to judge with")
    question = {"wake_smarter": decision.Noul(INSTRUCTIONS)}
    answers = decision.classify_for(
        pool, dict(state), question, rung=rung, timeout_s=timeout_s
    ).answers
    answer = answers["wake_smarter"]
    assert isinstance(answer, decision.BoolAnswer)  #
    return Difficulty(
        wake=answer.value,
        probability_true=answer.probability_true,
        confidence=answer.confidence,
    )


def state_for(contract: Contract, *, detail: str = "") -> dict[str, Any]:
    ""
    return {
        "task_type": contract.task_type,
        "task": contract.task,
        "target": contract.target,
        "detail": detail,
    }


def asleep_rungs(config: Config, pool: SourceMap) -> tuple[Rung, ...]:
    ""
    from mcgyvr.wake import wakeable_rungs

    wakeable = set(wakeable_rungs(config))
    return tuple(rung for rung in pool.rungs if rung.name in wakeable)


def smart_rung(config: Config, pool: SourceMap) -> Rung | None:
    ""
    rungs = asleep_rungs(config, pool)
    return rungs[-1] if rungs else None


def fast_rung(config: Config, pool: SourceMap) -> Rung | None:
    ""
    for rung in pool.rungs:
        unit = config.units.get(rung.name)
        if unit is not None and not unit.requires_credential:
            return rung
    return None


def wake_before_api(
    config: Config,
    pool: SourceMap,
    contract: Contract,
    *,
    judge_with: str,
    timeout_s: float | None = None,
    cooldown: Cooling | None = None,
) -> str | None:
    ""
    target = smart_rung(config, pool)
    if target is None:
        return None
    if cooldown is not None and cooldown.unavailable([pool.bind(target.name)]):
        return None
    answer = judge(pool, judge_with, state_for(contract), timeout_s=timeout_s)
    return target.name if answer.wake else None


def hook_for(
    config: Config,
    pool: SourceMap,
    *,
    cooldown: Cooling | None = None,
    timeout_s: float | None = None,
) -> Callable[[Contract], str | None] | None:
    ""
    if not config.get("serving.enable_sleep_wake"):
        return None
    fast = fast_rung(config, pool)
    smart = smart_rung(config, pool)
    if fast is None or smart is None or fast.name == smart.name:
        return None

    def hook(contract: Contract) -> str | None:
        return wake_before_api(
            config,
            pool,
            contract,
            judge_with=fast.name,
            timeout_s=timeout_s,
            cooldown=cooldown,
        )

    return hook
