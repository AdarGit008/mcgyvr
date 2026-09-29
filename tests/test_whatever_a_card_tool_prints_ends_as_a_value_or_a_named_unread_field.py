"""Whatever a card tool prints ends as a value or as a named unread field.

What a tool on the machine prints is untrusted, and so is what the reader
prints. A card name with a comma, a quote, a line break, control characters or
no end; a tool that prints nothing, garbage or half a line; a process name with
spaces; a size that is not a number: each ends in the reading as a value read
exactly, or as an empty field listed as unread with a reason. Parsing never
raises, and no card is reported with a figure it did not read.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.machinereader import MIB, Staged, run

if TYPE_CHECKING:
    from mcgyvr.fleet.machine import Card, Reading


def _read(where: Path, **staged: Any) -> Reading:
    from mcgyvr.fleet import machine

    ran = run(Staged(**staged), where)
    assert ran.returncode == 0, ran.stderr
    assert ran.unexpected == (), ran.unexpected
    return machine.parse(ran.stdout)


def _unread(reading: Reading) -> dict[str, str]:
    return {u.field: u.why for u in reading.unread}


def _cards(reading: Reading) -> dict[int, Card]:
    return {c.index: c for c in reading.cards}


def _one(text: bytes, where: Path, processes: bytes = b"") -> Reading:
    return _read(where, first_tool=text, first_tool_processes={0: (processes, 0)})


@pytest.mark.parametrize(
    "name",
    [
        "Example Card, Rev 2",
        "Example \"Card\" 'Q'",
        "Example Card ,,, trailing,",
        "  Example Card  ",
        "Example Carte Graphique été",
    ],
    ids=["comma", "quotes", "many-commas", "padded", "non-ascii"],
)
def test_a_card_name_that_is_text_is_read_exactly(name: str, tmp_path: Path) -> None:
    reading = _one(f"0, 8192, 100, 8092, {name}\n".encode(), tmp_path)
    card = _cards(reading)[0]
    assert card.name == name.strip()
    assert card.total_mib == 8192
    assert _unread(reading) == {}


@pytest.mark.parametrize(
    ("line", "why"),
    [
        (b"0, 8192, 100, 8092, Example\x1bCard\n", "control"),
        (b"0, 8192, 100, 8092, Example\x7fCard\n", "control"),
        (b"0, 8192, 100, 8092, " + b"X" * 5000 + b"\n", "longer"),
        (b"0, 8192, 100, 8092, \n", "no name"),
        (b"0, 8192, 100, 8092, Example\nCard\n", "line"),
    ],
    ids=["escape", "delete", "very-long", "empty", "line-break"],
)
def test_a_card_name_that_is_not_text_is_named_unread(
    line: bytes, why: str, tmp_path: Path
) -> None:
    reading = _one(line, tmp_path)
    card = _cards(reading)[0]
    assert card.name is None
    assert card.total_mib == 8192
    assert why in _unread(reading)["card.nvidia.0.name"]
    assert set(_cards(reading)) == {0}


@pytest.mark.parametrize(
    "text",
    [
        b"garbage without a single comma\n",
        b"\x00\xff\xfe binary \x01\x02\n",
        b"index, memory.total, memory.used, memory.free, name\n",
        b"Failed to initialize NVML: Driver/library version mismatch\n",
    ],
    ids=["words", "binary", "a-header", "an-error-on-stdout"],
)
def test_a_tool_that_prints_garbage_gives_no_card_and_names_the_tool(
    text: bytes, tmp_path: Path
) -> None:
    reading = _one(text, tmp_path)
    assert _cards(reading) == {}
    assert "cards.nvidia-smi" in _unread(reading)


def test_a_tool_that_prints_nothing_gives_no_card(tmp_path: Path) -> None:
    reading = _one(b"", tmp_path)
    assert _cards(reading) == {}


def test_half_a_line_reads_what_it_holds_and_names_the_rest(tmp_path: Path) -> None:
    reading = _one(b"0, 8192", tmp_path)
    card = _cards(reading)[0]
    assert card.total_mib == 8192
    assert (card.used_mib, card.free_mib, card.name) == (None, None, None)
    unread = _unread(reading)
    assert {"card.nvidia.0.used", "card.nvidia.0.free", "card.nvidia.0.name"} <= set(
        unread
    )


@pytest.mark.parametrize(
    "total",
    [b"8 GiB", b"-5", b"8192.5", b"99999999999999999999999", b"\xd9\xa1\xd9\xa2"],
    ids=["with-unit", "negative", "fraction", "too-large", "other-digits"],
)
def test_a_size_that_is_not_a_number_is_named_unread(
    total: bytes, tmp_path: Path
) -> None:
    reading = _one(b"0, " + total + b", 100, 8092, Example Card\n", tmp_path)
    card = _cards(reading)[0]
    assert card.total_mib is None
    assert card.name == "Example Card"
    assert _unread(reading)["card.nvidia.0.total"].strip()


def test_an_index_printed_twice_gives_neither_card(tmp_path: Path) -> None:
    text = b"0, 8192, 0, 8192, Example Card A\n0, 4096, 0, 4096, Example Card B\n"
    reading = _read(tmp_path, first_tool=text, first_tool_processes={0: (b"", 0)})
    assert _cards(reading) == {}
    assert "twice" in _unread(reading)["card.nvidia.0"]


def test_a_process_name_with_spaces_and_commas_is_read_exactly(
    tmp_path: Path,
) -> None:
    reading = _one(
        b"0, 8192, 300, 7892, Example Card\n",
        tmp_path,
        processes=b"4242, 300, /opt/example tool/serve --flag a,b\n",
    )
    (holder,) = _cards(reading)[0].holders
    assert (holder.pid, holder.mib, holder.name) == (
        4242,
        300,
        "/opt/example tool/serve --flag a,b",
    )


def test_a_process_whose_memory_is_not_available_names_it_unread(
    tmp_path: Path,
) -> None:
    reading = _one(
        b"0, 8192, 300, 7892, Example Card\n",
        tmp_path,
        processes=b"4242, [N/A], example-process\n",
    )
    (holder,) = _cards(reading)[0].holders
    assert (holder.pid, holder.mib) == (4242, None)
    assert "card.nvidia.0.holder.4242.mib" in _unread(reading)


@pytest.mark.parametrize(
    "processes",
    [b"not a process line\n", b"-1, 300, example\n", b"12, 300, bad\x1bname\n"],
    ids=["words", "negative-pid", "control-in-name"],
)
def test_a_process_listing_that_is_not_one_leaves_the_holders_unread(
    processes: bytes, tmp_path: Path
) -> None:
    reading = _one(b"0, 8192, 300, 7892, Example Card\n", tmp_path, processes)
    card = _cards(reading)[0]
    assert card.name == "Example Card"
    if b"bad" in processes:
        (holder,) = card.holders
        assert holder.name is None
        assert "card.nvidia.0.holder.12.name" in _unread(reading)
    else:
        assert card.holders is None
        assert "card.nvidia.0.holders" in _unread(reading)


@pytest.mark.parametrize(
    "text",
    [b"not json", b"[1, 2]", b'{"card0": "flat"}', b'{"card0": {"x": 1}}', b""],
    ids=["not-json", "a-list", "flat-entry", "no-fields", "empty"],
)
def test_a_second_tool_that_prints_garbage_never_gives_a_wrong_card(
    text: bytes, tmp_path: Path
) -> None:
    reading = _read(tmp_path, second_tool=text)
    for card in _cards(reading).values():
        assert card.name is None
        assert card.total_mib is None
    assert _unread(reading)


def test_a_second_tool_name_with_a_line_break_is_named_unread(tmp_path: Path) -> None:
    text = json.dumps(
        {
            "card3": {
                "Card series": "Example\nCard",
                "VRAM Total Memory (B)": str(4096 * MIB),
                "VRAM Total Used Memory (B)": "0",
            }
        }
    ).encode()
    reading = _read(tmp_path, second_tool=text)
    card = _cards(reading)[3]
    assert card.name is None
    assert card.total_mib == 4096
    assert "card.amd.3.name" in _unread(reading)


def test_a_container_name_with_commas_is_listed_as_the_unit_reader_lists_it(
    tmp_path: Path,
) -> None:
    from mcgyvr.fleet import machine

    listing = b"a" * 64 + b"|example, unit  one|example-project\n"
    reading = _read(tmp_path, containers=listing, restarts={"a" * 64: b"2\n"})
    assert reading.containers == (
        machine.Container(
            name="example_unit_one", id="a" * 64, project="example-project", restarts=2
        ),
    )


# The parser, fed directly: what reaches it may not come from this reader.


def test_parsing_never_raises_and_never_fills_a_figure() -> None:
    from mcgyvr.fleet import machine

    pieces = [
        "machine_id=",
        "machine_id=0123456789abcdef",
        "machine_id=zz",
        "host=",
        "host=box-5.example",
        "host=bad host",
        "cards=",
        "cards=none",
        "cards=nvidia-smi",
        "card=",
        "card=nvidia,0,8192,0,8192,Example",
        "card=nvidia,x,8192,0,8192,Example",
        "card=nvidia,0,,,,",
        "card=NV IDIA,0,1,1,1,x",
        "card=nvidia,1,1e3,0,0,Example",
        "holder=nvidia,0,12,300,p",
        "holder=nvidia,9,12,300,p",
        "holder=nvidia,0,x,300,p",
        "container=a,b,c,d",
        "container=a",
        "unread=",
        "unread=card.nvidia.0.total,",
        "unread=card.nvidia.0.total,why",
        "unread=bad key,why",
        "=",
        "no equals sign",
        "\x00\x01",
        "card=nvidia,0,8192,0,8192,Exa\u2028mple",
        "card=nvidia,0,8192,0,8192,Exa\u0085mple",
        "x" * 10_000,
    ]
    rng = random.Random(20260929)
    for _ in range(2000):
        text = "\n".join(rng.choice(pieces) for _ in range(rng.randint(0, 8)))
        reading = machine.parse(text)
        unread = {u.field for u in reading.unread}
        for card in reading.cards:
            key = f"card.{card.vendor}.{card.index}"
            for field, value in (
                ("name", card.name),
                ("total", card.total_mib),
                ("used", card.used_mib),
                ("free", card.free_mib),
                ("holders", card.holders),
            ):
                if value is None:
                    assert f"{key}.{field}" in unread, (text, key, field)
                elif field == "name":
                    assert isinstance(value, str)
                    assert value.isprintable(), text
                elif field != "holders":
                    assert isinstance(value, int) and value >= 0, text


def test_the_parser_names_a_line_it_does_not_know() -> None:
    from mcgyvr.fleet import machine

    reading = machine.parse("no equals sign\nsomething=else\n")
    assert [u.field for u in reading.unread].count("reading") == 2
