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
decision and a dispatch reach a unit identically. The only differences are in
the request body: ``logprobs`` instead of a generation cap, and the template
argument that turns a thinking model's thinking off for the one token asked
(``chat_template_kwargs``).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.pool import Endpoint, PoolError, SourceMap
from mcgyvr.runner import SERVER_SAMPLED, _post_json, _url_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcgyvr.capacity import Capacity

#: Single-token labels for a choice, most common first. 26 upper-case letters,
#: then 26 lower-case, then 10 digits — 62 labels, the most one token can carry
#: without inventing multi-token labels.
_CHOICE_LABELS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")

#: The two single-token labels a yes/no question is asked to pick between.
_YES_LABELS = ("Yes", "No")

#: The highest ``top_logprobs`` the compatible servers agree to return.
_MAX_TOP_LOGPROBS = 20

#: What the pool calls the unit that answers every typed decision, once
#: ``jev.unit`` binds one (:func:`classify_for`).
JEV_ROLE = "jev"


class DecisionError(Exception):
    """The endpoint answered, but not in a shape a decision can be read from."""


class UnboundRoleError(PoolError):
    """A decision was asked of a role that has no unit bound to answer it."""


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
            "stream": False,
            "logprobs": True,
            "top_logprobs": min(_MAX_TOP_LOGPROBS, len(labels)),
            # A thinking model's template opens every reply with its thinking
            # tag — Qwen3's first token was `<think>` at probability 1.0 in the
            # pilot — so no label can appear in the first token's top_logprobs
            # and every question is unreadable. The template argument turns
            # it off for this request alone, whatever the unit was launched
            # with: llama-server and vLLM both read `chat_template_kwargs` as
            # template arguments (the llama.cpp server README: "Allows sending
            # additional parameters to the json templating system. For
            # example: {"enable_thinking": false}"; vllm ChatCompletionRequest
            # .chat_template_kwargs). A generation (mcgyvr.runner) sends none:
            # a conversing model keeps its thinking.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if endpoint.sampling != SERVER_SAMPLED:
            # Greedy, as a decision must be; a unit whose server fixes its own
            # sampling refuses the field (`units.<unit>.sampling: server`).
            payload["temperature"] = 0.0
        document = _post_json(url, payload, headers, timeout_s)
        answers[name] = answer_for(question, _top_logprobs(document))
    return Decision(answers=answers)


def classify_role(
    source_map: SourceMap,
    role: str,
    state: Any,
    questions: Mapping[str, Question],
    *,
    capacity: Capacity | None = None,
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Decision | None:
    """Answer ``questions`` on the model a non-ladder ``role`` binds, or ``None``.

    :func:`classify` takes an :class:`~mcgyvr.pool.Endpoint`; this is the same
    seam crossing :func:`~mcgyvr.runner.dispatch_role` performs for a
    generation, done here for a decision. ``None`` mirrors
    :meth:`~mcgyvr.pool.SourceMap.role`: a role with no binding is an ordinary
    answer, not a failure, and a role declared but unusable still raises.

    ``capacity`` bounds the decision the way a dispatch is bounded — the role
    is the same machine as the ladder, and holding its source's slot for the
    length of the decision is what keeps a batch of classifications from
    describing a different machine than the one under load.
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
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Decision:
    """Answer ``questions`` on the model a ladder ``rung`` serves.

    :func:`classify_role` one seam over, for a rung rather than a role: the
    endpoint is the rung's own (:meth:`~mcgyvr.pool.SourceMap.bind`), the model
    is the one the rung names, and the slot is the per-source one a dispatch
    to that rung holds. Raises what ``bind`` raises for a rung the ladder does
    not offer, because asking a rung that is not there is a caller's mistake.
    """
    endpoint = source_map.bind(rung)
    offered = source_map.get(rung)
    model = offered.model if offered is not None else rung
    if capacity is None:
        return classify(endpoint, model, state, questions, timeout_s=timeout_s)
    with capacity.hold(endpoint):
        return classify(endpoint, model, state, questions, timeout_s=timeout_s)


def jev_bound(source_map: SourceMap) -> bool:
    """Whether ``jev.unit`` binds a unit, so every typed decision asks it.

    Raises what :meth:`~mcgyvr.pool.SourceMap.role_model` raises for a Jev
    unit declared on a source that cannot serve: a ``jev.unit`` that is
    misconfigured is not the same answer as no ``jev.unit`` at all, and
    falling back to the old askers in silence would hide the binding.
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
    timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
) -> Decision:
    """Ask the Jev unit when one is bound; else the ``role`` or ``rung`` named.

    The one place that chooses who answers a typed decision. With ``jev.unit``
    bound, every caller's questions go to that unit (:func:`classify_role` on
    :data:`JEV_ROLE`). Without it, each caller's go where they went before a
    Jev unit existed: the fallback ``role`` through :func:`classify_role`, or
    the fallback ``rung`` through :func:`classify_rung`. Exactly one of the two
    is named, or this raises :class:`ValueError`.

    A fallback role with no unit raises :class:`UnboundRoleError` rather than
    returning ``None``: every caller checked that its role was bound before it
    built the thing that asks, so reaching an unbound one here is a fault, not
    an ordinary absence.
    """
    if (role is None) == (rung is None):
        raise ValueError(
            "classify_for falls back to a role or a rung: name exactly one, "
            f"not role={role!r} and rung={rung!r}"
        )
    asked = JEV_ROLE if jev_bound(source_map) else role
    if asked is None:
        assert rung is not None  # narrowed by the check above
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
