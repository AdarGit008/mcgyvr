"""A rig id is refused, by itself, for a reading it cannot take whole.

What :func:`mcgyvr.fleet.ids.rig_id` is handed may not come from this
machine's reader: a remote rig sends its document over ssh, and nothing in it
is taken on trust. So the id holds the reader's own checks
(:func:`mcgyvr.serving.rigscan.name_problem`, ``is_size``,
``is_machine_id``) over every value it hashes, and refuses the id by name
when the machine id or a card's name or size is not one a reading takes, when
the reading names any of them unread (even beside a value), when a card
source failed or may be short, or when a card was dropped. A refusal says
what the user can do, since the reason the reading gives may come from
elsewhere and say nothing useful. These readings are built by hand, as
another machine might send them.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

CARD: dict[str, Any] = {
    "vendor": "nvidia",
    "index": 0,
    "name": "Example Card V",
    "total_mib": 7919,
    "used_mib": 0,
    "free_mib": 7919,
}


def _document(*cards: dict[str, Any], **change: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "machine": {"id": "0123456789abcdef", "host": "box-6.example"},
        "cards": [copy.deepcopy(card) for card in (cards or (CARD,))],
        "card_sources": ["nvidia-smi"],
        "unsized": [],
        "unread": [],
    }
    document.update(change)
    return document


def _card(**change: Any) -> dict[str, Any]:
    return {**CARD, **change}


def _unread(field: str, why: str = "a reason") -> list[dict[str, str]]:
    return [{"field": field, "why": why}]


def _rig_id(document: dict[str, Any]) -> str:
    from mcgyvr.fleet import ids

    return ids.rig_id(document)


def _refused(document: dict[str, Any], field: str) -> str:
    with pytest.raises(ValueError, match=field.replace(".", r"\.")) as refused:
        _rig_id(document)
    return str(refused.value)


def test_a_whole_reading_gets_an_id() -> None:
    assert _rig_id(_document()).startswith("rig-")


@pytest.mark.parametrize(
    "value",
    ["0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "zz" * 8, "", 12],
)
def test_a_machine_id_that_is_not_16_hex_is_refused(value: object) -> None:
    document = _document()
    document["machine"]["id"] = value
    _refused(document, "machine_id")


def test_a_reading_with_no_machine_is_refused() -> None:
    _refused(_document(machine=None), "machine_id")


@pytest.mark.parametrize(
    "field", ["machine_id", "card.nvidia.0.name", "card.nvidia.0.total"]
)
def test_a_value_the_reading_names_unread_is_refused_even_beside_a_value(
    field: str,
) -> None:
    """A reading may hold both a value and a line naming it unread; the id takes
    neither."""
    _refused(_document(unread=_unread(field)), field)


def test_a_used_figure_named_unread_does_not_refuse_the_id() -> None:
    """Free and used memory are not in the id, so their being unread is not."""
    assert _rig_id(_document(unread=_unread("card.nvidia.0.used")))


def test_a_card_the_reader_dropped_refuses_the_id() -> None:
    """The reader drops a card a source printed twice and names it whole."""
    unread = _unread("card.nvidia.0", "the card source printed index 0 twice")
    _refused(_document(unread=unread), "card.nvidia.0")


def test_a_card_that_is_not_an_object_refuses_the_id() -> None:
    document = _document()
    document["cards"].append("card=nvidia,1,100,0,100,Example")
    _refused(document, "reading")


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"total_mib": -1}, "card.nvidia.0.total"),
        ({"total_mib": 10**18}, "card.nvidia.0.total"),
        ({"total_mib": 10**30}, "card.nvidia.0.total"),
        ({"total_mib": "7919"}, "card.nvidia.0.total"),
        ({"total_mib": True}, "card.nvidia.0.total"),
        ({"total_mib": 7919.0}, "card.nvidia.0.total"),
        ({"total_mib": None}, "card.nvidia.0.total"),
        ({"name": None}, "card.nvidia.0.name"),
        ({"name": ""}, "card.nvidia.0.name"),
        ({"name": "Example\nCard"}, "card.nvidia.0.name"),
        ({"name": "Example\x00Card"}, "card.nvidia.0.name"),
        ({"name": "Exa\rmple"}, "card.nvidia.0.name"),
        ({"name": " Example Card"}, "card.nvidia.0.name"),
        ({"name": "N" * 257}, "card.nvidia.0.name"),
        ({"name": "Example\ufffdCard"}, "card.nvidia.0.name"),
        ({"name": "Example\u202eCard"}, "card.nvidia.0.name"),
        ({"name": "Example\u2028Card"}, "card.nvidia.0.name"),
        ({"name": "[N/A]"}, "card.nvidia.0.name"),
        ({"name": "N/A"}, "card.nvidia.0.name"),
        ({"name": b"Example Card"}, "card.nvidia.0.name"),
    ],
    ids=[
        "negative",
        "nineteen-digits",
        "huge",
        "size-as-text",
        "size-as-bool",
        "size-as-float",
        "size-missing",
        "name-missing",
        "empty",
        "line-break",
        "nul",
        "carriage-return",
        "leading-blank",
        "long",
        "replacement",
        "bidi-override",
        "line-separator",
        "n-a-bracketed",
        "n-a",
        "name-as-bytes",
    ],
)
def test_a_value_the_reader_would_not_take_is_refused(
    change: dict[str, object], field: str
) -> None:
    _refused(_document(_card(**change)), field)


def test_the_bounds_themselves_are_taken() -> None:
    """A name of 256 characters and a size of 18 digits are values a reading takes."""
    assert _rig_id(_document(_card(name="N" * 256, total_mib=int("1" * 18))))


@pytest.mark.parametrize(
    "field", ["cards.nvidia-smi", "cards.rocm-smi", "cards"], ids=lambda f: f
)
def test_a_card_source_that_failed_or_may_be_short_refuses_the_id(field: str) -> None:
    _refused(_document(unread=_unread(field)), field)


@pytest.mark.parametrize(
    ("document", "field", "remedy"),
    [
        (
            _document(unread=_unread("cards.nvidia-smi", "failed")),
            "cards.nvidia-smi",
            "read the machine again",
        ),
        (
            _document(_card(total_mib=None)),
            "card.nvidia.0.total",
            "read the machine again",
        ),
        (_document(_card(name="")), "card.nvidia.0.name", "a name that is text"),
        (_document(machine={"host": "box-6.example"}), "machine_id", "machine-id file"),
    ],
    ids=["a-failed-tool", "a-size-not-read", "a-name-not-read", "no-machine-id"],
)
def test_a_refusal_says_what_the_user_can_do_when_the_reason_does_not(
    document: dict[str, Any], field: str, remedy: str
) -> None:
    said = _refused(document, field)
    assert remedy in said
    assert "never hashed over a field that was not read" in said


def test_a_refusal_carries_the_reason_the_reading_gave() -> None:
    unread = _unread("card.nvidia.0.total", "nvidia-smi printed [N/A] for it")
    said = _refused(
        _document(_card(total_mib=None), unread=unread), "card.nvidia.0.total"
    )
    assert "nvidia-smi printed [N/A] for it" in said


def test_a_card_the_reading_names_unsized_is_left_out_of_the_id() -> None:
    """The id of a card beside it is the id of that card alone."""
    adapter = _card(
        vendor="pci-0xfff0", index=1, name="Example Adapter", total_mib=None
    )
    beside = _document(CARD, adapter, unsized=["card.pci-0xfff0.1"])
    assert _rig_id(beside) == _rig_id(_document())


def test_a_card_named_unsized_whose_size_was_read_stays_in_the_id() -> None:
    """``unsized`` leaves out only a card whose size is unread: naming a sized
    card there does not drop it from the id."""
    other = _card(index=1, name="Example Card W", total_mib=3001)
    both = _document(CARD, other)
    marked = _document(CARD, other, unsized=["card.nvidia.1"])
    assert _rig_id(marked) == _rig_id(both)
    assert _rig_id(marked) != _rig_id(_document())
