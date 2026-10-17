"""Judge whether a task is worth waking the smart resident rung for.

The climb hands `escalate` a wake hook built here. Before the climb gives up on
a rung and falls to the API, the hook asks the fast local model one yes-or-no
question about the task, and when the answer is yes it names the smart rung to
try instead: the wake itself is the climb's, and nothing in this module puts a
card to rest. Two conditions can take the hook away entirely: sleep and wake
off in the config, or a ladder with no sleeping rung or no credential-free rung
to ask. A rung the run is already holding out is never routed to.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr import decision
from mcgyvr.local_pool import Rung

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Mapping, Sequence

    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.local_pool import SourceMap

# The one question a judgment puts: a `Noul`, so the answer's value is true when
# the task reads as too hard for the fast resident model and the API alike.
INSTRUCTIONS = (
    "Is this task hard enough that the smarter resident rung should be woken "
    "to try it, instead of the fast resident model or the API?"
)


class Cooling(Protocol):
    """What the hook asks before routing to a rung: which endpoints are held out.

    The signatures are the pool's and the cooldown's, so a run's own hold and
    any stand-in answer here; a mapping that leaves an endpoint out takes it as
    available.
    """

    def unavailable(self, endpoints: Sequence[Any]) -> Mapping[str, str]: ...


class FleetManagerError(Exception):
    """A judgment could not be asked: the rung to ask it of is not on the pool."""


@dataclass(frozen=True)
class Difficulty:
    """What the judgment answered about one task.

    `wake` is the answer itself, `probability_true` the probability the reply put
    on Yes, and `confidence` how sure the reply was of the answer it gave.
    """

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
    """Ask the rung named `rung` whether `state` is hard enough to wake for.

    The one question is asked through `decision.classify_for` and read back as a
    bool answer, so the judgment is one request at the rung given, within
    `timeout_s`. `state` is copied into the request rather than read in place.
    Raises `FleetManagerError` when the pool names no such rung.
    """
    if pool.get(rung) is None:
        raise FleetManagerError(f"no rung named {rung!r} to judge with")
    question = {"wake_smarter": decision.Noul(INSTRUCTIONS)}
    answers = decision.classify_for(
        pool, dict(state), question, rung=rung, timeout_s=timeout_s
    ).answers
    answer = answers["wake_smarter"]
    assert isinstance(answer, decision.BoolAnswer)  # Noul asked, so bool is the answer
    return Difficulty(
        wake=answer.value,
        probability_true=answer.probability_true,
        confidence=answer.confidence,
    )


def state_for(contract: Contract, *, detail: str = "") -> dict[str, Any]:
    """The state a judgment is made from: the contract's task type, task and
    target, plus `detail`, free text about the attempt being judged.

    The hook judges a contract alone, so it passes no `detail`; a caller that
    knows why the attempt is being judged can say so.
    """
    return {
        "task_type": contract.task_type,
        "task": contract.task,
        "target": contract.target,
        "detail": detail,
    }


def asleep_rungs(config: Config, pool: SourceMap) -> tuple[Rung, ...]:
    """The pool's rungs that can be slept and woken, in the ladder's own order.

    `wake.wakeable_rungs` names the units with a launch spec and no resident
    unit; the pool narrows that to the rungs it can actually dispatch at. Empty
    when nothing on this ladder is a switch.
    """
    from mcgyvr.wake import wakeable_rungs

    wakeable = set(wakeable_rungs(config))
    return tuple(rung for rung in pool.rungs if rung.name in wakeable)


def smart_rung(config: Config, pool: SourceMap) -> Rung | None:
    """The rung a wake would bring up: the last of the sleepable ones, the
    ladder's smartest sleeping rung. None when nothing can be woken."""
    rungs = asleep_rungs(config, pool)
    return rungs[-1] if rungs else None


def fast_rung(config: Config, pool: SourceMap) -> Rung | None:
    """The rung a judgment is asked of: the first rung whose unit needs no
    credential, so the question is answered by a local model and not the API.

    The pool keeps the ladder's cheapest-first order. None when every rung on
    it names a key.
    """
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
    """The smart rung's name when this contract is worth waking it for, else None.

    None comes back when nothing on the ladder can be woken, when `cooldown`
    holds out the smart rung's endpoint, or when the judgment says the task is
    not hard enough. The question is asked of `judge_with`, normally the fast
    rung the climb is already trying.
    """
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
    """The wake hook the climb calls before it gives up on a rung, or None.

    None when `serving.enable_sleep_wake` is off, when the ladder has no rung
    that can be woken, when no rung is free of a credential to ask the judgment
    of, or when the fast and smart rungs are the same one: in each case there is
    nothing to offer that trying again would not. The hook answers with a rung
    name or None, judging every contract with the fast rung, within `timeout_s`
    and against the run's own `cooldown`.
    """
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
