"""A number may be keyed by link class and stated in the units of a link.

A link's numbers are keyed by its class (two cards in one machine, or two
machines), a member of a closed key space, so a machine's name can never be a
key, and are stated in bandwidth and time units whose bounds the product holds:
above 0, finite. The card memory a rank holds beyond its weights is keyed by
the engine, like the other numbers that are. The shipped file states each of
these for every key the code asks for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr import derived
from mcgyvr.fleet import links
from tests import link_fixture as lf
from tests import numbers_fixture as nf


def test_the_link_class_key_space_is_the_classes_of_a_link() -> None:
    assert derived.KEY_SPACES["link_class"] == links.LINK_CLASSES


def test_the_units_of_a_link_are_known() -> None:
    assert "GiB/s" in derived.UNITS and "microseconds" in derived.UNITS


def test_link_numbers_keyed_by_class_are_answered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lf.own_folders(tmp_path, monkeypatch)
    for name, (gib_s, latency_us) in lf.ESTIMATED.items():
        bandwidth = derived.lookup(derived.LINK_GIB_S, name)
        assert (bandwidth.value, bandwidth.unit) == (gib_s, "GiB/s")
        lag = derived.lookup(derived.LINK_LATENCY_US, name)
        assert (lag.value, lag.unit) == (latency_us, "microseconds")


def test_a_link_number_keyed_by_a_host_name_is_refused_by_name(tmp_path: Path) -> None:
    document = lf.invented_estimates()
    numbers = document["numbers"]
    assert isinstance(numbers, dict)
    numbers[derived.LINK_GIB_S]["values"][lf.HOST_A] = 1.0
    path = nf.write_json(tmp_path / "shipped.json", document)
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(derived.LINK_GIB_S, links.PCIE, path=path)
    assert lf.HOST_A in str(was.value) and str(path) in str(was.value)


@pytest.mark.parametrize("unit", ["GiB/s", "microseconds"])
@pytest.mark.parametrize("literal", ["0", "-1", "NaN", "Infinity", "true", '"3"'])
def test_a_link_value_outside_its_units_bounds_is_refused_by_name(
    unit: str, literal: str, tmp_path: Path
) -> None:
    document = lf.invented_estimates()
    numbers = document["numbers"]
    assert isinstance(numbers, dict)
    number = derived.LINK_GIB_S if unit == "GiB/s" else derived.LINK_LATENCY_US
    text = json.dumps(document).replace(
        f'"{links.PCIE}": {numbers[number]["values"][links.PCIE]}',
        f'"{links.PCIE}": {literal}',
    )
    path = tmp_path / "shipped.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(derived.DerivedNumbersError) as was:
        derived.lookup(number, links.PCIE, path=path)
    assert number in str(was.value) and str(path) in str(was.value)


def test_a_rank_allowance_is_keyed_by_the_engine(tmp_path: Path) -> None:
    document = {
        "_doc": "Invented for a test.",
        "schema": derived.NUMBERS_SCHEMA,
        "numbers": {
            derived.SHARD_ALLOWANCE: {
                "kind": "estimate",
                "estimates": "an invented quantity",
                "used_for": "nothing; a test reads it",
                "unit": "GiB",
                "key": "engine",
                "values": {"vllm": 2.25},
                "note": "invented for a test",
            }
        },
    }
    path = nf.write_json(tmp_path / "shipped.json", document)
    assert derived.shard_allowance_gib("vllm", path=path) == 2.25
    assert "vllm" in derived.KEY_SPACES["engine"]
    # An engine the entry does not state is refused by name, with what was sized.
    with pytest.raises(derived.DerivedNumbersError, match="while sizing a shard"):
        derived.shard_allowance_gib("llama.cpp", sizing="a shard", path=path)


def test_the_shipped_file_states_every_link_number_for_every_class() -> None:
    for name in links.LINK_CLASSES:
        for number in (derived.LINK_GIB_S, derived.LINK_LATENCY_US):
            answered = derived.lookup(number, name)
            assert answered.source == "estimate"
            assert answered.value > 0


def test_the_shipped_file_states_a_card_allowance_for_both_engines() -> None:
    assert derived.shard_allowance_gib("vllm") >= 0
    assert derived.shard_allowance_gib("llama.cpp") > 0
