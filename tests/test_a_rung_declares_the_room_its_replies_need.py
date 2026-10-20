"""A unit may declare the room its replies are given, and it is a ceiling.

A unit may declare ``output_tokens``. It used to be the number sent in place of
the contract's ``limits.max_output_tokens`` (``mcgyvr.gate.preflight``), and in
e2e run 3 a contract capped at 16 was sent the 32768 ``setup --api`` writes on
a hosted unit. Now the contract's cap is what the
work is worth and is sent exactly; a unit's ``output_tokens`` bounds it, beside
the room its window leaves for the prompt, and a cap above that ceiling is a
named refusal
(``tests/test_a_code_contracts_cap_is_sent_exactly_within_its_units_ceiling.py``).

What is asserted below: a unit may declare the room its replies are given;
the contract's number reaches the wire on a unit that declared room and on one
that declared none; and a raw-text reply stays uncapped wherever it runs.
"""

from __future__ import annotations

import textwrap

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.local_pool import source_map
from tests.rungs import PROSE_CONTRACT, caps_sent
from tests.rungs import ROOM_CONTRACT as CONTRACT

#: Two rungs on one rig that serves a 4096-token window. The dear rung declares
#: the room its replies need; the cheap one declares nothing, which is how the
#: fallback is told apart from an override that happens to agree.
LADDER = """\
units:
  local_qwen2.5-coder-3b:
    address: http://localhost:11434
    model: qwen2.5-coder:3b
    rig: box1
    width: 2
    window: 4096
  local_qwen3.6-35b-a3b:
    address: http://localhost:11434
    model: qwen3.6:35b-a3b
    rig: box1
    width: 2
    window: 4096
    output_tokens: 2048
ladder:
- local_qwen2.5-coder-3b
- local_qwen3.6-35b-a3b
"""


def cfg(body: str) -> str:
    return textwrap.dedent(body).strip() + "\n"


# --- the rung may say what its replies need -------------------------------


def test_a_rung_may_declare_the_room_its_replies_need() -> None:
    """The ladder is where a per-rung number can be written at all.

    Unset is ``None`` rather than a number, for the reason ``max_parallel`` is:
    "this rung was measured needing 2048" and "nobody said, so the contract's
    number stands" are different facts, and a rung defaulting to the contract's
    value would be indistinguishable from a rung that declared it.
    """
    config = parse_config(cfg(LADDER))
    cheap, dear = (config.units[n] for n in config.ladder.names)

    assert dear.output_tokens == 2048, (
        "a rung must be able to declare the room its replies need; without it "
        "the 35B rung is sent the same 1024 that cut 32 of its 82 replies"
    )
    assert cheap.output_tokens is None, (
        "a rung that declared nothing must stay distinguishable from one that "
        "declared the contract's number"
    )


# --- the number that reaches the wire -------------------------------------


@pytest.mark.parametrize("rung", ["local_qwen2.5-coder-3b", "local_qwen3.6-35b-a3b"])
def test_the_contracts_cap_is_sent_whether_or_not_the_rung_declared_room(
    rung: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The contract's number reaches the wire on both rungs, unreplaced.

    The dear rung declares 2048 and the contract states 1024, which is within
    it: 1024 is sent. The rung's number is room, not a reply size.
    """
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    sent = caps_sent(monkeypatch)
    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(CONTRACT)

    dispatch_prompt(pool, rung, build_prompt(contract), contract)

    assert sent == [(rung, 1024)]


# --- a contract cap that fits the rung's ceiling -------------------------


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


# --- a raw-text reply is uncapped ----------------------------------------


def test_reply_cap_is_none_for_an_uncapped_prose_reply() -> None:
    """A prose reply has no cap, so the rung's own ``output_tokens`` is not
    consulted — the reply is uncapped wherever it runs."""
    from mcgyvr.gate.preflight import reply_cap

    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(PROSE_CONTRACT)
    assert contract.limits.max_output_tokens is None

    assert reply_cap(contract, pool.bind("local_qwen3.6-35b-a3b")) is None


def test_a_small_window_does_not_refuse_an_uncapped_prose_reply() -> None:
    """A prose reply reserves nothing, so a window too small for any cap is
    still not a refusal: there is no cap for the window to hold."""
    from mcgyvr.gate.preflight import check_contract_against_rung

    small = cfg(LADDER).replace("window: 4096", "window: 64")
    pool = source_map(parse_config(small))
    contract = load_contract(PROSE_CONTRACT)

    assert (
        check_contract_against_rung(
            contract,
            "def fetch(url):\n    return url\n",
            rung=pool.bind("local_qwen3.6-35b-a3b"),
        )
        is None
    )
