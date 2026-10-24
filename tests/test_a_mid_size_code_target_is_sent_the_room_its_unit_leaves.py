"""A mid-size `code` target is sent all the room its unit leaves the prompt.

Held to a 32K-window unit, a target of about 9,900 tokens — well under the
worker-view ceiling — used to get a cap of twice its size from the decomposer,
narrowed to the room the prompt left, and was refused on a 16K unit whose room
was below half that cap. The decomposer states no cap now: the reply is sent
the unit's maximum, the room its window leaves once the prompt is paid for, on
a wide unit and a narrow one alike. A reply that outgrows a narrow unit's room
is cut off there, a named failure, and the climb moves on.
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
    ESTIMATE_RESERVE,
    check_contract_against_rung,
    unit_max,
)
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


def _contract(index: Index):  # type: ignore[no-untyped-def]
    result = decompose(
        index, "document listing", propose=ClassifierProposer(classify=_code)
    )
    (contract,) = result.contracts
    return contract


def test_a_mid_size_target_is_sent_the_whole_room_its_unit_leaves(
    tmp_path: Path,
) -> None:
    index = _repo(tmp_path, padding_lines=500)
    size = _size(index)
    assert 9000 < size < 11000
    contract = _contract(index)
    assert contract.limits.max_output_tokens is None

    prompt = build_prompt(contract).measured
    assert check_contract_against_rung(contract, prompt, rung=Rung()) is None
    cap = unit_max(Rung(), prompt)
    assert cap.tokens == 32768 - math.ceil(
        estimate_tokens(prompt) * (1 + ESTIMATE_RESERVE)
    )
    assert cap.tokens >= size, "the whole target still comes back"
    assert "local_32k" in cap.basis, cap.basis


def test_a_narrow_unit_is_sent_what_room_it_has_not_refused(tmp_path: Path) -> None:
    contract = _contract(_repo(tmp_path, padding_lines=500))
    prompt = build_prompt(contract).measured
    narrow = Rung(source="local_16k", context_window=16384)

    assert check_contract_against_rung(contract, prompt, rung=narrow) is None
    narrow_cap, wide_cap = unit_max(narrow, prompt), unit_max(Rung(), prompt)
    assert narrow_cap.tokens is not None and wide_cap.tokens is not None
    assert 0 < narrow_cap.tokens == wide_cap.tokens - (32768 - 16384)
