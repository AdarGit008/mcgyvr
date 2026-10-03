"""A unit shares its slots with riders only below its width, and none by default.

A host runs their own units for themselves, and may let riders the hub matches
use open slots of one (hitchhike). How many at most is the host's decision
about how their units are used, not a fact of what a unit is, so it is policy:
``rider_slots: {<unit>: N}`` in ``policy.yaml``, a per-unit map spelled the way
``attempts`` is. Turning sharing on or off, or changing how much, therefore
never changes the setup's identity: ``fleet.yaml`` and the lock written from it
are what they were.

* A unit the map does not name shares none (0).
* A share is below the unit's width, so the host always keeps a slot; a unit
  whose width is unset serves one request at once and shares none.
* The map names declared units only, and never a unit that needs a key
  (``api_key_env``, a hosted provider's, not the host's to share) nor a relief
  rung (another person's unit, lent to this host): each is refused by name.
* A value is a whole number of 0 or more, read the way every count is.
* ``fleet.yaml`` refuses ``units.<name>.rider_slots`` and says it belongs in
  ``policy.yaml``.
* The setup reference names it, rendered from the schema like every key.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from mcgyvr import docgen
from mcgyvr.config import Config, ConfigSchemaError, parse
from tests.test_fleet_lock_reads_fleet_and_policy_as_yaml import (
    EVIDENCE,
    FLEET_YAML,
)

FLEET = (
    "units:\n"
    "  local:\n"
    "    address: http://127.0.0.1:8080\n"
    "    model: qwen-small\n"
    "    width: {width}\n"
    "  hosted:\n"
    "    address: https://api.example.org/v1\n"
    "    model: big-hosted\n"
    "    api_key_env: SOME_KEY\n"
    "    width: 8\n"
)


def _load(policy: str, width: int = 4, relief: str = "") -> Config:
    return parse(
        FLEET.format(width=width),
        "ladder: [local, hosted]\n" + policy,
        relief_text=relief,
    )


def test_a_unit_the_map_does_not_name_shares_none() -> None:
    loaded = _load("")
    assert loaded.units["local"].rider_slots == 0
    assert loaded.units["hosted"].rider_slots == 0


@pytest.mark.parametrize(("width", "shared"), [(2, 1), (4, 1), (4, 3), (16, 15)])
def test_a_unit_shares_up_to_one_below_its_width(width: int, shared: int) -> None:
    loaded = _load(f"rider_slots: {{local: {shared}}}\n", width=width)
    assert loaded.units["local"].rider_slots == shared
    assert loaded.units["hosted"].rider_slots == 0


@pytest.mark.parametrize(
    ("policy", "says"),
    [
        ("rider_slots: {local: 4}", "below"),
        ("rider_slots: {local: 5}", "below"),
        ("rider_slots: {local: -1}", "at least 0"),
        ("rider_slots: {local: true}", "a number"),
        ("rider_slots: {local: '2'}", "a number"),
        ("rider_slots: {hosted: 2}", "api_key_env"),
        ("rider_slots: {nobody: 1}", "not a declared unit"),
    ],
)
def test_a_share_the_unit_cannot_give_is_refused_by_name(
    policy: str, says: str
) -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        _load(policy + "\n")
    assert "rider_slots." in str(refused.value)
    assert says in str(refused.value)


def test_a_unit_with_no_width_shares_none() -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        parse(
            "units:\n  local:\n    address: http://127.0.0.1:8080\n    model: m\n",
            "ladder: [local]\nrider_slots: {local: 1}\n",
        )
    assert "rider_slots.local" in str(refused.value)
    assert "width" in str(refused.value)


def test_a_relief_rung_is_not_the_hosts_to_share() -> None:
    rung = "hitchhike-" + "a" * 32
    relief = (
        "relief:\n"
        f"  {rung}:\n"
        "    address: https://hub.example.org/v1\n"
        f"    model: hitchhike@{'a' * 32}\n"
        "    api_key_env: MCGYVR_HUB_API_KEY\n"
        "    width: 4\n"
        "    position: within\n"
    )
    with pytest.raises(ConfigSchemaError) as refused:
        _load(f"rider_slots: {{{rung}: 1}}\n", relief=relief)
    assert f"rider_slots.{rung}" in str(refused.value)
    assert "relief" in str(refused.value)


def test_the_fleet_file_refuses_a_share_and_points_to_the_policy() -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        parse(
            "units:\n"
            "  local:\n"
            "    address: http://127.0.0.1:8080\n"
            "    model: qwen-small\n"
            "    width: 4\n"
            "    rider_slots: 2\n",
            "ladder: [local]\n",
        )
    assert "rider_slots" in str(refused.value)
    assert "policy.yaml" in str(refused.value)


def _lock(root: Path, policy: str) -> dict[str, bytes]:
    from mcgyvr.cli import main

    root.mkdir()
    (root / "fleet.yaml").write_text(FLEET_YAML, encoding="utf-8")
    (root / "policy.yaml").write_text(policy, encoding="utf-8")
    (root / "evidence.json").write_text(json.dumps(EVIDENCE), encoding="utf-8")
    code = main(
        [
            "fleet",
            "lock",
            "--fleet",
            str(root / "fleet.yaml"),
            "--evidence",
            str(root / "evidence.json"),
            "--policy",
            str(root / "policy.yaml"),
            "--root",
            str(root),
        ]
    )
    assert code == 0
    written = {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted((root / "records").rglob("*"))
        if path.is_file()
    }
    assert written
    return written


def test_changing_a_share_leaves_the_setups_identity_and_its_lock_as_they_were(
    tmp_path: Path,
) -> None:
    unit = next(iter(yaml.safe_load(FLEET_YAML)["units"]))
    policies = [
        f"ladder: [{unit}]\n",
        f"ladder: [{unit}]\nrider_slots: {{{unit}: 1}}\n",
        f"ladder: [{unit}]\nrider_slots: {{{unit}: 7}}\n",
    ]

    loaded = [parse(FLEET_YAML, policy) for policy in policies]
    assert [c.units[unit].rider_slots for c in loaded] == [0, 1, 7]
    assert all(c.declared["units"] == loaded[0].declared["units"] for c in loaded)

    locks = [
        _lock(tmp_path / f"setup-{index}", policy)
        for index, policy in enumerate(policies)
    ]
    assert locks[1] == locks[0]
    assert locks[2] == locks[0]


def test_the_setup_reference_names_the_share() -> None:
    text = docgen.render_setup()
    assert "`rider_slots`" in text
    assert "`units.rider_slots`" not in text
