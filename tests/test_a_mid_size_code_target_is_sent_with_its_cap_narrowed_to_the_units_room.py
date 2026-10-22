"""A mid-size `code` target is sent with its cap narrowed to the unit's room.

The typed proposer states a `code` contract's cap as twice its target, so the
whole file comes back with room to grow. Held to a 32K-window unit, a target
of about 9,900 tokens — well under the worker-view ceiling — got a cap of about
19,800 that its prompt left no room for, and `mcgyvr run` refused it ("lower to
18885") although the whole-file reply it needs, about 9,900, would fit. The cap
is now narrowed to the room the unit leaves, and refused only where that room
is below half of it: the target the reply returns.

The cap's own ceiling follows the worker-view ceiling the decomposition holds
to, too, so a caller that raises `max_input_tokens` gets a cap sized on its
target rather than one smaller than the file it must return.
"""

from __future__ import annotations

import math
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcgyvr.catalog import catalog
from mcgyvr.decision import Choice, ChoiceAnswer, Decision, Question
from mcgyvr.delegate import ClassifierProposer
from mcgyvr.gate.preflight import (
    check_contract_against_rung,
    least_reply,
    sized_reply_cap,
    unit_ceiling,
)
from mcgyvr.orchestrator.candidates import REPLY_CAP_CEILING, REPLY_CAP_MARGIN
from mcgyvr.orchestrator.decompose import decompose
from mcgyvr.orchestrator.index import Index, build_index
from mcgyvr.orchestrator.read import estimate_tokens
from mcgyvr.worker.prompt import build_prompt

#: A comment line of about 20 estimated tokens.
PADDING = "# " + "x" * 76 + "\n"


@dataclass(frozen=True)
class Rung:
    """A local unit serving a 32K window and stating no reply room of its own."""

    source: str = "local_32k"
    context_window: int | None = 32768
    output_tokens: int | None = None
    output_ceiling: int | None = None


def _repo(tmp_path: Path, padding_lines: int) -> Index:
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


def _size(index: Index) -> int:
    (file,) = (f for f in index.files if f.path == "listing.py")
    return estimate_tokens("\n".join(file.lines))


def _code(state: Any, questions: Mapping[str, Question]) -> Decision:
    """Pick `code`, then rank 0 for every other field."""
    ((field, question),) = questions.items()
    assert isinstance(question, Choice)
    key = next(iter(question.options))
    if field == "task_type":
        doc = catalog().require("code").doc
        (key,) = (k for k, line in question.options.items() if line == doc)
    answer = ChoiceAnswer(choice=key, probabilities={key: 1.0}, confidence=0.9)
    return Decision(answers={field: answer})


def test_a_mid_size_target_is_narrowed_not_refused(tmp_path: Path) -> None:
    index = _repo(tmp_path, padding_lines=500)
    size = _size(index)
    assert 9000 < size < 11000

    result = decompose(
        index, "document listing", propose=ClassifierProposer(classify=_code)
    )
    (contract,) = result.contracts
    stated = contract.limits.max_output_tokens
    assert stated == math.ceil(size * REPLY_CAP_MARGIN)

    prompt = build_prompt(contract).measured
    room = unit_ceiling(Rung(), prompt).tokens
    assert room is not None and least_reply(stated) <= room < stated

    assert check_contract_against_rung(contract, prompt, rung=Rung()) is None
    cap = sized_reply_cap(contract, Rung(), prompt=prompt)
    assert cap.tokens == room
    assert cap.tokens >= size, "the whole target still comes back"
    assert "narrowed" in cap.basis, cap.basis


def test_a_room_below_half_the_cap_is_still_refused(tmp_path: Path) -> None:
    index = _repo(tmp_path, padding_lines=500)
    result = decompose(
        index, "document listing", propose=ClassifierProposer(classify=_code)
    )
    (contract,) = result.contracts
    prompt = build_prompt(contract).measured

    narrow = Rung(source="local_16k", context_window=16384)
    issue = check_contract_against_rung(contract, prompt, rung=narrow)

    assert issue is not None and issue.reason == "output-cap", issue


def test_the_cap_follows_a_raised_worker_view_ceiling(tmp_path: Path) -> None:
    index = _repo(tmp_path, padding_lines=1000)
    size = _size(index)
    assert math.ceil(size * REPLY_CAP_MARGIN) > REPLY_CAP_CEILING

    result = decompose(
        index,
        "document listing",
        propose=ClassifierProposer(classify=_code),
        max_input_tokens=4 * REPLY_CAP_CEILING,
    )

    (contract,) = result.contracts
    assert contract.limits.max_output_tokens == math.ceil(size * REPLY_CAP_MARGIN)
