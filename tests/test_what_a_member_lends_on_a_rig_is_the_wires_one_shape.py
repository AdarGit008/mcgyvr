"""What a member lends on a rig is the wire's one shape.

A member sets on the hub what one rig lends: cards whole (every card, some,
or none), host memory in MiB and host cores. The hub sends it in the hello's
ack (:data:`hubwire.LENDING_FIELD`) and the rig's agent lends that; the shape
and its rules are :class:`hubwire.Lending`'s, and the hub imports them.

Held here: the field name and the fields; every rule :meth:`Lending.validate`
keeps refuses its own break and names the field; memory and cores are 0 or at
least their lending floor, never between; and the shipped schema's ``Lending``
carries the same fields and bounds, takes what validates and refuses what
does not.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from mcgyvr import hubwire
from tests import rig_schema

_RAM_FLOOR = hubwire.LEND_FLOOR_MB[hubwire.RESOURCE_RAM]


def _lending(**changed: Any) -> hubwire.Lending:
    fields: dict[str, Any] = {"cards": (0, 2), "ram_mb": 16_384, "cpu_cores": 4}
    return hubwire.Lending(**{**fields, **changed})


def _refused(field: str, lending: hubwire.Lending) -> None:
    with pytest.raises(ValueError, match=rf"^{field}: "):
        lending.validate()


def test_the_field_and_the_fields_are_one_name_each() -> None:
    assert hubwire.LENDING_FIELD == "lending"
    assert [f.name for f in dataclasses.fields(hubwire.Lending)] == [
        "cards",
        "ram_mb",
        "cpu_cores",
    ]


def test_a_lending_is_frozen_and_built_by_keyword() -> None:
    lending = _lending()
    with pytest.raises(dataclasses.FrozenInstanceError):
        lending.ram_mb = 0  # type: ignore[misc]
    with pytest.raises(TypeError):
        hubwire.Lending(None, 0, 0)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "lending",
    [
        _lending(),
        _lending(cards=None),
        _lending(cards=()),
        _lending(cards=tuple(range(hubwire.MAX_CARDS))),
        _lending(cards=(hubwire.MAX_RESOURCE_INDEX,)),
        _lending(ram_mb=0, cpu_cores=0),
        _lending(ram_mb=_RAM_FLOOR, cpu_cores=hubwire.LEND_FLOOR_CORES),
        _lending(ram_mb=hubwire.RESOURCE_MAX_MB, cpu_cores=hubwire.MAX_RESOURCE_CORES),
    ],
)
def test_a_lending_at_each_rules_edge_validates(lending: hubwire.Lending) -> None:
    lending.validate()


@pytest.mark.parametrize(
    "cards",
    [
        [0, 1],
        tuple(range(hubwire.MAX_CARDS + 1)),
        (-1,),
        (hubwire.MAX_RESOURCE_INDEX + 1,),
        (True,),
        (1.0,),
        ("0",),
        (3, 3),
        "01",
    ],
)
def test_the_cards_lent_are_none_or_at_most_16_distinct_card_indexes(
    cards: Any,
) -> None:
    _refused("cards", _lending(cards=cards))


@pytest.mark.parametrize(
    "ram_mb",
    [1, _RAM_FLOOR - 1, hubwire.RESOURCE_MAX_MB + 1, -1, True, 8192.0, None, "8192"],
)
def test_host_memory_lent_is_0_or_from_its_floor(ram_mb: Any) -> None:
    _refused("ram_mb", _lending(ram_mb=ram_mb))


@pytest.mark.parametrize(
    "cpu_cores",
    [1, hubwire.MAX_RESOURCE_CORES + 1, -1, False, 2.0, None],
)
def test_cores_lent_are_0_or_from_their_floor(cpu_cores: Any) -> None:
    _refused("cpu_cores", _lending(cpu_cores=cpu_cores))


def test_what_a_lending_lends_counts_as_lent() -> None:
    """An amount the wire takes is never one the floor turns to nothing."""
    ram = hubwire.Resource(
        kind=hubwire.RESOURCE_RAM,
        index=0,
        name="an invented host's memory",
        total_mb=_lending(ram_mb=_RAM_FLOOR).ram_mb,
        figure=hubwire.FIGURE_READING,
        backend=hubwire.BACKEND_CPU,
    )
    cpu = hubwire.Resource(
        kind=hubwire.RESOURCE_CPU,
        index=0,
        name="an invented host's cores",
        total_mb=0,
        cores=_lending(cpu_cores=hubwire.LEND_FLOOR_CORES).cpu_cores,
        figure=hubwire.FIGURE_READING,
        backend=hubwire.BACKEND_CPU,
    )
    assert hubwire.counts_as_lent(ram) and hubwire.counts_as_lent(cpu)


# --- the shipped schema -------------------------------------------------------------


def _schema() -> dict[str, Any]:
    return rig_schema.load(rig_schema.PROTOCOL)


def _body(lending: hubwire.Lending) -> dict[str, Any]:
    body = dataclasses.asdict(lending)
    if body["cards"] is not None:
        body["cards"] = list(body["cards"])
    return body


def test_the_hellos_ack_carries_a_lending_in_the_shipped_schema() -> None:
    ack = _schema()["$defs"]["AckBody"]["properties"]
    assert {"$ref": "#/$defs/Lending"} in ack[hubwire.LENDING_FIELD]["anyOf"]
    assert hubwire.LENDING_FIELD not in _schema()["$defs"]["AckBody"].get(
        "required", []
    )


def test_a_lendings_fields_and_bounds_are_the_shipped_schemas() -> None:
    node = _schema()["$defs"]["Lending"]
    props = node["properties"]
    assert list(props) == sorted(f.name for f in dataclasses.fields(hubwire.Lending))
    assert node["required"] == [f.name for f in dataclasses.fields(hubwire.Lending)]
    cards = next(b for b in props["cards"]["anyOf"] if b.get("type") == "array")
    assert cards["maxItems"] == hubwire.MAX_CARDS
    assert (cards["items"]["minimum"], cards["items"]["maximum"]) == (
        0,
        hubwire.MAX_RESOURCE_INDEX,
    )
    for field, floor, most in (
        ("ram_mb", _RAM_FLOOR, hubwire.RESOURCE_MAX_MB),
        ("cpu_cores", hubwire.LEND_FLOOR_CORES, hubwire.MAX_RESOURCE_CORES),
    ):
        none, lent = props[field]["anyOf"]
        assert none["const"] == 0
        assert (lent["minimum"], lent["maximum"]) == (floor, most)


@pytest.mark.parametrize(
    "lending",
    [
        _lending(),
        _lending(cards=None, ram_mb=0, cpu_cores=0),
        _lending(cards=(), ram_mb=_RAM_FLOOR, cpu_cores=hubwire.LEND_FLOOR_CORES),
    ],
)
def test_what_the_wire_validates_the_shipped_schema_takes(
    lending: hubwire.Lending,
) -> None:
    lending.validate()
    rig_schema.validate(_body(lending), _schema(), "#/$defs/Lending")
    ack = {"rig_id": "rig-1", hubwire.LENDING_FIELD: _body(lending)}
    rig_schema.validate(ack, _schema(), "#/$defs/AckBody")


@pytest.mark.parametrize(
    "lending",
    [
        _lending(ram_mb=_RAM_FLOOR - 1),
        _lending(cpu_cores=1),
        _lending(cards=(hubwire.MAX_RESOURCE_INDEX + 1,)),
        _lending(cards=tuple(range(hubwire.MAX_CARDS + 1))),
    ],
)
def test_what_the_wire_refuses_by_a_bound_the_shipped_schema_refuses(
    lending: hubwire.Lending,
) -> None:
    with pytest.raises(ValueError):
        lending.validate()
    with pytest.raises(rig_schema.SchemaError):
        rig_schema.validate(_body(lending), _schema(), "#/$defs/Lending")
