"""A rung states the window it serves, and the fit check measures against that.

Every token budget in mcgyvr is spent against a number the *contract* declared.
``context.max_input_tokens`` defaults to 4096 and is the only ceiling the live
path enforces (``mcgyvr.worker.prompt.build_prompt``), so a contract is measured
against the window it was written for and never against the window it reaches.
Nothing in ``sources``, ``ladder.tiers``, the capability table or a scan says how
large any rung's window is.

Two failures follow, and they are opposite. A contract declaring a ceiling larger
than the rung it lands on passes the check and is truncated by the engine at a
boundary nobody chose. A contract declaring a smaller one is refused on a rung
that had room. Which of the two happens is decided by a number the operator typed
into a file about the work, not by the machine that will answer.

The statements here are outcomes, not a design. Where the window is declared —
source, tier, probe or scan — is the port's to choose; that a rung *has* a
declared window a caller can read, and that the refusal names the rung's number
rather than the contract's, is the requirement.

The share added on 2026-09-06 (``limits.max_window_fraction``) is a share OF this
number, so it cannot be enforced until this exists.
"""

from __future__ import annotations

from typing import Any

from tests.red_port.conftest import required

BIG_CONTRACT = """
id: too-wide
task_type: function_implementation
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
context:
  max_input_tokens: 32768
stop_conditions:
  - The retry policy is not stated anywhere in the repo.
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  max_output_tokens: 1024
"""


def _rung_window(rung: Any) -> Any:
    return required(
        "read the context window a rung serves, from the rung itself",
        lambda: rung.context_window,
    )


def test_a_rung_states_the_window_it_serves() -> None:
    """A resolved rung carries its window as a number a caller can read.

    Asserted on the resolved rung rather than on a config key, because where it
    is written down is the port's choice and what must be true is that the
    dispatch path can ask.
    """
    from mcgyvr.pool import Rung

    rung = Rung(name="local", model="a-model")
    window = _rung_window(rung)
    assert isinstance(window, int) and window > 0, (
        f"a rung must report the window its backend serves, got {window!r}"
    )


def test_a_contract_wider_than_its_rung_is_refused_before_dispatch() -> None:
    """The case that is silently truncated today.

    A contract declaring 32768 of input, sent to a rung serving 4096, must be
    refused — and the refusal must name 4096, because the operator's next move is
    to decompose against the rung's real window and a message quoting 32768 tells
    them the opposite.
    """
    from mcgyvr.contract import loads

    contract = loads(BIG_CONTRACT)
    check = required(
        "refuse a contract that cannot fit the window of the rung it reaches",
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_against_rung"]
            ).check_contract_against_rung
        ),
    )
    issue = check(contract, "x" * 200, rung_window=4096)
    assert issue is not None, "a 32768-token ceiling on a 4096 rung must refuse"
    assert "4096" in issue.message, (
        f"the refusal must name the rung's window, not the contract's: {issue.message}"
    )


def test_a_contract_narrower_than_its_rung_is_not_refused_by_its_own_ceiling() -> None:
    """The opposite failure: a rung with room must not be refused.

    A contract written for a small window is not thereby too large for a big one.
    Today the only enforced ceiling is the contract's, so the rung's spare room is
    unreachable.
    """
    from mcgyvr.contract import loads

    narrow = loads(
        BIG_CONTRACT.replace("max_input_tokens: 32768", "max_input_tokens: 2048")
    )
    check = required(
        "refuse a contract that cannot fit the window of the rung it reaches",
        lambda: (
            __import__(
                "mcgyvr.gate.preflight", fromlist=["check_contract_against_rung"]
            ).check_contract_against_rung
        ),
    )
    assert check(narrow, "x" * 200, rung_window=8192) is None
