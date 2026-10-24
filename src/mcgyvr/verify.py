"""Ask a model that did not write a change to judge it against its contract.

Verification is settled in a fixed order. The family's policy decides whether a
model review is owed at all, the identity check refuses a reviewer whose
weights are the builder's, and only then is a reviewer asked. A reply that came
back is read as one of four outcomes (:class:`ReviewOutcome`), two of which
agree with the change. A reviewer that could not be asked, could not be read,
or was cut short yields an *unusable* review, which is never an approval.

The reply is read two ways. Prose is read by :func:`read_verdict`, which takes
the outcome token the first non-blank line opens with; the typed path reads a
:class:`~mcgyvr.decision.BoolAnswer` out of next-token probabilities instead.
:func:`reviewers_for` decides who is asked, per builder, from the ladder.
"""

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

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Mapping

    from mcgyvr.capacity import Capacity
    from mcgyvr.catalog import Family
    from mcgyvr.config import Config
    from mcgyvr.contract import Contract
    from mcgyvr.gate import GateResult
    from mcgyvr.local_pool import Rung, SourceMap

#: The role a `verifier:` unit is bound under. The typed verdict, the typed JEV
#: checks and the prose dispatch all ask for it by this name, so a config that
#: binds the role gets one model behind all three.
VERIFIER_ROLE = "verifier"

#: The family name of rungs served on the operator's own machine. It is read in
#: the two places that decide who may review: only a local rung is picked
#: unprompted by `reviewer_rung`, and a stand-in is taken from anywhere in this
#: family but from a hosted family only below a hosted `verifier.unit`.
LOCAL_FAMILY = "local"
#: How a reviewer is asked in prose: one prompt in, one reply out. A seam that
#: cannot reach its reviewer raises rather than returning nothing.
type Ask = Callable[[str], str]

#: How a reviewer is asked for a typed decision instead of prose: it takes the
#: state built by `verdict_state` (or the JEV state) and returns the answers read
#: from next-token probabilities. A `DecisionError` from it means the model
#: answered something unreadable, not that it was unreachable.
type Decide = Callable[[Any], Decision]

#: The one key a typed verdict fills, and the yes/no question that fills it. A
#: missing or non-boolean answer under this key is not read as an approval.
VERDICT_KEY = "verdict"
VERDICT_QUESTION = Noul(
    "Should this change be approved against the contract it was written for?"
)

#: The errors that mean "the reviewer answered, but not in a form that can be
#: read" — an endpoint with no choices, no logprobs, or none of the expected
#: labels in its top tokens. They are kept apart from a transport or binding
#: failure on purpose: `_typed_verdict` catches these and falls back to a prose
#: prompt on the same reviewer, while anything else is reported as the reviewer
#: being unreachable. `_TypedMemory` adds to the tuple at run time by making a
#: reviewer's first such refusal stick, so a model that already failed one typed
#: question is never asked another.
_NOT_TYPED: tuple[type[Exception], ...] = (DecisionError,)


class ReviewerUnavailableError(RuntimeError):
    """A reviewer was asked for and the role had nowhere to dispatch to.

    Raised by the prose seam built on the verifier role once that role turns
    out to have no source; `verify` turns it into an unusable review.
    """


class ReviewTruncatedError(RuntimeError):
    """A review completion was cut short, so its text is not a verdict.

    Raised for a completion whose stop reason is `TRUNCATED`; a verdict cut off
    mid-reply may have been about to name anything, so none of it is read.
    """


class ReviewOutcome(StrEnum):
    """The four tokens a prose review must open with.

    The two approving values map to agreement and the two refusing values to
    refusal (`_OPINION`); the enum's string value is the token itself, which is
    what `_TOKENS` matches against and what the prompt lists.
    """

    APPROVE = "APPROVE"
    APPROVE_WITH_NOTES = "APPROVE_WITH_NOTES"
    REMEDIATE = "REMEDIATE"
    ESCALATE = "ESCALATE"


# What each outcome is worth to the escalation path: approval with notes is
# still agreement, and an escalation is still a refusal of the change as
# applied. The mapping is what keeps `as_review` from having to enumerate them.
_OPINION: dict[ReviewOutcome, Opinion] = {
    ReviewOutcome.APPROVE: Opinion.AGREED,
    ReviewOutcome.APPROVE_WITH_NOTES: Opinion.AGREED,
    ReviewOutcome.REMEDIATE: Opinion.REFUSED,
    ReviewOutcome.ESCALATE: Opinion.REFUSED,
}


@dataclass(frozen=True)
class ReviewVerdict:
    """A prose verdict: the outcome token a reply opened with, and its notes."""

    outcome: ReviewOutcome
    notes: str = ""

    def as_review(self) -> Review:
        """Convert to the plain agreed/refused review the escalation path reads.

        The detail is the outcome token and, when there are notes, the notes
        after it, so the refusal text names the one of the four outcomes the
        reviewer chose.
        """
        word = self.outcome.value
        detail = f"{word}: {self.notes}" if self.notes else word
        if _OPINION[self.outcome] is Opinion.AGREED:
            return Review.agreed(detail)
        return Review.refused(detail)


# One compiled pattern per outcome, longest value first, so that
# APPROVE_WITH_NOTES is tried before APPROVE and cannot be read as a bare
# APPROVE with notes. The underscore is matched as either `_` or a space, and
# matching is case-insensitive; the pattern is used with `match`, and the
# trailing `\b` keeps a longer word that merely starts with a token from
# counting as that token.
_TOKENS: tuple[tuple[ReviewOutcome, re.Pattern[str]], ...] = tuple(
    (outcome, re.compile(outcome.value.replace("_", "[ _]") + r"\b", re.IGNORECASE))
    for outcome in sorted(ReviewOutcome, key=lambda o: -len(o.value))
)

#: What may sit between the outcome token and the notes on the same line:
#: blanks, punctuation and dashes. Everything else after the token is notes.
_NOTE_SEPARATORS = " \t:;.,-—\u2013"


def read_verdict(reply: str) -> ReviewVerdict | None:
    """Read the verdict out of a prose reply, or None when it names none.

    Only the first non-blank line is inspected: it must *begin* with one of the
    outcome tokens. The notes are whatever follows that token on the line, less
    `_NOTE_SEPARATORS`, joined to every later line. A reply whose first non-blank
    line opens with anything else — including a reviewer that begins with a
    preamble and names its outcome further down — returns None, which the caller
    treats as no verdict rather than as an approval.
    """
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
        # The first non-blank line is the only place a verdict may appear, and
        # it holds none of the four tokens: this reply states no outcome.
        return None
    return None


def read_typed_verdict(decision: Decision) -> Review:
    """Read the typed verdict from a decision's answers under `VERDICT_KEY`.

    Only a `BoolAnswer` is read: anything else (no answer at all, or an answer
    of another kind) is unusable, because a review with no readable answer is
    not an approval. The detail records the approve/refuse value with the
    probability of approval and the confidence behind it.
    """
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


# The deterministic gate's result as prose for the reviewer, in the three tiers
# the gate itself distinguishes: failures, observations that did not fail the
# change, and checks that could not run at all.


def gate_summary(gate: GateResult) -> str:
    """Render a gate result as the reviewer's "DETERMINISTIC CHECKS" section.

    One line says whether the gate accepted or rejected the change. Failures
    follow under "Failed:"; observations follow with a sentence saying they did
    not reject the change and that judging them is the reviewer's job; and
    environment issues follow with a sentence saying those checks never ran, so
    the change was never tested for them.
    """
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
    """The state a typed verdict is asked against, as one flat mapping.

    The task description, target, required interface and deterministic gate come
    from the contract's worker view. `original` is the file before the change:
    when it is None the contract's recorded target content is used instead, and
    an empty string stands for a change that creates a new file.
    """
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
    """The contract as the reviewer reads it, one constraint per line.

    Task type and task, then the target. The interface line appears only when
    the contract requires one, and each call the worker was allowed to make is
    listed with its path, signature and note. The conditions the worker was told
    to stop rather than guess on are listed last.
    """
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
    """The original-file section of the prompt.

    With content, the whole pre-change file is quoted. An empty string means the
    change creates `target`, and says so. None means the file was not supplied,
    and the reviewer is told that it is seeing the change without the file it
    changed and should judge only what the change itself shows.
    """
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
    """The prompt a prose reviewer is asked, as blank-line separated sections.

    The sections are, in order: who the reviewer is and that it wrote nothing
    here, the contract block, the deterministic gate summary, the original file,
    the change as applied to the target, and the instruction to open the reply
    with exactly one of the four outcome tokens. `original` follows
    `_original_block`, with None falling back to the contract's recorded target
    content.
    """
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


# Model identity. Two names that resolve to one set of weights must fold to one
# string here, and two names that resolve to different weights must not, because
# this folding is the whole of the self-review refusal.

# Letters that render as a Latin letter in another script: Cyrillic first, then
# Greek. Written as escapes so that the code point under test is readable in
# this file rather than being mistaken for the Latin letter it imitates.
_CONFUSABLES = str.maketrans(
    {
        # Cyrillic: \u0430 \u0435 \u043a \u043c \u043d \u043e \u0440 \u0441 \u0442
        # \u0443 \u0445 \u0455 \u0456 \u0458 \u045f \u045b \u0448 are not all of
        # them, only the ones a model name is likely to carry a homoglyph of.
        "\u0430": "a",  # CYRILLIC SMALL LETTER A
        "\u0435": "e",  # CYRILLIC SMALL LETTER IE
        "\u043a": "k",  # CYRILLIC SMALL LETTER KA
        "\u043c": "m",  # CYRILLIC SMALL LETTER EM
        "\u043d": "h",  # CYRILLIC SMALL LETTER EN
        "\u043e": "o",  # CYRILLIC SMALL LETTER O
        "\u0440": "p",  # CYRILLIC SMALL LETTER ER
        "\u0441": "c",  # CYRILLIC SMALL LETTER ES
        "\u0442": "t",  # CYRILLIC SMALL LETTER TE
        "\u0443": "y",  # CYRILLIC SMALL LETTER U
        "\u0445": "x",  # CYRILLIC SMALL LETTER HA
        "\u0455": "s",  # CYRILLIC SMALL LETTER DZE
        "\u0456": "i",  # CYRILLIC SMALL LETTER BYELORUSSIAN-UKRAINIAN I
        "\u0458": "j",  # CYRILLIC SMALL LETTER JE
        "\u0501": "d",  # CYRILLIC SMALL LETTER KOMI DE
        "\u051b": "q",  # CYRILLIC SMALL LETTER QA
        "\u051d": "w",  # CYRILLIC SMALL LETTER WE
        # Greek: as with the Cyrillic group, only the letters that look like one.
        "\u03b1": "a",  # GREEK SMALL LETTER ALPHA
        "\u03b2": "b",  # GREEK SMALL LETTER BETA
        "\u03b5": "e",  # GREEK SMALL LETTER EPSILON
        "\u03b9": "i",  # GREEK SMALL LETTER IOTA
        "\u03ba": "k",  # GREEK SMALL LETTER KAPPA
        "\u03bd": "v",  # GREEK SMALL LETTER NU
        "\u03bf": "o",  # GREEK SMALL LETTER OMICRON
        "\u03c1": "p",  # GREEK SMALL LETTER RHO
        "\u03c4": "t",  # GREEK SMALL LETTER TAU
        "\u03c5": "u",  # GREEK SMALL LETTER UPSILON
        "\u03c7": "x",  # GREEK SMALL LETTER CHI
    }
)

# Separators carry no information about which weights a name points at, so they
# are dropped after folding: `acme-coder`, `acme_coder`, `acme.coder` and
# `acme coder` are one name. The dash category is dropped as well, which catches
# the dash variants that are not spelled out in the literal string.
_SEPARATORS = "-_. \t\u2212"
_SEPARATOR_CATEGORY = "Pd"

# Ollama treats an untagged model name as `:latest` on its own, so the two
# spellings name the same weights and the tag is removed before comparing.
_DEFAULT_TAG = ":latest"

# A sharded checkpoint publishes one index name per shard. The shard marker says
# which piece of one set of weights a name is, not which weights they are, so it
# is dropped and every shard folds to the name of the unsharded model.
_SHARD = re.compile(r"-\d{1,5}-of-\d{1,5}$")


def model_identity(name: str) -> str:
    """Fold a model name to the identity of the weights it resolves to.

    The steps, in the order the code applies them: NFKC-normalise; drop control,
    format and line/paragraph/space separators (so an invisible character cannot
    tell two names apart); casefold; replace the homoglyphs in `_CONFUSABLES`;
    keep only the part after the last `\\` or `/`, so a provider prefix or a
    directory does not count; drop one weights suffix and, if there was one, a
    trailing shard marker; drop a trailing `:latest`; and finally drop the
    characters in `_SEPARATORS` and the dash category.

    Two spellings of one set of weights therefore fold to one string and two
    sets of weights stay distinct — a version tag is not a file. A name that
    folds to nothing returns the empty string, which compares equal to nothing.
    """
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


# The self-review refusal, as one function with two reasons so that each reason
# can be reported in its own words.


def _independence_fault(builder: str, reviewer: str) -> str | None:
    """Why this reviewer may not review this change, or None when it may.

    Two faults, both decided on `model_identity` alone. A name that folds to
    nothing leaves the two names' distance unestablished, so independence cannot
    be claimed. Two names that fold together are one model, and a model does not
    verify its own output — that is refused here, before any request is made.
    """
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
    """Whether the reviewer is a different model from the builder.

    The boolean face of `_independence_fault`, for the ladder code that has to
    pass over a rung without reporting a reason.
    """
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
    """Have `reviewer` judge `change` against `contract`, and return its review.

    The order is deliberate. A family under a `GATE_ONLY` policy owes no model
    review at all, so the gate is the whole bar and the review is unusable
    without anyone being asked. Next comes the independence check, before any
    spend. Then, when a `decide` seam is given, the typed verdict is tried
    first; it returns None only when the reviewer answered something unreadable,
    in which case the same reviewer is asked in prose. Finally the prose prompt
    is built and `ask` is called.

    Anything that goes wrong on the reviewer's side — the seam raising, a reply
    that names no outcome, a truncated reply — is unusable rather than a
    refusal: the change is not blamed for the reviewer's failure, and an
    unusable review is never an approval.
    """
    if required_policy(contract, family) == GATE_ONLY:
        # No prompt is built and no reviewer is asked: under this policy the
        # deterministic gate is the whole bar for work in this family, and
        # saying so is better than reporting an unasked review as agreement.
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
        # A reviewer-side failure is not the builder's failure and must not
        # become one. A refused connection, a timeout, a role with no source, a
        # reply cut short mid-sentence — each of them raises out of `ask` or
        # `read_verdict`, and each becomes an unusable review: the caller
        # records the change as accepted but unverified instead of failing work
        # that may be perfectly good. Every exception is caught here for that
        # reason, and the message keeps the type out of the way and the cause in.
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
    """The typed path, or None when it should fall back to prose.

    Builds the state, asks `decide` for a `Decision` and reads the boolean under
    `VERDICT_KEY`. A `_NOT_TYPED` error means the reviewer answered but the
    answer could not be read, so None sends `verify` on to a prose prompt on the
    same reviewer; any other error is the reviewer being unreachable, and is
    unusable.
    """
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
    """A typed-verdict seam bound to the verifier role, or None if it is unbound.

    The seam asks only `VERDICT_QUESTION` under `VERDICT_KEY`, through
    `classify_for`, so the answer is read from next-token probabilities rather
    than from prose.
    """
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
) -> Ask | None:
    """A prose-ask seam bound to the verifier role, or None if it is unbound.

    The request carries only the prompt, and its reply is sent the unit's
    maximum within the room the prompt leaves (`runner.at_unit_max`). A dispatch that
    comes back empty raises `ReviewerUnavailableError`, and a truncated reply
    raises `ReviewTruncatedError` through `_review_text`.
    """
    # A role with no model returns None instead of raising, so the caller can say
    # "the role has no model to ask" once, where the reviewer is chosen, rather
    # than at the first change that needs reviewing.
    if source_map.role_model(VERIFIER_ROLE) is None:
        return None

    def ask(prompt: str) -> str:
        completion = dispatch_role(
            source_map,
            VERIFIER_ROLE,
            Request(prompt=prompt, max_output_tokens=None),
            capacity=capacity,
        )
        if completion is None:  # unreachable once the role has a model
            raise ReviewerUnavailableError(
                f"the {VERIFIER_ROLE!r} role has no source to dispatch to"
            )
        return _review_text(completion, f"the {VERIFIER_ROLE!r} role")

    return ask


def _review_text(completion: Completion, who: str) -> str:
    """The text of a review completion, unless it was cut short.

    A truncated completion raises `ReviewTruncatedError` naming `who`: the part
    that arrived may stop before the verdict, so none of it is read.
    """
    if completion.truncated:
        raise ReviewTruncatedError(
            f"the review from {who} was cut short, so its verdict is not read"
        )
    return completion.text


# A chosen reviewer, as the caller that asks it and the result file that names it
# both need it.


@dataclass(frozen=True)
class Reviewer:
    """One reviewer that can be asked, and how it is named in the result.

    `model` is the model behind it and `ask` its prose seam; `decide` is the
    typed verdict seam and `jev` the typed JEV checks, either of which may be
    absent. `where` records how it was addressed (a config key or a rung), and
    `instead`, when set, says why this reviewer stood in for another. `unit` is
    the rung or unit name to name it by, when there is one.
    """

    model: str
    ask: Ask
    decide: Decide | None = None
    jev: JevCheck | None = None
    where: str = ""
    unit: str | None = None
    instead: str = ""

    @property
    def label(self) -> str:
        """How the result file and the journal name this reviewer.

        The unit when there is one, else the model, with the stand-in reason in
        parentheses when it stood in for the configured verifier.
        """
        who = self.unit or self.model
        return f"{who} ({self.instead})" if self.instead else who


@dataclass(frozen=True)
class NoReviewer:
    """No reviewer could be chosen, and the reason, in a sentence.

    The caller records the change as accepted but unverified, so the reason is
    read as the whole explanation of why nothing was asked.
    """

    reason: str


#: Choose a reviewer per builder rung name; the choice is memoised by the callers
#: of `reviewers_for`, so this is asked once per builder.
type Reviewers = Callable[[str], Reviewer | NoReviewer]


def _climb(config: Config, source_map: SourceMap) -> list[tuple[str, Rung]]:
    """Every rung of the ladder in climb order, tagged with its family name.

    Families come cheapest first (`Family.rank`), and each family's rungs keep
    the order they are mapped in.
    """
    grouped = by_family(config, source_map)
    return [
        (family.name, rung)
        for family in sorted(grouped, key=lambda family: family.rank)
        for rung in grouped[family]
    ]


def reviewer_rung(config: Config, source_map: SourceMap, builder: str) -> str | None:
    """The rung that reviews work built on `builder`, or None if there is none.

    The first rung above `builder` on the climb that is in the local family,
    serves a model other than the builder's and is up. A hosted family is passed
    over whatever its model: a hosted reviewer is asked only when
    `verifier.unit` names it. A rung a record says is down — slept, or put down
    for a sleeper — is passed over too, since a review never wakes a unit. None
    when `builder` is not on the climb, or when nothing above it qualifies — the
    dearest local rung has nothing dearer than itself.
    """
    from mcgyvr.wake import known_down

    climb = _climb(config, source_map)
    names = [rung.name for _, rung in climb]
    if builder not in names:
        return None
    built_with = climb[names.index(builder)][1].model
    for family, rung in climb[names.index(builder) + 1 :]:
        if (
            family == LOCAL_FAMILY
            and independent(built_with, rung.model)
            and known_down(config, rung.name) is None
        ):
            return rung.name
    return None


def stand_in_rung(
    config: Config, source_map: SourceMap, builder: str, unit: str
) -> str | None:
    """A rung that may review in place of `unit` when the unit built the change.

    The anchor is `unit`'s place on the climb, or `builder`'s when the unit is
    not on the ladder. Candidates are the rungs below the anchor, nearest first,
    then the rungs above it, in that order. A candidate is passed over when it is
    the builder's own rung or serves the builder's model, whatever its name, and
    when a record says it is down. A local candidate always qualifies; a hosted
    one only when `unit` is itself hosted, and only from below the anchor — a
    stand-in never costs more than the review the operator chose.
    """
    from mcgyvr.wake import known_down

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
        if known_down(config, rung.name) is not None:
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
    """Build the chooser that names a reviewer for each builder rung.

    With `verifier.enabled: false` every builder gets the same `NoReviewer`.
    With `verifier.unit` set, that unit is the reviewer, asked through the role
    seams, unless it serves the model that built the change — then
    `_standing_in` looks for a rung that may review instead, as it does when a
    record says the unit is down. With no unit set, `_on_rung` picks the next
    dearer local rung serving another model. Which rung reviews is asked again
    for every builder, since a swap can put a unit down mid-run; the reviewer
    built for each builder and rung is reused.
    """
    from mcgyvr.wake import known_down

    if not config.get("verifier.enabled", True):
        off = NoReviewer("review is switched off by `verifier.enabled: false`")
        return lambda builder: off

    unit = config.get("verifier.unit")
    picked: dict[tuple[str, str | None], Reviewer | NoReviewer] = {}
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
            down = known_down(config, str(unit))
            if down is None and (built is None or not _same_model(built.model, model)):
                return named
            key = (builder, stand_in_rung(config, source_map, builder, str(unit)))
            if key not in picked:
                picked[key] = _standing_in(
                    config,
                    source_map,
                    builder,
                    str(unit),
                    model,
                    capacity=capacity,
                    timeout_s=timeout_s,
                    down=down,
                )
            return picked[key]

        return named_or_stand_in

    def pick(builder: str) -> Reviewer | NoReviewer:
        key = (builder, reviewer_rung(config, source_map, builder))
        if key not in picked:
            picked[key] = _on_rung(
                config, source_map, builder, capacity=capacity, timeout_s=timeout_s
            )
        return picked[key]

    return pick


def _same_model(builder: str, reviewer: str) -> bool:
    """Whether two names fold to one model, with a blank name matching nothing.

    The identity comparison the stand-in branch needs, kept apart from
    `independent` so that a blank name is a non-match rather than a fault.
    """
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
    down: str | None = None,
) -> Reviewer | NoReviewer:
    """The reviewer for work the configured verifier unit cannot review.

    Either its model wrote the change, or `down` says why a record has the unit
    down — a review never wakes a unit. Asks `stand_in_rung` for a rung that may
    review instead and, when one comes back with a source, builds it through
    `_askable` with the reason for standing in. With no such rung the answer is
    a `NoReviewer` that gives the reason and names what a fallback would have to
    be.
    """
    if down is not None:
        why = (
            f"`verifier.unit` {unit!r} is down ({down}), and a review never "
            f"wakes a unit"
        )
        instead = f"a fallback for `verifier.unit` {unit!r}, which is down"
    else:
        why = (
            f"`verifier.unit` {unit!r} serves {model!r}, the model that wrote this "
            f"change, and a model does not review its own output"
        )
        instead = (
            f"a fallback for `verifier.unit` {unit!r}, whose model {model!r} "
            f"wrote this change"
        )
    rung = stand_in_rung(config, source_map, builder, unit)
    offered = source_map.get(rung) if rung is not None else None
    if rung is None or offered is None:
        return NoReviewer(
            f"{why}; no other unit was available to review it instead — a "
            f"fallback is a usable rung whose model is not the builder's, local, "
            f"or hosted and below a hosted `verifier.unit` on the ladder"
        )
    return _askable(
        source_map,
        rung,
        offered.model,
        capacity=capacity,
        timeout_s=timeout_s,
        instead=instead,
    )


def _on_rung(
    config: Config,
    source_map: SourceMap,
    builder: str,
    *,
    capacity: Capacity | None,
    timeout_s: float | None,
) -> Reviewer | NoReviewer:
    """The reviewer for a builder when no `verifier.unit` is configured.

    The rung `reviewer_rung` names, built through `_askable`, or a `NoReviewer`
    explaining that nothing above the builder in the local family serves another
    model and that only `verifier.unit` can bring in a hosted reviewer.
    """
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
    """A `Reviewer` that dispatches everything to one rung.

    The prose ask is a plain `dispatch` to `rung`, sent the unit's maximum
    reply within the room the prompt leaves (`runner.at_unit_max`), and
    the typed seams are `classify_for` on the same rung — one for the verdict,
    one for `JEV_QUESTIONS`. Both typed seams go through one `_TypedMemory`, so a
    refusal recorded by either is remembered by both. `instead` is carried into
    the label when this reviewer stands in for another.
    """

    def ask(prompt: str) -> str:
        completion = dispatch(
            source_map,
            rung,
            Request(prompt=prompt, max_output_tokens=None),
            capacity=capacity,
        )
        return _review_text(completion, f"rung {rung!r}")

    def by_rung(state: Any, questions: Mapping[str, Question]) -> Decision:
        # One place to dispatch typed questions to this rung: the verdict and the
        # JEV checks differ only in which questions they put to it.
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
    """Remembers a reviewer's first unreadable answer, per reviewer.

    A reviewer that could not answer one typed question is not asked another:
    once `refused` is set, every seam built by `guard` re-raises that same
    exception instead of spending another request on a model that has shown it
    cannot be read this way.
    """

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
