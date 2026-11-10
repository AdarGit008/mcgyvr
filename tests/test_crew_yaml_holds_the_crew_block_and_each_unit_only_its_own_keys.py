"""``crew.yaml`` holds the crew block, and each crew unit only its own keys.

``mcgyvr rig crew sync`` writes ``crew.yaml`` whole: one key, ``crew``, whose
entries are units your crews lend, each carrying only what the sync writes
(``address``, ``model``, ``api_key_env``, ``width``, ``scope``). Its reader keeps
every unit as given, since its fields are the schema's ``units`` fields, and
refuses any other key, top-level or in a unit, by name and with the keys that
are valid there: an ignored key is a file that does not do what it says. A
setup loads the file through the same reader, so a refusal there stops the
setup as a schema error naming ``crew.yaml``.

The hub, its address and the units are invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.config import ConfigSchemaError, load
from mcgyvr.fleet.files import FleetFileError, load_crew

CREW = """\
crew:
  crew-coder:
    address: https://hub.example.org/v1
    model: example-coder-7b
    api_key_env: EXAMPLE_HUB_KEY
    width: 2
    scope: crew
"""


def test_each_crew_unit_is_kept_as_given() -> None:
    assert load_crew(CREW) == {
        "crew": {
            "crew-coder": {
                "address": "https://hub.example.org/v1",
                "model": "example-coder-7b",
                "api_key_env": "EXAMPLE_HUB_KEY",
                "width": 2,
                "scope": "crew",
            }
        }
    }


def test_a_key_beside_crew_is_refused_naming_the_one_that_is_valid() -> None:
    with pytest.raises(FleetFileError, match=r"crew\.yaml: unknown key 'units'.*crew"):
        load_crew(CREW + "units: {}\n")


@pytest.mark.parametrize("key", ["position", "hosted_by", "api_key"])
def test_a_key_a_crew_unit_does_not_take_is_refused_by_name(key: str) -> None:
    text = CREW + f"    {key}: x\n"
    with pytest.raises(FleetFileError, match=rf"crew\.crew-coder: unknown key '{key}'"):
        load_crew(text)


def test_a_crew_unit_that_is_not_a_block_is_refused() -> None:
    with pytest.raises(FleetFileError, match=r"crew\.yaml: crew\.crew-coder"):
        load_crew("crew:\n  crew-coder: just-a-word\n")


def test_a_setup_whose_crew_yaml_carries_a_foreign_key_does_not_load(
    tmp_path: Path,
) -> None:
    (tmp_path / "fleet.yaml").write_text(
        "units:\n  local_fast:\n    address: http://fast-box.example:8000\n"
        "    model: example-coder-3b\n    width: 1\n",
        encoding="utf-8",
    )
    (tmp_path / "policy.yaml").write_text("ladder: [local_fast]\n", encoding="utf-8")
    (tmp_path / "crew.yaml").write_text(CREW + "    position: top\n", encoding="utf-8")
    with pytest.raises(ConfigSchemaError, match=r"crew\.yaml"):
        load(tmp_path)
