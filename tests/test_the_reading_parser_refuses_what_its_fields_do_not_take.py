"""The reading parser refuses, by itself, what its fields do not take.

What the parser reads may not come from this machine reader, so it holds its
own checks and does not lean on the reader's: a value a field does not take is
left empty and named unread, a line it does not understand or a card printed
twice is named, and a reading that holds either gets no short id.
"""

from __future__ import annotations

import pytest

HEAD = "machine_id=0123456789abcdef\nhost=box-6.example\ncards=nvidia-smi\n"
CARD = "card=nvidia,0,7919,0,7919,Example Card V\n"


def _parse(text: str) -> object:
    from mcgyvr.fleet import machine

    return machine.parse(text)


def _unread(text: str) -> dict[str, str]:
    from mcgyvr.fleet import machine

    return {u.field: u.why for u in machine.parse(text).unread}


def _refused(text: str, field: str) -> None:
    from mcgyvr.fleet import machine

    with pytest.raises(ValueError, match=field.replace(".", r"\.")):
        machine.short_id(machine.parse(text))


def test_a_card_printed_twice_is_dropped_named_and_refuses_the_id() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + CARD + "card=nvidia,0,3001,0,3001,Example Card W\n"
    reading = machine.parse(text)
    assert reading.cards == ()
    assert "card.nvidia.0" in _unread(text)
    _refused(text, "card.nvidia.0")


def test_a_line_not_understood_is_named_and_refuses_the_id() -> None:
    text = HEAD + CARD + "gpu=something\n"
    assert "reading" in _unread(text)
    _refused(text, "reading")


@pytest.mark.parametrize("key", ["machine_id", "host", "machine_id_from"])
def test_a_field_printed_twice_is_taken_from_neither(key: str) -> None:
    from mcgyvr.fleet import machine

    values = {
        "machine_id": ("0123456789abcdef", "fedcba9876543210"),
        "host": ("box-6.example", "box-7.example"),
        "machine_id_from": ("/etc/machine-id", "hostname"),
    }[key]
    text = "".join(f"{key}={value}\n" for value in values) + "cards=none\n"
    reading = machine.parse(text)
    assert getattr(reading, key) is None
    assert "more than once" in _unread(text)[key]


@pytest.mark.parametrize(
    "value", ["0123456789ABCDEF", "0123456789abcde", "0123456789abcdef0", "zz" * 8]
)
def test_a_machine_id_that_is_not_16_hex_is_refused(value: str) -> None:
    from mcgyvr.fleet import machine

    text = f"machine_id={value}\ncards=none\n"
    assert machine.parse(text).machine_id is None
    assert "machine_id" in _unread(text)


def test_an_unread_reason_is_made_printable_and_bounded() -> None:
    text = HEAD + "unread=card.nvidia.0.total,bad\x1b[31m" + "x" * 1000 + "\n"
    why = _unread(text)["card.nvidia.0.total"]
    assert why.isprintable()
    assert "\x1b" not in why
    assert len(why) <= 300


def test_an_unread_line_naming_no_field_is_named_as_not_understood() -> None:
    text = HEAD + "unread=bad field name,why\n"
    unread = _unread(text)
    assert "bad field name" not in unread
    assert "reading" in unread


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

    text = HEAD + "container=good,2,p,0\n" + line + "\n"
    reading = machine.parse(text)
    assert reading.containers is None
    assert "containers" in _unread(text)


def test_a_carriage_return_at_a_lines_end_is_taken_off() -> None:
    from mcgyvr.fleet import machine

    text = (HEAD + CARD).replace("\n", "\r\n")
    reading = machine.parse(text)
    (card,) = reading.cards
    assert card.name == "Example Card V"
    assert reading.host == "box-6.example"


def test_a_carriage_return_inside_a_name_is_refused() -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse(HEAD + "card=nvidia,0,7919,0,7919,Exa\rmple\n")
    assert reading.cards[0].name is None


def test_holders_of_a_card_the_reading_does_not_hold_are_named() -> None:
    text = HEAD + CARD + "holder=nvidia,4,12,300,example-process\n"
    assert "card.nvidia.4" in _unread(text)["reading"]


def test_a_name_over_the_bound_is_refused_by_the_parser() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + "card=nvidia,0,7919,0,7919," + "N" * 257 + "\n"
    assert machine.parse(text).cards[0].name is None
    assert "longer" in _unread(text)["card.nvidia.0.name"]
    ok = HEAD + "card=nvidia,0,7919,0,7919," + "N" * 256 + "\n"
    assert machine.parse(ok).cards[0].name == "N" * 256


def test_a_size_over_the_digit_bound_is_refused_by_the_parser() -> None:
    from mcgyvr.fleet import machine

    text = HEAD + "card=nvidia,0," + "1" * 19 + ",0,0,Example Card V\n"
    assert machine.parse(text).cards[0].total_mib is None
    assert "card.nvidia.0.total" in _unread(text)
    ok = HEAD + "card=nvidia,0," + "1" * 18 + ",0,0,Example Card V\n"
    assert machine.parse(ok).cards[0].total_mib == int("1" * 18)


@pytest.mark.parametrize(
    ("text", "field", "remedy"),
    [
        (
            HEAD + CARD + "unread=cards.nvidia-smi,failed\n",
            "cards.nvidia-smi",
            "read the machine again",
        ),
        (
            HEAD + "card=nvidia,0,,0,,Example Card V\n",
            "card.nvidia.0.total",
            "installed and working",
        ),
        (
            "host=box-6.example\ncards=nvidia-smi\n" + CARD,
            "machine_id",
            "machine-id file",
        ),
    ],
    ids=["a-failed-tool", "a-size-not-read", "no-machine-id"],
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
