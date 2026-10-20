"""A `code` contract's cap is sent exactly, within the ceiling of the unit it reaches.

E2e run 3 T1: ``setup --api`` writes ``output_tokens: 32768`` on every hosted
unit, and the unit's number *replaced* a contract's stated cap — a contract
capped at 16 was sent 32768. Now the contract's cap is
what the work is worth and is never replaced; the unit says how much room it
has, and that is a ceiling, not a number to send.

The ceiling of one dispatch, with ``P`` the assembled prompt as charged (the
estimate every window check spends, its measured reserve included) and ``C``
the unit's served window:

* ``C - P`` where the window is known — the prompt is a constant, the output
  cap is what adjusts;
* ``output_tokens`` where only that is set (a hosted unit);
* the smaller of the two where both are;
* neither known: the dispatch fails loud, naming ``units.<unit>.window`` and
  ``units.<unit>.output_tokens``.

A contract cap above the ceiling fails loud, naming the cap, the unit, ``C``,
``P``, the ceiling and the fix. At or below it, the contract's cap is sent
exactly.
"""

from __future__ import annotations

import math

import pytest

from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.preflight import ESTIMATE_RESERVE, unit_ceiling
from mcgyvr.local_pool import source_map
from mcgyvr.orchestrator.read import estimate_tokens
from tests.rungs import caps_sent

CONTRACT = """
id: impl
task_type: code
task: Add retry with backoff to the fetch helper.
target: src/pkg/fetch.py
stop_conditions: ["The retry policy is not stated anywhere in the repo."]
acceptance: ["python -c 'import sys; sys.exit(0)'"]
scope:
  allow: ["src/**/*.py"]
limits:
  max_output_tokens: {cap}
"""


def unit(name: str, room: str) -> str:
    return (
        "units:\n"
        f"  {name}:\n"
        "    address: http://rig-a.invalid:8080\n"
        "    model: some-coder\n"
        "    width: 1\n" + room + f"ladder: [{name}]\n"
    )


#: A hosted unit as `setup --api` writes it: room for replies, no window.
HOSTED = unit("api_coder", "    output_tokens: 32768\n")
#: A local unit as setup writes it: the window its backend serves.
WINDOWED = unit("local_coder", "    window: 4096\n")
#: A unit that states both.
BOTH = unit("local_coder", "    window: 4096\n    output_tokens: 1024\n")
#: A unit that states neither.
BARE = unit("local_bare", "")


def contract(cap: int):  # type: ignore[no-untyped-def]
    return load_contract(CONTRACT.format(cap=cap))


def charged(text: str) -> int:
    return math.ceil(estimate_tokens(text) * (1 + ESTIMATE_RESERVE))


def sent(
    setup: str, name: str, cap: int, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, int | None]]:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    seen = caps_sent(monkeypatch)
    work = contract(cap)
    dispatch_prompt(source_map(parse_config(setup)), name, build_prompt(work), work)
    return seen


# --- the ceiling ------------------------------------------------------------


def test_the_ceiling_is_the_window_less_the_prompt_as_charged() -> None:
    prompt = "x" * 4000
    ceiling = unit_ceiling(
        source_map(parse_config(WINDOWED)).bind("local_coder"), prompt
    )
    assert ceiling.tokens == 4096 - charged(prompt)


def test_the_ceiling_is_output_tokens_where_no_window_is_known() -> None:
    ceiling = unit_ceiling(source_map(parse_config(HOSTED)).bind("api_coder"), "x")
    assert ceiling.tokens == 32768


def test_the_ceiling_is_the_smaller_where_both_are_known() -> None:
    rung = source_map(parse_config(BOTH)).bind("local_coder")
    assert unit_ceiling(rung, "x").tokens == 1024
    prompt = "x" * 12000
    assert unit_ceiling(rung, prompt).tokens == 4096 - charged(prompt)


def test_the_ceiling_is_unknown_where_neither_is() -> None:
    assert (
        unit_ceiling(source_map(parse_config(BARE)).bind("local_bare"), "x").tokens
        is None
    )


# --- what is sent ------------------------------------------------------------


def test_a_hosted_units_room_does_not_replace_the_contracts_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run 3 regression: a contract capped at 16 was sent 32768."""
    assert sent(HOSTED, "api_coder", 16, monkeypatch) == [("api_coder", 16)]


@pytest.mark.parametrize("cap", [1, 512, 1024])
def test_a_cap_within_the_ceiling_is_sent_exactly(
    cap: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert sent(BOTH, "local_coder", cap, monkeypatch) == [("local_coder", cap)]


def test_a_cap_above_the_ceiling_fails_loud_and_is_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import OutputCapTooLargeError
    from mcgyvr.worker.prompt import build_prompt

    with pytest.raises(OutputCapTooLargeError) as refused:
        sent(WINDOWED, "local_coder", 4000, monkeypatch)
    prompt = build_prompt(contract(4000)).measured
    said = str(refused.value)
    for named in (
        "4000",
        "'local_coder'",
        "4096",
        str(charged(prompt)),
        str(4096 - charged(prompt)),
        "limits.max_output_tokens",
    ):
        assert named in said, (named, said)


def test_a_cap_above_a_units_output_tokens_fails_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import OutputCapTooLargeError

    captured = caps_sent(monkeypatch)
    with pytest.raises(OutputCapTooLargeError) as refused:
        sent(HOSTED, "api_coder", 40000, monkeypatch)
    assert captured == []
    said = str(refused.value)
    assert "40000" in said and "32768" in said and "'api_coder'" in said, said


def test_a_unit_with_no_ceiling_fails_loud_naming_both_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import UnitCeilingUnknownError

    with pytest.raises(UnitCeilingUnknownError) as refused:
        sent(BARE, "local_bare", 256, monkeypatch)
    said = str(refused.value)
    assert "units.local_bare.window" in said, said
    assert "units.local_bare.output_tokens" in said, said
