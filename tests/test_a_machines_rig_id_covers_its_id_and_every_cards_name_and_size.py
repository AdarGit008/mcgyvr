"""A machine's rig id covers its machine id and every card's name and size.

The rig id (:func:`mcgyvr.fleet.ids.rig_id`) is a digest, under the ``rig-``
prefix, over the machine id and every card's name and total memory, the cards
sorted by name and size so that their indexes, which a card tool may renumber,
do not move it; two equal cards count twice. It changes when the machine id, a
card's name or size, or the number of cards changes. Free and used memory, the
card indexes and everything the snapshot holds (the kernel, the driver,
docker) do not move it; the host name moves it only through a machine id
derived from it. Names are taken in one Unicode form. A card the reading names
unsized (no installed tool reads it, no source publishes its size) is left
out, and a value is hashed as it is. A reading that could not read a covered
field of any other card, or whose card list may be short, gets no rig id, and
the refusal names the field and what the user can do.
"""

from __future__ import annotations

import copy
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from tests.machine_shapes import shape, shapes
from tests.machinereader import machine_reading, reading, replace, run, stage


def _reading(label: str, where: Path) -> dict[str, Any]:
    return machine_reading(shape(label), where)


def _rig_id(document: dict[str, Any]) -> str:
    from mcgyvr.fleet import ids

    return ids.rig_id(document)


def _with(document: dict[str, Any], **change: Any) -> dict[str, Any]:
    changed = copy.deepcopy(document)
    changed.update(change)
    return changed


def _one_card(**card: Any) -> dict[str, Any]:
    """A hand-built reading of one card, as another machine might send one."""
    return {
        "machine": {"id": "0123456789abcdef", "host": "box-4.example"},
        "cards": [
            {
                "vendor": "nvidia",
                "index": 0,
                "name": "Example Card U",
                "total_mib": 7919,
                "used_mib": 0,
                "free_mib": 7919,
                **card,
            }
        ],
        "card_sources": ["nvidia-smi"],
        "unsized": [],
        "unread": [],
    }


def test_the_rig_prefix_is_an_identity_prefix_and_the_machine_one_is_retired() -> None:
    from mcgyvr.fleet import ids

    assert "rig-" in ids.IDENTITY_PREFIXES
    assert "mch-" in ids._RETIRED_PREFIXES


def test_every_readable_machine_gets_a_rig_id_under_that_prefix(
    tmp_path: Path,
) -> None:
    named = {}
    for number, m in enumerate(shapes()):
        document = machine_reading(m, tmp_path / str(number))
        try:
            named[m.label] = _rig_id(document)
        except ValueError:
            continue
    assert len(named) >= len(shapes()) // 2, sorted(named)
    assert all(i.startswith("rig-") for i in named.values())
    assert len(set(named.values())) == len(named)


def test_the_rig_id_moves_with_any_cards_name_or_size_and_the_machine_id(
    tmp_path: Path,
) -> None:
    document = _reading("several-sizes", tmp_path)
    before = _rig_id(document)
    for place in range(len(document["cards"])):
        for change in ({"name": "Example Card Z"}, {"total_mib": 1}):
            moved = copy.deepcopy(document)
            moved["cards"][place].update(change)
            assert _rig_id(moved) != before, (place, change)
    other = copy.deepcopy(document)
    other["machine"]["id"] = "f" * 16
    assert _rig_id(other) != before
    assert _rig_id(_with(document, cards=document["cards"][:-1])) != before


def test_the_rig_id_ignores_what_is_not_the_machine(tmp_path: Path) -> None:
    """Load, the host name, and every fact the snapshot holds do not name it:
    a driver upgrade is a machine that changed, said by the gate."""
    document = _reading("busy-beside-free", tmp_path)
    before = _rig_id(document)
    elsewhere = copy.deepcopy(document)
    for card in elsewhere["cards"]:
        card.update(used_mib=0, free_mib=card["total_mib"])
    elsewhere["machine"].update(host="box-3.example", id_from="hostname")
    elsewhere["snapshot"] = {"driver": "590.1", "kernel": "7.0.0", "docker": "30.0"}
    assert _rig_id(elsewhere) == before


def test_the_same_cards_on_two_machines_get_two_rig_ids(tmp_path: Path) -> None:
    here = _reading("same-cards-here", tmp_path / "here")
    there = _reading("same-cards-there", tmp_path / "there")
    assert _rig_id(here) != _rig_id(there)


def test_a_reading_missing_a_covered_field_gets_no_rig_id_and_names_it(
    tmp_path: Path,
) -> None:
    document = _reading("unreadable-size", tmp_path)
    with pytest.raises(ValueError, match=r"card\.nvidia\.1\.total"):
        _rig_id(document)


def test_a_machine_without_its_card_tool_gets_an_id_over_the_cards_it_sizes(
    tmp_path: Path,
) -> None:
    """Its cards whose size no source publishes are left out, and named so."""
    document = _reading("no-reader", tmp_path)
    assert document["unsized"]
    left = set(document["unsized"])
    sized = [
        c for c in document["cards"] if f"card.{c['vendor']}.{c['index']}" not in left
    ]
    assert _rig_id(document) == _rig_id(_with(document, cards=sized, unsized=[]))


def test_a_card_tool_that_failed_gets_no_rig_id(tmp_path: Path) -> None:
    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=3)
    document = reading(run(staged, tmp_path).stdout)
    with pytest.raises(ValueError, match=r"cards\.nvidia-smi"):
        _rig_id(document)


def test_a_reading_without_a_machine_id_gets_no_rig_id() -> None:
    document = _one_card()
    document["machine"] = {"host": "box-4.example"}
    with pytest.raises(ValueError, match="machine_id"):
        _rig_id(document)


def test_the_rig_id_does_not_move_with_card_indexes_or_their_order(
    tmp_path: Path,
) -> None:
    document = _reading("several-sizes", tmp_path)
    before = _rig_id(document)
    assert _rig_id(_with(document, cards=document["cards"][::-1])) == before
    renumbered = copy.deepcopy(document)
    count = len(renumbered["cards"])
    for place, card in enumerate(renumbered["cards"]):
        card["index"] = count - place
    renumbered["unread"] = []
    assert _rig_id(renumbered) == before


def test_two_equal_cards_count_twice(tmp_path: Path) -> None:
    document = _reading("four-equal", tmp_path)
    before = _rig_id(document)
    assert _rig_id(_with(document, cards=document["cards"][:3])) != before


def test_a_name_is_taken_in_one_unicode_form() -> None:
    composed = "Example Carte \u00e9"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    assert _rig_id(_one_card(name=composed)) == _rig_id(_one_card(name=decomposed))


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"total_mib": "7919"}, "card.nvidia.0.total"),
        ({"total_mib": True}, "card.nvidia.0.total"),
        ({"total_mib": 7919.0}, "card.nvidia.0.total"),
        ({"name": 7919}, "card.nvidia.0.name"),
    ],
    ids=["size-as-text", "size-as-bool", "size-as-float", "name-as-number"],
)
def test_a_covered_field_of_the_wrong_type_gets_no_rig_id(
    change: dict[str, object], field: str
) -> None:
    with pytest.raises(ValueError, match=field.replace(".", r"\.")):
        _rig_id(_one_card(**change))


def test_a_machine_id_of_the_wrong_type_gets_no_rig_id() -> None:
    document = _one_card()
    document["machine"]["id"] = 12
    with pytest.raises(ValueError, match="machine_id"):
        _rig_id(document)


def test_a_card_of_unread_size_is_refused_naming_it_and_what_to_do(
    tmp_path: Path,
) -> None:
    document = _reading("unreadable-size", tmp_path)
    with pytest.raises(ValueError) as refused:
        _rig_id(document)
    said = str(refused.value)
    assert "card.nvidia.1.total" in said
    assert "read the machine again" in said


def test_a_failed_tool_is_refused_naming_it_and_what_to_do(tmp_path: Path) -> None:
    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=3)
    document = reading(run(staged, tmp_path).stdout)
    with pytest.raises(ValueError) as refused:
        _rig_id(document)
    said = str(refused.value)
    assert "nvidia-smi" in said
    assert "Run nvidia-smi by hand" in said
