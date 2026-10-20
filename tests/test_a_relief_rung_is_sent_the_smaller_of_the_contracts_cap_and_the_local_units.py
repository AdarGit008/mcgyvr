"""A relief rung is sent the smaller of the contract's cap and the local unit's.

A rung of the rider's own is sent the contract's ``limits.max_output_tokens``,
held to its unit's ceiling and never replaced by it
(``tests/test_a_code_contracts_cap_is_sent_exactly_within_its_units_ceiling.py``).
A relief rung is another person's unit and declares nothing, so it was sent
the contract's cap whatever the rider's own unit allows.

The cap sent to a relief rung is the smaller of the contract's cap and the
local unit's ``output_tokens``, the local unit being the first usable rung of
the rider's own ladder, the one a ride stands in for when it is full:

* contract 8192, local unit 2048: the ride is sent 2048;
* contract 1024, local unit 2048: the ride is sent 1024;
* a local unit that declares none: the contract's, as on that unit itself;
* a contract with no cap (a raw-text reply), local unit 2048: the ride is
  sent 2048. The local unit's limit applies to the ride whatever the
  contract says, so another person's unit is not asked for a reply with no
  bound;
* neither declares one: the ride is sent none.

That bound is the hub's, not the product's harness, and is kept as it was
when the cap model changed. On the rider's own rungs the
contract's cap is sent exactly, and a contract with no cap — a chat run, a raw
connection — is sent none there.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.preflight import reply_cap
from mcgyvr.local_pool import SourceMap, source_map
from tests.rungs import PROSE_CONTRACT, RIDE, RUNG_ID, caps_sent
from tests.rungs import ROOM_CONTRACT as CONTRACT

LOCAL = "local_fast"


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_KEY", "mhu_" + "1" * 16)


def pool(local: int | None, *, second: int | None = None) -> SourceMap:
    """A ladder of one local unit (and a dearer second), with one relief rung."""

    def room(tokens: int | None) -> str:
        return "" if tokens is None else f"    output_tokens: {tokens}\n"

    text = (
        "units:\n"
        f"  {LOCAL}:\n"
        "    address: http://localhost:8080\n"
        "    model: qwen2.5-coder-3b\n"
        "    width: 1\n" + room(local) + "  local_dear:\n"
        "    address: http://localhost:8081\n"
        "    model: qwen3.6:35b-a3b\n"
        "    width: 1\n" + room(second) + f"ladder: [{LOCAL}, local_dear]\n"
        "fanout: idle\n"
        "relief:\n"
        f"  {RIDE}:\n"
        "    address: http://localhost:8765/v1\n"
        f"    model: hitchhike@{RUNG_ID}\n"
        "    api_key_env: HUB_KEY\n"
        "    width: 1\n"
        "    position: within\n"
        "    served_model: qwen2.5-coder-7b\n"
    )
    return source_map(parse_config(text))


def contract(cap: int | None) -> Contract:
    if cap is None:
        return load_contract(PROSE_CONTRACT)
    # A reply may not be declared larger than what the contract may read.
    return load_contract(
        CONTRACT.replace("max_output_tokens: 1024", f"max_output_tokens: {cap}")
        + "context:\n  max_input_tokens: 16384\n"
    )


@pytest.mark.parametrize(
    ("declared", "local", "sent"),
    [
        (8192, 2048, 2048),  # the local unit's is the smaller
        (1024, 2048, 1024),  # the contract's is the smaller
        (2048, 2048, 2048),
        (1024, None, 1024),  # the local unit declares none: the contract's
        (None, 2048, 2048),  # no cap on the contract: the local unit's
        (None, None, None),  # neither declares one: uncapped
    ],
)
def test_a_ride_is_capped_at_the_smaller_of_the_two(
    declared: int | None, local: int | None, sent: int | None
) -> None:
    assert reply_cap(contract(declared), pool(local).bind(RIDE)) == sent


def test_the_local_unit_is_the_first_rung_of_the_riders_own_ladder() -> None:
    # The dearer rung needs more room for its replies; a ride stands in for
    # the rung work starts on, and is capped as that one is.
    assert reply_cap(contract(8192), pool(2048, second=4096).bind(RIDE)) == 2048
    assert reply_cap(contract(8192), pool(None, second=4096).bind(RIDE)) == 8192


def test_the_contracts_own_number_is_sent_on_the_local_rung() -> None:
    assert reply_cap(contract(1024), pool(2048).bind(LOCAL)) == 1024


def test_a_contract_with_no_cap_is_still_uncapped_on_the_riders_own_rungs() -> None:
    assert reply_cap(contract(None), pool(2048).bind(LOCAL)) is None
    assert reply_cap(contract(None), pool(2048, second=4096).bind("local_dear")) is None


def test_a_ride_for_a_contract_with_no_cap_takes_the_first_local_rungs() -> None:
    assert reply_cap(contract(None), pool(2048, second=4096).bind(RIDE)) == 2048
    assert reply_cap(contract(None), pool(None, second=4096).bind(RIDE)) is None


def test_the_smaller_number_is_what_reaches_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    seen = caps_sent(monkeypatch)
    large, small = contract(8192), contract(1024)

    dispatch_prompt(pool(2048), RIDE, build_prompt(large), large)
    dispatch_prompt(pool(2048), LOCAL, build_prompt(small), small)

    assert seen == [(RIDE, 2048), (LOCAL, 1024)]


def test_the_local_units_limit_reaches_the_wire_for_a_contract_with_no_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    seen = caps_sent(monkeypatch)
    # A chat run: a raw connection that states no cap and is sent none on the
    # rider's own rungs, while a ride still carries the local unit's limit.
    work = load_contract("id: sky\ntask_type: chat\ntask: Why is the sky blue?\n")
    assert work.limits.max_output_tokens is None

    dispatch_prompt(pool(2048), RIDE, build_prompt(work), work)
    dispatch_prompt(pool(2048), LOCAL, build_prompt(work), work)
    dispatch_prompt(pool(None), RIDE, build_prompt(work), work)

    assert seen == [(RIDE, 2048), (LOCAL, None), (RIDE, None)]
