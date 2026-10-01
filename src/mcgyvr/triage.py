"""Routing triage: a Jev-class classifier names a task's type and a semantic
floor, and the ladder climbs from that floor.

The classifier answers two typed questions about JSON ``state`` — never prose —
and nothing else. The first is a :class:`~mcgyvr.decision.Choice` over the
catalog's task types; the second is a :class:`~mcgyvr.decision.Score` rating how
complex the work is, whose expected level is the family the ladder should enter
at. Both are answered by :func:`mcgyvr.decision.classify` through the one wire
path the runner already uses, so a triage and a dispatch reach a unit
identically.

The result is :class:`Triage`: a ``task_type`` and a ``floor``. The ``floor``
is the only thing this module is allowed to say about the climb, and it is a
*hint*, not a plan. It is passed straight to :func:`mcgyvr.escalate.ascent`'s
``floor`` (or :func:`mcgyvr.route.plan`'s ``family``), and the ladder still
validates and climbs deterministically from there.

**Ascent is a rule, not a model call.** :mod:`mcgyvr.route` and
:mod:`mcgyvr.escalate` already compute the families, rungs, attempts and
ceilings as a reproducible, diffable tuple before anything is dispatched. This
module names one thing — where that climb *begins* — and does not, and must
not, touch the order of anything above it. The classifier cannot reorder the
ladder, drop a rung inside a family, or ask for a ping-pong, because none of
those decisions are asked here: the only typed question about the climb is
"which family is the floor".

**The floor is a hint, and it is clamped before it is consumed.** The
complexity rating maps to a family, and then :func:`floor_for` takes the dearer
of that hint and the task type's own starting family. The catalog's
``starts_on`` is the *minimum* — where work of a type may begin — so a hint
cheaper than it is a bad hint and degrades to a normal climb, which is the type
floor and nothing more. A hint at or above the type floor is honoured as a
raised entry: the same ladder, started higher. Either way the climb is a suffix
of the normal one, never a reordering, because a floor only drops cheaper
leading families.

**The mapping is the family order, not a second table.** The complexity score's
levels are the catalog families in declared rank order, cheapest first, so the
expected level *is* the family rank and :func:`family_for_level` does not
introduce a rubric that could drift from the catalog. A catalog whose families
change count changes the score's levels with it, up to the score's own ten-level
limit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcgyvr.catalog import Catalog, Family, TaskType
from mcgyvr.catalog import catalog as load_catalog
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import (
    Choice,
    ChoiceAnswer,
    Decision,
    Question,
    Score,
    ScoreAnswer,
    classify,
    classify_role,
)
from mcgyvr.pool import Endpoint, SourceMap

#: The question names, stable so a caller can read the answers by key.
TASK_TYPE_QUESTION = "task_type"
FLOOR_QUESTION = "floor"


class TriageError(Exception):
    """A decision answered, but not in a shape a triage can be read from."""


@dataclass(frozen=True)
class Triage:
    """What a triage named: the task type, and the family the ladder enters at.

    ``floor`` is already clamped to be at least ``task_type.starts_on`` — see
    :func:`floor_for` — so it is safe to hand to
    :func:`mcgyvr.escalate.ascent` as ``floor`` and to nothing else. It is a
    hint, not a plan: the ladder it is passed to still builds and validates the
    climb, and starts from this family instead of the type's own.
    """

    task_type: TaskType
    floor: Family


def build_questions(catalog: Catalog) -> dict[str, Question]:
    """The two typed questions a triage answers, over ``catalog``.

    The task-type question is a :class:`Choice` keyed by the catalog's own
    names, so the classifier can only name a type the catalog declares. The
    floor question is a :class:`Score` whose levels are the catalog families in
    rank order, cheapest first, so the expected level is the family rank.
    """
    return {
        TASK_TYPE_QUESTION: Choice(
            instructions=(
                "What kind of work is this task? Pick the task type whose "
                "guarantee matches what the task asks for."
            ),
            options={task_type.name: task_type.doc for task_type in catalog.task_types},
        ),
        FLOOR_QUESTION: Score(
            instructions=(
                "How complex is this work? Rate the cheapest tier that can "
                "complete it, so the ladder knows where to start."
            ),
            levels=tuple(family.doc for family in catalog.families),
        ),
    }


def family_for_level(families: tuple[Family, ...], level: float) -> Family:
    """The family a complexity ``level`` names, clamped into the family range.

    The score's expected level is rounded to the nearest rank and floored at
    both ends, so however confident or diffuse the answer, the result is always
    a real family of the catalog the score was built from.
    """
    index = round(level)
    index = max(0, min(index, len(families) - 1))
    return families[index]


def floor_for(task_type: TaskType, hinted: Family) -> Family:
    """The entry family: the dearer of the type's floor and the hinted one.

    ``task_type.starts_on`` is where work of that type *may* begin, so a hint
    cheaper than it is a bad hint and degrades to the type's own floor — a
    normal climb. A hint at or above it raises the entry without ever lowering
    it.
    """
    if hinted.rank >= task_type.starts_on.rank:
        return hinted
    return task_type.starts_on


def read_triage(catalog: Catalog, decision: Decision) -> Triage:
    """The :class:`Triage` a :class:`Decision` reads as, over ``catalog``.

    Raises :class:`TriageError` when an answer is not the typed shape the
    questions asked for — a caller handed the wrong decision, not a weak hint.
    """
    type_answer = decision.answers.get(TASK_TYPE_QUESTION)
    if not isinstance(type_answer, ChoiceAnswer):
        raise TriageError(
            f"the {TASK_TYPE_QUESTION!r} answer is not a choice, so no task "
            "type can be read from it"
        )
    floor_answer = decision.answers.get(FLOOR_QUESTION)
    if not isinstance(floor_answer, ScoreAnswer):
        raise TriageError(
            f"the {FLOOR_QUESTION!r} answer is not a score, so no floor can "
            "be read from it"
        )
    task_type = catalog.require(type_answer.choice)
    hinted = family_for_level(catalog.families, floor_answer.level)
    return Triage(task_type=task_type, floor=floor_for(task_type, hinted))


def triage(
    endpoint: Endpoint,
    model: str,
    state: Any,
    *,
    catalog: Catalog | None = None,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Triage:
    """Name the task type and semantic floor for ``state``, on ``model``.

    Builds the two typed questions over ``catalog`` (the shipped one when none
    is given) and answers them with :func:`mcgyvr.decision.classify` — one
    logprobs request per question, through the runner's own transport.
    """
    known = catalog if catalog is not None else load_catalog()
    decision = classify(
        endpoint, model, state, build_questions(known), timeout_s=timeout_s
    )
    return read_triage(known, decision)


def triage_for(
    source_map: SourceMap,
    role: str,
    *,
    catalog: Catalog | None = None,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Callable[[Any], Triage] | None:
    """The install's ``role`` as a typed triage, or ``None`` when it has none.

    Mirrors :func:`triage` one seam over: where that one takes an
    :class:`~mcgyvr.pool.Endpoint` and a model, this one dispatches through
    :func:`~mcgyvr.decision.classify_role` below the seam, so only the
    :class:`Triage` decision returns and no endpoint crosses it.
    """
    if source_map.role_model(role) is None:
        return None
    known = catalog if catalog is not None else load_catalog()

    def triage_state(state: Any) -> Triage:
        decision = classify_role(
            source_map, role, state, build_questions(known), timeout_s=timeout_s
        )
        if decision is None:  # the role was bound a moment ago
            raise TriageError(f"the {role!r} role has no source to answer a decision")
        return read_triage(known, decision)

    return triage_state
