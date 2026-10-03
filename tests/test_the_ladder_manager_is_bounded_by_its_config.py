"""The ladder manager does only what the ``manager`` block of the config allows.

The manager is a long-running loop that may sleep and wake units, change
``fanout`` and move a local unit to the front of the local family. None of that
is the manager's to decide on its own: every number it works to, and every
choice it may make, is a key of the config, so a run is reproducible from the
file it was made under and the bounds are written where the owner of the rig
reads them.

What must hold:

* A config that says nothing about ``manager`` has the block filled in, and the
  defaults read back through ``Config.get``. Every numeric default is a choice
  and is documented as one.
* ``manager.fanouts`` names fan-out modes drawn from the same choices as
  ``fanout``, and ``manager.leads`` names units that are on the ladder and need
  no credential, because a unit that is not laddered cannot be moved to the
  front of anything and a hosted unit is not "local".
* A duplicate in either list, an entry outside its set, and a lead that needs a
  credential are refused when the config loads, by key, so the mistake is
  found before any machine is touched.
"""

from __future__ import annotations

import pytest

from mcgyvr.config import ConfigSchemaError, parse

#: Two local units on invented hosts and one hosted unit, all on the ladder.
FLEET = """\
units:
  local_fast:
    address: http://fast-box.example:8000
    model: small-model
    rig: fast-box
    width: 2
  local_smart:
    address: http://smart-box.example:8000
    model: large-model
    rig: smart-box
    width: 1
  api_big:
    address: https://api.example.com
    model: hosted-model
    api_key_env: EXAMPLE_API_KEY
ladder:
- local_fast
- local_smart
- api_big
"""


def test_a_config_that_says_nothing_has_the_manager_block_at_its_defaults() -> None:
    config = parse(FLEET)

    assert config.get("manager.interval_s") == 30
    assert config.get("manager.confirm") == 3
    assert config.get("manager.dwell_s") == 600
    assert config.get("manager.fanouts") == []
    assert config.get("manager.leads") == []


def test_a_valid_manager_block_parses_and_reads_back() -> None:
    config = parse(
        FLEET
        + "manager:\n"
        + "  interval_s: 10\n"
        + "  confirm: 2\n"
        + "  dwell_s: 0\n"
        + "  fanouts: [none, full]\n"
        + "  leads: [local_smart, local_fast]\n"
    )

    assert config.get("manager.interval_s") == 10
    assert config.get("manager.confirm") == 2
    assert config.get("manager.dwell_s") == 0
    assert config.get("manager.fanouts") == ["none", "full"]
    assert config.get("manager.leads") == ["local_smart", "local_fast"]


@pytest.mark.parametrize(
    ("key", "value"),
    [("interval_s", 0), ("confirm", 0), ("dwell_s", -1)],
)
def test_a_number_below_its_floor_is_refused_by_key(key: str, value: int) -> None:
    with pytest.raises(ConfigSchemaError, match=f"manager.{key}"):
        parse(FLEET + f"manager:\n  {key}: {value}\n")


def test_a_fanout_the_config_does_not_know_is_refused_by_key() -> None:
    with pytest.raises(ConfigSchemaError, match=r"manager\.fanouts\.1") as refused:
        parse(FLEET + "manager:\n  fanouts: [none, wide]\n")

    message = str(refused.value)
    assert "'wide'" in message
    assert "none, idle, full" in message, "the valid modes are named"


def test_a_duplicate_fanout_is_refused_by_key() -> None:
    with pytest.raises(ConfigSchemaError, match=r"manager\.fanouts\.1") as refused:
        parse(FLEET + "manager:\n  fanouts: [idle, idle]\n")

    assert "more than once" in str(refused.value)


def test_a_duplicate_lead_is_refused_by_key() -> None:
    with pytest.raises(ConfigSchemaError, match=r"manager\.leads\.1") as refused:
        parse(FLEET + "manager:\n  leads: [local_fast, local_fast]\n")

    assert "more than once" in str(refused.value)


def test_a_lead_that_is_not_on_the_ladder_is_refused_by_key() -> None:
    declared_off_ladder = FLEET.replace("- local_smart\n", "")

    with pytest.raises(ConfigSchemaError, match=r"manager\.leads\.0") as refused:
        parse(declared_off_ladder + "manager:\n  leads: [local_smart]\n")

    message = str(refused.value)
    assert "'local_smart'" in message
    assert "not on the ladder" in message


def test_a_lead_nobody_declared_is_refused_by_key() -> None:
    with pytest.raises(ConfigSchemaError, match=r"manager\.leads\.0") as refused:
        parse(FLEET + "manager:\n  leads: [ghost]\n")

    assert "'ghost'" in str(refused.value)


def test_a_lead_that_needs_a_credential_is_refused_by_key() -> None:
    with pytest.raises(ConfigSchemaError, match=r"manager\.leads\.1") as refused:
        parse(FLEET + "manager:\n  leads: [local_fast, api_big]\n")

    message = str(refused.value)
    assert "'api_big'" in message
    assert "credential" in message, "the reason a hosted unit cannot lead is said"
    assert "EXAMPLE_API_KEY" not in message, "the variable's name is not needed"


def test_an_unknown_manager_key_is_refused_like_any_other_unknown_key() -> None:
    with pytest.raises(ConfigSchemaError, match="manager: unknown key 'speed'"):
        parse(FLEET + "manager:\n  speed: 3\n")
