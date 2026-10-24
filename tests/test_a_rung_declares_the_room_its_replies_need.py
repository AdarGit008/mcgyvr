"""A unit may declare the room its replies are given, and it is what they are sent.

A unit may declare ``output_tokens``. Every request is sent its unit's maximum:
that number, clamped to the room the unit's window leaves the prompt
(``tests/test_every_generating_request_is_sent_its_units_maximum.py``). A
contract's own ``limits.max_output_tokens`` is read and never sent.

What is asserted below: a unit may declare the room its replies are given; a
rung that declared room is sent it, and one that declared none is sent what its
window leaves; and a window too small for a large reply is not a refusal while
the prompt leaves it room.
"""

from __future__ import annotations

import textwrap

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.local_pool import source_map
from tests.rungs import ROOM_CONTRACT as CONTRACT
from tests.rungs import UNCAPPED_CONTRACT, caps_sent

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
    "this rung was measured needing 2048" and "nobody said, so the window's
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


def test_each_rung_is_sent_its_own_units_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dear rung declares 2048 and is sent it, not the contract's 1024; the
    cheap one declares nothing and is sent the room its window leaves."""
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.gate.preflight import unit_ceiling
    from mcgyvr.worker.prompt import build_prompt

    sent = caps_sent(monkeypatch)
    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(CONTRACT)
    prompt = build_prompt(contract)
    cheap, dear = "local_qwen2.5-coder-3b", "local_qwen3.6-35b-a3b"
    room = unit_ceiling(pool.bind(cheap), prompt.measured).tokens
    assert room is not None and room > 2048

    dispatch_prompt(pool, cheap, prompt, contract)
    dispatch_prompt(pool, dear, prompt, contract)

    assert sent == [(cheap, room), (dear, 2048)]


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


# --- a contract that states no cap ---------------------------------------


def test_a_contract_with_no_cap_is_sent_the_rungs_room() -> None:
    from mcgyvr.gate.preflight import unit_max

    pool = source_map(parse_config(cfg(LADDER)))
    contract = load_contract(UNCAPPED_CONTRACT)
    assert contract.limits.max_output_tokens is None

    assert unit_max(pool.bind("local_qwen3.6-35b-a3b"), "x").tokens == 2048


def test_a_small_window_does_not_refuse_a_contract_with_no_cap() -> None:
    """A window too small for a long reply is still not a refusal while the
    prompt leaves it room: the reply is sent what room there is."""
    from mcgyvr.gate.preflight import check_contract_against_rung

    small = cfg(LADDER).replace("window: 4096", "window: 64")
    pool = source_map(parse_config(small))
    contract = load_contract(UNCAPPED_CONTRACT)

    assert (
        check_contract_against_rung(
            contract,
            "def fetch(url):\n    return url\n",
            rung=pool.bind("local_qwen3.6-35b-a3b"),
        )
        is None
    )
