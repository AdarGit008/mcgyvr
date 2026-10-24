"""A relief rung is sent no more than the local unit it stands in for gives.

Every request is sent its unit's maximum
(``tests/test_every_generating_request_is_sent_its_units_maximum.py``). A relief
rung is another person's unit and declares nothing, so its maximum is the
reply room of the local unit it stands in for — the first usable rung of the
rider's own ladder, the one a ride stands in for when it is full:

* local unit 2048: the ride is sent 2048, whatever the contract states;
* a local unit that declares none: the ride has no ceiling, and is sent none;
* the rider's own rungs are sent their own unit's maximum.

That bound is the hub's, not the product's harness, and is kept as it was
when the cap model changed.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import Contract
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.preflight import unit_max
from mcgyvr.local_pool import SourceMap, source_map
from tests.rungs import RIDE, RUNG_ID, UNCAPPED_CONTRACT, caps_sent
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
        return load_contract(UNCAPPED_CONTRACT)
    # A reply may not be declared larger than what the contract may read.
    return load_contract(
        CONTRACT.replace("max_output_tokens: 1024", f"max_output_tokens: {cap}")
        + "context:\n  max_input_tokens: 16384\n"
    )


def cap(contract_: Contract, rung: str, pool_: SourceMap) -> int | None:
    from mcgyvr.worker.prompt import build_prompt

    return unit_max(pool_.bind(rung), build_prompt(contract_).measured).tokens


@pytest.mark.parametrize(
    ("declared", "local", "sent"),
    [
        (8192, 2048, 2048),  # the contract's cap is not sent
        (1024, 2048, 2048),
        (None, 2048, 2048),
        (1024, None, None),  # the local unit declares none: nothing to send
        (None, None, None),
    ],
)
def test_a_ride_is_sent_the_local_units_room(
    declared: int | None, local: int | None, sent: int | None
) -> None:
    assert cap(contract(declared), RIDE, pool(local)) == sent


def test_the_local_unit_is_the_first_rung_of_the_riders_own_ladder() -> None:
    # The dearer rung needs more room for its replies; a ride stands in for
    # the rung work starts on, and is capped as that one is.
    assert cap(contract(8192), RIDE, pool(2048, second=4096)) == 2048
    assert cap(contract(8192), RIDE, pool(None, second=4096)) is None


def test_the_riders_own_rungs_are_sent_their_own_units_maximum() -> None:
    assert cap(contract(1024), LOCAL, pool(2048)) == 2048
    assert cap(contract(None), "local_dear", pool(2048, second=4096)) == 4096


def test_the_local_units_room_is_what_reaches_the_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    seen = caps_sent(monkeypatch)
    large, small = contract(8192), contract(1024)

    dispatch_prompt(pool(2048), RIDE, build_prompt(large), large)
    dispatch_prompt(pool(2048), LOCAL, build_prompt(small), small)

    assert seen == [(RIDE, 2048), (LOCAL, 2048)]
