""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr import whole
from mcgyvr.local_pool import Endpoint, PoolError, SourceMap
from mcgyvr.runner import SERVER_SAMPLED, _post_json, _url_for, request_timeout

if TYPE_CHECKING:  #
    from mcgyvr.capacity import Capacity

#
#ry
#
_CHOICE_LABELS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")

#
_YES_LABELS = ("Yes", "No")

#
_MAX_TOP_LOGPROBS = 20

#
#
JEV_ROLE = "jev"


class DecisionError(Exception):
    ""


class UnboundRoleError(PoolError):
    ""


#


@dataclass(frozen=True)
class Choice:
    ""

    instructions: str
    options: Mapping[str, str]


@dataclass(frozen=True)
class Noul:
    ""

    instructions: str


@dataclass(frozen=True)
class Score:
    ""

    instructions: str
    levels: tuple[str, ...]


Question = Choice | Noul | Score


#


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
    ""

    answers: Mapping[str, Answer]


#


def labels_for(question: Question) -> tuple[str, ...]:
    ""
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


#


def build_prompt(state: Any, name: str, question: Question) -> str:
    ""
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


#


def probabilities_from_logprobs(
    top_logprobs: Sequence[Mapping[str, Any]], labels: Sequence[str]
) -> tuple[float, ...]:
    ""
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
    ""
    count = len(probabilities)
    if count <= 1:
        return 1.0
    peak = max(probabilities)
    return (count * peak - 1.0) / (count - 1.0)


def answer_for(question: Question, top_logprobs: Sequence[Mapping[str, Any]]) -> Answer:
    ""
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
    ""
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


#


def classify(
    endpoint: Endpoint,
    model: str,
    state: Any,
    questions: Mapping[str, Question],
    *,
    timeout_s: float | None = None,
) -> Decision:
    ""
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
            #
            #he
            #bs
            #
            #
            #
            #
            #
            #
            #
            #
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if endpoint.sampling != SERVER_SAMPLED:
            #
            #
            payload["temperature"] = 0.0
        #
        #
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
    ""
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
    ""
    endpoint = source_map.bind(rung)
    offered = source_map.get(rung)
    model = offered.model if offered is not None else rung
    if capacity is None:
        return classify(endpoint, model, state, questions, timeout_s=timeout_s)
    with capacity.hold(endpoint):
        return classify(endpoint, model, state, questions, timeout_s=timeout_s)


def jev_bound(source_map: SourceMap) -> bool:
    ""
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
    ""
    if (role is None) == (rung is None):
        raise ValueError(
            "classify_for falls back to a role or a rung: name exactly one, "
            f"not role={role!r} and rung={rung!r}"
        )
    asked = JEV_ROLE if jev_bound(source_map) else role
    if asked is None:
        assert rung is not None  #
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
