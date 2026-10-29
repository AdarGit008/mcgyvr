"""A rig advertises what it lends as resources, and the wire defines them once.

A hello and a heartbeat carry, beside the legacy ``cards[]``, the resources a
rig lends: a discrete card (``gpu``), a device whose memory is the host's
(``unified``), host memory (``ram``) and host cores (``cpu``). The names, the
closed sets and the rules a resource keeps are :mod:`mcgyvr.hubwire`'s; the
hub mirrors them in its own types until it imports them.

Held here: each closed set is the one the plan fixes and holds no value twice;
a resource's name and memory follow the card's published rules; every rule
:meth:`hubwire.Resource.validate` keeps refuses its own break and names the
field; an advert fits by count and by ``(kind, index)``, and a card index is
one card's whatever its kind; the legacy cards come out of a unified-only, a
gpu-only and a mixed advert; and a standby unit is named for every kind.
"""

from __future__ import annotations

import dataclasses
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
        "total_mb": 12_000 + index,
        "free_mb": 11_000,
        "cores": None,
        "shared_with_ram": False,
        "bandwidth_gbps": 360.0,
        "figure": "reading",
        "backend": "cuda",
    }
    return hubwire.Resource(**{**fields, **changed})


def _unified(index: int = 0, **changed: Any) -> hubwire.Resource:
    fields: dict[str, Any] = {
        "kind": hubwire.RESOURCE_UNIFIED,
        "index": index,
        "name": "Example Unified GPU",
        "total_mb": 49_152,
        "free_mb": None,
        "cores": None,
        "shared_with_ram": True,
        "bandwidth_gbps": 400.0,
        "figure": "estimate",
        "backend": "metal",
    }
    return hubwire.Resource(**{**fields, **changed})


def _ram(**changed: Any) -> hubwire.Resource:
    fields: dict[str, Any] = {
        "kind": hubwire.RESOURCE_RAM,
        "index": 0,
        "name": "host RAM",
        "total_mb": 32_768,
        "free_mb": 20_000,
        "cores": None,
        "shared_with_ram": False,
        "bandwidth_gbps": None,
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
        "cores": 8,
        "shared_with_ram": False,
        "bandwidth_gbps": 60.0,
        "figure": "estimate",
        "backend": "cpu",
    }
    return hubwire.Resource(**{**fields, **changed})


# --- the closed sets are the plan's ---------------------------------------------


def test_the_closed_sets_are_the_ones_the_plan_fixes() -> None:
    assert hubwire.RESOURCE_KINDS == ("gpu", "unified", "ram", "cpu")
    assert hubwire.RESOURCE_BACKENDS == ("cuda", "metal", "vulkan", "rocm", "cpu")
    assert hubwire.FIGURE_KINDS == ("estimate", "reading")
    assert hubwire.HOST_OS == ("linux", "darwin", "windows")
    assert hubwire.HOST_ARCH == ("x86_64", "arm64")
    assert hubwire.MAX_RESOURCES == 32
    kinds = (
        hubwire.RESOURCE_GPU,
        hubwire.RESOURCE_UNIFIED,
        hubwire.RESOURCE_RAM,
        hubwire.RESOURCE_CPU,
    )
    assert kinds == hubwire.RESOURCE_KINDS
    assert hubwire.CARD_KINDS == (hubwire.RESOURCE_GPU, hubwire.RESOURCE_UNIFIED)


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
        "shared_with_ram",
        "bandwidth_gbps",
        "figure",
        "backend",
    ]


def test_a_resource_is_frozen_and_built_by_keyword() -> None:
    resource = _gpu()
    with pytest.raises(dataclasses.FrozenInstanceError):
        resource.index = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        hubwire.Resource("gpu", 0)  # type: ignore[misc]


def test_a_resource_name_and_memory_follow_the_cards_published_rules() -> None:
    """A resource's name is shown where a card's is and its memory is counted
    as a card's: the shipped schema's card rules are the resource's."""
    card = rig_schema.load(rig_schema.PROTOCOL)["$defs"]["CardReport"]["properties"]
    assert card["name"]["pattern"] == f"^{hubwire.RESOURCE_NAME.pattern}$"
    assert card["name"]["maxLength"] == hubwire.RESOURCE_NAME_MAX
    assert card["name"]["minLength"] == 1
    for field in ("vram_total_mb", "vram_free_mb"):
        assert (card[field]["minimum"], card[field]["maximum"]) == (
            0,
            hubwire.RESOURCE_MAX_MB,
        )


def test_the_rig_protocols_card_rules_are_the_resources() -> None:
    """The rig agent's card name and memory bound are the same rules: a card
    reported as a resource and as a card is refused by neither or both."""
    from mcgyvr.rig import protocol

    assert protocol.CARD_NAME.pattern == hubwire.RESOURCE_NAME.pattern
    assert protocol.CARD_NAME_MAX == hubwire.RESOURCE_NAME_MAX
    assert protocol.MAX_MB == hubwire.RESOURCE_MAX_MB


# --- every validator ------------------------------------------------------------


@pytest.mark.parametrize("resource", [_gpu(), _unified(), _ram(), _cpu()])
def test_a_resource_of_each_kind_validates(resource: hubwire.Resource) -> None:
    resource.validate()


@pytest.mark.parametrize(
    ("resource", "field"),
    [
        (_gpu(kind="npu"), "kind"),
        (_gpu(kind="GPU"), "kind"),
        (_gpu(index=-1), "index"),
        (_gpu(index=True), "index"),
        (_gpu(index=1.0), "index"),
        (_gpu(name=""), "name"),
        (_gpu(name="x" * 129), "name"),
        (_gpu(name="card\nname"), "name"),
        (_gpu(name="card‮name"), "name"),
        (_gpu(name="card\x85name"), "name"),
        (_gpu(name=7), "name"),
        (_gpu(total_mb=-1), "total_mb"),
        (_gpu(total_mb=hubwire.RESOURCE_MAX_MB + 1), "total_mb"),
        (_gpu(total_mb=1.5), "total_mb"),
        (_gpu(free_mb=-1), "free_mb"),
        (_gpu(free_mb=12_001), "free_mb"),
        (_gpu(free_mb=False), "free_mb"),
        (_cpu(total_mb=1024), "total_mb"),
        (_cpu(cores=None), "cores"),
        (_cpu(cores=0), "cores"),
        (_cpu(cores=True), "cores"),
        (_gpu(cores=8), "cores"),
        (_ram(cores=4), "cores"),
        (_unified(cores=1), "cores"),
        (_unified(shared_with_ram=False), "shared_with_ram"),
        (_gpu(shared_with_ram=True), "shared_with_ram"),
        (_ram(shared_with_ram=True), "shared_with_ram"),
        (_cpu(shared_with_ram=True), "shared_with_ram"),
        (_gpu(shared_with_ram=1), "shared_with_ram"),
        (_gpu(bandwidth_gbps=0.0), "bandwidth_gbps"),
        (_gpu(bandwidth_gbps=-1.0), "bandwidth_gbps"),
        (_gpu(bandwidth_gbps=math.inf), "bandwidth_gbps"),
        (_gpu(bandwidth_gbps=math.nan), "bandwidth_gbps"),
        (_gpu(bandwidth_gbps=True), "bandwidth_gbps"),
        (_gpu(bandwidth_gbps="360"), "bandwidth_gbps"),
        (_gpu(figure="measured"), "figure"),
        (_gpu(figure=None), "figure"),
        (_gpu(backend="opencl"), "backend"),
        (_gpu(backend="CUDA"), "backend"),
    ],
)
def test_each_rule_a_resource_keeps_refuses_its_break_and_names_the_field(
    resource: hubwire.Resource, field: str
) -> None:
    with pytest.raises(ValueError, match=f"^{field}: "):
        resource.validate()


@pytest.mark.parametrize(
    "resource",
    [
        _gpu(index=0, total_mb=0, free_mb=0),
        _gpu(name="x" * hubwire.RESOURCE_NAME_MAX),
        _gpu(name="Карта ü 显卡"),
        _gpu(total_mb=hubwire.RESOURCE_MAX_MB, free_mb=hubwire.RESOURCE_MAX_MB),
        _gpu(free_mb=None, bandwidth_gbps=None),
        _gpu(bandwidth_gbps=448),
        _cpu(free_mb=0),
        _ram(index=3, backend="cpu", figure="estimate"),
    ],
)
def test_a_resource_at_each_rules_edge_validates(resource: hubwire.Resource) -> None:
    resource.validate()


# --- an advert fits -------------------------------------------------------------


def test_an_advert_fits_up_to_its_most_resources() -> None:
    most = [_gpu(i) for i in range(hubwire.MAX_RESOURCES)]
    assert hubwire.resources_fit(most)
    assert hubwire.resources_fit([])
    assert not hubwire.resources_fit([*most, _ram()])


def test_an_advert_names_each_kind_and_index_once() -> None:
    assert hubwire.resources_fit([_gpu(0), _gpu(1), _ram(), _cpu()])
    assert hubwire.resources_fit([_ram(index=0), _cpu(index=0)])
    assert not hubwire.resources_fit([_gpu(0), _gpu(0, name="Another Card")])
    assert not hubwire.resources_fit([_ram(), _ram(total_mb=1024)])


def test_a_card_index_is_one_cards_whatever_its_kind() -> None:
    """A gpu and a unified resource each become a legacy card at their index,
    so the two kinds share the card indexes."""
    assert hubwire.resources_fit([_gpu(0), _unified(1)])
    assert not hubwire.resources_fit([_gpu(0), _unified(0)])


# --- the legacy cards ------------------------------------------------------------


def test_a_unified_only_advert_is_one_card_with_none_free_when_unread() -> None:
    advert = [_unified(), _ram(), _cpu()]
    assert hubwire.cards_from_resources(advert) == [
        {
            "index": 0,
            "name": "Example Unified GPU",
            "vram_total_mb": 49_152,
            "vram_free_mb": 0,
        }
    ]


def test_a_gpu_only_advert_is_its_cards_by_index() -> None:
    advert = [_gpu(1, free_mb=9_000), _gpu(0)]
    assert hubwire.cards_from_resources(advert) == [
        {
            "index": 0,
            "name": "Example Card 0",
            "vram_total_mb": 12_000,
            "vram_free_mb": 11_000,
        },
        {
            "index": 1,
            "name": "Example Card 1",
            "vram_total_mb": 12_001,
            "vram_free_mb": 9_000,
        },
    ]


def test_a_mixed_advert_is_its_gpu_and_unified_cards_and_nothing_else() -> None:
    advert = [_cpu(), _gpu(2), _ram(), _unified(0, free_mb=30_000)]
    cards = hubwire.cards_from_resources(advert)
    assert [(c["index"], c["vram_free_mb"]) for c in cards] == [(0, 30_000), (2, 11_000)]
    assert hubwire.cards_from_resources([_ram(), _cpu()]) == []


def test_the_legacy_cards_are_the_shape_the_published_schema_takes() -> None:
    protocol = rig_schema.load(rig_schema.PROTOCOL)
    for card in hubwire.cards_from_resources([_gpu(0), _unified(1), _gpu(2)]):
        rig_schema.validate(card, protocol, "#/$defs/CardReport")


def test_no_legacy_card_is_made_from_a_resource_that_breaks_a_rule() -> None:
    with pytest.raises(ValueError, match="^shared_with_ram: "):
        hubwire.cards_from_resources([_unified(shared_with_ram=False)])
    with pytest.raises(ValueError, match="card index 0 twice"):
        hubwire.cards_from_resources([_gpu(0), _unified(0)])


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


def test_a_cpu_resource_is_a_whole_model_unit_and_the_wire_says_so() -> None:
    doc = hubwire.Resource.__doc__ or ""
    assert "whole models only" in doc
    assert "never a pipeline stage" in doc
