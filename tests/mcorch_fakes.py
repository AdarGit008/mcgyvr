"""Scripted doubles for mcorch's two seams, so no test needs a model.

``ScriptedRung`` answers each call from a script and records what it was
asked; ``ScriptedJev`` answers each typed question from a script keyed by the
question's name. Both refuse an unscripted ask with an ``AssertionError``, so a
test that asks one question too many fails where it asked rather than on a
default nobody wrote.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcgyvr.decision import (
    Answer,
    BoolAnswer,
    Choice,
    ChoiceAnswer,
    Decision,
    Noul,
    Question,
    Score,
    ScoreAnswer,
)
from mcgyvr.mcorch.wire import RungCall, RungReply, RungToolCall


class ScriptedRung:
    """A rung that answers from a script and keeps every call it was sent."""

    def __init__(self, *replies: RungReply) -> None:
        self._replies = list(replies)
        self.calls: list[RungCall] = []

    def __call__(self, call: RungCall) -> RungReply:
        self.calls.append(call)
        if not self._replies:
            raise AssertionError("the rung was asked more than its script answers")
        return self._replies.pop(0)


class ScriptedJev:
    """Jev as a script: each question's name maps to the option or answer it picks.

    A :class:`Choice` answer is the option key; a :class:`Noul` answer is a
    bool; a :class:`Score` answer is the level index. Every ask is recorded as
    ``(name, state)`` in :attr:`asked`.
    """

    def __init__(self, **answers: str | bool | int) -> None:
        self._answers: dict[str, str | bool | int] = dict(answers)
        self.asked: list[tuple[str, Any]] = []

    def __call__(self, state: Any, questions: Mapping[str, Question]) -> Decision:
        answers: dict[str, Answer] = {}
        for name, question in questions.items():
            self.asked.append((name, state))
            if name not in self._answers:
                raise AssertionError(f"Jev was asked {name!r}, which the script lacks")
            answers[name] = _answer(question, self._answers[name])
        return Decision(answers=answers)


def _answer(question: Question, scripted: str | bool | int) -> Answer:
    if isinstance(question, Noul):
        value = bool(scripted)
        return BoolAnswer(
            value=value, probability_true=0.9 if value else 0.1, confidence=0.8
        )
    if isinstance(question, Score):
        level = int(scripted)
        probabilities = {
            name: (1.0 if index == level else 0.0)
            for index, name in enumerate(question.levels)
        }
        return ScoreAnswer(
            level=float(level), probabilities=probabilities, confidence=1.0
        )
    assert isinstance(question, Choice)
    chosen = str(scripted)
    if chosen not in question.options:
        raise AssertionError(f"{chosen!r} is not one of {sorted(question.options)}")
    probabilities = {key: (0.9 if key == chosen else 0.1) for key in question.options}
    return ChoiceAnswer(choice=chosen, probabilities=probabilities, confidence=0.8)


def text(reply: str) -> RungReply:
    return RungReply(text=reply, tool_calls=())


def calls(*pairs: tuple[str, str], text: str = "") -> RungReply:
    """A reply calling each ``(name, arguments_json)`` under ids ``call_<n>``."""
    return RungReply(
        text=text,
        tool_calls=tuple(
            RungToolCall(id=f"call_{index}", name=name, arguments=arguments)
            for index, (name, arguments) in enumerate(pairs)
        ),
    )
