"""A unit shares its slots with riders only below its width, and none by default.

A host runs their own units for themselves, and may let riders the hub matches
use open slots of one (hitchhike). How many at most is a fact of the unit, so
it is a key of the unit: ``units.<name>.rider_slots``, written in
``fleet.yaml`` beside the width it is a share of.

* Absent, it is 0: a unit nobody said to share is not shared, and a setup
  that never names the key is the setup it was (its canonical rendering and
  so its identity do not move).
* It is below the unit's width, so the host always keeps a slot of their own;
  a unit whose width is unset serves one request at once and shares none.
* A unit that needs a key (``api_key_env``) is a hosted provider's, not the
  host's to share, and sharing one is refused at load.
* It is a whole number of 0 or more, read the way every count is: a bool, a
  string or a negative is refused by name.
* It is a fact of the unit, so the policy file refuses it as it refuses
  ``width``.
* The setup reference names it, rendered from the schema like every key.
"""

from __future__ import annotations

import pytest

from mcgyvr import docgen
from mcgyvr.config import ConfigSchemaError, parse


def _setup(**unit: object) -> str:
    lines = [
        "units:",
        "  local:",
        "    address: http://127.0.0.1:8080",
        "    model: qwen-small",
    ]
    lines += [f"    {key}: {value}" for key, value in unit.items()]
    lines += ["ladder: [local]"]
    return "\n".join(lines) + "\n"


def test_a_unit_that_names_no_rider_slots_shares_none_and_keeps_its_identity() -> None:
    plain = parse(_setup(width=4))
    assert plain.units["local"].rider_slots == 0
    assert "rider_slots" not in plain.declared["units"]["local"]
    assert plain.canonical() == parse(_setup(width=4, rider_slots=0)).canonical()


@pytest.mark.parametrize(("width", "shared"), [(2, 1), (4, 1), (4, 3), (16, 15)])
def test_a_unit_shares_up_to_one_below_its_width(width: int, shared: int) -> None:
    loaded = parse(_setup(width=width, rider_slots=shared))
    assert loaded.units["local"].rider_slots == shared
    assert loaded.declared["units"]["local"]["rider_slots"] == shared


@pytest.mark.parametrize(
    ("unit", "says"),
    [
        ({"width": 4, "rider_slots": 4}, "below"),
        ({"width": 4, "rider_slots": 5}, "below"),
        ({"width": 1, "rider_slots": 1}, "below"),
        ({"rider_slots": 1}, "width"),
        ({"width": 4, "rider_slots": -1}, "at least 0"),
        ({"width": 4, "rider_slots": "true"}, "a number"),
        ({"width": 4, "rider_slots": "'2'"}, "a number"),
        ({"width": 4, "rider_slots": 2, "api_key_env": "SOME_KEY"}, "api_key_env"),
    ],
)
def test_a_share_the_unit_cannot_give_is_refused_by_name(
    unit: dict[str, object], says: str
) -> None:
    with pytest.raises(ConfigSchemaError) as refused:
        parse(_setup(**unit))
    assert "units.local.rider_slots" in str(refused.value)
    assert says in str(refused.value)


def test_the_policy_file_refuses_a_share_as_a_fact_of_the_unit() -> None:
    fleet = _setup(width=4)
    with pytest.raises(ConfigSchemaError) as refused:
        parse(
            "units:\n"
            "  local:\n"
            "    address: http://127.0.0.1:8080\n"
            "    model: qwen-small\n"
            "    width: 4\n",
            "ladder: [local]\nrider_slots: 2\n",
        )
    assert "rider_slots" in str(refused.value)
    assert "fleet.yaml" in str(refused.value)
    assert parse(fleet).units["local"].rider_slots == 0


def test_the_setup_reference_names_the_share() -> None:
    text = docgen.render_setup()
    assert "`units.rider_slots`" in text
