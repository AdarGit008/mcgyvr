"""A setup synced before the rename still loads its hitchhike rungs, for one release.

``hitchhike.yaml`` was called ``relief.yaml`` and its one key ``relief``. A
setup holding only the old file is read from it as if it were the new one, so
an upgrade loses no rung, and the next ``mcgyvr rig rungs sync`` writes
``hitchhike.yaml`` and removes the old file. Where both are there the new one
is read. ``relief`` anywhere a person writes (fleet.yaml, policy.yaml, a setup
written as one document) is refused, naming ``hitchhike``. And a hub that
still lists each rung with the flag ``relief: true`` (a constant the rider no
longer reads) is answered as one that does not.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, load, parse
from mcgyvr.rig import rungs
from tests.rigsyncs import (
    FIRST,
    FLEET,
    POLICY,
    Hub,
    a_syncing_hub,
    a_syncing_setup,
    cli,
)

RUNG = f"hitchhike-{FIRST}"


def _rungs(key: str, env: str = "MCGYVR_HUB_API_KEY") -> str:
    return (
        f"api_key_env: {env}\n"
        f"{key}:\n"
        f"  {RUNG}:\n"
        "    address: https://hub.example.org/v1\n"
        f"    model: hitchhike@{FIRST}\n"
        f"    api_key_env: {env}\n"
        "    width: 2\n"
        "    position: below_floor\n"
    )


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return a_syncing_setup(tmp_path, monkeypatch)


@pytest.fixture
def hub(setup: Path) -> Iterator[Hub]:
    with a_syncing_hub(setup) as made:
        yield made


def test_a_setup_holding_only_the_old_file_loads_its_rungs(setup: Path) -> None:
    (setup / "relief.yaml").write_text(_rungs("relief"), encoding="utf-8")

    config = load(setup)

    assert list(config.hitchhike) == [RUNG]
    assert config.hitchhike[RUNG].hitchhike is True


def test_hitchhike_yaml_is_read_where_both_files_are_there(setup: Path) -> None:
    (setup / "relief.yaml").write_text("relief: [\n", encoding="utf-8")
    (setup / "hitchhike.yaml").write_text(_rungs("hitchhike"), encoding="utf-8")

    assert list(load(setup).hitchhike) == [RUNG]


def test_the_key_env_is_read_from_the_old_file_too(setup: Path) -> None:
    (setup / "relief.yaml").write_text(
        _rungs("relief", env="MY_HUB_KEY"), encoding="utf-8"
    )

    assert rungs.key_env(setup) == "MY_HUB_KEY"


def test_a_sync_writes_hitchhike_yaml_and_removes_the_old_file(
    setup: Path, hub: Hub
) -> None:
    (setup / "relief.yaml").write_text(_rungs("relief"), encoding="utf-8")
    hub.answer(hub.listing(FIRST))

    assert cli() == 0

    assert not (setup / "relief.yaml").exists()
    written = (setup / "hitchhike.yaml").read_text(encoding="utf-8")
    assert "\nhitchhike:\n" in written
    assert "relief" not in written
    assert list(load(setup).hitchhike) == [RUNG]


def test_a_listing_still_carrying_the_old_flag_is_read_as_before(
    setup: Path, hub: Hub
) -> None:
    listing = hub.listing(FIRST)
    for each in listing["rungs"]:
        each["relief"] = True
    hub.answer(listing)

    assert cli() == 0

    assert list(load(setup).hitchhike) == [RUNG]


@pytest.mark.parametrize("key", ["relief", "hitchhike"])
@pytest.mark.parametrize("where", ["fleet.yaml", "policy.yaml"])
def test_a_rungs_block_in_a_file_a_person_writes_is_refused_naming_hitchhike_yaml(
    key: str, where: str
) -> None:
    block = f"{key}: {{}}\n"
    fleet, policy = (
        (FLEET + block, POLICY)
        if where == "fleet.yaml"
        else (
            FLEET,
            POLICY + block,
        )
    )

    with pytest.raises(ConfigSchemaError) as refused:
        parse(fleet, policy)

    said = str(refused.value)
    assert where in said
    assert "hitchhike.yaml" in said
    assert ("`relief` is now `hitchhike`" in said) == (key == "relief")


def test_a_setup_written_as_one_document_refuses_the_old_key_naming_hitchhike() -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        parse(FLEET + POLICY + "relief: {}\n")

    assert "`relief` is now `hitchhike`" in str(refused.value)


def test_a_file_carrying_both_names_is_refused(setup: Path) -> None:
    both = _rungs("hitchhike") + "relief: {}\n"
    (setup / "hitchhike.yaml").write_text(both, encoding="utf-8")

    with pytest.raises(ConfigSchemaError) as refused:
        load(setup)

    assert "keep `hitchhike`" in str(refused.value)
