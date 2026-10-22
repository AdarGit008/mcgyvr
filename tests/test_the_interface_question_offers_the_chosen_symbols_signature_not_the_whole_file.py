"""The interface question offers the chosen symbol's signature, not the file's.

The interface question used to offer every signature in the target after the
chosen one, and a typed question holds at most 62 options, so `mcgyvr delegate`
on a target with 62 or more definitions crashed with ``ValueError: a Choice
holds 1 to 62 options, got 63``. The work keeps one interface: with a symbol
chosen the question offers "none" and that symbol's signature, and with no
symbol it offers "none" and at most eight of the target's signatures.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question, labels_for
from mcgyvr.delegate import ClassifierProposer
from mcgyvr.orchestrator.decompose import decompose
from mcgyvr.orchestrator.index import Index, build_index

#: One past the 62 options a typed question can carry.
DEFINITIONS = 63

#: The text of the symbol question's no-symbol option (orchestrator/fields.py).
NO_SYMBOL = "no specific symbol — the whole file is the work"


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@t.io", "-c", "user.name=t", *args],
            cwd=root,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    (root / "chunk.py").write_text(
        "".join(f"def f{n}(a{n}):\n    return a{n}\n\n" for n in range(DEFINITIONS))
    )
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    return build_index(root)


def _sure(choice: str) -> ChoiceAnswer:
    return ChoiceAnswer(choice=choice, probabilities={choice: 1.0}, confidence=0.9)


def _choosing(asked: dict[str, Choice], *, whole_file: bool = False) -> Any:
    """Pick `code`, the no-symbol option when `whole_file`, rank 0 elsewhere."""

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        # The labels a real classify reads the reply with: past 62 options
        # there are none, and this raises the ValueError `delegate` crashed on.
        labels_for(question)
        asked[field] = question
        wanted = {
            "task_type": catalog().require("code").doc,
            "symbol": NO_SYMBOL if whole_file else None,
        }.get(field)
        if wanted is None:
            return Decision(answers={field: _sure(next(iter(question.options)))})
        (key,) = (k for k, line in question.options.items() if line == wanted)
        return Decision(answers={field: _sure(key)})

    return classify


def test_a_chosen_symbol_offers_only_its_own_signature(repo: Index) -> None:
    asked: dict[str, Choice] = {}
    result = decompose(
        repo, "change f0 in chunk.py", propose=ClassifierProposer(_choosing(asked))
    )

    assert result.refusals == ()
    options = list(asked["interface"].options.values())
    assert len(options) == 2
    assert options[1].startswith("def f0(")


def test_a_whole_file_pick_offers_at_most_eight_signatures(repo: Index) -> None:
    asked: dict[str, Choice] = {}
    result = decompose(
        repo,
        "change chunk.py",
        propose=ClassifierProposer(_choosing(asked, whole_file=True)),
    )

    assert result.refusals == ()
    assert len(asked["interface"].options) == 1 + 8
