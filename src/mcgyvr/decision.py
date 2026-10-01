"""Typed decisions over a unit's next-token probabilities.

The Jev-class primitive: a caller hands a :class:`~mcgyvr.pool.Endpoint` some
``state`` and a set of typed ``questions``, and gets back typed ``answers``
with a probability per option — never prose. A :class:`Choice` picks one of
several options, a :class:`Noul` answers yes or no, and a :class:`Score` rates
on a rubric. Each is a bounded judgment, and the model is asked to produce it
as a single token, so there is nothing to parse and no way to get an invalid
class back.

The mechanism is next-token probability, not generation. Every question
becomes one chat prompt — the state, the question, and the options under
single-token labels — sent with ``max_tokens: 1`` and ``logprobs``. The answer
is read from the labels' probabilities in the reply's ``top_logprobs``, so a
small model served by llama.cpp or vLLM answers a decision without ever
composing a sentence. Labels are ``Yes``/``No`` for a :class:`Noul`, digits for
a :class:`Score`, and letters for a :class:`Choice`.

Two limits are named rather than hidden:

* **A choice holds at most 62 options, and a score at most 10 levels.** Those
  are the single-token labels this module can hand back (letters, then digits).
* **``top_logprobs`` is capped at 20**, the value the OpenAI-compatible
  servers agree on. A choice with more than 20 options cannot see every label
  in one call: labels beyond the server's top 20 read as zero. Larger choices
  want a two-stage ranking (shortlist, then re-judge), which is a caller's
  decision, not this module's.

The transport is :func:`~mcgyvr.runner._post_json` and
:func:`~mcgyvr.runner._url_for`, the same wire path the runner uses, so a
decision and a dispatch reach a unit identically. The only difference is the
request body: ``logprobs`` instead of a generation cap.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.pool import Endpoint
from mcgyvr.runner import _post_json, _url_for

#: Single-token labels for a choice, most common first. 26 upper-case letters,
#: then 26 lower-case, then 10 digits — 62 labels, the most one token can carry
#: without inventing multi-token labels.
_CHOICE_LABELS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")

#: The two single-token labels a yes/no question is asked to pick between.
_YES_LABELS = ("Yes", "No")

#: The highest ``top_logprobs`` the compatible servers agree to return.
_MAX_TOP_LOGPROBS = 20


class DecisionError(Exception):
    """The endpoint answered, but not in a shape a decision can be read from."""


# --- questions -------------------------------------------------------------


@dataclass(frozen=True)
class Choice:
    """Pick exactly one option, keyed by name, with a probability for each."""

    instructions: str
    options: Mapping[str, str]


@dataclass(frozen=True)
class Noul:
    """A yes/no question."""

    instructions: str


@dataclass(frozen=True)
class Score:
    """Rate on a rubric of ``levels``, lowest first."""

    instructions: str
    levels: tuple[str, ...]


Question = Choice | Noul | Score


# --- answers ---------------------------------------------------------------


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
    """One answer per question, keyed by the question's name."""

    answers: Mapping[str, Answer]


# --- the label scheme ------------------------------------------------------


def labels_for(question: Question) -> tuple[str, ...]:
    """The single-token labels a question is answered under, in order.

    :class:`Noul` is ``("Yes", "No")``; :class:`Score` is the digits up to its
    level count; :class:`Choice` is letters. The returned order is the order
    the probabilities are read back in.
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


# --- the prompt ------------------------------------------------------------


def build_prompt(state: Any, name: str, question: Question) -> str:
    """The chat prompt that asks ``question`` for a single-token answer.

    The state is serialized once and placed before the question. The options
    are listed under their labels, so the label is the only token the model is
    asked to produce.
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


# --- reading an answer -----------------------------------------------------


def probabilities_from_logprobs(
    top_logprobs: Sequence[Mapping[str, Any]], labels: Sequence[str]
) -> tuple[float, ...]:
    """The normalized probability of each label, from a ``top_logprobs`` list.

    Each entry is a ``{"token": ..., "logprob": ...}`` object. A label the
    server did not return reads as zero. The result sums to 1 when any label
    is present, and raises :class:`ProtocolError` when none is — an answer
    whose labels are all absent is not a weak answer, it is unreadable.
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
    """How far the peak stands above a uniform answer, from 0 to 1.

    ``(n * peak - 1) / (n - 1)``: a flat distribution is 0, a single certain
    label is 1. A single option has no spread and reads as certain.
    """
    count = len(probabilities)
    if count <= 1:
        return 1.0
    peak = max(probabilities)
    return (count * peak - 1.0) / (count - 1.0)


def answer_for(question: Question, top_logprobs: Sequence[Mapping[str, Any]]) -> Answer:
    """The typed answer a ``top_logprobs`` list reads as, for one question."""
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
    """The first token's ``top_logprobs`` list, or a :class:`ProtocolError`."""
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


# --- the network call ------------------------------------------------------


def classify(
    endpoint: Endpoint,
    model: str,
    state: Any,
    questions: Mapping[str, Question],
    *,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Decision:
    """Answer ``questions`` about ``state`` on ``model``, served by ``endpoint``.

    One request per question, each sent with ``max_tokens: 1`` and ``logprobs``
    and read from the reply's ``top_logprobs``. A keyless endpoint gets no
    ``Authorization`` header, the same as a dispatch through the runner.
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
            "temperature": 0.0,
            "stream": False,
            "logprobs": True,
            "top_logprobs": min(_MAX_TOP_LOGPROBS, len(labels)),
        }
        document = _post_json(url, payload, headers, timeout_s)
        answers[name] = answer_for(question, _top_logprobs(document))
    return Decision(answers=answers)
