"""``mcgyvr rig crew sync`` keeps the units your crews lend you, and touches nothing else.

The hub lists, at its OpenAI models address under ``x-mcgyvr-scope: crew``, the
models your crews' rigs serve now, each with the slots of its ready units. The
sync asks once with your personal key and that scope, and writes the answer
whole into ``crew.yaml`` beside the setup: one unit per listed model, at the
hub's ``/v1`` address, naming the key's variable, as wide as the slots listed,
and under scope crew. A model the hub no longer lists is gone after the next
sync; one a ladder step or a role binds is refused by name instead, and nothing
is written. The hub's answer is hostile until read: one entry this client
cannot read refuses the whole answer.

A crew unit is a plain unit: a step or a role binds it by name, under every use
case, and every request to it names scope crew. It is served from the crew pool,
which lends free, so it is not an api rung and fan-out may use it.

The fetch and the writer are ``rungs sync``'s, shared: its ``relief.yaml`` is
held here to the bytes it wrote before crew units existed.

Every hub here is a loopback server this test starts.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from tests.rigsyncs import (
    FIRST,
    KEY,
    Hub,
    a_syncing_hub,
    a_syncing_setup,
)

CODER = "qwen3-coder-30b"
SMALL = "qwen2.5-coder-7b"


def cli(*argv: str) -> int:
    from mcgyvr.cli import main

    return main(["rig", "crew", "sync", *argv])


def rungs_cli(*argv: str) -> int:
    from mcgyvr.cli import main

    return main(["rig", "rungs", "sync", *argv])


def models(*listed: tuple[str, list[int]]) -> dict[str, Any]:
    """The hub's models answer, each model with its ready units' slots."""
    return {
        "object": "list",
        "data": [
            {
                "id": name,
                "object": "model",
                "created": 0,
                "owned_by": "pool",
                hubwire.MODEL_SLOTS: slots,
            }
            for name, slots in listed
        ],
    }


def crew(setup: Path) -> dict[str, Any]:
    """The crew units the setup loads with, by name."""
    from mcgyvr.config import load

    config = load(setup)
    return {name: unit for name, unit in config.units.items() if name in config.crew}


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_syncing_setup(tmp_path, monkeypatch)


@pytest.fixture
def hub(setup: Path) -> Iterator[Hub]:
    with a_syncing_hub(setup) as made:
        yield made


# --- what a sync writes --------------------------------------------------------


def test_each_listed_model_is_kept_as_a_unit_under_scope_crew(
    setup: Path, hub: Hub
) -> None:
    hub.answer(models((CODER, [4, 2]), (SMALL, [1])))

    assert cli() == 0

    kept = crew(setup)
    assert sorted(kept) == [f"crew-{SMALL}", f"crew-{CODER}"]
    coder = kept[f"crew-{CODER}"]
    assert coder.scope == hubwire.SCOPE_CREW
    assert coder.address == f"{hub.address}{hubwire.API_ROOT}"
    assert coder.model == CODER
    assert coder.api_key_env == "MCGYVR_HUB_API_KEY"
    assert coder.width == 6
    assert coder.relief is False
    assert kept[f"crew-{SMALL}"].width == 1


def test_the_hub_is_asked_once_with_the_personal_key_under_scope_crew(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(models((CODER, [2])))

    assert cli() == 0

    (asked,) = hub.asked
    assert asked["method"] == "GET"
    assert asked["path"] == hubwire.MODELS_PATH
    assert asked["authorization"] == f"Bearer {KEY}"
    assert asked["scope"] == hubwire.SCOPE_CREW
    out = capsys.readouterr()
    written = (setup / "crew.yaml").read_text(encoding="utf-8")
    for text in (out.out, out.err, written):
        assert KEY not in text


def test_a_sync_says_what_it_kept_and_where(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(models((CODER, [4, 2])))

    assert cli() == 0

    out = capsys.readouterr().out
    assert f"kept 1 crew unit(s) in {setup / 'crew.yaml'}" in out
    assert f"  crew-{CODER}  x6  {CODER}" in out


def test_a_sync_touches_neither_the_fleet_nor_the_policy_nor_the_relief_rungs(
    setup: Path, hub: Hub
) -> None:
    before = {path.name: path.read_bytes() for path in setup.iterdir()}
    hub.answer(models((CODER, [2])))

    assert cli() == 0

    after = {path.name: path.read_bytes() for path in setup.iterdir()}
    assert sorted(after) == sorted([*before, "crew.yaml"])
    assert {name: after[name] for name in before} == before


def test_a_model_the_hub_no_longer_lists_is_gone_after_the_next_sync(
    setup: Path, hub: Hub
) -> None:
    hub.answer(models((CODER, [2]), (SMALL, [1])))
    assert cli() == 0

    hub.answer(models((SMALL, [1])))
    assert cli() == 0

    assert sorted(crew(setup)) == [f"crew-{SMALL}"]


def test_an_answer_with_no_crew_model_writes_none_and_removes_the_stale_ones(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    hub.answer(models((CODER, [2])))
    assert cli() == 0

    hub.answer(models())
    assert cli() == 0

    assert crew(setup) == {}
    assert "kept 0 crew unit(s)" in capsys.readouterr().out


def test_a_unit_the_ladder_binds_is_not_dropped_and_is_named(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    hub.answer(models((CODER, [2])))
    assert cli() == 0
    policy = setup / "policy.yaml"
    policy.write_text(f"ladder: [local_fast, crew-{CODER}]\n", encoding="utf-8")
    kept = (setup / "crew.yaml").read_bytes()

    hub.answer(models())
    assert cli() == Exit.ERROR

    assert f"crew-{CODER}" in capsys.readouterr().err
    assert (setup / "crew.yaml").read_bytes() == kept


# --- what a sync refuses -------------------------------------------------------


def test_a_hub_that_cannot_be_reached_is_said_and_nothing_is_removed(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    hub.answer(models((CODER, [2])))
    assert cli() == 0
    kept = (setup / "crew.yaml").read_bytes()
    capsys.readouterr()

    assert cli("--hub", "http://127.0.0.1:9") == Exit.ERROR

    assert "could not be reached" in capsys.readouterr().err
    assert (setup / "crew.yaml").read_bytes() == kept


def test_a_hub_that_refuses_is_said_and_nothing_is_written(
    setup: Path, hub: Hub, capsys: pytest.CaptureFixture[str]
) -> None:
    from mcgyvr.exits import Exit

    hub.answer({"error": {"code": "invalid_api_key"}}, status=401)

    assert cli() == Exit.REFUSED
    assert "401" in capsys.readouterr().err
    assert not (setup / "crew.yaml").exists()


def _malformed() -> list[Any]:
    good = models((CODER, [2]))["data"][0]
    return [
        [],
        {"object": "list"},
        {"object": "list", "data": {}},
        {"object": "list", "data": ["x"]},
        {"object": "list", "data": [{**good, "id": "../etc"}]},
        {"object": "list", "data": [{**good, "id": f"{hubwire.RUNG_PREFIX}{FIRST}"}]},
        {"object": "list", "data": [{**good, hubwire.MODEL_SLOTS: 2}]},
        {"object": "list", "data": [{**good, hubwire.MODEL_SLOTS: [0]}]},
        {"object": "list", "data": [{**good, hubwire.MODEL_SLOTS: [True]}]},
        {"object": "list", "data": [good, good]},
    ]


@pytest.mark.parametrize("answer", _malformed())
def test_an_answer_this_client_cannot_read_whole_is_refused_whole(
    setup: Path, hub: Hub, answer: Any
) -> None:
    from mcgyvr.exits import Exit

    hub.answer(models((SMALL, [1])))
    assert cli() == 0
    kept = (setup / "crew.yaml").read_bytes()

    hub.answer(answer)
    assert cli() == Exit.REFUSED

    assert (setup / "crew.yaml").read_bytes() == kept


def test_with_no_key_nothing_is_asked(
    setup: Path,
    hub: Hub,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from mcgyvr.exits import Exit

    monkeypatch.delenv("MCGYVR_HUB_API_KEY")

    assert cli() == Exit.ERROR
    assert "MCGYVR_HUB_API_KEY" in capsys.readouterr().err
    assert hub.asked == []


def test_a_crew_unit_named_as_a_fleet_unit_is_refused(setup: Path) -> None:
    from mcgyvr.config import ConfigError, load

    (setup / "crew.yaml").write_text(
        "crew:\n  local_fast:\n    address: https://hub.example/v1\n"
        f"    model: {CODER}\n    api_key_env: MCGYVR_HUB_API_KEY\n    width: 1\n"
        "    scope: crew\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="local_fast"):
        load(setup)


# --- what a crew unit is to a dispatch -----------------------------------------


def _bound(setup: Path, hub: Hub, policy: str) -> Any:
    from mcgyvr.config import load

    hub.answer(models((CODER, [2])))
    assert cli() == 0
    (setup / "policy.yaml").write_text(policy, encoding="utf-8")
    return load(setup)


def test_a_request_to_a_crew_unit_names_scope_crew(setup: Path, hub: Hub) -> None:
    from mcgyvr.local_pool import source_map
    from mcgyvr.runner import request_headers

    config = _bound(setup, hub, f"ladder: [local_fast, crew-{CODER}]\n")

    endpoint = source_map(config).endpoints[f"crew-{CODER}"]
    assert request_headers(endpoint)[hubwire.SCOPE_HEADER] == hubwire.SCOPE_CREW


@pytest.mark.parametrize("use_case", hubwire.USE_CASES)
def test_a_step_and_a_role_bind_a_crew_unit_under_every_use_case(
    setup: Path, hub: Hub, use_case: str
) -> None:
    name = f"crew-{CODER}"
    config = _bound(
        setup,
        hub,
        f"use_case: {use_case}\nladder: [local_fast, {name}]\nverifier:\n"
        f"  unit: {name}\n",
    )

    assert name in config.ladder.names
    assert config.get("verifier.unit") == name


def test_a_crew_unit_is_not_an_api_rung_so_fan_out_may_use_it(
    setup: Path, hub: Hub
) -> None:
    from mcgyvr.route import family_of

    config = _bound(setup, hub, f"ladder: [local_fast, crew-{CODER}]\n")

    assert family_of(config, f"crew-{CODER}").name == "local"


def test_a_unit_with_a_key_under_another_scope_is_still_an_api_rung() -> None:
    from mcgyvr.catalog import catalog
    from mcgyvr.config import Unit

    for scope in (hubwire.SCOPE_OWN, hubwire.SCOPE_ANYONE):
        unit = Unit(
            name="hosted",
            address="https://api.example.com/v1",
            model="vendor-large",
            api_key_env="EXAMPLE_API_KEY",
            scope=scope,
        )
        assert catalog().family_of(unit).name == "api"
    ride = Unit(
        name="ride",
        address="https://hub.example/v1",
        model=hubwire.rung_model(FIRST),
        api_key_env="MCGYVR_HUB_API_KEY",
        relief=True,
        scope=hubwire.SCOPE_CREW,
    )
    assert catalog().family_of(ride).name == "api"


# --- rungs sync is what it was -------------------------------------------------


def _relief_as_written_before(address: str) -> str:
    """``relief.yaml`` for one listed rung, as ``rungs sync`` wrote it before
    crew units existed."""
    return (
        "# Written by `mcgyvr rig rungs sync`, which rewrites it whole: an edit\n"
        "# here lasts until the next sync. Each host can read the prompts sent\n"
        "# to their rung.\n"
        "relief:\n"
        f"  hitchhike-{FIRST}:\n"
        f"    address: {address}/v1\n"
        f"    model: hitchhike@{FIRST}\n"
        "    api_key_env: MCGYVR_HUB_API_KEY\n"
        "    width: 2\n"
        "    position: below_floor\n"
        "    hosted_by: bob\n"
        "    served_model: Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf\n"
        "    busy_answers:\n"
        "    - status: 404\n"
        "      code: model_not_found\n"
        "    - status: 503\n"
        "      code: hitchhike_host_away\n"
        "    - status: 503\n"
        "      code: hitchhike_not_served_yet\n"
        "    - status: 503\n"
        "      code: pool_busy\n"
        "    scope: anyone\n"
    )


def test_rungs_sync_writes_its_relief_rungs_byte_for_byte_beside_crew_units(
    setup: Path, hub: Hub
) -> None:
    hub.answer(models((CODER, [2])))
    assert cli() == 0
    crew_kept = (setup / "crew.yaml").read_bytes()

    hub.answer(hub.listing(FIRST))
    assert rungs_cli() == 0

    relief = (setup / "relief.yaml").read_text(encoding="utf-8")
    assert relief == _relief_as_written_before(hub.address)
    assert (setup / "crew.yaml").read_bytes() == crew_kept
    assert hub.asked[-1]["path"] == "/api/v1/me/rungs"
