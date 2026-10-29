"""A role or a ladder step may bind a hub unit, on a pool that serves the use case.

A unit the hub lent (a relief rung, as ``mcgyvr rig rungs sync`` writes it) may
be named by a ladder step or by ``orchestrator``, ``verifier`` or ``jev``, as a
unit of your own fleet is. A relief rung so bound is a unit of the dispatch; one
the ladder names is a step of it and is no longer ridden as relief. A relief
rung nothing binds is ridden as before, under ``fanout: idle`` alone.

Whatever a role or a step binds must be served from a pool that serves the
setup's use case. The pool comes from the wire (``hubwire.serving_pool``): a
ride's model is the hitchhike pool, and otherwise the unit's scope names it.
Which use cases a pool serves is ``hubwire.pool_serves``, never a rule of the
config's own. Under ``mcgyvr-code`` a unit served from the general pool, which
serves models raw, is refused when the setup is read, naming the unit, its scope
and the use case; ``code``, ``chat`` and ``agent`` run on any scope.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.capacity import SlotUnavailableError
from mcgyvr.config import ConfigSchemaError, parse
from tests.rigsyncs import FIRST

HUB = "https://hub.example.org/v1"
KEY_ENV = "MCGYVR_HUB_API_KEY"
RIDE = f"hitchhike-{FIRST}"

FLEET = f"""\
units:
  local:
    address: http://box.invalid:8080
    model: coder-7b
    width: 2
  pool_coder:
    address: {HUB}
    model: coder-32b
    api_key_env: {KEY_ENV}
    scope: anyone
"""
RELIEF = f"""\
relief:
  {RIDE}:
    address: {HUB}
    model: hitchhike@{FIRST}
    api_key_env: {KEY_ENV}
    width: 2
    position: below_floor
    scope: anyone
"""

#: Each place a unit is bound, as the policy line that binds `name` there.
BINDINGS = {
    "ladder": "ladder: [local, {name}]\n",
    "orchestrator": "ladder: [local]\norchestrator: {{unit: {name}}}\n",
    "verifier": "ladder: [local]\nverifier: {{unit: {name}}}\n",
    "jev": "ladder: [local]\njev: {{unit: {name}}}\n",
}


def _setup(where: str, name: str, use_case: str = "mcgyvr-code") -> str:
    return f"{FLEET}{BINDINGS[where].format(name=name)}use_case: {use_case}\n"


@pytest.fixture(autouse=True)
def _keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, "mhu_" + "k" * 40)


def _sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, str]]]:
    from mcgyvr import runner

    sent: list[tuple[str, dict[str, str]]] = []

    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, headers))
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            "usage": {},
        }

    monkeypatch.setattr(runner, "_post_json", post)
    return sent


# --- a hub unit binds ----------------------------------------------------------


def test_a_ladder_step_naming_a_relief_rung_is_a_step_and_no_longer_ridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcgyvr import runner
    from mcgyvr.local_pool import source_map

    config = parse(_setup("ladder", RIDE) + "fanout: idle\n", relief_text=RELIEF)

    assert config.ladder.names == ("local", RIDE)
    assert config.units[RIDE].relief is True
    assert RIDE not in config.relief
    pool = source_map(config)
    assert [r.name for r in pool.rungs] == ["local", RIDE]
    assert pool.relief == ()

    sent = _sent(monkeypatch)
    ask = runner.Request(prompt="hello", max_output_tokens=16)
    with contextlib.suppress(runner.RunnerError, SlotUnavailableError):
        runner.dispatch(pool, RIDE, ask)
    ((url, headers),) = sent
    assert url.startswith(HUB)
    assert headers[hubwire.SCOPE_HEADER] == hubwire.SCOPE_ANYONE


@pytest.mark.parametrize("role", ["orchestrator", "verifier", "jev"])
def test_a_role_naming_a_relief_rung_resolves_to_it(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    from mcgyvr import runner
    from mcgyvr.local_pool import source_map

    config = parse(_setup(role, RIDE), relief_text=RELIEF)
    pool = source_map(config)

    binding = pool.role(role)
    assert binding is not None
    assert binding.endpoint.source == RIDE
    assert binding.model == f"hitchhike@{FIRST}"
    sent = _sent(monkeypatch)
    ask = runner.Request(prompt="hello", max_output_tokens=16)
    with contextlib.suppress(runner.RunnerError, SlotUnavailableError):
        runner.dispatch_role(pool, role, ask)
    ((url, headers),) = sent
    assert url.startswith(HUB)
    assert headers[hubwire.SCOPE_HEADER] == hubwire.SCOPE_ANYONE


def test_a_relief_rung_a_role_binds_is_still_ridden_as_relief() -> None:
    config = parse(_setup("verifier", RIDE) + "fanout: idle\n", relief_text=RELIEF)

    assert RIDE in config.relief
    assert config.units[RIDE] is config.relief[RIDE]


def test_a_relief_rung_a_role_binds_is_not_said_to_duplicate_itself() -> None:
    from mcgyvr.escalate import redundant_relief

    config = parse(_setup("verifier", RIDE) + "fanout: idle\n", relief_text=RELIEF)

    assert redundant_relief(config) == ()


def test_a_name_neither_a_unit_nor_a_relief_rung_is_refused_naming_both() -> None:
    with pytest.raises(ConfigSchemaError, match=r"ladder\.1: 'nowhere'.*relief"):
        parse(_setup("ladder", "nowhere"), relief_text=RELIEF)


# --- relief nothing binds ------------------------------------------------------


def test_a_relief_rung_nothing_binds_is_ridden_as_before() -> None:
    from mcgyvr.local_pool import source_map

    config = parse(f"{FLEET}ladder: [local]\nfanout: idle\n", relief_text=RELIEF)

    assert RIDE in config.relief
    assert RIDE not in config.units
    pool = source_map(config)
    assert [r.name for r in pool.relief] == [RIDE]
    assert [r.name for r in pool.rungs] == ["local"]


# --- the pool must serve the use case ------------------------------------------


@pytest.mark.parametrize("where", sorted(BINDINGS))
def test_mcgyvr_code_refuses_a_unit_whose_pool_serves_models_raw(where: str) -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        parse(_setup(where, "pool_coder"), relief_text=RELIEF)

    said = str(refused.value)
    assert "'pool_coder'" in said
    assert "scope 'anyone'" in said
    assert f"{hubwire.POOL_GENERAL} pool" in said
    assert "use case 'mcgyvr-code'" in said


@pytest.mark.parametrize("use_case", ["code", "chat", "agent"])
@pytest.mark.parametrize("where", sorted(BINDINGS))
def test_a_raw_use_case_runs_on_any_scope(where: str, use_case: str) -> None:
    config = parse(_setup(where, "pool_coder", use_case), relief_text=RELIEF)

    assert config.units["pool_coder"].scope == hubwire.SCOPE_ANYONE


@pytest.mark.parametrize("scope", hubwire.SCOPE_VALUES)
@pytest.mark.parametrize("where", sorted(BINDINGS))
def test_a_ride_serves_mcgyvr_code_whatever_its_scope(where: str, scope: str) -> None:
    stated = RELIEF.replace("scope: anyone", f"scope: {scope}")
    config = parse(_setup(where, RIDE), relief_text=stated)

    assert config.units[RIDE].scope == scope


def test_mcgyvr_code_is_the_use_case_a_setup_naming_none_is_held_to() -> None:
    unnamed = f"{FLEET}{BINDINGS['ladder'].format(name='pool_coder')}"

    with pytest.raises(ConfigSchemaError, match="use case 'mcgyvr-code'"):
        parse(unnamed)


def test_a_jev_switched_off_is_not_held_to_its_pool() -> None:
    off = _setup("jev", "pool_coder").replace(
        "jev: {unit: pool_coder}", "jev: {unit: pool_coder, enabled: false}"
    )

    assert parse(off).get("jev.unit") == "pool_coder"


def test_the_rule_is_the_wires_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """A general pool that served ``mcgyvr-code`` would be taken: the config
    holds no rule of its own about which scope is allowed."""
    served = {**hubwire.POOL_USE_CASES, hubwire.POOL_GENERAL: hubwire.USE_CASES}
    monkeypatch.setattr(hubwire, "POOL_USE_CASES", served)

    assert parse(_setup("ladder", "pool_coder")).ladder.names == ("local", "pool_coder")
