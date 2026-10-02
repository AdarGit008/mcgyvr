"""The fleet-manager hook: a Jev difficulty judgment that routes a task to the
smarter resident rung before the API.

Jev may **route and wake** — a bounded, dispatch-time judgment over a task.
This per-task hook still only routes and never sleeps, and nothing in this
module reaches for the door's ``down`` direction: putting a unit back to sleep
is the ladder manager's (:mod:`mcgyvr.ladder_manager`, run by ``mcgyvr
manage``), bounded to units that can sleep and wake and gated by the same
``serving.enable_sleep_wake`` switch. Flavor A only: asleep + wake-on-demand;
multi-model resident hot-swap is out of scope.

The judgment is one :class:`~mcgyvr.decision.Noul` question — "is this task hard
enough to want the smarter rung?" — answered as a single-token probability,
never prose, through :func:`mcgyvr.decision.classify`. The wake itself is not
this module's: the rung the hook names is dispatched through the ordinary
:mod:`mcgyvr.drive` path, whose :class:`mcgyvr.wake.Waker` wakes a sleeping
card on the refused connection it returns (fail-first, never probe-first). So
the hook *routes*, and the existing wake-on-demand does the waking, still gated
by ``serving.enable_sleep_wake`` and live admission exactly as it is today.

This module sits above the seam: it names rungs and reads a contract, and it
never imports an :class:`~mcgyvr.pool.Endpoint` or :mod:`mcgyvr.serving`. It
asks :mod:`mcgyvr.decision` to judge through a rung's own endpoint (bound by
:meth:`~mcgyvr.pool.SourceMap.bind`), and it asks :mod:`mcgyvr.wake` which
rungs are asleep — both below-the-seam answers, read through seams that return
rungs and names rather than machines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from mcgyvr import decision
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.pool import Rung

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Callable, Mapping, Sequence

    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.pool import SourceMap

#: The one bounded question Jev is asked. A single-token ``Yes``/``No``.
INSTRUCTIONS = (
    "Is this task hard enough that the smarter resident rung should be woken "
    "to try it, instead of the fast resident model or the API?"
)


class Cooling(Protocol):
    """What the hook asks a cooldown: which of these endpoints cannot serve now.

    :class:`mcgyvr.cooldown.Cooldown` answers it; the endpoints are the ones
    :meth:`~mcgyvr.pool.SourceMap.bind` hands back, and the hook passes them
    through without looking inside.
    """

    def unavailable(self, endpoints: Sequence[Any]) -> Mapping[str, str]: ...


class FleetManagerError(Exception):
    """A difficulty judgment could not be made, or a wake it routed to was refused."""


@dataclass(frozen=True)
class Difficulty:
    """Jev's answer to the routing question, with how sure it was."""

    wake: bool
    probability_true: float
    confidence: float


def judge(
    pool: SourceMap,
    rung: str,
    state: Mapping[str, Any],
    *,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Difficulty:
    """Ask Jev whether to wake the smarter rung for this task.

    One :class:`~mcgyvr.decision.Noul` question through
    :func:`~mcgyvr.decision.classify`, so the answer arrives as a single-token
    probability — never prose and never a second HTTP path. The judgment runs
    on the endpoint ``rung`` resolves to, so a decision and a dispatch reach
    that unit identically.
    """
    resolved = pool.get(rung)
    if resolved is None:
        raise FleetManagerError(f"no rung named {rung!r} to judge with")
    question = {"wake_smarter": decision.Noul(INSTRUCTIONS)}
    answers = decision.classify(
        pool.bind(rung), resolved.model, dict(state), question, timeout_s=timeout_s
    ).answers
    answer = answers["wake_smarter"]
    assert isinstance(answer, decision.BoolAnswer)  # narrowed by classify
    return Difficulty(
        wake=answer.value,
        probability_true=answer.probability_true,
        confidence=answer.confidence,
    )


def state_for(contract: Contract, *, detail: str = "") -> dict[str, Any]:
    """The state the judgment reads: the task, and what the fast rung said."""
    return {
        "task_type": contract.task_type,
        "task": contract.task,
        "target": contract.target,
        "detail": detail,
    }


def asleep_rungs(config: Config, pool: SourceMap) -> tuple[Rung, ...]:
    """The resident rungs mcgyvr holds a launch spec for, in ladder order.

    "Asleep" is "down plus a file mcgyvr wrote" (:mod:`mcgyvr.wake`), and the
    file's presence is answerable without the network. The names are
    :func:`mcgyvr.wake.wakeable_rungs`', reused rather than restated; a rung is
    a candidate exactly when its card holds exactly one launch spec.
    """
    from mcgyvr.wake import wakeable_rungs

    wakeable = set(wakeable_rungs(config))
    return tuple(rung for rung in pool.rungs if rung.name in wakeable)


def smart_rung(config: Config, pool: SourceMap) -> Rung | None:
    """The dearest resident rung this config can wake, or ``None``.

    The ladder is cheapest-first, so the last wakeable resident rung is the
    "smarter" one the difficulty judgment may route to.
    """
    rungs = asleep_rungs(config, pool)
    return rungs[-1] if rungs else None


def fast_rung(config: Config, pool: SourceMap) -> Rung | None:
    """The cheapest resident rung — the model the judgment is asked on.

    The fast resident model is the one already up and cheap to ask, which is
    why it carries the judgment.
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
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
    cooldown: Cooling | None = None,
) -> str | None:
    """The hook: name the smarter rung to route to before the API, or ``None``.

    Returns the rung name when Jev judges the task hard enough to want the
    smarter rung; ``None`` says escalate straight to the API. ``judge_with`` is
    the fast rung the judgment runs on. Routing to the returned rung wakes it
    on demand through the ordinary dispatch path — the hook does not wake, and
    it never sleeps a card. A smart rung the ``cooldown`` holds out is never
    routed to, and Jev is not asked: the answer would be a wake that fails.
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
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Callable[[Contract], str | None] | None:
    """The hook for an install that can judge, or ``None`` when nothing to decide.

    ``None`` is the honest answer for a ladder with no asleep smarter rung —
    including one whose only resident rung is also the cheapest, so "fast" and
    "smart" name the same model — because there is then no routing decision for
    the judgment to make. It is also ``None`` where ``serving.enable_sleep_wake``
    is off: the hook routes to wake, and a rung nothing may wake is a rung a
    route to would fail on. ``cooldown`` is read at each task, so a smart rung
    that cools after the hook was built is not routed to either.
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
