"""Relief rungs live in ``relief.yaml``, apart from the units and the ladder.

A relief rung is a unit somebody else hosts and lends through the hub
("hitchhike"): ``mcgyvr rig rungs sync`` writes them, and nothing else does.
They are kept out of the two files a person writes:

* ``fleet.yaml`` is locked and says what runs on *your* rigs; a host's unit is
  not one of them, and a lock that changed whenever a hub re-matched would be
  no lock.
* ``policy.yaml`` is written and commented by hand; a sync that rewrote it
  would take the comments with it, and the ladder in it is the order of *your*
  capability, which a relief rung never joins.

So ``relief.yaml`` is a third file, read beside the other two when it is there.
Its rungs are loaded as units marked ``relief``, never as members of
``units`` or of the ladder: routing reads them only where a full rung spills
(``fanout: idle``), and nothing that walks the ladder or the fleet sees them.
Every key is the schema's; an unknown one is refused, and the credential is
the NAME of a variable, as everywhere else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, load, parse
from mcgyvr.fleet.files import FleetFileError, load_relief

FLEET = """\
units:
  local_fast:
    address: http://fast-box.example:8000
    model: qwen2.5-coder-3b
    width: 1
"""
POLICY = """\
ladder: [local_fast]
fanout: idle
"""
RUNG_ID = "0f3c9a1e2b4d4c6f8a0b1c2d3e4f5a6b"
RELIEF = f"""\
relief:
  hitchhike-{RUNG_ID}:
    address: https://hub.example.org/v1
    model: hitchhike@{RUNG_ID}
    api_key_env: MCGYVR_HUB_API_KEY
    width: 2
    position: below_floor
    hosted_by: bob
    served_model: Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf
"""
NAME = f"hitchhike-{RUNG_ID}"


def setup(tmp_path: Path, relief: str | None = RELIEF) -> Path:
    (tmp_path / "fleet.yaml").write_text(FLEET, encoding="utf-8")
    (tmp_path / "policy.yaml").write_text(POLICY, encoding="utf-8")
    if relief is not None:
        (tmp_path / "relief.yaml").write_text(relief, encoding="utf-8")
    return tmp_path


def test_a_relief_rung_is_read_from_relief_yaml_as_a_unit_marked_relief(
    tmp_path: Path,
) -> None:
    config = load(setup(tmp_path))

    rung = config.relief[NAME]
    assert rung.relief is True
    assert rung.address == "https://hub.example.org/v1"
    assert rung.model == f"hitchhike@{RUNG_ID}"
    assert rung.api_key_env == "MCGYVR_HUB_API_KEY"
    assert rung.width == 2
    assert rung.position == "below_floor"
    assert rung.hosted_by == "bob"
    assert rung.served_model == "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"


def test_a_relief_rung_is_neither_a_unit_of_the_fleet_nor_a_step_of_the_ladder(
    tmp_path: Path,
) -> None:
    config = load(setup(tmp_path))

    assert NAME not in config.units
    assert NAME not in config.ladder.names
    assert all(not unit.relief for unit in config.units.values())


def test_a_setup_without_relief_yaml_has_no_relief_rungs(tmp_path: Path) -> None:
    assert load(setup(tmp_path, relief=None)).relief == {}


def test_an_empty_relief_block_is_no_relief_rungs(tmp_path: Path) -> None:
    assert load(setup(tmp_path, relief="relief: {}\n")).relief == {}


def test_a_merged_document_carries_its_relief_block_too() -> None:
    config = parse(FLEET + POLICY + RELIEF)

    assert config.relief[NAME].relief is True


@pytest.mark.parametrize("where", ["fleet.yaml", "policy.yaml"])
def test_a_relief_block_in_a_hand_written_file_is_refused_naming_relief_yaml(
    tmp_path: Path, where: str
) -> None:
    folder = setup(tmp_path, relief=None)
    written = folder / where
    written.write_text(written.read_text(encoding="utf-8") + RELIEF, encoding="utf-8")

    with pytest.raises(ConfigSchemaError, match=r"relief\.yaml"):
        load(folder)


def test_relief_yaml_holds_the_relief_block_and_nothing_else() -> None:
    with pytest.raises(FleetFileError, match="ladder"):
        load_relief(RELIEF + "ladder: [local_fast]\n")


@pytest.mark.parametrize(
    "key", ["rig", "launch", "engine", "container", "relief", "price"]
)
def test_a_key_a_relief_rung_does_not_take_is_refused(tmp_path: Path, key: str) -> None:
    with pytest.raises(ConfigSchemaError, match=key):
        load(setup(tmp_path, relief=RELIEF + f"    {key}: x\n"))


@pytest.mark.parametrize(
    "key", ["address", "model", "api_key_env", "width", "position"]
)
def test_a_relief_rung_missing_a_required_key_is_refused_by_name(
    tmp_path: Path, key: str
) -> None:
    kept = "".join(
        line + "\n"
        for line in RELIEF.splitlines()
        if not line.strip().startswith(f"{key}:")
    )

    with pytest.raises(ConfigSchemaError, match=key):
        load(setup(tmp_path, relief=kept))


def test_a_relief_rung_names_its_credential_never_holds_it(tmp_path: Path) -> None:
    holding = RELIEF.replace("MCGYVR_HUB_API_KEY", "sk-" + "a" * 24)

    with pytest.raises(ConfigSchemaError, match="api_key_env"):
        load(setup(tmp_path, relief=holding))


def test_a_relief_rung_of_no_width_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigSchemaError, match="width"):
        load(setup(tmp_path, relief=RELIEF.replace("width: 2", "width: 0")))


def test_a_position_the_hub_does_not_name_is_refused(tmp_path: Path) -> None:
    wrong = RELIEF.replace("below_floor", "beside_the_ladder")

    with pytest.raises(ConfigSchemaError, match="position"):
        load(setup(tmp_path, relief=wrong))


def test_a_relief_rung_named_like_a_unit_of_the_fleet_is_refused(
    tmp_path: Path,
) -> None:
    clash = RELIEF.replace(NAME, "local_fast")

    with pytest.raises(ConfigSchemaError, match="local_fast"):
        load(setup(tmp_path, relief=clash))


def test_a_relief_address_carrying_credentials_is_refused(tmp_path: Path) -> None:
    carrying = RELIEF.replace(
        "https://hub.example.org", "https://me:secret@hub.example.org"
    )

    with pytest.raises(ConfigSchemaError, match="credentials"):
        load(setup(tmp_path, relief=carrying))


def test_a_relief_rung_cannot_be_put_on_the_ladder(tmp_path: Path) -> None:
    folder = setup(tmp_path)
    (folder / "policy.yaml").write_text(
        f"ladder: [local_fast, {NAME}]\nfanout: idle\n", encoding="utf-8"
    )

    with pytest.raises(ConfigSchemaError, match="not a declared unit"):
        load(folder)
