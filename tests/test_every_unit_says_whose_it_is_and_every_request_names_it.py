"""Every unit says whose it is, and every request to it names that.

A hub serves one model from several places: a member's own rigs, their crews'
rigs, or anyone's (``mcgyvr.hubwire.SCOPE_VALUES``). It tells a crew unit from
a general-pool unit of the same model by the scope header
(``hubwire.SCOPE_HEADER``), so every unit carries a ``scope`` and every chat
request to it, the runner's and Jev's alike, names it beside the use case.

* A unit of your fleet is ``own`` unless it says otherwise.
* A relief rung keeps the scope ``mcgyvr rig rungs sync`` writes. The hub
  matched the rung to you under your own serve scope and hands a ride only to
  rungs you are matched to, so the sync writes the scope that keeps the hub's
  match the only filter: ``anyone``.
* The header goes out through ``runner.request_headers`` alone.

No request leaves the process: the transport is replaced, and what it was
handed is what is checked.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from mcgyvr import hubwire
from mcgyvr.capacity import SlotUnavailableError
from mcgyvr.config import ConfigSchemaError, parse
from tests.rigsyncs import FIRST, rung

HUB = "https://hub.example.org"
KEY_ENV = "MCGYVR_HUB_API_KEY"
RIDE = f"hitchhike-{FIRST}"

FLEET = f"""\
units:
  local:
    address: http://box.invalid:8080
    model: coder-7b
    width: 2
  crew_coder:
    address: {HUB}/v1
    model: coder-32b
    api_key_env: {KEY_ENV}
    scope: crew
"""
RELIEF = f"""\
relief:
  {RIDE}:
    address: {HUB}/v1
    model: hitchhike@{FIRST}
    api_key_env: {KEY_ENV}
    width: 2
    position: below_floor
"""


def _unit(scope: str | None) -> str:
    stated = "" if scope is None else f"    scope: {scope}\n"
    return (
        "units:\n  local:\n    address: http://box.invalid:8080\n"
        f"    model: coder-7b\n{stated}ladder: [local]\nuse_case: chat\n"
    )


def test_a_unit_of_your_fleet_is_your_own_unless_it_says_otherwise() -> None:
    assert parse(_unit(None)).units["local"].scope == hubwire.SCOPE_OWN


@pytest.mark.parametrize("scope", hubwire.SCOPE_VALUES)
def test_a_unit_takes_each_scope_the_wire_names(scope: str) -> None:
    assert parse(_unit(scope)).units["local"].scope == scope


def test_a_scope_the_wire_does_not_name_is_refused() -> None:
    with pytest.raises(ConfigSchemaError, match=r"units\.local\.scope.*Valid"):
        parse(_unit("everyone"))


def test_a_relief_rung_is_anyones_when_its_block_names_no_scope() -> None:
    config = parse(f"{FLEET}ladder: [local]\n", relief_text=RELIEF)

    assert config.relief[RIDE].scope == hubwire.SCOPE_ANYONE


def test_a_relief_rung_keeps_the_scope_its_block_names() -> None:
    stated = RELIEF + "    scope: crew\n"

    assert parse(f"{FLEET}ladder: [local]\n", relief_text=stated).relief[
        RIDE
    ].scope == (hubwire.SCOPE_CREW)


# --- the header ------------------------------------------------------------------


def _capture(
    monkeypatch: pytest.MonkeyPatch, module: Any, sent: list[tuple[str, dict[str, str]]]
) -> None:
    def post(
        url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        sent.append((url, headers))
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "Yes"},
                    "logprobs": {
                        "content": [
                            {"top_logprobs": [{"token": "Yes", "logprob": -0.1}]}
                        ]
                    },
                }
            ],
            "usage": {},
        }

    monkeypatch.setattr(module, "_post_json", post)


@pytest.mark.parametrize("use_case", ["mcgyvr-code", "code", "chat", "agent"])
def test_every_request_names_its_units_scope_beside_the_use_case(
    monkeypatch: pytest.MonkeyPatch, use_case: str
) -> None:
    from mcgyvr import decision, runner
    from mcgyvr.decision import Noul
    from mcgyvr.local_pool import source_map

    monkeypatch.setenv(KEY_ENV, "mhu_" + "k" * 40)
    setup = f"{FLEET}ladder: [local, crew_coder]\nfanout: idle\nuse_case: {use_case}\n"
    pool = source_map(parse(setup, relief_text=RELIEF))
    sent: list[tuple[str, dict[str, str]]] = []
    _capture(monkeypatch, runner, sent)
    _capture(monkeypatch, decision, sent)
    ask = runner.Request(prompt="hello", max_output_tokens=16)

    for name in ("local", "crew_coder", RIDE):
        with contextlib.suppress(runner.RunnerError, SlotUnavailableError):
            runner.runner_for(pool.bind(name)).generate("m", ask)
        decision.classify(pool.bind(name), "m", {"x": 1}, {"q": Noul("Q?")})

    named = [(h[hubwire.SCOPE_HEADER], h[hubwire.USE_CASE_HEADER]) for _, h in sent]
    assert named == [
        (hubwire.SCOPE_OWN, use_case),
        (hubwire.SCOPE_OWN, use_case),
        (hubwire.SCOPE_CREW, use_case),
        (hubwire.SCOPE_CREW, use_case),
        (hubwire.SCOPE_ANYONE, use_case),
        (hubwire.SCOPE_ANYONE, use_case),
    ]


def test_the_runners_headers_name_the_units_scope() -> None:
    from mcgyvr import runner
    from mcgyvr.local_pool import source_map

    pool = source_map(parse(_unit("crew")))
    headers = runner.request_headers(pool.bind("local"))

    assert headers[hubwire.SCOPE_HEADER] == hubwire.SCOPE_CREW


# --- what a sync writes ------------------------------------------------------------


def _rides() -> Any:
    from mcgyvr.rig import rungs

    listing = {
        "ride": True,
        "privacy": "the host can read your prompts",
        "refresh_s": 300,
        "rungs": [rung(FIRST, f"{HUB}/v1")],
    }
    return rungs.read(listing, HUB)


def test_a_sync_writes_each_rungs_scope_and_the_file_reads_it_back() -> None:
    from mcgyvr.rig import rungs

    text = rungs.render(_rides(), KEY_ENV)

    written = yaml.safe_load(text)["relief"][RIDE]
    assert written["scope"] == hubwire.SCOPE_ANYONE
    config = parse(f"{FLEET}ladder: [local]\n", relief_text=text)
    assert config.relief[RIDE].scope == written["scope"]


def test_a_sync_whose_ladder_steps_on_a_relief_rung_reports_only_your_own_rungs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ladder step may name a relief rung, so the setup is read with the rungs
    already kept; the hub is told only the rungs of your own fleet."""
    from mcgyvr.rig import rungs

    (tmp_path / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(
        f"ladder: [local, {RIDE}]\nuse_case: code\n", encoding="utf-8"
    )
    (tmp_path / "relief.yaml").write_text(RELIEF, encoding="utf-8")
    reported: list[dict[str, Any]] = []

    def fetch(hub: str, key: str, report: dict[str, Any]) -> Any:
        reported.append(report)
        return _rides()

    monkeypatch.setattr(rungs, "fetch", fetch)
    rungs.sync(tmp_path, HUB, "mhu_" + "k" * 40, KEY_ENV)

    (report,) = reported
    assert [r["model"] for r in report["ladder"]["rungs"]] == ["coder-7b"]
    kept = yaml.safe_load((tmp_path / "relief.yaml").read_text(encoding="utf-8"))
    assert kept["relief"][RIDE]["scope"] == hubwire.SCOPE_ANYONE
