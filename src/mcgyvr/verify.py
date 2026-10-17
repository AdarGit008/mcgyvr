""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from mcgyvr.catalog import catalog
from mcgyvr.decision import (
    BoolAnswer,
    Decision,
    DecisionError,
    Noul,
    Question,
    classify_for,
)
from mcgyvr.escalate import GATE_ONLY, Opinion, Review, required_policy
from mcgyvr.gate.jev import JEV_QUESTIONS, JevCheck, jev_check_for
from mcgyvr.route import by_family
from mcgyvr.runner import Completion, Request, dispatch, dispatch_role
from mcgyvr.weights import WEIGHTS_SUFFIXES

if TYPE_CHECKING:  #
    from collections.abc import Mapping

    from mcgyvr.capacity import Capacity
    from mcgyvr.catalog import Family
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.local_pool import Rung, SourceMap

#
#
#
VERIFIER_ROLE = "verifier"

#
#
#
#
LOCAL_FAMILY = "local"
#
#
#
type Ask = Callable[[str], str]

#
#
#
#
#
type Decide = Callable[[Any], Decision]

#
#
VERDICT_KEY = "verdict"
VERDICT_QUESTION = Noul(
    "Should this change be approved against the contract it was written for?"
)

#
#
#
#
#
#
#nd
#
_NOT_TYPED: tuple[type[Exception], ...] = (DecisionError,)


class ReviewerUnavailableError(RuntimeError):
    ""


class ReviewTruncatedError(RuntimeError):
    ""


class ReviewOutcome(StrEnum):
    ""

    APPROVE = "APPROVE"
    APPROVE_WITH_NOTES = "APPROVE_WITH_NOTES"
    REMEDIATE = "REMEDIATE"
    ESCALATE = "ESCALATE"


#
#ed
#
#
#
#
_OPINION: dict[ReviewOutcome, Opinion] = {
    ReviewOutcome.APPROVE: Opinion.AGREED,
    ReviewOutcome.APPROVE_WITH_NOTES: Opinion.AGREED,
    ReviewOutcome.REMEDIATE: Opinion.REFUSED,
    ReviewOutcome.ESCALATE: Opinion.REFUSED,
}


@dataclass(frozen=True)
class ReviewVerdict:
    ""

    outcome: ReviewOutcome
    notes: str = ""

    def as_review(self) -> Review:
        ""
        word = self.outcome.value
        detail = f"{word}: {self.notes}" if self.notes else word
        if _OPINION[self.outcome] is Opinion.AGREED:
            return Review.agreed(detail)
        return Review.refused(detail)


#
#
#
#
_TOKENS: tuple[tuple[ReviewOutcome, re.Pattern[str]], ...] = tuple(
    (outcome, re.compile(outcome.value.replace("_", "[ _]") + r"\b", re.IGNORECASE))
    for outcome in sorted(ReviewOutcome, key=lambda o: -len(o.value))
)

#
#
#
#
#
_NOTE_SEPARATORS = " \t:;.,-—\u2013"


def read_verdict(reply: str) -> ReviewVerdict | None:
    ""
    lines = reply.strip().splitlines()
    for index, line in enumerate(lines):
        opening = line.strip()
        if not opening:
            continue
        for outcome, pattern in _TOKENS:
            found = pattern.match(opening)
            if found is None:
                continue
            head = opening[found.end() :].lstrip(_NOTE_SEPARATORS)
            tail = "\n".join(lines[index + 1 :]).strip()
            return ReviewVerdict(
                outcome=outcome,
                notes="\n".join(part for part in (head, tail) if part),
            )
        #
        # a
        #
        return None
    return None


def read_typed_verdict(decision: Decision) -> Review:
    ""
    answer = decision.answers.get(VERDICT_KEY)
    if not isinstance(answer, BoolAnswer):
        return Review.unusable(
            "the typed verdict carried no readable answer; a review with no "
            "readable answer is not an approval."
        )
    detail = "typed verdict: approve" if answer.value else "typed verdict: refuse"
    detail += (
        f" (probability of approval {answer.probability_true:.2f}, "
        f"confidence {answer.confidence:.2f})"
    )
    return Review.agreed(detail) if answer.value else Review.refused(detail)


#


def gate_summary(gate: GateResult) -> str:
    ""
    verdict = "accepted" if gate.accepted else "rejected"
    lines = [f"The deterministic gate {verdict} this change."]
    if gate.findings:
        lines.append("Failed:")
        lines.extend(f"- {finding.for_model()}" for finding in gate.findings)
    if gate.observations:
        lines.append(
            "Reported without rejecting. These did not fail the change and no "
            "check is asking for them to be fixed; judging them is yours:"
        )
        lines.extend(f"- {finding.for_model()}" for finding in gate.observations)
    if gate.environment_issues:
        lines.append("Could not run, so this change was never checked for it:")
        lines.extend(f"- {issue}" for issue in gate.environment_issues)
    return "\n".join(lines)


def verdict_state(
    contract: Contract,
    gate: GateResult,
    change: str,
    original: str | None = None,
) -> dict[str, Any]:
    ""
    view = contract.worker_view()
    pre = original if original is not None else view["target_content"]
    return {
        "task_type": view["task_type"],
        "task": view["task"],
        "target": view["target"],
        "interface": view["interface"],
        "deterministic_gate": gate_summary(gate),
        "original": pre,
        "change": change,
    }


def _contract_block(view: dict[str, Any]) -> str:
    ""
    lines = [
        f"task ({view['task_type']}): {view['task']}",
        f"target: {view['target']}",
    ]
    if view["interface"]:
        lines.append(f"the result must expose exactly: {view['interface']}")
    for dep in view["deps"]:
        note = f"  # {dep['note']}" if dep["note"] else ""
        lines.append(f"may call: {dep['path']}: {dep['signature']}{note}")
    for condition in view["stop_conditions"]:
        lines.append(f"was told to stop rather than guess if: {condition}")
    return "\n".join(lines)


def _original_block(original: str | None, target: str) -> str:
    ""
    if original:
        return f"ORIGINAL FILE before the change ({target}), in full:\n{original}"
    if original == "":
        return "ORIGINAL FILE: none — the change creates a new file."
    return (
        f"ORIGINAL FILE: not supplied. You are seeing the change to {target} "
        f"and not the file it changed; judge only what the change itself shows, "
        f"and say so if that is not enough."
    )


def build_prompt(
    contract: Contract,
    *,
    gate: GateResult,
    change: str,
    original: str | None = None,
) -> str:
    ""
    view = contract.worker_view()
    pre = original if original is not None else view["target_content"]
    outcomes = " | ".join(outcome.value for outcome in ReviewOutcome)
    return "\n\n".join(
        [
            "You are an independent code verifier. Judge the change below "
            "against the contract it was written for. You did not write it, you "
            "cannot edit it, and nothing about how it was written is shown to "
            "you.",
            f"CONTRACT:\n{_contract_block(view)}",
            f"DETERMINISTIC CHECKS (already run, before you were asked):\n"
            f"{gate_summary(gate)}",
            _original_block(pre, view["target"]),
            f"CHANGE as applied to {view['target']}:\n{change}",
            f"Evaluate: contract compliance, correctness, regression risk, "
            f"scope expansion, unnecessary complexity.\n"
            f"Your reply MUST START with exactly one outcome token "
            f"({outcomes}) as the first word of the first line, then brief "
            f"notes. A reply that starts with anything else is discarded "
            f"unread.",
        ]
    )


#

#
#
#
#es
#
#
_CONFUSABLES = str.maketrans(
    {
        #
        "\u0430": "a",  #
        "\u0435": "e",  #
        "\u043a": "k",  #
        "\u043c": "m",  #
        "\u043d": "h",  #
        "\u043e": "o",  #
        "\u0440": "p",  #
        "\u0441": "c",  #
        "\u0442": "t",  #
        "\u0443": "y",  #
        "\u0445": "x",  #
        "\u0455": "s",  #
        "\u0456": "i",  #
        "\u0458": "j",  #
        "\u0501": "d",  #
        "\u051b": "q",  #
        "\u051d": "w",  #
        #
        "\u03b1": "a",  #
        "\u03b2": "b",  #
        "\u03b5": "e",  #
        "\u03b9": "i",  #
        "\u03ba": "k",  #
        "\u03bd": "v",  #
        "\u03bf": "o",  #
        "\u03c1": "p",  #
        "\u03c4": "t",  #
        "\u03c5": "u",  #
        "\u03c7": "x",  #
    }
)

#
#
#
#
#
#
_SEPARATORS = "-_. \t\u2212"
_SEPARATOR_CATEGORY = "Pd"

#
#
#
_DEFAULT_TAG = ":latest"

#
#
#
#
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")


def model_identity(name: str) -> str:
    ""
    folded = unicodedata.normalize("NFKC", name)
    folded = "".join(
        char
        for char in folded
        if unicodedata.category(char) not in {"Cc", "Cf", "Zl", "Zp", "Zs"}
    )
    folded = folded.casefold().translate(_CONFUSABLES)
    folded = folded.replace("\\", "/").rpartition("/")[2]
    for suffix in WEIGHTS_SUFFIXES:
        if folded.endswith(suffix):
            folded = _SHARD.sub("", folded[: -len(suffix)])
            break
    if folded.endswith(_DEFAULT_TAG):
        folded = folded[: -len(_DEFAULT_TAG)]
    return "".join(
        char
        for char in folded
        if char not in _SEPARATORS and unicodedata.category(char) != _SEPARATOR_CATEGORY
    )


#


def _independence_fault(builder: str, reviewer: str) -> str | None:
    ""
    if not model_identity(builder) or not model_identity(reviewer):
        return (
            f"independence cannot be established: the change was written by "
            f"{builder!r} and the reviewer is {reviewer!r}, and a review is "
            f"only worth the distance between those two names."
        )
    if model_identity(builder) == model_identity(reviewer):
        return (
            f"the reviewer is {reviewer!r}, the model that wrote this change "
            f"({builder!r}). A model does not verify its own output, so nothing "
            f"was asked and nothing was spent."
        )
    return None


def independent(builder: str, reviewer: str) -> bool:
    ""
    return _independence_fault(builder, reviewer) is None


def verify(
    contract: Contract,
    *,
    family: Family,
    gate: GateResult,
    change: str,
    builder: str,
    reviewer: str,
    ask: Ask,
    original: str | None = None,
    decide: Decide | None = None,
) -> Review:
    ""
    if required_policy(contract, family) == GATE_ONLY:
        #
        #
        #
        #
        return Review.unusable(
            f"no verifier is owed: work in the {family.name!r} family under a "
            f"{GATE_ONLY!r} contract is accepted on the deterministic gate, so "
            f"no model was asked."
        )

    fault = _independence_fault(builder, reviewer)
    if fault is not None:
        return Review.unusable(fault)

    if decide is not None:
        typed = _typed_verdict(contract, gate, change, reviewer, original, decide)
        if typed is not None:
            return typed

    prompt = build_prompt(contract, gate=gate, change=change, original=original)
    try:
        reply = ask(prompt)
        verdict = read_verdict(reply)
    except Exception as exc:
        #
        #
        #
        # a
        #
        #
        #
        #
        return Review.unusable(f"the reviewer {reviewer!r} could not be asked: {exc}")

    if verdict is None:
        opening = next((line for line in reply.splitlines() if line.strip()), "")
        return Review.unusable(
            f"the reply from {reviewer!r} states no verdict — it opens "
            f"{opening.strip()[:120]!r}, and a reply that names no outcome is "
            f"not an approval."
        )
    return verdict.as_review()


def _typed_verdict(
    contract: Contract,
    gate: GateResult,
    change: str,
    reviewer: str,
    original: str | None,
    decide: Decide,
) -> Review | None:
    ""
    state = verdict_state(contract, gate, change, original)
    try:
        decision = decide(state)
    except _NOT_TYPED:
        return None
    except Exception as exc:
        return Review.unusable(f"the reviewer {reviewer!r} could not be asked: {exc}")
    return read_typed_verdict(decision)


def decider_for(
    source_map: SourceMap,
    *,
    timeout_s: float | None = None,
    capacity: Capacity | None = None,
) -> Decide | None:
    ""
    if source_map.role_model(VERIFIER_ROLE) is None:
        return None

    def decide(state: Any) -> Decision:
        return classify_for(
            source_map,
            state,
            {VERDICT_KEY: VERDICT_QUESTION},
            role=VERIFIER_ROLE,
            capacity=capacity,
            timeout_s=timeout_s,
        )

    return decide


def reviewer_for(
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    max_output_tokens: int | None = None,
) -> Ask | None:
    ""
    #
    #
    #
    #
    if source_map.role_model(VERIFIER_ROLE) is None:
        return None

    def ask(prompt: str) -> str:
        completion = dispatch_role(
            source_map,
            VERIFIER_ROLE,
            Request(prompt=prompt, max_output_tokens=max_output_tokens),
            capacity=capacity,
        )
        if completion is None:  #
            raise ReviewerUnavailableError(
                f"the {VERIFIER_ROLE!r} role has no source to dispatch to"
            )
        return _review_text(completion, f"the {VERIFIER_ROLE!r} role")

    return ask


def _review_text(completion: Completion, who: str) -> str:
    ""
    if completion.truncated:
        raise ReviewTruncatedError(
            f"the review from {who} was cut short, so its verdict is not read"
        )
    return completion.text


#


@dataclass(frozen=True)
class Reviewer:
    ""

    model: str
    ask: Ask
    decide: Decide | None = None
    jev: JevCheck | None = None
    where: str = ""
    unit: str | None = None
    instead: str = ""

    @property
    def label(self) -> str:
        ""
        who = self.unit or self.model
        return f"{who} ({self.instead})" if self.instead else who


@dataclass(frozen=True)
class NoReviewer:
    ""

    reason: str


#
type Reviewers = Callable[[str], Reviewer | NoReviewer]


def _climb(config: Config, source_map: SourceMap) -> list[tuple[str, Rung]]:
    ""
    grouped = by_family(config, source_map)
    return [
        (family.name, rung)
        for family in sorted(grouped, key=lambda family: family.rank)
        for rung in grouped[family]
    ]


def reviewer_rung(config: Config, source_map: SourceMap, builder: str) -> str | None:
    ""
    climb = _climb(config, source_map)
    names = [rung.name for _, rung in climb]
    if builder not in names:
        return None
    built_with = climb[names.index(builder)][1].model
    for family, rung in climb[names.index(builder) + 1 :]:
        if family == LOCAL_FAMILY and independent(built_with, rung.model):
            return rung.name
    return None


def stand_in_rung(
    config: Config, source_map: SourceMap, builder: str, unit: str
) -> str | None:
    ""
    built = source_map.get(builder)
    if built is None:
        return None
    climb = _climb(config, source_map)
    names = [rung.name for _, rung in climb]
    anchor = unit if unit in names else builder
    if anchor not in names:
        return None
    at = names.index(anchor)
    paid = catalog().family_of(config.units[unit]).name != LOCAL_FAMILY
    nearest = [
        *((family, rung, True) for family, rung in reversed(climb[:at])),
        *((family, rung, False) for family, rung in climb[at + 1 :]),
    ]
    for family, rung, cheaper in nearest:
        if rung.name == builder or not independent(built.model, rung.model):
            continue
        if family == LOCAL_FAMILY or (paid and cheaper):
            return rung.name
    return None


def reviewers_for(
    config: Config,
    source_map: SourceMap,
    *,
    capacity: Capacity | None = None,
    timeout_s: float | None = None,
) -> Reviewers:
    ""
    if not config.get("verifier.enabled", True):
        off = NoReviewer("review is switched off by `verifier.enabled: false`")
        return lambda builder: off

    unit = config.get("verifier.unit")
    picked: dict[str, Reviewer | NoReviewer] = {}
    if unit is not None:
        model = source_map.role_model(VERIFIER_ROLE)
        ask = reviewer_for(source_map, capacity=capacity)
        decide = decider_for(source_map, timeout_s=timeout_s, capacity=capacity)
        jev = jev_check_for(
            source_map, VERIFIER_ROLE, timeout_s=timeout_s, capacity=capacity
        )
        if model is None or ask is None:
            unbound = NoReviewer(
                f"`verifier.unit` names {unit!r} and the {VERIFIER_ROLE!r} role "
                f"has no model to ask"
            )
            return lambda builder: unbound
        memory = _TypedMemory()
        named = Reviewer(
            model=model,
            ask=ask,
            decide=memory.guard(decide) if decide is not None else None,
            jev=JevCheck(decide=memory.guard(jev.decide)) if jev is not None else None,
            where=f"`verifier.unit` {unit!r}",
            unit=str(unit),
        )

        def named_or_stand_in(builder: str) -> Reviewer | NoReviewer:
            built = source_map.get(builder)
            if built is None or not _same_model(built.model, model):
                return named
            if builder not in picked:
                picked[builder] = _standing_in(
                    config,
                    source_map,
                    builder,
                    str(unit),
                    model,
                    capacity=capacity,
                    timeout_s=timeout_s,
                )
            return picked[builder]

        return named_or_stand_in

    def pick(builder: str) -> Reviewer | NoReviewer:
        if builder not in picked:
            picked[builder] = _on_rung(
                config, source_map, builder, capacity=capacity, timeout_s=timeout_s
            )
        return picked[builder]

    return pick


def _same_model(builder: str, reviewer: str) -> bool:
    ""
    built = model_identity(builder)
    return bool(built) and built == model_identity(reviewer)


def _standing_in(
    config: Config,
    source_map: SourceMap,
    builder: str,
    unit: str,
    model: str,
    *,
    capacity: Capacity | None,
    timeout_s: float | None,
) -> Reviewer | NoReviewer:
    ""
    wrote = (
        f"`verifier.unit` {unit!r} serves {model!r}, the model that wrote this change"
    )
    rung = stand_in_rung(config, source_map, builder, unit)
    offered = source_map.get(rung) if rung is not None else None
    if rung is None or offered is None:
        return NoReviewer(
            f"{wrote}, and a model does not review its own output; no other unit "
            f"was available to review it instead — a fallback is a usable rung "
            f"whose model is not the builder's, local, or hosted and below a "
            f"hosted `verifier.unit` on the ladder"
        )
    return _askable(
        source_map,
        rung,
        offered.model,
        capacity=capacity,
        timeout_s=timeout_s,
        instead=(
            f"a fallback for `verifier.unit` {unit!r}, whose model {model!r} "
            f"wrote this change"
        ),
    )


def _on_rung(
    config: Config,
    source_map: SourceMap,
    builder: str,
    *,
    capacity: Capacity | None,
    timeout_s: float | None,
) -> Reviewer | NoReviewer:
    ""
    rung = reviewer_rung(config, source_map, builder)
    offered = source_map.get(rung) if rung is not None else None
    if rung is None or offered is None:
        return NoReviewer(
            f"no local rung dearer than {builder!r} serves a model other than "
            f"the builder's, so there is no independent reviewer; a hosted "
            f"rung reviews only when `verifier.unit` names it"
        )
    return _askable(
        source_map, rung, offered.model, capacity=capacity, timeout_s=timeout_s
    )


def _askable(
    source_map: SourceMap,
    rung: str,
    model: str,
    *,
    capacity: Capacity | None,
    timeout_s: float | None,
    instead: str = "",
) -> Reviewer:
    ""

    def ask(prompt: str) -> str:
        completion = dispatch(
            source_map,
            rung,
            Request(prompt=prompt, max_output_tokens=None),
            capacity=capacity,
        )
        return _review_text(completion, f"rung {rung!r}")

    def by_rung(state: Any, questions: Mapping[str, Question]) -> Decision:
        #
        #
        return classify_for(
            source_map,
            state,
            questions,
            rung=rung,
            capacity=capacity,
            timeout_s=timeout_s,
        )

    memory = _TypedMemory()

    def decide(state: Any) -> Decision:
        return by_rung(state, {VERDICT_KEY: VERDICT_QUESTION})

    def checks(state: Any) -> Decision:
        return by_rung(state, JEV_QUESTIONS)

    return Reviewer(
        model=model,
        ask=ask,
        decide=memory.guard(decide),
        jev=JevCheck(decide=memory.guard(checks)),
        where=f"rung {rung!r}",
        unit=rung,
        instead=instead,
    )


class _TypedMemory:
    ""

    def __init__(self) -> None:
        self.refused: Exception | None = None

    def guard(self, decide: Decide) -> Decide:
        def guarded(state: Any) -> Decision:
            if self.refused is not None:
                raise self.refused
            try:
                return decide(state)
            except _NOT_TYPED as exc:
                self.refused = exc
                raise

        return guarded
