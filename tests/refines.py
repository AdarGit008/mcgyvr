"""A scripted jev for the refining proposer, and the repository it is asked about.

`ScriptedJev` stands in for the jev unit behind `ClassifierProposer.classify`:
each typed question is answered by rule and kept, so a test can say what was
asked, in what order, about what. A field's Choice is answered with the first
option whose text holds the word the script names for that field, else with
its first option; the `split` question is answered by `split`, a rule over the
state the question is about; and every answer is given at `confidence`, or at
the one `confidences` names for that question.

`repository` is a small checkout whose files and definitions a request can
name, so resolution finds them: `listing.py` defines `listing` and `paginate`,
`report.py` defines `render` and `summary`.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcgyvr.decision import BoolAnswer, Choice, ChoiceAnswer, Decision, Noul, Question
from mcgyvr.delegate import ClassifierProposer
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.telemetry import ShadowSink
from mcgyvr.refine import RefiningProposer

#: The model the scripted jev's decisions are recorded under.
MODEL = "jev-scripted:1b"


@dataclass(frozen=True)
class Asked:
    """One question put to the scripted jev: its name, state and shape."""

    name: str
    state: Any
    question: Question


def never(state: Mapping[str, Any]) -> bool:
    """The split rule that answers No to every proposal."""
    return False


def tasks(*split: str) -> Callable[[Mapping[str, Any]], bool]:
    """The split rule that answers Yes for a proposal whose task is one of `split`."""
    return lambda state: state["task"] in split


@dataclass
class ScriptedJev:
    """Answers each typed question by rule and keeps every one it was asked."""

    split: Callable[[Mapping[str, Any]], bool] = never
    picks: Mapping[str, str] = field(default_factory=dict)
    confidence: float = 1.0
    confidences: Mapping[str, float] = field(default_factory=dict)
    asked: list[Asked] = field(default_factory=list)

    def __call__(self, state: Any, questions: Mapping[str, Question]) -> Decision:
        answers: dict[str, Any] = {}
        for name, question in questions.items():
            self.asked.append(Asked(name, state, question))
            confidence = self.confidences.get(name, self.confidence)
            if isinstance(question, Noul):
                value = self.split(state)
                answers[name] = BoolAnswer(
                    value=value,
                    probability_true=1.0 if value else 0.0,
                    confidence=confidence,
                )
                continue
            assert isinstance(question, Choice)
            key = self._pick(name, question)
            answers[name] = ChoiceAnswer(
                choice=key, probabilities={key: 1.0}, confidence=confidence
            )
        return Decision(answers=answers)

    def names(self) -> list[str]:
        """The name of every question asked, in the order it was asked."""
        return [asked.name for asked in self.asked]

    def _pick(self, name: str, question: Choice) -> str:
        wanted = self.picks.get(name)
        if wanted is not None:
            for key, text in question.options.items():
                if wanted in text:
                    return key
        return next(iter(question.options))


def refining(
    jev: ScriptedJev,
    *,
    sink: ShadowSink | None = None,
    max_splits: int = 3,
    max_fanout: int = 8,
) -> RefiningProposer:
    """The refining proposer over a classifier that asks `jev`."""
    return RefiningProposer(
        ClassifierProposer(classify=jev, sink=sink, model=MODEL),
        max_splits=max_splits,
        max_fanout=max_fanout,
    )


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def repository(root: Path) -> Index:
    """`listing.py` and `report.py`, committed, and the index built from them."""
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "listing.py").write_text(
        "def listing(items):\n    return items\n\n\n"
        "def paginate(items, size=10):\n    return items[:size]\n"
    )
    (root / "report.py").write_text(
        "def render(rows):\n    return rows\n\n\n"
        "def summary(rows):\n    return len(rows)\n"
    )
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "seed")
    return build_index(root)
