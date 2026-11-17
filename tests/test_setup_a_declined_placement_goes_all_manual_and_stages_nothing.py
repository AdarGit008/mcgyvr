"""``mcgyvr setup`` commits a placement only on a yes, and a no stages nothing.

After the plan is printed the wizard asks whether to commit it (Enter is no).
On a no it asks how to go on: ``manual`` (the default the prompt names, the
all-manual terminal) or ``model-path`` (plan again from a model store). The
all-manual terminal exits 0 with nothing staged, started or locked, and
prints the commands that stage the setup by hand.

The rig is :class:`tests.setup_door.FakeRig` behind the door; the prompts are
answered through the setup's own prompt seams; nothing reaches a machine.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr import cli
from mcgyvr.cli.commands.setup import (
    CONSENT_QUESTION,
    MODEL_STORE_QUESTION,
    SKIP_REC_QUESTION,
    _ask_skip_rec,
    _consent_to_placement,
)
from tests import setup_door as sd

USE_CASE = "Use case — [m] mcgyvr-code, [k] code, [c] chat, [a] agent: "


def _declining(monkeypatch: pytest.MonkeyPatch, rig: sd.FakeRig) -> list[str]:
    """The flow harness with the real consent gate, answered with Enter (no)."""
    asked = sd.interactive(monkeypatch, rig, {}, typed={USE_CASE: "m"})
    monkeypatch.setattr(
        cli.commands.setup, "_consent_to_placement", _consent_to_placement
    )
    return asked


@pytest.mark.parametrize(
    ("said", "way"),
    [
        ("", "manual"),
        ("manual", "manual"),
        ("I'll do it myself", "manual"),
        ("model-path", "model-path"),
        ("I have a model path", "model-path"),
    ],
)
def test_the_skip_question_takes_enter_as_the_manual_it_names(
    monkeypatch: pytest.MonkeyPatch, said: str, way: str
) -> None:
    asked: list[str] = []

    def ask(question: str, prompt: Any = None) -> str:
        asked.append(question)
        return said

    monkeypatch.setattr(cli.commands.setup, "_ask", ask)

    assert SKIP_REC_QUESTION.endswith("[manual] ")
    assert _ask_skip_rec() == way
    assert asked == [SKIP_REC_QUESTION]


def test_enter_on_consent_then_on_the_skip_question_asks_no_model_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _declining(monkeypatch, sd.FakeRig())

    assert cli.main(["setup"]) == 0

    assert asked[-2:] == [CONSENT_QUESTION, SKIP_REC_QUESTION]
    assert MODEL_STORE_QUESTION not in asked, "Enter is manual: no folder is asked"
