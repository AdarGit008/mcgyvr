"""One contract cap is applied at every rung, and it is wrong for at least one.

``limits.max_output_tokens`` exists only on the contract
(``src/mcgyvr/contract.py:401`` ``LIMITS_FIELDS``) and reaches the wire at
``src/mcgyvr/drive.py:281`` ``dispatch_prompt``. ``TIER_FIELDS``
(``src/mcgyvr/config.py:327``) has no output key at all, so one number is sent
to every rung a contract climbs — a 3B model and a 35B reasoning model are
given the same room to answer in.

Measured this session over 358 ``attempt`` rows in the live journal, one
contract cap of 1024 throughout:

===========================  ===  ===  ====  ====  ============  ======
rung                           n  p50   p90   p95  at the cap    tok/s
===========================  ===  ===  ====  ====  ============  ======
local_qwen2.5-coder-3b       150  322   502   716  0/150           51.1
local_qwen2.5-coder-7b       126  215   396   465  0/126           27.9
local_qwen3.6-35b-a3b         82  850  1024  1024  **32/82**       17.0
===========================  ===  ===  ====  ====  ============  ======

The top rung wrote roughly four times as much as the cheap ones and was cut at
the cap on 39% of its replies. A cut reply is not a short reply:
``mcgyvr.worker.reply`` refuses a truncated file rather than applying it
(``reply[incomplete-reply]``), so each of those 32 spent the dearest rung in
the ladder and produced nothing. The cheap rungs never came within 300 tokens
of the same number. Prompts ran 740-775 tokens against a declared 4096 window,
so this is not the context window; it is one number where the ladder needs
three.

What must be true, and is asserted below: a rung may declare the room its
replies need; that number is what reaches the wire on that rung and nowhere
else; a rung that declares nothing still sends the contract's number; a
declared room that does not fit the rung's own window is a named refusal rather
than the truncation it was written to prevent; and a contract must still say
what it is willing to spend, because the ladder can be re-pointed at rungs that
declare nothing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.pool import Protocol, source_map
from tests import livejournal as lj

#: Two rungs on one rig that serves a 4096-token window. The dear rung declares
#: the room its replies need; the cheap one declares nothing, which is how the
#: fallback is told apart from an override that happens to agree.
LADDER = """
version: 1
sources:
  srv1:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 2
    context_window: 4096
ladder:
  tiers:
    - name: local_qwen2.5-coder-3b
      source: srv1
      model: qwen2.5-coder:3b
    - name: local_qwen3.6-35b-a3b
      source: srv1
      model: qwen3.6:35b-a3b
      output_tokens: 2048
"""

#: A model-executed contract whose own cap is the 1024 the live rows were
#: written under, declared rather than derived so the number is the operator's.
CONTRACT = """
id: impl
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  max_output_tokens: 1024
"""


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


def caps_sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Record the rung and the cap of every request the driver dispatches.

    The substitution is the seam the whole project is built on:
    ``mcgyvr.runner.dispatch`` takes a rung name and a source map, so nothing
    above it knows a socket exists. What is asserted is the number on the
    request, which is the number the backend is actually given.
    """
    from mcgyvr import drive
    from mcgyvr.runner import Completion, StopReason

    seen: list[tuple[str, int]] = []

    def fake_dispatch(
        source_map: Any, rung: str, request: Any, *, capacity: Any = None
    ) -> Completion:
        seen.append((rung, request.max_output_tokens))
        return Completion(
            text="```python\nx = 1\n```",
            stop_reason=StopReason.COMPLETE,
            raw_stop_reason="stop",
            model="qwen2.5-coder:3b",
            source="srv1",
            protocol=Protocol.OPENAI,
            max_output_tokens=request.max_output_tokens,
            latency_s=0.0,
        )

    monkeypatch.setattr(drive, "dispatch", fake_dispatch)
    return seen


# --- the rung may say what its replies need -------------------------------


def test_a_rung_may_declare_the_room_its_replies_need() -> None:
    """The ladder is where a per-rung number can be written at all.

    Unset is ``None`` rather than a number, for the reason ``max_parallel`` is:
    "this rung was measured needing 2048" and "nobody said, so the contract's
    number stands" are different facts, and a rung defaulting to the contract's
    value would be indistinguishable from a rung that declared it.
    """
    config = parse_config(cfg(LADDER))
    cheap, dear = config.ladder.tiers

    assert dear.output_tokens == 2048, (
        "a rung must be able to declare the room its replies need; without it "
        "the 35B rung is sent the same 1024 that cut 32 of its 82 replies"
    )
    assert cheap.output_tokens is None, (
        "a rung that declared nothing must stay distinguishable from one that "
        "declared the contract's number"
    )


# --- the number that reaches the wire -------------------------------------


def test_the_rung_that_declared_the_room_sends_its_own_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rung's number, not the contract's, is what the backend is given."""
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = caps_sent(monkeypatch)
    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(CONTRACT)
    assert contract.limits.max_output_tokens == 1024

    dispatch_prompt(pool, "local_qwen3.6-35b-a3b", build_prompt(contract), contract)

    assert sent == [("local_qwen3.6-35b-a3b", 2048)], (
        f"the rung declared 2048 and must be sent 2048; got {sent!r}. Taking "
        f"the lower of the two numbers re-creates the truncation this exists "
        f"to end"
    )


def test_a_rung_that_declared_nothing_still_sends_the_contracts_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The contract's number is the fallback, not a floor and not a ceiling.

    This is what ``dispatch_prompt`` has always sent, and it must keep sending
    it: a ladder can be re-pointed at rungs that declare nothing.
    """
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = caps_sent(monkeypatch)
    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(CONTRACT)

    dispatch_prompt(pool, "local_qwen2.5-coder-3b", build_prompt(contract), contract)

    assert sent == [("local_qwen2.5-coder-3b", 1024)]


def test_the_cheap_rung_is_not_dragged_up_by_the_dear_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One contract, one climb, two different numbers on the wire.

    The whole defect in one assertion: the same contract reaching two rungs
    must not carry one number to both. The 3B rung's replies had a p95 of 716
    and never approached 1024; raising it to the 35B rung's 2048 would spend
    the cheap rung's window on room it has never used.
    """
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = caps_sent(monkeypatch)
    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(CONTRACT)
    prompt = build_prompt(contract)

    dispatch_prompt(pool, "local_qwen2.5-coder-3b", prompt, contract)
    dispatch_prompt(pool, "local_qwen3.6-35b-a3b", prompt, contract)

    assert sent == [("local_qwen2.5-coder-3b", 1024), ("local_qwen3.6-35b-a3b", 2048)]


# --- a room that does not fit the rung it was declared on -----------------


def test_a_rung_room_that_does_not_fit_its_own_window_is_refused_by_name() -> None:
    """The failure mode a per-rung number introduces, refused where it is read.

    A rung declaring 4096 of reply on a rig serving a 4096-token window has
    left nothing for the prompt. Sending it is the same silent truncation the
    per-rung number exists to prevent, one level up, so the gate names it: the
    rung, its number and the window it does not fit.
    """
    from mcgyvr.gate.preflight import check_contract_against_rung

    over = cfg(LADDER).replace("output_tokens: 2048", "output_tokens: 4096")
    pool = source_map(parse_config(over))
    issue = check_contract_against_rung(
        load_contract(CONTRACT),
        "def fetch(url):\n    return url\n",
        rung=pool.bind("local_qwen3.6-35b-a3b"),
    )

    assert issue is not None, (
        "a reply cap as large as the whole window leaves no room for a prompt "
        "and must be refused before anything is dispatched"
    )
    assert issue.reason == "output-cap", (
        f"the refusal must be about the cap rather than about the prompt that "
        f"happened to be measured with it; got {issue.reason!r}"
    )
    assert "4096" in issue.message and "srv1" in issue.message, (
        f"the refusal must name the number and the rung whose window it does "
        f"not fit: {issue.message}"
    )


def test_a_rung_room_that_fits_is_not_refused() -> None:
    """The opposite direction on the same ladder — a check, not a wall."""
    from mcgyvr.gate.preflight import check_contract_against_rung

    pool = source_map(parse_config(cfg(LADDER)))
    assert (
        check_contract_against_rung(
            load_contract(CONTRACT),
            "def fetch(url):\n    return url\n",
            rung=pool.bind("local_qwen3.6-35b-a3b"),
        )
        is None
    )


def test_the_rungs_room_is_what_the_fit_is_measured_against() -> None:
    """The reserve the gate holds back is the number that will be sent.

    A prompt that fits beside the contract's 1024 but not beside the rung's
    2048 must be refused on the rung that will send 2048. Measuring the fit
    against a number the dispatch will not use is how a check comes to pass on
    a request that then arrives truncated.
    """
    from mcgyvr.gate.preflight import check_contract_against_rung

    contract = load_contract(CONTRACT)
    pool = source_map(parse_config(cfg(LADDER)))
    # 2000 estimated tokens, charged as 2640 against the estimator's measured
    # 32% reserve: room beside 1024 in a 4096 window, none beside 2048.
    prompt = "x" * 8_000

    assert (
        check_contract_against_rung(
            contract, prompt, rung=pool.bind("local_qwen2.5-coder-3b")
        )
        is None
    ), "the cheap rung reserves the contract's 1024 and this prompt fits beside it"

    issue = check_contract_against_rung(
        contract, prompt, rung=pool.bind("local_qwen3.6-35b-a3b")
    )
    assert issue is not None, (
        "the dear rung will be sent 2048, so 2048 is what the prompt must be "
        "measured against"
    )
    assert "2048" in issue.message, (
        f"the refusal must name the reserve it actually enforced: {issue.message}"
    )


# --- the contract still has to say what it will spend ---------------------


def test_a_contract_with_no_cap_is_still_refused_on_a_ladder_that_declares_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rung declaring room does not excuse a contract from declaring spend.

    The two numbers answer different questions — what this unit of work is
    worth, and what that backend needs to finish a reply — so a ladder that
    answers the second has not answered the first. The refusal
    (``mcgyvr.cli._cap_undeclared``, owner 2026-09-05: "fail loud when no
    budget is declared") must survive this change untouched.
    """
    uncapped = CONTRACT.replace("limits:\n  max_output_tokens: 1024\n", "")
    path = lj.make_contract(tmp_path / "impl.yaml", uncapped)

    assert lj.main(["contract", str(path)]) == 2
    assert "limits.max_output_tokens" in capsys.readouterr().err
