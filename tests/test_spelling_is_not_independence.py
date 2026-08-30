"""§4, first item — the self-verification refusal, defeated by how a name is typed.

:func:`mcgyvr.verify.verify` refuses to let a model review the change it just
wrote, and it refuses *before* the spend: the reviewer is never asked. The
refusal is the whole warrant behind
:attr:`~mcgyvr.escalate.Assurance.VERIFIED`, and it is decided by comparing two
strings that come out of a config file.

The comparison was ``strip().casefold()``. That answers the case the module's
own docstring names — a config that capitalises a model differently — and
nothing else. Every line below is one way to write two names for one model that
``strip().casefold()`` reads as two models:

``qwen2.5-coder`` / ``qwen2.5-coder:latest``
    Not an attack. Ollama defaults an untagged name to ``:latest`` itself, so
    these are the same weights on the same host, spelled the two ways Ollama's
    own documentation spells them. This is the one a working install hits by
    accident.

``ollama/qwen2.5-coder:7b`` / ``qwen2.5-coder:7b``
    A provider prefix. The routing half of the name says where to send the
    request; it does not name a different model.

``qwen2.5-coder:7b`` with a ``U+200B`` in it
    A zero-width space: invisible in the config file, invisible in the refusal
    message, and enough to make the two names unequal.

``qwen2.5-coder:7b`` with a ``U+043E`` for its ``o``
    A Cyrillic homoglyph. Same pixels, different code point.

Both are written below as escapes rather than as the characters themselves,
because a reader of this file has to be able to see which one is which — and
because ruff's ``RUF001`` would otherwise flag the very thing under test.

The controls matter as much, because "refuse everything that looks similar"
would pass all four and break the ordinary install. Two tiers of one family are
two models — ``qwen2.5-coder:32b`` reviewing ``qwen2.5-coder:7b`` is the setup
most local installs run, and refusing it leaves them with no verifier at all.
So is ``mistral`` beside ``mixtral``: one letter apart, and not the same
weights.

The rule these are all measured against:

    Two names that resolve to one set of weights are one model, however they
    are spelled. Two names that resolve to different weights are two models,
    however close the spelling.
"""

from __future__ import annotations

from typing import Any

import pytest

from mcgyvr.catalog import Family
from mcgyvr.contract import loads
from mcgyvr.escalate import Opinion
from mcgyvr.gate import GateResult
from mcgyvr.verify import verify

CONTRACT = """
id: fetch-retry
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  attempts: 5
"""

MODEL_FAMILY = Family(name="local", rank=1, doc="a model on the operator's own machine")

CHANGE = "--- a/src/pkg/fetch.py\n+++ b/src/pkg/fetch.py\n@@\n+    pass\n"

APPROVAL = "APPROVE — the retry policy matches the contract and nothing else changed."

# Pairs that name one model twice. Each is a way the old comparison was defeated.
SAME_MODEL = [
    pytest.param("qwen2.5-coder", "qwen2.5-coder:latest", id="ollama-tag-default"),
    pytest.param("qwen2.5-coder:latest", "qwen2.5-coder", id="tag-default-reversed"),
    pytest.param("qwen2.5-coder:7b", "ollama/qwen2.5-coder:7b", id="provider-prefix"),
    pytest.param("qwen2.5-coder:7b", "hf.co/Qwen/qwen2.5-coder:7b", id="registry-path"),
    pytest.param("qwen2.5-coder:7b", "qwen2.5-\u200bcoder:7b", id="zero-width-space"),
    pytest.param("qwen2.5-coder:7b", "qwen2.5-c\u043eder:7b", id="cyrillic-homoglyph"),
    pytest.param("qwen2.5-coder:7b", "qwen2.5\u2011coder:7b", id="non-breaking-hyphen"),
    pytest.param("qwen2.5-coder:7b", " Qwen2.5-Coder:7B ", id="case-and-whitespace"),
]

# Pairs that name two models. A fix that refuses these is worse than the defect.
DIFFERENT_MODELS = [
    pytest.param("qwen2.5-coder:7b", "qwen2.5-coder:32b", id="two-tiers-one-family"),
    pytest.param("mistral:7b", "mixtral:8x7b", id="one-letter-apart"),
    pytest.param("qwen2.5-coder:7b", "llama3.1:8b", id="unrelated"),
]


@pytest.fixture
def contract() -> Any:
    return loads(CONTRACT)


class Reviewer:
    """A reviewer that answers, and remembers whether it was asked.

    Not a callable that raises: :func:`~mcgyvr.verify.verify` catches
    everything the seam can raise and turns it into the same
    :attr:`~mcgyvr.escalate.Opinion.UNUSABLE` the refusal returns, so a raising
    stand-in would make every one of these tests pass against a comparison that
    refuses nothing. The refusal and the spend are asserted separately.
    """

    def __init__(self, reply: str = APPROVAL) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


def _review(contract: Any, builder: str, reviewer: str, ask: Any) -> Any:
    return verify(
        contract,
        family=MODEL_FAMILY,
        gate=GateResult(),
        change=CHANGE,
        builder=builder,
        reviewer=reviewer,
        ask=ask,
    )


@pytest.mark.parametrize(("builder", "reviewer"), SAME_MODEL)
def test_one_model_spelled_two_ways_is_still_one_model(
    contract: Any, builder: str, reviewer: str
) -> None:
    """The refusal survives the spelling, and still happens before the spend."""
    asked = Reviewer()

    review = _review(contract, builder, reviewer, asked)

    assert review.opinion is Opinion.UNUSABLE, (
        f"{builder!r} reviewed itself spelled as {reviewer!r}: {review}"
    )
    assert not asked.prompts, (
        f"{builder!r} was asked to review its own output as {reviewer!r} — a "
        f"self-review that ran and was then discarded is the spend the rule "
        f"exists to prevent"
    )


@pytest.mark.parametrize(("builder", "reviewer"), DIFFERENT_MODELS)
def test_two_models_are_not_collapsed_into_one(
    contract: Any, builder: str, reviewer: str
) -> None:
    """The control: a real reviewer is asked, and its approval reads as one."""
    asked = Reviewer()

    review = _review(contract, builder, reviewer, asked)

    assert asked.prompts, f"{reviewer!r} is not {builder!r} and was never asked"

    assert review.opinion is Opinion.AGREED, (
        f"{reviewer!r} is not {builder!r} and was refused anyway: {review}"
    )


def test_the_refusal_names_both_spellings_as_the_operator_wrote_them(
    contract: Any,
) -> None:
    """A normalised name in the message would send the operator to a config line
    that does not exist. Both names are echoed as typed."""
    builder, reviewer = "qwen2.5-coder", "ollama/qwen2.5-coder:latest"

    review = _review(contract, builder, reviewer, Reviewer())

    assert builder in review.detail, f"the builder's own spelling is gone: {review}"
    assert reviewer in review.detail, f"the reviewer's own spelling is gone: {review}"
