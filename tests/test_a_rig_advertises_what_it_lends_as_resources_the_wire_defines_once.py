"""A rig advertises what it lends as resources, and the wire defines them once.

A hello and a heartbeat carry, beside the legacy ``cards[]``, the resources a
rig lends: a discrete card (``gpu``), a device whose memory is the host's
(``unified``), host memory (``ram``) and host cores (``cpu``), on a host that
names its os, arch and version. The names, the closed sets and the rules are
:mod:`mcgyvr.hubwire`'s, and the hub imports them.

Held here: each closed set holds the values the hub takes, each once; the rig
agent's card rules are the resource's, by import, and the shipped schema's;
every rule :meth:`hubwire.Resource.validate`, :meth:`hubwire.Host.validate`
and :meth:`hubwire.ResourceReading.validate` keep refuses its own break and
names the field; an advert and a heartbeat fit by count, by ``(kind, index)``,
by card and by the kinds a rig names once (one unified device, its memory, its
cores); the legacy cards come out of a unified-only, a gpu-only and a mixed
advert, and the card readings out of a heartbeat's; each closed set is built
from its values' own names; and a standby unit is named and sized for every
kind.
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Any

import pytest

from mcgyvr import hubwire
from tests import rig_schema


def _gpu(index: int = 0, **changed: Any) -> hubwire.Resource:
    fields: dict[str, Any] = {
        "kind": hubwire.RESOURCE_GPU,
        "index": index,
        "name": f"Example Card {index}",
        "total_mb": 20_000 + index,
        "free_mb": 19_000,
        "cores": None,
        "bandwidth_gbps": 512.0,
        "bandwidth_figure": "estimate",
        "figure": "reading",
        "backend": "cuda",
    }
    return hubwire.Resource(**{**fields, **changed})


def _unified(index: int = 0, **changed: Any) -> hubwire.Resource:
    fields: dict[str, Any] = {
        "kind": hubwire.RESOURCE_UNIFIED,
        "index": index,
        "name": "Example Unified GPU",
        "total_mb": 40_000,
        "free_mb": None,
        "cores": None,
        "bandwidth_gbps": 300.0,
        "bandwidth_figure": "estimate",
        "figure": "estimate",
        "backend": "metal",
    }
    return hubwire.Resource(**{**fields, **changed})


def _ram(**changed: Any) -> hubwire.Resource:
    fields: dict[str, Any] = {
        "kind": hubwire.RESOURCE_RAM,
        "index": 0,
        "name": "host RAM",
        "total_mb": 30_000,
        "free_mb": 20_000,
        "cores": None,
        "bandwidth_gbps": None,
        "bandwidth_figure": None,
        "figure": "reading",
        "backend": "cpu",
    }
    return hubwire.Resource(**{**fields, **changed})


def _cpu(**changed: Any) -> hubwire.Resource:
    fields: dict[str, Any] = {
        "kind": hubwire.RESOURCE_CPU,
        "index": 0,
        "name": "CPU",
        "total_mb": 0,
        "free_mb": None,
        "cores": 6,
        "bandwidth_gbps": 50.0,
        "bandwidth_figure": "estimate",
        "figure": "estimate",
        "backend": "cpu",
    }
    return hubwire.Resource(**{**fields, **changed})


def _host(**changed: Any) -> hubwire.Host:
    fields: dict[str, Any] = {"os": "linux", "arch": "x86_64", "version": "1.2.3"}
    return hubwire.Host(**{**fields, **changed})


def _reading(
    kind: str = "gpu", index: int = 0, **changed: Any
) -> hubwire.ResourceReading:
    fields: dict[str, Any] = {"kind": kind, "index": index, "free_mb": 1}
    return hubwire.ResourceReading(**{**fields, **changed})


def _refused(field: str, check: Any) -> None:
    with pytest.raises(ValueError, match=rf"^{field}: "):
        check()


# --- the closed sets hold the values the hub takes --------------------------------


def test_the_closed_sets_hold_the_values_the_hub_takes() -> None:
    assert hubwire.RESOURCE_KINDS == ("gpu", "unified", "ram", "cpu")
    assert hubwire.RESOURCE_BACKENDS == ("cuda", "metal", "vulkan", "rocm", "cpu")
    assert hubwire.FIGURE_KINDS == ("estimate", "reading")
    assert (hubwire.FIGURE_ESTIMATE, hubwire.FIGURE_READING) == hubwire.FIGURE_KINDS
    assert hubwire.HOST_OS == ("linux", "darwin", "windows")
    assert hubwire.HOST_ARCH == ("x86_64", "arm64")
    kinds = (
        hubwire.RESOURCE_GPU,
        hubwire.RESOURCE_UNIFIED,
        hubwire.RESOURCE_RAM,
        hubwire.RESOURCE_CPU,
    )
    assert kinds == hubwire.RESOURCE_KINDS
    assert hubwire.CARD_KINDS == (hubwire.RESOURCE_GPU, hubwire.RESOURCE_UNIFIED)


@pytest.mark.parametrize(
    ("values", "names"),
    [
        (
            hubwire.RESOURCE_BACKENDS,
            (
                hubwire.BACKEND_CUDA,
                hubwire.BACKEND_METAL,
                hubwire.BACKEND_VULKAN,
                hubwire.BACKEND_ROCM,
                hubwire.BACKEND_CPU,
            ),
        ),
        (
            hubwire.HOST_OS,
            (hubwire.HOST_LINUX, hubwire.HOST_DARWIN, hubwire.HOST_WINDOWS),
        ),
        (hubwire.HOST_ARCH, (hubwire.ARCH_X86_64, hubwire.ARCH_ARM64)),
    ],
)
def test_each_closed_set_is_its_values_names_in_order(
    values: tuple[str, ...], names: tuple[str, ...]
) -> None:
    """A reader imports a value by its name, never by its place in the set:
    a reorder of the set cannot rename one."""
    assert names == values
    assert all(name is value for name, value in zip(names, values, strict=True))


def test_each_value_name_holds_its_value() -> None:
    assert (hubwire.BACKEND_CUDA, hubwire.BACKEND_METAL) == ("cuda", "metal")
    assert (hubwire.BACKEND_VULKAN, hubwire.BACKEND_ROCM) == ("vulkan", "rocm")
    assert hubwire.BACKEND_CPU == "cpu"
    assert (hubwire.HOST_LINUX, hubwire.HOST_DARWIN) == ("linux", "darwin")
    assert hubwire.HOST_WINDOWS == "windows"
    assert (hubwire.ARCH_X86_64, hubwire.ARCH_ARM64) == ("x86_64", "arm64")


def test_the_limits_are_the_ones_the_hub_takes() -> None:
    assert hubwire.MAX_RESOURCES == 32
    assert hubwire.MAX_CARDS == 16
    assert hubwire.MAX_RESOURCE_INDEX == 63
    assert hubwire.MAX_RESOURCE_CORES == 1024
    assert hubwire.MAX_BANDWIDTH_GBPS == 100_000.0
    assert type(hubwire.MAX_BANDWIDTH_GBPS) is float
    assert hubwire.RESOURCE_NAME_MAX == 128
    assert hubwire.HOST_VERSION_MAX == 64


@pytest.mark.parametrize(
    "values",
    [
        hubwire.RESOURCE_KINDS,
        hubwire.RESOURCE_BACKENDS,
        hubwire.FIGURE_KINDS,
        hubwire.HOST_OS,
        hubwire.HOST_ARCH,
    ],
)
def test_a_closed_set_holds_each_value_once_and_lower_case(
    values: tuple[str, ...],
) -> None:
    assert isinstance(values, tuple)
    assert len(set(values)) == len(values)
    assert all(v == v.lower() and v.strip() == v and v for v in values)


def test_the_fields_are_the_contracts_in_its_order() -> None:
    assert [f.name for f in dataclasses.fields(hubwire.Resource)] == [
        "kind",
        "index",
        "name",
        "total_mb",
        "free_mb",
        "cores",
        "ddr",
        "bandwidth_gbps",
        "bandwidth_figure",
        "figure",
        "backend",
    ]
    assert [f.name for f in dataclasses.fields(hubwire.ResourceReading)] == [
        "kind",
        "index",
        "free_mb",
    ]
    assert [f.name for f in dataclasses.fields(hubwire.Host)] == [
        "os",
        "arch",
        "version",
    ]


def test_a_resource_is_frozen_and_built_by_keyword() -> None:
    resource = _gpu()
    with pytest.raises(dataclasses.FrozenInstanceError):
        resource.index = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        hubwire.Resource("gpu", 0)  # type: ignore[call-arg]


def test_the_rig_agents_card_rules_are_the_resources_by_import() -> None:
    """A card reported as a resource and as a card is refused by neither or
    both: the rig agent's card rules are the wire's own objects."""
    from mcgyvr.rig import protocol

    assert protocol.CARD_NAME is hubwire.RESOURCE_NAME
    assert protocol.CARD_NAME_MAX is hubwire.RESOURCE_NAME_MAX
    assert protocol.MAX_MB is hubwire.RESOURCE_MAX_MB
    assert protocol.MAX_CARD_INDEX is hubwire.MAX_RESOURCE_INDEX
    assert protocol.MAX_CARDS is hubwire.MAX_CARDS


def test_the_card_rules_are_the_ones_the_shipped_schema_holds() -> None:
    schema = rig_schema.load(rig_schema.PROTOCOL)
    card = schema["$defs"]["CardReport"]["properties"]
    assert card["name"]["pattern"] == f"^{hubwire.RESOURCE_NAME.pattern}$"
    assert (card["name"]["minLength"], card["name"]["maxLength"]) == (
        1,
        hubwire.RESOURCE_NAME_MAX,
    )
    assert card["index"]["maximum"] == hubwire.MAX_RESOURCE_INDEX
    for field in ("vram_total_mb", "vram_free_mb"):
        assert (card[field]["minimum"], card[field]["maximum"]) == (
            0,
            hubwire.RESOURCE_MAX_MB,
        )
    cards = schema["$defs"]["HelloBody"]["properties"]["cards"]
    assert cards["maxItems"] == hubwire.MAX_CARDS


def _defs(name: str) -> dict[str, Any]:
    node: dict[str, Any] = rig_schema.load(rig_schema.PROTOCOL)["$defs"][name]
    return node


def _value(node: dict[str, Any]) -> dict[str, Any]:
    if "anyOf" in node:
        return next(b for b in node["anyOf"] if b.get("type") != "null")
    return node


def test_a_resources_fields_and_bounds_are_the_shipped_schemas() -> None:
    resource = _defs("Resource")
    props = resource["properties"]
    fields = dataclasses.fields(hubwire.Resource)
    assert set(props) == {f.name for f in fields}
    assert set(resource["required"]) == {
        f.name for f in fields if f.default is dataclasses.MISSING
    }
    assert tuple(props["kind"]["enum"]) == hubwire.RESOURCE_KINDS
    assert tuple(props["backend"]["enum"]) == hubwire.RESOURCE_BACKENDS
    assert tuple(props["figure"]["enum"]) == hubwire.FIGURE_KINDS
    assert tuple(_value(props["bandwidth_figure"])["enum"]) == hubwire.FIGURE_KINDS
    assert (props["index"]["minimum"], props["index"]["maximum"]) == (
        0,
        hubwire.MAX_RESOURCE_INDEX,
    )
    assert props["name"]["pattern"] == f"^(?:{hubwire.RESOURCE_NAME.pattern})$"
    assert props["name"]["maxLength"] == hubwire.RESOURCE_NAME_MAX
    assert props["total_mb"]["maximum"] == hubwire.RESOURCE_MAX_MB
    assert _value(props["free_mb"])["maximum"] == hubwire.RESOURCE_MAX_MB
    cores = _value(props["cores"])
    assert (cores["minimum"], cores["maximum"]) == (1, hubwire.MAX_RESOURCE_CORES)
    ddr = _value(props["ddr"])
    assert (ddr["minimum"], ddr["maximum"]) == (1, hubwire.MAX_RAM_DDR)
    bandwidth = _value(props["bandwidth_gbps"])
    assert (bandwidth["exclusiveMinimum"], bandwidth["maximum"]) == (
        0,
        hubwire.MAX_BANDWIDTH_GBPS,
    )


def test_a_readings_and_a_hosts_fields_are_the_shipped_schemas() -> None:
    reading = _defs("ResourceReading")["properties"]
    assert set(reading) == {f.name for f in dataclasses.fields(hubwire.ResourceReading)}
    assert tuple(reading["kind"]["enum"]) == hubwire.RESOURCE_KINDS
    assert reading["index"]["maximum"] == hubwire.MAX_RESOURCE_INDEX
    assert reading["free_mb"]["maximum"] == hubwire.RESOURCE_MAX_MB
    host = _defs("Host")["properties"]
    assert set(host) == {f.name for f in dataclasses.fields(hubwire.Host)}
    assert tuple(host["os"]["enum"]) == hubwire.HOST_OS
    assert tuple(host["arch"]["enum"]) == hubwire.HOST_ARCH
    assert host["version"]["maxLength"] == hubwire.HOST_VERSION_MAX
    assert host["version"]["pattern"] == f"^(?:{hubwire.RESOURCE_NAME.pattern})$"


def test_a_hello_and_a_heartbeat_carry_at_most_an_adverts_resources() -> None:
    hello = _defs("HelloBody")["properties"]
    beat = _defs("HeartbeatBody")["properties"]
    assert hello["resources"]["maxItems"] == hubwire.MAX_RESOURCES
    assert beat["resources"]["maxItems"] == hubwire.MAX_RESOURCES


def test_what_the_wire_validates_the_shipped_schema_takes() -> None:
    protocol = rig_schema.load(rig_schema.PROTOCOL)
    for resource in (_gpu(), _unified(), _ram(), _ram(ddr=4), _cpu()):
        resource.validate()
        body = dataclasses.asdict(resource)
        rig_schema.validate(body, protocol, "#/$defs/Resource")
    rig_schema.validate(
        dataclasses.asdict(_reading("unified", 1, free_mb=3)),
        protocol,
        "#/$defs/ResourceReading",
    )
    rig_schema.validate(dataclasses.asdict(_host()), protocol, "#/$defs/Host")


def test_a_ddr_generation_goes_through_the_shipped_schema_and_back() -> None:
    protocol = rig_schema.load(rig_schema.PROTOCOL)
    body = json.loads(json.dumps(dataclasses.asdict(_ram(ddr=5))))
    rig_schema.validate(body, protocol, "#/$defs/Resource")
    back = hubwire.Resource(**body)
    back.validate()
    assert back.ddr == 5
    with pytest.raises(rig_schema.SchemaError):
        rig_schema.validate(
            {**body, "ddr": hubwire.MAX_RAM_DDR + 1}, protocol, "#/$defs/Resource"
        )


# --- a resource -------------------------------------------------------------------


@pytest.mark.parametrize("resource", [_gpu(), _unified(), _ram(), _cpu()])
def test_a_resource_of_each_kind_validates(resource: hubwire.Resource) -> None:
    resource.validate()


@pytest.mark.parametrize("kind", ["npu", "GPU", "", None, 0])
def test_a_resource_names_a_kind_the_wire_holds(kind: Any) -> None:
    _refused("kind", _gpu(kind=kind).validate)


@pytest.mark.parametrize("index", [-1, 64, True, 1.0, "0", None])
def test_a_resource_index_is_a_whole_number_0_to_63(index: Any) -> None:
    _refused("index", dataclasses.replace(_gpu(), index=index).validate)


@pytest.mark.parametrize(
    "name",
    ["", "x" * 129, "card\nname", "card\u202ename", "card\x85name", "\ud800", 7, None],
)
def test_a_resource_name_is_1_to_128_printable_characters(name: Any) -> None:
    _refused("name", _gpu(name=name).validate)


@pytest.mark.parametrize(
    "resource",
    [
        _gpu(total_mb=0, free_mb=0),
        _unified(total_mb=0),
        _ram(total_mb=0, free_mb=0),
        _gpu(total_mb=hubwire.RESOURCE_MAX_MB + 1),
        _gpu(total_mb=1.5),
        _gpu(total_mb=True),
        _gpu(total_mb=None),
        _cpu(total_mb=1024),
    ],
)
def test_a_resource_lends_at_least_a_mib_and_cpu_lends_none(
    resource: hubwire.Resource,
) -> None:
    _refused("total_mb", resource.validate)


@pytest.mark.parametrize("free_mb", [-1, 20_001, False, 1.0, "1"])
def test_a_resources_free_mib_is_none_or_within_what_it_lends(free_mb: Any) -> None:
    _refused("free_mb", _gpu(free_mb=free_mb).validate)


@pytest.mark.parametrize(
    "resource",
    [
        _cpu(cores=None),
        _cpu(cores=0),
        _cpu(cores=hubwire.MAX_RESOURCE_CORES + 1),
        _cpu(cores=True),
        _gpu(cores=8),
        _ram(cores=4),
        _unified(cores=1),
    ],
)
def test_only_a_cpu_resource_lends_cores_1_to_1024(resource: hubwire.Resource) -> None:
    _refused("cores", resource.validate)


@pytest.mark.parametrize(
    "resource",
    [
        _gpu(ddr=4),
        _unified(ddr=5),
        _cpu(ddr=4),
        _ram(ddr=0),
        _ram(ddr=hubwire.MAX_RAM_DDR + 1),
        _ram(ddr=4.0),
        _ram(ddr=True),
        _ram(ddr="4"),
    ],
)
def test_only_host_memory_names_a_ddr_generation_1_to_its_most(
    resource: hubwire.Resource,
) -> None:
    _refused("ddr", resource.validate)


@pytest.mark.parametrize("ddr", [None, 1, 3, 4, 5, hubwire.MAX_RAM_DDR])
def test_host_memory_of_any_or_an_unknown_ddr_generation_validates(
    ddr: int | None,
) -> None:
    _ram(ddr=ddr).validate()


def test_only_a_unified_device_shares_the_hosts_memory() -> None:
    assert [k for k in hubwire.RESOURCE_KINDS if hubwire.shares_ram(k)] == ["unified"]
    assert not hubwire.shares_ram("npu")


@pytest.mark.parametrize(
    "bandwidth",
    [0.0, -1.0, math.inf, math.nan, 10**400, 100_000.5, True, "360"],
)
def test_a_bandwidth_is_none_or_a_number_over_0_to_its_most(bandwidth: Any) -> None:
    _refused("bandwidth_gbps", _gpu(bandwidth_gbps=bandwidth).validate)


@pytest.mark.parametrize("figure", ["measured", "Reading", None])
def test_a_memory_figure_is_an_estimate_or_a_reading(figure: Any) -> None:
    _refused("figure", _gpu(figure=figure).validate)


@pytest.mark.parametrize(
    "resource",
    [
        _gpu(bandwidth_figure=None),
        _gpu(bandwidth_figure="measured"),
        _gpu(bandwidth_gbps=None, bandwidth_figure="estimate"),
        _ram(bandwidth_figure="reading"),
    ],
)
def test_a_bandwidth_says_what_it_is_and_only_a_bandwidth_does(
    resource: hubwire.Resource,
) -> None:
    _refused("bandwidth_figure", resource.validate)


def test_memory_and_bandwidth_each_say_what_they_are() -> None:
    """A device's memory may be read while its bandwidth is an estimate, and
    the other way round: each number names its own figure."""
    _gpu(figure="reading", bandwidth_figure="estimate").validate()
    _unified(figure="estimate", bandwidth_figure="reading").validate()


@pytest.mark.parametrize(
    "resource",
    [
        _gpu(backend="opencl"),
        _gpu(backend="CUDA"),
        _gpu(backend="cpu"),
        _unified(backend="cpu"),
        _ram(backend="cuda"),
        _cpu(backend="metal"),
    ],
)
def test_host_memory_and_cores_compute_on_cpu_and_a_card_never_does(
    resource: hubwire.Resource,
) -> None:
    _refused("backend", resource.validate)


@pytest.mark.parametrize(
    "resource",
    [
        _gpu(index=hubwire.MAX_RESOURCE_INDEX),
        _gpu(total_mb=1, free_mb=0),
        _gpu(name="x" * hubwire.RESOURCE_NAME_MAX),
        _gpu(name="\u041a\u0430\u0440\u0442\u0430 \xfc \u663e\u5361"),
        _gpu(total_mb=hubwire.RESOURCE_MAX_MB, free_mb=hubwire.RESOURCE_MAX_MB),
        _gpu(free_mb=None, bandwidth_gbps=None, bandwidth_figure=None),
        _gpu(bandwidth_gbps=448, backend="vulkan"),
        _gpu(bandwidth_gbps=hubwire.MAX_BANDWIDTH_GBPS, backend="rocm"),
        _unified(backend="vulkan"),
        _cpu(cores=1, free_mb=0),
        _cpu(cores=hubwire.MAX_RESOURCE_CORES),
        _ram(index=3, figure="estimate"),
    ],
)
def test_a_resource_at_each_rules_edge_validates(resource: hubwire.Resource) -> None:
    resource.validate()


# --- an advert fits -------------------------------------------------------------


def _unfit(resources: list[hubwire.Resource], why: str) -> None:
    with pytest.raises(ValueError, match=rf"^resources: {why}"):
        hubwire.resources_fit(resources)


def test_an_advert_fits_up_to_its_most_resources() -> None:
    """Its widest is every card a hello takes, one of them unified, the
    host's memory and its cores; the count bound refuses an advert longer
    still before any other."""
    cards = hubwire.MAX_CARDS
    widest = [*(_gpu(i) for i in range(cards - 1)), _ram(), _cpu()]
    widest += [_unified(cards - 1)]
    hubwire.resources_fit(widest)
    hubwire.resources_fit([])
    _unfit([_gpu(i) for i in range(hubwire.MAX_RESOURCES + 1)], "more than 32")


def test_an_advert_reports_no_more_cards_than_a_hello_takes() -> None:
    hubwire.resources_fit([_gpu(i) for i in range(hubwire.MAX_CARDS)])
    _unfit([_gpu(i) for i in range(hubwire.MAX_CARDS + 1)], "more than 16 cards")


def test_an_advert_names_each_kind_and_index_once() -> None:
    hubwire.resources_fit([_gpu(0), _gpu(1), _ram(), _cpu()])
    _unfit([_gpu(0), _gpu(0, name="Another Card")], "a kind and index twice")


def test_a_card_index_is_one_cards_whatever_its_kind() -> None:
    """A gpu and a unified resource each become a legacy card at their index,
    so the two kinds share the card indexes."""
    hubwire.resources_fit([_gpu(0), _unified(1)])
    _unfit([_gpu(0), _unified(0)], "a card index twice")


def test_an_advert_lends_the_hosts_memory_once_and_its_cores_once() -> None:
    _unfit([_ram(), _ram(index=1)], "more than one ram")
    _unfit([_cpu(), _cpu(index=1)], "more than one cpu")


def test_the_kinds_a_rig_names_once_are_its_unified_device_memory_and_cores() -> None:
    assert hubwire.ONE_PER_RIG == (
        hubwire.RESOURCE_UNIFIED,
        hubwire.RESOURCE_RAM,
        hubwire.RESOURCE_CPU,
    )
    assert hubwire.RESOURCE_GPU not in hubwire.ONE_PER_RIG


def test_an_advert_names_at_most_one_unified_device() -> None:
    """A host has one memory to share, so a rig names one device whose
    memory is the host's; discrete cards beside it are any number."""
    hubwire.resources_fit([_unified(0), _gpu(1), _gpu(2), _ram(), _cpu()])
    _unfit([_unified(0), _unified(1)], "more than one unified")
    _unfit([_gpu(0), _unified(1), _unified(2, name="Another")], "more than one unified")
    with pytest.raises(ValueError, match=r"^resources: more than one unified"):
        hubwire.cards_from_resources([_unified(0), _unified(1)])


def test_an_advert_fits_only_when_each_resource_validates() -> None:
    with pytest.raises(ValueError, match=r"^kind: "):
        hubwire.resources_fit([_gpu(kind=["gpu"])])


# --- the legacy cards ------------------------------------------------------------


def test_a_unified_only_advert_is_one_card_all_free_until_it_is_read() -> None:
    advert = [_unified(), _ram(), _cpu()]
    assert hubwire.cards_from_resources(advert) == [
        {
            "index": 0,
            "name": "Example Unified GPU",
            "vram_total_mb": 40_000,
            "vram_free_mb": 40_000,
        }
    ]


def test_a_gpu_only_advert_is_its_cards_by_index() -> None:
    advert = [_gpu(1, free_mb=9_000), _gpu(0)]
    assert hubwire.cards_from_resources(advert) == [
        {
            "index": 0,
            "name": "Example Card 0",
            "vram_total_mb": 20_000,
            "vram_free_mb": 19_000,
        },
        {
            "index": 1,
            "name": "Example Card 1",
            "vram_total_mb": 20_001,
            "vram_free_mb": 9_000,
        },
    ]


def test_a_mixed_advert_is_its_gpu_and_unified_cards_and_nothing_else() -> None:
    advert = [_cpu(), _gpu(2), _ram(), _unified(0, free_mb=30_000)]
    cards = hubwire.cards_from_resources(advert)
    assert [(c["index"], c["vram_free_mb"]) for c in cards] == [
        (0, 30_000),
        (2, 19_000),
    ]
    assert hubwire.cards_from_resources([_ram(), _cpu()]) == []


def test_the_legacy_cards_are_the_shape_the_published_schema_takes() -> None:
    protocol = rig_schema.load(rig_schema.PROTOCOL)
    for card in hubwire.cards_from_resources([_gpu(0), _unified(1), _gpu(2)]):
        rig_schema.validate(card, protocol, "#/$defs/CardReport")


def test_no_legacy_card_is_made_from_an_advert_that_does_not_fit() -> None:
    _refused(
        "backend",
        lambda: hubwire.cards_from_resources([_unified(backend="cpu")]),
    )
    with pytest.raises(ValueError, match=r"^resources: a card index twice"):
        hubwire.cards_from_resources([_gpu(0), _unified(0)])


@pytest.mark.parametrize(
    "char",
    [
        "\u061c",
        "\u200b",
        "\u200e",
        "\u200f",
        "\u2028",
        "\u2029",
        "\u2060",
        "\u2064",
        "\ufeff",
    ],
)
def test_a_name_and_a_version_hold_no_invisible_format_character(char: str) -> None:
    _refused("name", _gpu(name=f"Example{char}Card").validate)
    _refused("version", _host(version=f"1.2{char}").validate)


# --- a heartbeat's readings ---------------------------------------------------------


def test_a_reading_names_its_resource_and_the_mib_free_now() -> None:
    _reading("unified", 0, free_mb=0).validate()
    _reading(
        "ram", hubwire.MAX_RESOURCE_INDEX, free_mb=hubwire.RESOURCE_MAX_MB
    ).validate()


@pytest.mark.parametrize("kind", ["disk", None, "cpu"])
def test_a_reading_is_of_a_memory_resource(kind: Any) -> None:
    _refused("kind", _reading(kind).validate)


@pytest.mark.parametrize("index", [-1, 64, True])
def test_a_readings_index_is_a_resources(index: Any) -> None:
    _refused("index", _reading(index=index).validate)


@pytest.mark.parametrize("free_mb", [-1, hubwire.RESOURCE_MAX_MB + 1, None, True])
def test_a_readings_free_mib_is_a_whole_number_within_the_most(free_mb: Any) -> None:
    _refused("free_mb", _reading(free_mb=free_mb).validate)


def test_a_heartbeat_fits_by_the_adverts_rules() -> None:
    hubwire.readings_fit([_reading("gpu", 0), _reading("unified", 1), _reading("ram")])
    for readings, why in (
        ([_reading("gpu", 0), _reading("gpu", 0)], "a kind and index twice"),
        ([_reading("gpu", 0), _reading("unified", 0)], "a card index twice"),
        ([_reading("gpu", i) for i in range(17)], "more than 16 cards"),
        ([_reading("ram", 0), _reading("ram", 1)], "more than one ram"),
        ([_reading("unified", 0), _reading("unified", 1)], "more than one unified"),
    ):
        with pytest.raises(ValueError, match=rf"^resources: {why}"):
            hubwire.readings_fit(readings)


def test_a_heartbeats_card_readings_are_its_gpu_and_unified_readings_by_index() -> None:
    readings = [
        _reading("ram", 0, free_mb=5),
        _reading("gpu", 2, free_mb=7),
        _reading("unified", 0, free_mb=9),
    ]
    assert hubwire.card_readings_from(readings) == [
        {"index": 0, "vram_free_mb": 9},
        {"index": 2, "vram_free_mb": 7},
    ]
    protocol = rig_schema.load(rig_schema.PROTOCOL)
    for card in hubwire.card_readings_from(readings):
        rig_schema.validate(card, protocol, "#/$defs/CardReading")
    with pytest.raises(ValueError, match=r"^resources: a card index twice"):
        hubwire.card_readings_from([_reading("gpu", 0), _reading("unified", 0)])


# --- the host -------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [_host(os=os, arch=arch) for os in hubwire.HOST_OS for arch in hubwire.HOST_ARCH]
    + [_host(version="x" * hubwire.HOST_VERSION_MAX)],
)
def test_a_host_of_each_os_and_arch_validates(host: hubwire.Host) -> None:
    host.validate()


@pytest.mark.parametrize("os", ["freebsd", "Darwin", None])
def test_a_host_names_an_os_the_wire_holds(os: Any) -> None:
    _refused("os", _host(os=os).validate)


@pytest.mark.parametrize("arch", ["aarch64", "amd64", None])
def test_a_host_names_an_arch_the_wire_holds(arch: Any) -> None:
    _refused("arch", _host(arch=arch).validate)


@pytest.mark.parametrize("version", ["", "x" * 65, "6.8\n", "\udc80", 6])
def test_a_hosts_version_is_1_to_64_printable_characters(version: Any) -> None:
    _refused("version", _host(version=version).validate)


# --- standby is counted in units named per kind -----------------------------------


def test_every_kind_has_one_standby_unit_and_only_names_it() -> None:
    assert dict(hubwire.STANDBY_UNITS) == {
        "gpu": "card",
        "unified": "card",
        "ram": "16GiB",
        "cpu": "8cores",
    }
    assert tuple(hubwire.STANDBY_UNITS) == hubwire.RESOURCE_KINDS
    with pytest.raises(TypeError):
        hubwire.STANDBY_UNITS["ram"] = "1GiB"  # type: ignore[index]


def test_every_kinds_standby_unit_has_the_size_its_name_says() -> None:
    """A hub pays standby per unit of these sizes: a card, 16384 MiB of host
    memory, 8 cores; the names are made from them."""
    assert dict(hubwire.STANDBY_UNIT_SIZE) == {
        "gpu": 1,
        "unified": 1,
        "ram": 16384,
        "cpu": 8,
    }
    assert tuple(hubwire.STANDBY_UNIT_SIZE) == tuple(hubwire.STANDBY_UNITS)
    assert hubwire.MB_PER_GIB == 1024
    ram = hubwire.STANDBY_UNIT_SIZE[hubwire.RESOURCE_RAM] // hubwire.MB_PER_GIB
    assert hubwire.STANDBY_UNITS[hubwire.RESOURCE_RAM] == f"{ram}GiB"
    cores = hubwire.STANDBY_UNIT_SIZE[hubwire.RESOURCE_CPU]
    assert hubwire.STANDBY_UNITS[hubwire.RESOURCE_CPU] == f"{cores}cores"
    with pytest.raises(TypeError):
        hubwire.STANDBY_UNIT_SIZE["ram"] = 1  # type: ignore[index]


# --- the least a resource lends to count --------------------------------------------


def test_the_lending_floor_is_named_per_kind() -> None:
    assert dict(hubwire.LEND_FLOOR_MB) == {"gpu": 2048, "unified": 4096, "ram": 8192}
    assert set(hubwire.LEND_FLOOR_MB) == set(hubwire.RESOURCE_KINDS) - {"cpu"}
    assert hubwire.LEND_FLOOR_CORES == 2
    assert hubwire.RAM_DDR_MIN == 4


@pytest.mark.parametrize(
    ("kind", "total_mb", "cores", "lent"),
    [
        ("gpu", 2048, None, True),
        ("gpu", 2047, None, False),
        ("gpu", 1, None, False),
        ("unified", 4096, None, True),
        ("unified", 4095, None, False),
        ("ram", 8192, None, True),
        ("ram", 8191, None, False),
        ("ram", 4096, None, False),
        ("ram", 1, None, False),
        ("cpu", 0, 2, True),
        ("cpu", 0, 1, False),
        ("cpu", 0, None, False),
    ],
)
def test_a_resource_counts_as_lent_only_at_its_kinds_floor(
    kind: str, total_mb: int, cores: int | None, lent: bool
) -> None:
    resource = hubwire.Resource(
        kind=kind,
        index=0,
        name="an invented device",
        total_mb=total_mb,
        cores=cores,
        figure="reading",
        backend="cpu" if kind == "cpu" else "cuda",
    )
    assert hubwire.counts_as_lent(resource) is lent


@pytest.mark.parametrize(
    ("total_mb", "ddr", "lent"),
    [
        (8192, None, True),
        (16384, 3, False),
        (8192, 4, True),
        (8191, 5, False),
        (hubwire.RESOURCE_MAX_MB, 1, False),
        (8192, hubwire.MAX_RAM_DDR, True),
    ],
)
def test_host_memory_counts_as_lent_only_when_ddr4_or_newer_or_unknown(
    total_mb: int, ddr: int | None, lent: bool
) -> None:
    resource = _ram(total_mb=total_mb, free_mb=None, ddr=ddr)
    resource.validate()
    assert hubwire.counts_as_lent(resource) is lent


# --- the RPC protocol a split model's workers speak -------------------------------


def test_the_rpc_protocol_field_is_one_name() -> None:
    assert hubwire.RPC_PROTO_FIELD == "rpc_proto"
    assert hubwire.RPC_PROTO_MAX == 255
    assert [f.name for f in dataclasses.fields(hubwire.RpcProto)] == ["major", "minor"]


@pytest.mark.parametrize("proto", [(0, 0), (8, 0), (8, 12), (255, 255)])
def test_an_rpc_protocol_of_whole_numbers_validates(proto: tuple[int, int]) -> None:
    hubwire.RpcProto(major=proto[0], minor=proto[1]).validate()


@pytest.mark.parametrize(
    ("major", "minor", "field"),
    [
        (-1, 0, "major"),
        (True, 0, "major"),
        (8.0, 0, "major"),
        ("8", 0, "major"),
        (256, 0, "major"),
        (8, -1, "minor"),
        (8, None, "minor"),
        (8, False, "minor"),
        (8, 10**9, "minor"),
    ],
)
def test_each_part_of_an_rpc_protocol_is_a_whole_number_of_0_to_255(
    major: Any, minor: Any, field: str
) -> None:
    _refused(field, hubwire.RpcProto(major=major, minor=minor).validate)


@pytest.mark.parametrize(
    ("head", "worker", "compatible"),
    [
        ((8, 0), (8, 0), True),
        ((8, 2), (8, 1), True),
        ((8, 2), (8, 0), True),
        ((8, 1), (8, 2), False),
        ((8, 0), (7, 0), False),
        ((7, 5), (8, 0), False),
        ((9, 9), (8, 9), False),
    ],
)
def test_a_head_takes_a_worker_of_its_major_and_no_newer_minor(
    head: tuple[int, int], worker: tuple[int, int], compatible: bool
) -> None:
    """llama.cpp's head refuses a worker of another major or a newer minor."""

    def proto(p: tuple[int, int]) -> hubwire.RpcProto:
        return hubwire.RpcProto(major=p[0], minor=p[1])

    assert hubwire.rpc_compatible(proto(head), proto(worker)) is compatible
