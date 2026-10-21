"""The classifier proposer states a ``code`` contract's reply cap itself.

A model-written ``code`` contract states ``limits.max_output_tokens``, and a
proposal without one is refused at decomposition. No single-token choice can
say what a reply is worth, so the classifier used to hand every ``code``
request to the prose proposer. The cap is now stated deterministically from the
chosen target's size: the reply is a whole file, so it is sized on the whole
target whichever symbol the task names, times a margin, and held between a
floor and the worker-view ceiling. The contract it yields is emitted, loads,
and passes the cap checks ``mcgyvr run`` makes before any model is called.
"""

from __future__ import annotations

import math
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.catalog import catalog
from mcgyvr.contract import dumps as dump_contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import ClassifierProposer, proposer_by_authoring
from mcgyvr.gate.preflight import check_cap_stated
from mcgyvr.orchestrator.candidates import (
    NEW_TARGET_TOKENS,
    REPLY_CAP_CEILING,
    REPLY_CAP_FLOOR,
    REPLY_CAP_MARGIN,
    reply_cap,
)
from mcgyvr.orchestrator.decompose import Evidence, Proposal, decompose
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import estimate_tokens, explore
from mcgyvr.orchestrator.resolve import resolve

#: The text of the symbol question's no-symbol option (orchestrator/fields.py).
NO_SYMBOL = "no specific symbol — the whole file is the work"

#: A comment line long enough that a few hundred of them clear the floor.
PADDING = "# " + "x" * 76 + "\n"


def _repo(tmp_path: Path, padding_lines: int = 0) -> Index:
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
    text = "def listing(items):\n    return items\n" + PADDING * padding_lines
    (root / "listing.py").write_text(text)
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    return build_index(root)


@pytest.fixture
def repo(tmp_path: Path) -> Index:
    return _repo(tmp_path)


def _evidence(index: Index) -> Evidence:
    resolution = resolve(index, "document listing")
    return Evidence(
        prompt="document listing",
        index=index,
        resolution=resolution,
        exploration=explore(index, resolution),
        vocabulary=catalog().task_types,
    )


def _chooses_code(asked: list[Mapping[str, Question]], *, symbol: str = "") -> Any:
    """Pick `code`, the symbol whose option reads `symbol` (else rank 0), rank 0
    for everything else."""

    def classify(state: Any, questions: Mapping[str, Question]) -> Decision:
        asked.append(questions)
        ((field, question),) = questions.items()
        assert isinstance(question, Choice)
        if field == "task_type":
            text = catalog().require("code").doc
            return Decision(answers={field: _sure(_option_for(question, text))})
        if field == "symbol" and symbol:
            return Decision(answers={field: _sure(_option_for(question, symbol))})
        return Decision(answers={field: _sure(next(iter(question.options)))})

    return classify


def _option_for(question: Choice, text: str) -> str:
    """The candidate id whose option line is `text`."""
    for key, rendered in question.options.items():
        if rendered == text:
            return key
    raise AssertionError(f"{text!r} is not offered")


def _sure(choice: str) -> ChoiceAnswer:
    return ChoiceAnswer(choice=choice, probabilities={choice: 1.0}, confidence=0.9)


def _whole_file_cap(index: Index) -> int:
    """The cap the formula gives for listing.py, from its indexed content."""
    (file,) = (f for f in index.files if f.path == "listing.py")
    size = estimate_tokens("\n".join(file.lines))
    return min(
        max(math.ceil(size * REPLY_CAP_MARGIN), REPLY_CAP_FLOOR), REPLY_CAP_CEILING
    )


def _propose(index: Index, *, symbol: str = "") -> Proposal:
    asked: list[Mapping[str, Question]] = []
    (proposal,) = ClassifierProposer(classify=_chooses_code(asked, symbol=symbol))(
        _evidence(index)
    )
    return proposal


def test_code_is_the_type_that_must_state_a_cap() -> None:
    capped = {task.name for task in catalog().task_types if task.needs_output_cap}
    assert capped == {"code"}


def test_a_whole_file_code_proposal_states_a_cap_sized_on_the_target(
    tmp_path: Path,
) -> None:
    index = _repo(tmp_path, padding_lines=200)
    proposal = _propose(index, symbol=NO_SYMBOL)

    assert proposal.task_type == "code"
    assert proposal.task.endswith(": listing.py.")
    assert proposal.max_output_tokens == _whole_file_cap(index)
    # Sized on the file, not clamped: the padding clears the floor.
    assert REPLY_CAP_FLOOR < proposal.max_output_tokens < REPLY_CAP_CEILING


def test_a_symbol_code_proposal_is_sized_on_the_whole_file_it_returns(
    tmp_path: Path,
) -> None:
    """The reply is a whole file, so naming a symbol does not shrink the cap."""
    index = _repo(tmp_path, padding_lines=200)
    proposal = _propose(index)

    assert proposal.task.endswith(": listing in listing.py.")
    assert proposal.max_output_tokens == _whole_file_cap(index)


def test_a_small_target_is_held_to_the_floor(repo: Index) -> None:
    assert _propose(repo).max_output_tokens == REPLY_CAP_FLOOR


def test_a_large_target_is_clamped_to_the_ceiling(tmp_path: Path) -> None:
    index = _repo(tmp_path, padding_lines=1000)
    (file,) = (f for f in index.files if f.path == "listing.py")
    unclamped = math.ceil(estimate_tokens("\n".join(file.lines)) * REPLY_CAP_MARGIN)
    assert unclamped > REPLY_CAP_CEILING

    assert _propose(index).max_output_tokens == REPLY_CAP_CEILING


def test_a_target_with_no_content_yet_is_sized_on_the_default(repo: Index) -> None:
    code = catalog().require("code")
    expected = max(math.ceil(NEW_TARGET_TOKENS * REPLY_CAP_MARGIN), REPLY_CAP_FLOOR)
    assert reply_cap(_evidence(repo), code, "new_module.py") == expected


def test_a_classifier_code_contract_loads_and_passes_the_cap_guards(
    tmp_path: Path,
) -> None:
    index = _repo(tmp_path, padding_lines=200)

    def prose(evidence: Evidence) -> Sequence[Proposal]:
        raise AssertionError("the classifier states the cap; prose is not asked")

    asked: list[Mapping[str, Question]] = []
    propose = proposer_by_authoring(
        "classifier",
        typed=ClassifierProposer(classify=_chooses_code(asked)),
        prose=prose,
    )
    assert propose is not None
    result = decompose(index, "document listing", propose=propose)

    assert result.refusals == ()
    (contract,) = result.contracts
    assert contract.task_type == "code"
    assert contract.limits.max_output_tokens == _whole_file_cap(index)
    reloaded = load_contract(dump_contract(contract))
    assert reloaded.limits.max_output_tokens == contract.limits.max_output_tokens
    assert check_cap_stated(reloaded) is None
