"""A machine's short id covers its machine id and every card's name and size.

The short id is a digest, under its own identity prefix, over the machine id
and every card's name and total memory, the cards sorted by name and size so
that their indexes, which a card tool may renumber, do not move it; two equal
cards count twice. It changes when the machine id, a card's name or size, or
the number of cards changes. Free and used memory, the processes on a card,
the card indexes and the containers do not move it; the host name moves it
only through a machine id derived from it. Names are taken in one Unicode form.
A card the reading names unsized (no installed tool reads it, no source
publishes its size) is left out, and a value is hashed as it is. A reading that
could not read a covered field of any other card, or whose card list may be
short, gets no short id, and the refusal names the field and what the user can
do.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.machine_shapes import shape, shapes
from tests.machinereader import machine_read_text, replace, run, stage

if TYPE_CHECKING:
    from mcgyvr.fleet.machine import Reading


def _reading(label: str, where: Path) -> Reading:
    from mcgyvr.fleet import machine as reader

    return reader.parse(machine_read_text(shape(label), where))


def test_the_short_id_has_its_own_prefix_among_the_identity_prefixes() -> None:
    from mcgyvr.fleet import ids, machine

    assert machine.SHORT_ID_PREFIX in ids.IDENTITY_PREFIXES
    assert machine.SHORT_ID_PREFIX not in ids._RETIRED_PREFIXES


def test_every_readable_machine_gets_a_short_id_under_that_prefix(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    named = {}
    for number, m in enumerate(shapes()):
        reading = machine.parse(machine_read_text(m, tmp_path / str(number)))
        try:
            named[m.label] = machine.short_id(reading)
        except ValueError:
            continue
    assert len(named) >= len(shapes()) // 2, sorted(named)
    assert all(i.startswith(machine.SHORT_ID_PREFIX) for i in named.values())
    assert len(set(named.values())) == len(named)


def test_the_short_id_moves_with_any_cards_name_or_size_and_the_machine_id(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("several-sizes", tmp_path)
    before = machine.short_id(reading)
    for place in range(len(reading.cards)):
        for change in ({"name": "Example Card Z"}, {"total_mib": 1}):
            cards = list(reading.cards)
            cards[place] = dataclasses.replace(cards[place], **change)
            moved = dataclasses.replace(reading, cards=tuple(cards))
            assert machine.short_id(moved) != before, (place, change)
    other = dataclasses.replace(reading, machine_id="f" * 16)
    assert machine.short_id(other) != before
    fewer = dataclasses.replace(reading, cards=reading.cards[:-1])
    assert machine.short_id(fewer) != before


def test_the_short_id_ignores_what_is_not_the_machine(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("busy-beside-free", tmp_path)
    before = machine.short_id(reading)
    idle = tuple(
        dataclasses.replace(c, used_mib=0, free_mib=c.total_mib, holders=())
        for c in reading.cards
    )
    elsewhere = dataclasses.replace(
        reading,
        cards=idle,
        host="box-3.example",
        containers=(),
        machine_id_from="hostname",
    )
    assert machine.short_id(elsewhere) == before


def test_the_same_cards_on_two_machines_get_two_short_ids(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    here = _reading("same-cards-here", tmp_path / "here")
    there = _reading("same-cards-there", tmp_path / "there")
    assert machine.short_id(here) != machine.short_id(there)


def test_a_reading_missing_a_covered_field_gets_no_short_id_and_names_it(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("unreadable-size", tmp_path)
    with pytest.raises(ValueError, match=r"card\.nvidia\.1\.total"):
        machine.short_id(reading)


def test_a_machine_without_its_card_tool_gets_an_id_over_the_cards_it_sizes(
    tmp_path: Path,
) -> None:
    """Its cards whose size no source publishes are left out, and named so."""
    from mcgyvr.fleet import machine

    reading = _reading("no-reader", tmp_path)
    assert reading.unsized
    left = {key for key in reading.unsized}
    sized = tuple(c for c in reading.cards if c.key not in left)
    assert machine.short_id(reading) == machine.short_id(
        dataclasses.replace(reading, cards=sized, unsized=())
    )


def test_the_short_id_hashes_a_value_as_it_is_never_as_a_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Were the policy to take a card of unread size or name, it would not be
    hashed as a card of 0 MiB or one named ``None``."""
    from mcgyvr.fleet import machine

    monkeypatch.setattr(machine, "_policy", lambda reading: ([], frozenset()))
    reading = _reading("one-card", tmp_path)
    (card,) = reading.cards

    def with_card(**change: object) -> str:
        changed = dataclasses.replace(card, **change)  # type: ignore[arg-type]
        return machine.short_id(dataclasses.replace(reading, cards=(changed,)))

    assert with_card(total_mib=None) != with_card(total_mib=0)
    assert with_card(name=None) != with_card(name="None")


def test_a_card_tool_that_failed_gets_no_short_id(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=3)
    reading = machine.parse(run(staged, tmp_path).stdout)
    with pytest.raises(ValueError, match=r"cards\.nvidia-smi"):
        machine.short_id(reading)


def test_a_reading_without_a_machine_id_gets_no_short_id() -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse("host=box-4.example\ncards=none\n")
    with pytest.raises(ValueError, match="machine_id"):
        machine.short_id(reading)


def test_the_short_id_does_not_move_with_card_indexes_or_their_order(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("several-sizes", tmp_path)
    before = machine.short_id(reading)
    assert (
        machine.short_id(dataclasses.replace(reading, cards=reading.cards[::-1]))
        == before
    )
    renumbered = tuple(
        dataclasses.replace(card, index=len(reading.cards) - place)
        for place, card in enumerate(reading.cards)
    )
    assert machine.short_id(dataclasses.replace(reading, cards=renumbered)) == before


def test_two_equal_cards_count_twice(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("four-equal", tmp_path)
    before = machine.short_id(reading)
    assert (
        machine.short_id(dataclasses.replace(reading, cards=reading.cards[:3]))
        != before
    )


def test_a_name_is_taken_in_one_unicode_form() -> None:
    from mcgyvr.fleet import machine

    def one(name: str) -> str:
        reading = machine.parse(
            "machine_id=0123456789abcdef\ncards=nvidia-smi\n"
            f"card=nvidia,0,7919,0,7919,{name}\nend=\n"
        )
        return machine.short_id(reading)

    composed = "Example Carte \u00e9"
    decomposed = "Example Carte e\u0301"
    assert composed != decomposed
    assert one(composed) == one(decomposed)


def _typed(**change: object) -> object:
    from mcgyvr.fleet import machine

    reading = machine.parse(
        "machine_id=0123456789abcdef\ncards=nvidia-smi\n"
        "card=nvidia,0,7919,0,7919,Example Card U\nend=\n"
    )
    card = dataclasses.replace(reading.cards[0], **change)  # type: ignore[arg-type]
    return dataclasses.replace(reading, cards=(card,))


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"total_mib": "7919"}, "card.nvidia.0.total"),
        ({"total_mib": True}, "card.nvidia.0.total"),
        ({"total_mib": 7919.0}, "card.nvidia.0.total"),
        ({"name": b"Example Card U"}, "card.nvidia.0.name"),
    ],
    ids=["size-as-text", "size-as-bool", "size-as-float", "name-as-bytes"],
)
def test_a_covered_field_of_the_wrong_type_gets_no_short_id(
    change: dict[str, object], field: str
) -> None:
    from mcgyvr.fleet import machine

    reading = _typed(**change)
    assert isinstance(reading, machine.Reading)
    with pytest.raises(ValueError, match=field.replace(".", r"\.")):
        machine.short_id(reading)


def test_a_machine_id_of_the_wrong_type_gets_no_short_id() -> None:
    from mcgyvr.fleet import machine

    reading = _typed()
    assert isinstance(reading, machine.Reading)
    with pytest.raises(ValueError, match="machine_id"):
        machine.short_id(dataclasses.replace(reading, machine_id=12))  # type: ignore[arg-type]


def test_a_card_of_unread_size_is_refused_naming_it_and_what_to_do(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    reading = _reading("unreadable-size", tmp_path)
    with pytest.raises(ValueError) as refused:
        machine.short_id(reading)
    said = str(refused.value)
    assert "card.nvidia.1.total" in said
    assert "read the machine again" in said


def test_a_failed_tool_is_refused_naming_it_and_what_to_do(tmp_path: Path) -> None:
    from mcgyvr.fleet import machine

    staged = replace(stage(shape("one-card")), first_tool=b"", first_tool_exit=3)
    reading = machine.parse(run(staged, tmp_path).stdout)
    with pytest.raises(ValueError) as refused:
        machine.short_id(reading)
    said = str(refused.value)
    assert "nvidia-smi" in said
    assert "Run nvidia-smi by hand" in said


def test_a_reading_built_without_the_parser_is_hashed_in_one_unicode_form(
    tmp_path: Path,
) -> None:
    import unicodedata

    from mcgyvr.fleet import machine

    reading = _reading("one-card", tmp_path)
    (card,) = reading.cards
    assert card.name is not None
    named = "Example Carte é"
    forms = [
        dataclasses.replace(
            reading,
            cards=(dataclasses.replace(card, name=unicodedata.normalize(form, named)),),
        )
        for form in ("NFC", "NFD")
    ]
    assert forms[0].cards[0].name != forms[1].cards[0].name
    assert machine.short_id(forms[0]) == machine.short_id(forms[1])
