"""The setup wizard's decision tree says what its prompts offer.

:data:`mcgyvr.cli.setup_stages.DECISION_TREE` is the wizard's tree as data:
each question, the answers it takes and the default Enter picks. The prompts
in :mod:`mcgyvr.cli.commands.setup` do not read it, so this test is what
holds the two equal: for every node, the prompt is answered on stdin, as a
user answers it, and what it takes and what Enter gives are read back.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pytest

from mcgyvr.cli.commands import setup
from mcgyvr.cli.setup_stages import DECISION_TREE, Decision

#: The lock question, as `_setup_sample` asks it.
LOCK_QUESTION = "Lock the fleet and name it live? [y/n] "

#: A pick among named answers: the prompt, and the table's word for what it
#: answers.
CHOOSE: dict[str, tuple[Callable[[], Any], Callable[[Any], str]]] = {
    "rigs": (
        setup._ask_setup_rigs,
        lambda got: "local" if got == ("localhost",) else str(got),
    ),
    "coding.deployment": (setup._ask_deployment, str),
    "coding.fanout": (setup._ask_fanout, str),
    "chat.context-quant": (setup._ask_context_quant, str),
    "skip-rec": (lambda: setup._ask_skip_rec(), str),
}
#: A yes/no question: Enter is no.
CONFIRM: dict[str, Callable[[], bool]] = {
    "coding.jev": lambda: setup._confirm(setup.JEV_QUESTION),
    "coding.sleep-wake": setup._ask_sleep_wake,
    "coding.ruff": setup._ask_ruff,
    "recommend": setup._consent_to_placement,
    "start": lambda: setup._confirm(setup._start_question(("rig-s",))),
    "lock": lambda: setup._confirm(LOCK_QUESTION),
}
#: A free answer: the prompt, an answer of the kind the option names and what
#: it reads it as, and the table's word for what Enter gives.
FREE: dict[str, tuple[Callable[[], Any], str, Any, Callable[[Any], str]]] = {
    "agent.slots": (setup._ask_slots, "4", 4, str),
}
#: Asked inside the recommend step (`_setup_downloads`), which lane L1B owns:
#: not driven from here.
INSIDE_THE_STEP = {"download"}


def _typed(monkeypatch: pytest.MonkeyPatch, *lines: str) -> None:
    """Answer the prompts on stdin, one line each, as a user types them."""
    monkeypatch.setattr("sys.stdin", io.StringIO("".join(f"{x}\n" for x in lines)))


@pytest.mark.parametrize("node", DECISION_TREE, ids=lambda node: node.name)
def test_each_node_of_the_tree_holds_what_its_prompt_offers(
    monkeypatch: pytest.MonkeyPatch, node: Decision
) -> None:
    if node.name in INSIDE_THE_STEP:
        assert node.options == ("yes", "no") and node.default == "no"
    elif node.name == "use-case":
        assert node.options == setup._setup_use_cases()
        for name in node.options:
            _typed(monkeypatch, name)
            assert setup._ask_setup_use_case() == name
        assert node.default is None
        _typed(monkeypatch, "", "", "")
        with pytest.raises(setup._SetupInteractiveError):
            setup._ask_setup_use_case()
    elif node.name in CHOOSE:
        ask, word = CHOOSE[node.name]
        _typed(monkeypatch, "")
        assert word(ask()) == node.default
        _typed(monkeypatch, *["not-an-answer"] * setup._SETUP_TRIES)
        with pytest.raises(setup._SetupInteractiveError) as refused:
            ask()
        assert str(refused.value).endswith(
            f"setup offers {setup._spoken_or(node.options)}"
        )
    elif node.name in CONFIRM:
        confirm = CONFIRM[node.name]
        assert node.options == ("yes", "no")
        _typed(monkeypatch, "")
        assert node.default == ("yes" if confirm() else "no")
        _typed(monkeypatch, "yes")
        assert confirm() is True
    else:
        assert node.name in FREE, f"{node.name}: no prompt is held to this node"
        ask, said, read, word = FREE[node.name]
        assert len(node.options) == 1
        _typed(monkeypatch, said)
        assert ask() == read
        _typed(monkeypatch, "")
        assert word(ask()) == node.default
