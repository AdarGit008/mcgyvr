"""Every generating request is sent its unit's maximum, clamped to the room left.

The reply cap used to be a per-call choice: a rung attempt was sent the
contract's ``limits.max_output_tokens`` (twice the target, from the
decomposer), a decomposition and a review were sent no cap at all. The owner's
intent is the most the unit can give, as the product's rule rather than a
setting. With ``P`` the prompt as charged (the estimate every window check
spends, its measured reserve included) and ``C`` the unit's served window, the
cap every generating request is sent is:

* ``C - P`` where only the window is known;
* ``output_tokens`` where only that is stated (a hosted unit);
* the smaller of the two where both are, so prompt and cap never outgrow ``C``;
* nothing where neither is: a model-written ``code`` dispatch fails loud,
  naming ``units.<unit>.window`` and ``units.<unit>.output_tokens``.

A contract's own ``limits.max_output_tokens`` is read and never sent. A request
that states its own small cap — a one-token decision, a warm-up, a probe —
keeps it.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from mcgyvr import runner
from mcgyvr.config import parse as parse_config
from mcgyvr.contract import loads as load_contract
from mcgyvr.gate.preflight import (
    ESTIMATE_RESERVE,
    check_contract_against_rung,
    unit_ceiling,
    unit_max,
)
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


def contract(cap: int | None = None):  # type: ignore[no-untyped-def]
    if cap is None:
        return load_contract(CONTRACT)
    return load_contract(CONTRACT + f"limits:\n  max_output_tokens: {cap}\n")


def charged(text: str) -> int:
    return math.ceil(estimate_tokens(text) * (1 + ESTIMATE_RESERVE))


def sent(
    setup: str, name: str, monkeypatch: pytest.MonkeyPatch, cap: int | None = None
) -> list[tuple[str, int | None]]:
    from mcgyvr.drive import dispatch_prompt
    from mcgyvr.worker.prompt import build_prompt

    seen = caps_sent(monkeypatch)
    work = contract(cap)
    dispatch_prompt(source_map(parse_config(setup)), name, build_prompt(work), work)
    return seen


def measured(cap: int | None = None) -> str:
    from mcgyvr.worker.prompt import build_prompt

    return build_prompt(contract(cap)).measured


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


# --- a rung's attempt ---------------------------------------------------------


def test_a_hosted_unit_is_sent_its_output_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sent(HOSTED, "api_coder", monkeypatch) == [("api_coder", 32768)]


def test_a_windowed_unit_is_sent_the_room_its_window_leaves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = 4096 - charged(measured())
    assert sent(WINDOWED, "local_coder", monkeypatch) == [("local_coder", room)]


def test_a_unit_stating_both_is_sent_the_smaller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert 4096 - charged(measured()) > 1024, "the window is not the smaller here"
    assert sent(BOTH, "local_coder", monkeypatch) == [("local_coder", 1024)]


@pytest.mark.parametrize("stated", [16, 1024, 40000])
def test_a_contracts_own_cap_is_never_what_is_sent(
    stated: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run 3 contract capped at 16 is sent what its unit can give."""
    assert sent(HOSTED, "api_coder", monkeypatch, stated) == [("api_coder", 32768)]
    room = 4096 - charged(measured(stated))
    assert sent(WINDOWED, "local_coder", monkeypatch, stated)[-1] == (
        "local_coder",
        room,
    )


@pytest.mark.parametrize("size", [0, 2000, 8000, 12000])
def test_prompt_and_cap_never_outgrow_the_window(size: int) -> None:
    rung = source_map(parse_config(BOTH)).bind("local_coder")
    prompt = "x" * size
    cap = unit_max(rung, prompt).tokens
    assert cap is not None and cap >= 1
    assert charged(prompt) + cap <= 4096
    assert cap <= 1024


def test_a_prompt_that_leaves_no_room_is_refused_before_it_is_sent() -> None:
    rung = source_map(parse_config(WINDOWED)).bind("local_coder")
    issue = check_contract_against_rung(contract(), "x" * 13000, rung=rung)
    assert issue is not None and issue.reason == "prompt-too-large", issue
    assert unit_max(rung, "x" * 13000).tokens is None


def test_a_unit_with_no_ceiling_fails_loud_naming_both_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.drive import UnitCeilingUnknownError

    with pytest.raises(UnitCeilingUnknownError) as refused:
        sent(BARE, "local_bare", monkeypatch)
    said = str(refused.value)
    assert "units.local_bare.window" in said, said
    assert "units.local_bare.output_tokens" in said, said


def test_the_cap_travels_with_the_sentence_that_explains_it() -> None:
    rung = source_map(parse_config(BOTH)).bind("local_coder")
    cap = unit_max(rung, "x")
    assert cap.tokens == 1024
    assert "'local_coder'" in cap.basis and "`output_tokens` is 1024" in cap.basis


# --- every other generating request: decomposition, review --------------------


def _wire(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    posted: list[dict[str, Any]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        posted.append(payload)
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "[]"}}],
            "usage": {},
        }

    monkeypatch.setattr(runner, "_post_json", post)
    return posted


@pytest.mark.parametrize("role", ["orchestrator", "verifier"])
def test_a_role_request_that_states_no_cap_is_sent_the_units_maximum(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = source_map(parse_config(BOTH + f"{role}:\n  unit: local_coder\n"))
    posted = _wire(monkeypatch)

    answer = runner.dispatch_role(
        pool, role, runner.Request(prompt="hello", max_output_tokens=None)
    )

    assert answer is not None
    assert posted[0]["max_tokens"] == 1024
    assert answer.max_output_tokens == 1024
    assert "'local_coder'" in answer.cap_basis


def test_the_decomposer_and_the_reviewer_are_sent_the_units_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr.delegate import proposer_for
    from mcgyvr.orchestrator.decompose import Evidence
    from mcgyvr.verify import reviewer_for

    setup = (
        WINDOWED
        + "orchestrator:\n  unit: local_coder\nverifier:\n  unit: local_coder\n"
    )
    pool = source_map(parse_config(setup))
    posted = _wire(monkeypatch)
    monkeypatch.setattr("mcgyvr.delegate.build_prompt", lambda evidence: "propose")

    propose = proposer_for(pool)
    review = reviewer_for(pool)
    assert propose is not None and review is not None
    propose(Evidence.__new__(Evidence))
    review("review this")

    assert [p["max_tokens"] for p in posted] == [
        4096 - charged("propose"),
        4096 - charged("review this"),
    ]


def test_a_request_that_states_its_own_cap_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = source_map(parse_config(BOTH))
    posted = _wire(monkeypatch)
    runner.dispatch(
        pool, "local_coder", runner.Request(prompt="ready?", max_output_tokens=8)
    )
    assert posted[0]["max_tokens"] == 8


def test_a_unit_stating_no_ceiling_leaves_a_role_request_uncapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = source_map(parse_config(BARE + "verifier:\n  unit: local_bare\n"))
    posted = _wire(monkeypatch)
    runner.dispatch_role(
        pool, "verifier", runner.Request(prompt="hello", max_output_tokens=None)
    )
    assert "max_tokens" not in posted[0]


def test_the_count_covers_the_system_prompt_and_the_turns() -> None:
    rung = source_map(parse_config(WINDOWED)).bind("local_coder")
    bare = runner.at_unit_max(rung, runner.Request(prompt="q", max_output_tokens=None))
    padded = runner.at_unit_max(
        rung,
        runner.Request(
            prompt="q",
            max_output_tokens=None,
            system="s" * 2000,
            turns=({"role": "user", "content": "t" * 2000},),
        ),
    )
    assert bare.max_output_tokens is not None
    assert padded.max_output_tokens is not None
    assert padded.max_output_tokens < bare.max_output_tokens - 1000
