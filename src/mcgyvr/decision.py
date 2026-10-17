"""Typed decisions read from a single token of an endpoint's reply.

A question is one of three shapes: a Choice of named options, a Noul asking
yes or no, or a Score rating on an ordered scale. build_prompt renders the
state, the question and the labels a reply may use; classify sends that to an
OpenAI-compatible chat completions endpoint for exactly one token with the log
probabilities of the alternatives at that position, and answer_for turns the
resulting distribution over the label tokens into a ChoiceAnswer, BoolAnswer
or ScoreAnswer. A caller therefore gets a value together with the probability
of every option and a confidence, instead of a string to parse.

classify_role and classify_rung resolve an endpoint out of a SourceMap, and
classify_for chooses between the two, preferring the jev role when a unit is
bound to it.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr import whole
from mcgyvr.local_pool import Endpoint, PoolError, SourceMap
from mcgyvr.runner import SERVER_SAMPLED, _post_json, _url_for, request_timeout

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity

#: Labels a Choice reply may use, in order: upper case letters, then lower
#: case ones, then digits. A Choice with more options than there are labels
#: has no single-token label per option, which labels_for refuses.
_CHOICE_LABELS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")

#: Labels a Noul reply may use, in order: index 0 is Yes, index 1 is No.
_YES_LABELS = ("Yes", "No")

#: Ceiling on how many alternatives a request asks the endpoint for per position.
_MAX_TOP_LOGPROBS = 20

#: Role that answers every decision once a unit is bound to it: the judge of
#: every verdict. classify_for prefers it over the role its caller names.
JEV_ROLE = "jev"


class DecisionError(Exception):
    """The reply cannot be read as a decision, so no answer can be taken from it."""


class UnboundRoleError(PoolError):
    """A decision was asked of a role that has no unit bound to answer it."""


# A question is the instructions put to the endpoint plus the shape of its reply;
# the Question union below is the three shapes that can be asked.


@dataclass(frozen=True)
class Choice:
    """Pick one of `options`: the reply's label names the option key answered."""

    instructions: str
    options: Mapping[str, str]


@dataclass(frozen=True)
class Noul:
    """A yes or no question: the answer is true when Yes is at least as likely as No."""

    instructions: str


@dataclass(frozen=True)
class Score:
    """Rate on 2 to 10 named levels, lowest first; the reply's digit is the index."""

    instructions: str
    levels: tuple[str, ...]


Question = Choice | Noul | Score


# What each kind of question is answered with, with its probabilities and
# confidence.


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: Mapping[str, float]
    confidence: float


@dataclass(frozen=True)
class BoolAnswer:
    value: bool
    probability_true: float
    confidence: float


@dataclass(frozen=True)
class ScoreAnswer:
    level: float
    probabilities: Mapping[str, float]
    confidence: float


Answer = ChoiceAnswer | BoolAnswer | ScoreAnswer


@dataclass(frozen=True)
class Decision:
    """The answers to the questions asked, keyed by the name each was asked under."""

    answers: Mapping[str, Answer]


# Reading a question into labels and a prompt, and a reply back into a decision.


def labels_for(question: Question) -> tuple[str, ...]:
    """The single-token labels a reply to this question may use, in the order
    its values take them: Yes and No for a Noul, one digit per level for a
    Score, and one letter per option for a Choice.

    A Score is held to 2 to 10 levels and a Choice to 1 to 62 options, since
    outside those ranges a label would need more than one token; a ValueError
    says which limit was crossed.
    """
    if isinstance(question, Noul):
        return _YES_LABELS
    if isinstance(question, Score):
        if not 2 <= len(question.levels) <= 10:
            raise ValueError(
                "a Score holds 2 to 10 levels, got "
                f"{len(question.levels)}. A rating outside that range has no "
                "single-token label to read."
            )
        return tuple("0123456789"[: len(question.levels)])
    if not 1 <= len(question.options) <= len(_CHOICE_LABELS):
        raise ValueError(
            f"a Choice holds 1 to {len(_CHOICE_LABELS)} options, got "
            f"{len(question.options)}. More options have no single-token "
            "label to read."
        )
    return _CHOICE_LABELS[: len(question.options)]


# The text of a question: the state it is about, then the question and the
# labels it may be answered with.


def build_prompt(state: Any, name: str, question: Question) -> str:
    """Render the prompt for one question: the state as JSON, the question's
    instructions under its name, and then the labels from `labels_for` the
    reply may use, each with what it stands for, so the model answers with a
    single label token.
    """
    state_json = json.dumps(state, ensure_ascii=False)
    lines = [
        "Answer a typed question about the state below. Reply with exactly one "
        "token, and nothing else.",
        "",
        "State:",
        state_json,
        "",
        f'Question "{name}": {question.instructions}',
    ]
    if isinstance(question, Noul):
        lines += ["", "Answer with exactly one token:", "Yes", "No"]
        return "\n".join(lines)
    if isinstance(question, Score):
        lines += ["", "Rate on this scale, lowest first:", ""]
        for index, level in enumerate(question.levels):
            lines.append(f"{index}: {level}")
        lines += ["", "Answer with exactly one token: the number of your rating."]
        return "\n".join(lines)
    labels = labels_for(question)
    lines += ["", "Options:", ""]
    for label, (_key, description) in zip(
        labels, question.options.items(), strict=True
    ):
        lines.append(f"{label}: {description}")
    lines += ["", "Answer with exactly one token: the letter of your option."]
    return "\n".join(lines)


# A reply's log probabilities read as label probabilities, and how decided they
# are.


def probabilities_from_logprobs(
    top_logprobs: Sequence[Mapping[str, Any]], labels: Sequence[str]
) -> tuple[float, ...]:
    """The probability of each label, in label order, from the alternatives the
    endpoint reported at the reply's first position.

    Each reported token's logprob is exponentiated; a label the endpoint did
    not report counts as 0.0. The values are then divided by their own total,
    so the returned probabilities sum to 1 over the labels alone and any mass
    the endpoint gave to other tokens is dropped. When no label was reported
    at all the total is 0.0 and a DecisionError says the reply cannot be read.
    """
    by_token: dict[str, float] = {}
    for entry in top_logprobs:
        token = entry.get("token")
        logprob = entry.get("logprob")
        if isinstance(token, str) and isinstance(logprob, (int, float)):
            by_token[token] = math.exp(float(logprob))
    raw = [by_token.get(label, 0.0) for label in labels]
    total = sum(raw)
    if total <= 0.0:
        raise DecisionError(
            f"no label from {labels!r} appeared in the reply's top_logprobs; "
            "the answer cannot be read as a decision."
        )
    return tuple(probability / total for probability in raw)


def confidence(probabilities: Sequence[float]) -> float:
    """How far the likeliest label stands above a flat distribution over the
    same number of labels: 0.0 when they are all equally likely, 1.0 when one
    holds all the probability, and 1.0 for fewer than two labels.
    """
    count = len(probabilities)
    if count <= 1:
        return 1.0
    peak = max(probabilities)
    return (count * peak - 1.0) / (count - 1.0)


def answer_for(question: Question, top_logprobs: Sequence[Mapping[str, Any]]) -> Answer:
    """Read a reply, by its top logprobs, as the answer its question asks for.

    A Noul is true when Yes is at least as likely as No, with
    `probability_true` the probability of Yes. A Score reports the expected
    level, the sum of each level's index times its probability, alongside the
    probabilities per level. A Choice reports the key of the likeliest option,
    the first of them when two tie. All three carry the same `confidence` for
    the distribution they were read from.
    """
    labels = labels_for(question)
    probabilities = probabilities_from_logprobs(top_logprobs, labels)
    strength = confidence(probabilities)
    if isinstance(question, Noul):
        return BoolAnswer(
            value=probabilities[0] >= probabilities[1],
            probability_true=probabilities[0],
            confidence=strength,
        )
    if isinstance(question, Score):
        expected = sum(
            index * probability for index, probability in enumerate(probabilities)
        )
        return ScoreAnswer(
            level=expected,
            probabilities=dict(zip(question.levels, probabilities, strict=True)),
            confidence=strength,
        )
    keys = tuple(question.options)
    peak = max(range(len(keys)), key=lambda index: probabilities[index])
    return ChoiceAnswer(
        choice=keys[peak],
        probabilities=dict(zip(keys, probabilities, strict=True)),
        confidence=strength,
    )


def _top_logprobs(document: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """The reported alternatives for the reply's first token, taken from
    `choices[0].logprobs.content[0].top_logprobs`; entries that are not
    mappings are dropped. A document missing any of those levels raises a
    DecisionError naming what the endpoint left out, since no answer can be
    read without them.
    """
    choices = document.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DecisionError(
            "the endpoint answered with no choices, so no decision can be read"
        )
    first = choices[0]
    logprobs = first.get("logprobs") if isinstance(first, dict) else None
    content = logprobs.get("content") if isinstance(logprobs, dict) else None
    if not isinstance(content, list) or not content:
        raise DecisionError(
            "the endpoint answered without logprobs content, so no decision can be read"
        )
    entry = content[0]
    top = entry.get("top_logprobs") if isinstance(entry, dict) else None
    if not isinstance(top, list) or not top:
        raise DecisionError(
            "the endpoint answered without top_logprobs, so no decision can be read"
        )
    return tuple(item for item in top if isinstance(item, dict))


# Asking an endpoint the questions one request at a time, and reading each reply.


def classify(
    endpoint: Endpoint,
    model: str,
    state: Any,
    questions: Mapping[str, Question],
    *,
    timeout_s: float | None = None,
) -> Decision:
    """Ask `endpoint`, serving `model`, every question in `questions`, and read
    each reply into an answer under the name the question was asked by.

    Each question is one streamed chat completion for a single token, with the
    alternatives at that position reported: one per label of the question, but
    never more than `_MAX_TOP_LOGPROBS`, and thinking disabled in the chat
    template so the one token is the answer rather than the start of a
    reasoning trace. A credential from the endpoint, when it has one, is sent
    as a bearer token. Unless the unit fixes its own sampling on the server
    side, the temperature is set to 0.0.

    A transport or endpoint failure surfaces as the error `_post_json` raises,
    and a reply carrying no readable alternative raises DecisionError. The
    endpoint is asked once per question, in the order the questions are given.
    The timeout is `timeout_s` when it is given, otherwise the one resolved
    from the endpoint.
    """
    url = _url_for(endpoint.base_url, "/v1/chat/completions")
    headers = {"Content-Type": "application/json"}
    key = endpoint.credential()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    answers: dict[str, Answer] = {}
    for name, question in questions.items():
        prompt = build_prompt(state, name, question)
        labels = labels_for(question)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1,
            "logprobs": True,
            "top_logprobs": min(_MAX_TOP_LOGPROBS, len(labels)),
            # One token is the whole reply: max_tokens asks for exactly one, so
            # the first position of the reply is the answer, and logprobs asks
            # for the log probabilities the endpoint reports at that position.
            # top_logprobs sets how many alternatives to report there: one per
            # label, capped at _MAX_TOP_LOGPROBS, so every label the question
            # offers has a chance to appear. A shorter list would hide probability
            # the answer depends on, and a longer one would report tokens no
            # label of this question uses.
            # enable_thinking is off in the chat template, so a reasoning unit
            # spends its single token on the label itself instead of opening a
            # thinking block that would use up the token and leave no label to read.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if endpoint.sampling != SERVER_SAMPLED:
            # This unit takes its sampling from the request, so pin the
            # temperature to 0.0 and let the labels be as reproducible as it allows.
            payload["temperature"] = 0.0
        # A server-sampled unit fixes its own sampling and refuses a temperature
        # parameter, so the field is left out of its request entirely.
        document = _post_json(
            url, whole.asking(payload), headers, request_timeout(endpoint, timeout_s)
        )
        answers[name] = answer_for(question, _top_logprobs(document))
    return Decision(answers=answers)


def classify_role(
    source_map: SourceMap,
    role: str,
    state: Any,
    questions: Mapping[str, Question],
    *,
    capacity: Capacity | None = None,
    timeout_s: float | None = None,
) -> Decision | None:
    """Ask the unit bound to `role`, or return None when no unit is bound to it.

    An unknown role, or one whose unit could not be built, raises from the
    source map instead of returning None. When `capacity` is given, the
    request is made while holding that endpoint's slot.
    """
    binding = source_map.role(role)
    if binding is None:
        return None
    if capacity is None:
        return classify(
            binding.endpoint, binding.model, state, questions, timeout_s=timeout_s
        )
    with capacity.hold(binding.endpoint):
        return classify(
            binding.endpoint, binding.model, state, questions, timeout_s=timeout_s
        )


def classify_rung(
    source_map: SourceMap,
    rung: str,
    state: Any,
    questions: Mapping[str, Question],
    *,
    capacity: Capacity | None = None,
    timeout_s: float | None = None,
) -> Decision:
    """Ask the rung named `rung`, resolving its endpoint and model from the map.

    An unknown or unavailable rung raises from the source map. The model is the
    one the rung is configured with, falling back to the rung name when the map
    holds no rung by that name. When `capacity` is given, the request is made
    while holding that endpoint's slot.
    """
    endpoint = source_map.bind(rung)
    offered = source_map.get(rung)
    model = offered.model if offered is not None else rung
    if capacity is None:
        return classify(endpoint, model, state, questions, timeout_s=timeout_s)
    with capacity.hold(endpoint):
        return classify(endpoint, model, state, questions, timeout_s=timeout_s)


def jev_bound(source_map: SourceMap) -> bool:
    """Whether a unit is bound to the jev role, which is what makes classify_for
    send it the decisions rather than the role its caller names.
    """
    return source_map.role_model(JEV_ROLE) is not None


def classify_for(
    source_map: SourceMap,
    state: Any,
    questions: Mapping[str, Question],
    *,
    role: str | None = None,
    rung: str | None = None,
    capacity: Capacity | None = None,
    timeout_s: float | None = None,
) -> Decision:
    """Ask for a decision through the source map, naming exactly one of `role`
    and `rung`; naming both or neither raises ValueError.

    When a unit is bound to the `jev` role it answers whatever `role` says, so
    the caller's choice of role only matters while jev is unbound. Otherwise
    the named role answers, and a role the map reports as bound to nothing
    raises UnboundRoleError. With jev unbound and no role named, the rung
    answers.
    """
    if (role is None) == (rung is None):
        raise ValueError(
            "classify_for falls back to a role or a rung: name exactly one, "
            f"not role={role!r} and rung={rung!r}"
        )
    asked = JEV_ROLE if jev_bound(source_map) else role
    if asked is None:
        assert rung is not None  # the check above guarantees the rung was named
        return classify_rung(
            source_map, rung, state, questions, capacity=capacity, timeout_s=timeout_s
        )
    decision = classify_role(
        source_map, asked, state, questions, capacity=capacity, timeout_s=timeout_s
    )
    if decision is None:
        raise UnboundRoleError(
            f"the {asked!r} role has no unit bound to answer a decision"
        )
    return decision
