"""The reading parser refuses, by itself, what its fields do not take.

What the parser reads may not come from this machine reader, so it holds its
own checks and does not lean on the reader's: a value a field does not take is
left empty and named unread, a line it does not understand, a card printed
twice or a reading without its end line is named, a value the reading itself
names unread is dropped, and a reading that holds any of these gets no short
id. The short id holds the same checks for a reading built without the parser.
"""

from __future__ import annotations

import dataclasses
import unicodedata

import pytest

HEAD = "machine_id=0123456789abcdef\nhost=box-6.example\ncards=nvidia-smi\n"
CARD = "card=nvidia,0,7919,0,7919,Example Card V\n"
END = "end=\n"


def _parse(text: str) -> object:
    from mcgyvr.fleet import machine

    return machine.parse(text)


def _unread(text: str) -> dict[str, str]:
    from mcgyvr.fleet import machine

    return {u.field: u.why for u in machine.parse(text).unread}


def _whys(text: str, field: str) -> list[str]:
    from mcgyvr.fleet import machine

    return [u.why for u in machine.parse(text).unread if u.field == field]


def _refused(text: str, field: str) -> None:
    from mcgyvr.fleet import machine

    with pytest.raises(ValueError, match=field.replace(".", r"\.")):
        machine.short_id(machine.parse(text))


def test_a_whole_reading_parses_with_nothing_unread_and_gets_an_id() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + CARD + END
    reading = machine.parse(text)
    assert reading.unread == ()
    assert machine.short_id(reading).startswith(machine.SHORT_ID_PREFIX)


def test_a_card_printed_twice_is_dropped_named_and_refuses_the_id() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + CARD + "card=nvidia,0,3001,0,3001,Example Card W\n" + END
    reading = machine.parse(text)
    assert reading.cards == ()
    assert "card.nvidia.0" in _unread(text)
    _refused(text, "card.nvidia.0")


def test_a_line_not_understood_is_named_and_refuses_the_id() -> None:
    text = HEAD + CARD + "gpu=something\n" + END
    assert any("not a line" in why for why in _whys(text, "reading"))
    _refused(text, "reading")


def test_a_reading_without_its_end_line_is_named_and_refuses_the_id() -> None:
    """A reading cut short looks whole but for its end line."""
    text = HEAD + CARD
    assert any("end line" in why for why in _whys(text, "reading"))
    _refused(text, "reading")


def test_a_line_after_the_end_line_is_named() -> None:
    text = HEAD + END + CARD
    assert any("after the end line" in why for why in _whys(text, "reading"))


@pytest.mark.parametrize("key", ["machine_id", "host", "machine_id_from"])
def test_a_field_printed_twice_is_taken_from_neither(key: str) -> None:
    from mcgyvr.fleet import machine

    values = {
        "machine_id": ("0123456789abcdef", "fedcba9876543210"),
        "host": ("box-6.example", "box-7.example"),
        "machine_id_from": ("/etc/machine-id", "hostname"),
    }[key]
    text = "".join(f"{key}={value}\n" for value in values) + "cards=none\n" + END
    reading = machine.parse(text)
    assert getattr(reading, key) is None
    assert "more than once" in _unread(text)[key]


@pytest.mark.parametrize(
    "value", ["0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "zz" * 8]
)
def test_a_machine_id_that_is_not_16_hex_is_refused(value: str) -> None:
    from mcgyvr.fleet import machine

    text = f"machine_id={value}\ncards=none\n" + END
    assert machine.parse(text).machine_id is None
    assert "machine_id" in _unread(text)


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ("host=box 6.example", "host"),
        ("host=box-6.exaémple", "host"),
        ("machine_id_from=etc/machine-id", "machine_id_from"),
        ("machine_id_from=/etc/machine id", "machine_id_from"),
    ],
    ids=["host-space", "host-non-ascii", "from-relative", "from-space"],
)
def test_a_host_or_id_source_that_is_not_one_is_refused(line: str, field: str) -> None:
    from mcgyvr.fleet import machine

    text = "machine_id=0123456789abcdef\ncards=none\n" + line + "\n" + END
    assert getattr(machine.parse(text), field) is None
    assert field in _unread(text)


@pytest.mark.parametrize("value", ["Bad Source", "nvidia-smi,", "UPPER", "a" * 40])
def test_card_sources_that_are_not_source_names_are_refused(value: str) -> None:
    from mcgyvr.fleet import machine

    text = f"machine_id=0123456789abcdef\ncards={value}\n" + END
    assert machine.parse(text).card_sources == ()
    assert "cards" in _unread(text)
    _refused(text, "cards")


@pytest.mark.parametrize(
    ("line", "field", "attribute"),
    [
        ("unread=machine_id,a reason\n", "machine_id", None),
        ("unread=card.nvidia.0.name,a reason\n", "card.nvidia.0.name", "name"),
        ("unread=card.nvidia.0.total,a reason\n", "card.nvidia.0.total", "total_mib"),
        ("unread=card.nvidia.0.used,a reason\n", "card.nvidia.0.used", "used_mib"),
    ],
    ids=["machine-id", "name", "total", "used"],
)
def test_a_value_the_reading_names_unread_is_dropped(
    line: str, field: str, attribute: str | None
) -> None:
    """A value printed beside a line that names it unread is not taken."""
    from mcgyvr.fleet import machine

    text = HEAD + CARD + line + END
    reading = machine.parse(text)
    if attribute is None:
        assert reading.machine_id is None
    else:
        (card,) = reading.cards
        assert getattr(card, attribute) is None
    assert field in _unread(text)
    if attribute != "used_mib":
        _refused(text, field)


@pytest.mark.parametrize(
    "field", ["machine_id", "card.nvidia.0.name", "card.nvidia.0.total"]
)
def test_the_short_id_refuses_a_value_its_reading_names_unread(field: str) -> None:
    """A reading built without the parser may hold both; the id takes neither."""
    from mcgyvr.fleet import machine

    reading = machine.parse(HEAD + CARD + END)
    named = dataclasses.replace(
        reading, unread=(machine.Unread(field=field, why="a reason"),)
    )
    with pytest.raises(ValueError, match=field.replace(".", r"\.")):
        machine.short_id(named)


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"total_mib": -1}, "card.nvidia.0.total"),
        ({"total_mib": 10**30}, "card.nvidia.0.total"),
        ({"name": ""}, "card.nvidia.0.name"),
        ({"name": "Example\nCard"}, "card.nvidia.0.name"),
        ({"name": "Example\x00Card"}, "card.nvidia.0.name"),
        ({"name": " Example Card"}, "card.nvidia.0.name"),
        ({"name": "N" * 257}, "card.nvidia.0.name"),
    ],
    ids=["negative", "huge", "empty", "line-break", "nul", "leading-blank", "long"],
)
def test_the_short_id_refuses_a_value_the_parser_would_refuse(
    change: dict[str, object], field: str
) -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse(HEAD + CARD + END)
    (card,) = reading.cards
    card = dataclasses.replace(card, **change)  # type: ignore[arg-type]
    changed = dataclasses.replace(reading, cards=(card,))
    with pytest.raises(ValueError, match=field.replace(".", r"\.")):
        machine.short_id(changed)


def test_an_unread_reason_is_made_printable_and_bounded() -> None:
    text = HEAD + "unread=card.nvidia.0.total,bad\x1b[31m" + "x" * 1000 + "\n" + END
    why = _unread(text)["card.nvidia.0.total"]
    assert why.isprintable()
    assert "\x1b" not in why
    assert len(why) <= 300


def test_an_unread_line_naming_no_field_is_named_as_not_understood() -> None:
    text = HEAD + "unread=bad field name,why\n" + END
    unread = _unread(text)
    assert "bad field name" not in unread
    assert any("naming no field" in why for why in _whys(text, "reading"))


@pytest.mark.parametrize(
    "line",
    [
        "container=a b,1,p,0",
        "container=a,1\x1b,p,0",
        "container=a,1,p",
        "container=" + "n" * 300 + ",1,p,0",
    ],
    ids=["space", "control", "three-fields", "too-long"],
)
def test_a_container_line_the_parser_refuses_leaves_the_containers_unread(
    line: str,
) -> None:
    from mcgyvr.fleet import machine

    text = HEAD + "container=good,2,p,0\n" + line + "\n" + END
    reading = machine.parse(text)
    assert reading.containers is None
    assert "containers" in _unread(text)


def test_a_carriage_return_at_a_lines_end_is_taken_off() -> None:
    from mcgyvr.fleet import machine

    text = (HEAD + CARD + END).replace("\n", "\r\n")
    reading = machine.parse(text)
    (card,) = reading.cards
    assert card.name == "Example Card V"
    assert reading.host == "box-6.example"
    assert reading.unread == ()


def test_a_carriage_return_inside_a_name_is_refused() -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse(HEAD + "card=nvidia,0,7919,0,7919,Exa\rmple\n" + END)
    assert reading.cards[0].name is None


@pytest.mark.parametrize(
    "name",
    [
        "Example\ufffdCard",
        "Example\u202eCard",
        "Example\u2028Card",
        "[N/A]",
        "N/A",
    ],
    ids=["replacement", "bidi-override", "line-separator", "n-a-bracketed", "n-a"],
)
def test_a_name_that_is_no_name_is_refused(name: str) -> None:
    """A byte that did not decode, a hidden direction change, or [N/A]."""
    from mcgyvr.fleet import machine

    text = HEAD + f"card=nvidia,0,7919,0,7919,{name}\n" + END
    assert machine.parse(text).cards[0].name is None
    assert "card.nvidia.0.name" in _unread(text)


def test_a_name_is_kept_in_one_unicode_form() -> None:
    from mcgyvr.fleet import machine

    decomposed = unicodedata.normalize("NFD", "Example Carte été")
    reading = machine.parse(HEAD + f"card=nvidia,0,7919,0,7919,{decomposed}\n" + END)
    assert reading.cards[0].name == unicodedata.normalize("NFC", decomposed)


def test_holders_of_a_card_the_reading_does_not_hold_are_named() -> None:
    text = HEAD + CARD + "holder=nvidia,4,12,300,example-process\n" + END
    assert any("card.nvidia.4" in why for why in _whys(text, "reading"))


def test_a_name_over_the_bound_is_refused_by_the_parser() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + "card=nvidia,0,7919,0,7919," + "N" * 257 + "\n" + END
    assert machine.parse(text).cards[0].name is None
    assert "longer" in _unread(text)["card.nvidia.0.name"]
    ok = HEAD + "card=nvidia,0,7919,0,7919," + "N" * 256 + "\n" + END
    assert machine.parse(ok).cards[0].name == "N" * 256


def test_a_size_over_the_digit_bound_is_refused_by_the_parser() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + "card=nvidia,0," + "1" * 19 + ",0,0,Example Card V\n" + END
    assert machine.parse(text).cards[0].total_mib is None
    assert "card.nvidia.0.total" in _unread(text)
    ok = HEAD + "card=nvidia,0," + "1" * 18 + ",0,0,Example Card V\n" + END
    assert machine.parse(ok).cards[0].total_mib == int("1" * 18)


@pytest.mark.parametrize(
    ("text", "field", "remedy"),
    [
        (
            HEAD + CARD + "unread=cards.nvidia-smi,failed\n" + END,
            "cards.nvidia-smi",
            "read the machine again",
        ),
        (
            HEAD + "card=nvidia,0,,0,,Example Card V\n" + END,
            "card.nvidia.0.total",
            "read the machine again",
        ),
        (
            HEAD + "card=nvidia,0,7919,0,7919,\n" + END,
            "card.nvidia.0.name",
            "a name that is text",
        ),
        (
            "host=box-6.example\ncards=nvidia-smi\n" + CARD + END,
            "machine_id",
            "machine-id file",
        ),
    ],
    ids=["a-failed-tool", "a-size-not-read", "a-name-not-read", "no-machine-id"],
)
def test_a_refusal_says_what_the_user_can_do_when_the_reason_does_not(
    text: str, field: str, remedy: str
) -> None:
    """The reason in a reading may come from elsewhere and say nothing useful."""
    from mcgyvr.fleet import machine

    with pytest.raises(ValueError) as refused:
        machine.short_id(machine.parse(text))
    said = str(refused.value)
    assert field in said
    assert remedy in said


def test_a_card_the_reading_names_unsized_is_left_out_of_the_id() -> None:
    """The id of a card beside it is the id of that card alone."""
    from mcgyvr.fleet import machine

    text = (
        HEAD
        + CARD
        + "card=pci-0xfff0,1,,,,Example Adapter\n"
        + "unsized=pci-0xfff0,1\n"
        + END
    )
    reading = machine.parse(text)
    assert reading.unsized == ("card.pci-0xfff0.1",)
    assert machine.short_id(reading) == machine.short_id(
        machine.parse(HEAD + CARD + END)
    )


@pytest.mark.parametrize(
    "line",
    [
        "unsized=nvidia,0\n",
        "unsized=pci-0xfff0,7\n",
        "unsized=Not A Vendor,1\n",
    ],
    ids=["a-card-of-read-size", "no-such-card", "not-a-card"],
)
def test_an_unsized_line_that_names_no_card_of_unread_size_refuses_the_id(
    line: str,
) -> None:
    from mcgyvr.fleet import machine

    text = HEAD + CARD + line + END
    reading = machine.parse(text)
    assert reading.unsized == ()
    _refused(text, "reading")
