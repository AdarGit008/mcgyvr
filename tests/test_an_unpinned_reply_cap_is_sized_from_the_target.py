"""A contract that pins no reply cap has it sized from the file it changes.

The e2e run of 2026-10-13 put DeepSeek's reasoning models behind a contract
cap of 1024 and got empty replies on both rungs: the hidden reasoning spent
the cap before a line was written. 4096 failed the same way on a duration
parser the dearer rung finished in 16216 tokens. A cap stated in the contract
cannot know which model serves it or how big the target is; the attempt knows
both. So a contract that states none is sized at each attempt
(:func:`mcgyvr.contract.auto_reply_cap`): the task type's floor plus twice the
target's estimated tokens — a full rewrite must fit — and a reasoning
allowance on top. The unit's ``output_tokens`` bounds it, the room the rung's
window leaves beside the prompt trims the reasoning half (never the visible
one), a cap the contract states still wins, and the journal row records the
number sent and how it was reached.
"""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import (
    CAP_STEP,
    NEW_FILE_STEP,
    REASONING_ALLOWANCE,
    REWRITE_FACTOR,
    Contract,
)
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.preflight import (
    check_contract_against_rung,
    reply_cap,
    sized_reply_cap,
)
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.read import estimate_tokens
from tests import livejournal as lj

#: One rung that declares nothing, one that bounds its replies, one with a
#: window small enough that the reasoning allowance cannot fit beside a prompt.
LADDER = textwrap.dedent(
    """\
    units:
      plain:
        address: http://localhost:11434
        model: qwen2.5-coder:7b
        rig: srv1
        width: 1
      bounded:
        address: http://localhost:11435
        model: deepseek-reasoner
        rig: srv1
        width: 1
        output_tokens: 8192
      small:
        address: http://localhost:11436
        model: qwen2.5-coder:3b
        rig: srv1
        width: 1
        window: 8192
    ladder:
    - plain
    - bounded
    - small
    """
)

#: A model contract that states no cap; `acceptance` makes its floor the
#: running allowance.
UNPINNED = """
id: impl
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
"""

SMALL_TARGET = "def fetch(url):\n    return url\n"
LARGE_TARGET = "def fetch(url):\n    return url\n" * 200


def _rung(name: str) -> Any:
    return source_map(parse_config(LADDER)).bind(name)


def _with(target: str, text: str = UNPINNED) -> Contract:
    return replace(load_contract(text), target_content=target)


def _sized(floor: int, target: str) -> int:
    """The arithmetic the module docstring states, spelled from the constants."""
    tokens = estimate_tokens(target) if target else 0
    grown = REWRITE_FACTOR * tokens if tokens else NEW_FILE_STEP
    visible = -(-(floor + grown) // CAP_STEP) * CAP_STEP
    return visible + REASONING_ALLOWANCE


def test_an_unpinned_contract_is_sized_and_not_declared() -> None:
    contract = load_contract(UNPINNED)
    assert not contract.max_output_tokens_declared
    # The loader's figure is the floor the attempt sizes up from.
    assert contract.limits.max_output_tokens == 1024


def test_a_larger_target_is_given_a_larger_cap() -> None:
    small = reply_cap(_with(SMALL_TARGET), _rung("plain"))
    large = reply_cap(_with(LARGE_TARGET), _rung("plain"))

    assert small == _sized(1024, SMALL_TARGET)
    assert large == _sized(1024, LARGE_TARGET)
    assert large is not None and small is not None
    assert (
        large - small
        >= REWRITE_FACTOR
        * (estimate_tokens(LARGE_TARGET) - estimate_tokens(SMALL_TARGET))
        - CAP_STEP
    ), "a full rewrite of the larger file must fit"
    assert small > REASONING_ALLOWANCE, "room to reason before the file is written"


def test_a_file_that_does_not_exist_yet_gets_the_new_file_step() -> None:
    cap = sized_reply_cap(_with(""), _rung("plain"))
    assert cap.tokens == _sized(1024, "")
    assert f"{NEW_FILE_STEP} for a new file" in cap.basis


def test_the_units_output_tokens_bounds_the_sized_cap() -> None:
    """The unit says how much its backend can be given; the sizing stays under it."""
    cap = sized_reply_cap(_with(LARGE_TARGET), _rung("bounded"))
    assert cap.tokens == 8192
    assert cap.basis.startswith("auto: ")
    assert "bounded by rung" in cap.basis and "output_tokens" in cap.basis


def test_a_cap_the_contract_states_still_wins() -> None:
    pinned = UNPINNED + "limits:\n  max_output_tokens: 1536\n"
    cap = sized_reply_cap(_with(LARGE_TARGET, pinned), _rung("plain"))
    assert cap.tokens == 1536
    assert cap.basis == "the contract's limits.max_output_tokens"


def test_the_reasoning_half_is_trimmed_to_the_window_left_beside_the_prompt() -> None:
    """A small local window is not refused for headroom a reasoning model might use."""
    contract = _with(SMALL_TARGET)
    prompt = "Change the file.\n" + SMALL_TARGET
    rung = _rung("small")

    cap = sized_reply_cap(contract, rung, prompt=prompt)

    assert cap.tokens is not None
    assert cap.tokens < _sized(1024, SMALL_TARGET), "the reasoning half was trimmed"
    assert cap.tokens >= _sized(1024, SMALL_TARGET) - REASONING_ALLOWANCE
    assert "reasoning trimmed" in cap.basis
    assert check_contract_against_rung(contract, prompt, rung=rung) is None


def test_the_visible_half_is_never_trimmed_and_is_refused_by_name() -> None:
    """A target too big to re-emit in the window is a contract too big for the rung."""
    huge = "x = 1\n" * 6000  # ~9000 estimated tokens: a rewrite of it fills 8192
    contract = _with(huge)
    issue = check_contract_against_rung(contract, "Change it.", rung=_rung("small"))
    assert issue is not None
    assert issue.reason == "output-cap"
    assert "the target needs a visible reply of" in issue.message


def test_the_cap_may_exceed_the_prompt_budget() -> None:
    """The cap counts reasoning that is never read back, so the prompt budget
    does not bound it."""
    contract = _with(SMALL_TARGET)
    cap = reply_cap(contract, _rung("plain"))
    assert cap is not None and cap > contract.max_input_tokens


def test_a_run_sends_the_sized_cap_and_journals_how_it_was_reached(
    tmp_path: Path,
    home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Through ``mcgyvr run`` to the wire: the target is read off the workspace.

    Only the HTTP post is stubbed, so the runner that builds the completion —
    and copies the basis onto it — is the real one, and the number asserted
    is the ``max_tokens`` in the body that would have been sent.
    """
    from mcgyvr import runner as runner_module

    bodies: list[dict[str, Any]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        bodies.append(payload)
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": lj.GOOD_REPLY},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        }

    monkeypatch.setattr(runner_module, "_post_json", post, raising=True)
    monkeypatch.setattr(runner_module, "_get_text", lambda url, timeout: None)
    repo = lj.make_repo(tmp_path / "repo")
    journal = tmp_path / "journal"
    config = lj.make_config(tmp_path / "setup", journal_dir=journal)
    unpinned = lj.MODEL_CONTRACT.replace("limits:\n  max_output_tokens: 256\n", "")
    assert "max_output_tokens" not in unpinned
    contract = lj.make_contract(tmp_path / "impl.yaml", unpinned)

    assert lj.main(lj.run_args(contract, repo, config)) == 0
    capsys.readouterr()

    target = (repo / "src" / "pkg" / "messy.py").read_text(encoding="utf-8")
    expected = _sized(load_contract(unpinned).limits.max_output_tokens or 0, target)
    (body,) = bodies
    assert body["max_tokens"] == expected
    (row,) = [r for r in lj.rows(journal) if r.get("record_kind") == "attempt"]
    assert row["max_output_tokens"] == expected
    assert row["cap_basis"].startswith("auto: ")
    assert f"= {expected}" in row["cap_basis"]
