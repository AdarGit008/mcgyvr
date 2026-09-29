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
import time
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
    reading = _one(f"0, 7919, 100, 7819, {name}\n".encode(), tmp_path)
    card = _cards(reading)[0]
    assert card.name == name.strip()
    assert card.total_mib == 7919
    assert _unread(reading) == {}


@pytest.mark.parametrize(
    ("line", "why"),
    [
        (b"0, 7919, 100, 7819, Example\x1bCard\n", "control"),
        (b"0, 7919, 100, 7819, Example\x7fCard\n", "control"),
        (b"0, 7919, 100, 7819, " + b"X" * 300 + b"\n", "longer"),
        (b"0, 7919, 100, 7819, \n", "no name"),
        (b"0, 7919, 100, 7819, Example\nCard\n", "line"),
    ],
    ids=["escape", "delete", "very-long", "empty", "line-break"],
)
def test_a_card_name_that_is_not_text_is_named_unread(
    line: bytes, why: str, tmp_path: Path
) -> None:
    reading = _one(line, tmp_path)
    card = _cards(reading)[0]
    assert card.name is None
    assert card.total_mib == 7919
    assert why in _unread(reading)["card.nvidia.0.name"]
    assert set(_cards(reading)) == {0}


def test_the_reader_itself_prints_no_name_longer_than_its_bound(
    tmp_path: Path,
) -> None:
    """The reader, not only the parser after it, holds back an over-long name.

    The parser's input may come from elsewhere and the reader's output may be
    read by something other than this parser, so each keeps the bound.
    """
    from mcgyvr.fleet import machine

    long_name = "Example Card " + "X" * 300
    ran = run(
        Staged(
            first_tool=f"0, 7919, 100, 7819, {long_name}\n".encode(),
            first_tool_processes={0: (b"", 0)},
        ),
        tmp_path,
    )
    assert ran.returncode == 0, ran.stderr
    assert "X" * 300 not in ran.stdout
    reading = machine.parse(ran.stdout)
    assert "printed a name longer than" in _unread(reading)["card.nvidia.0.name"]


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


def test_a_tool_that_prints_nothing_gives_no_card_and_is_named(
    tmp_path: Path,
) -> None:
    reading = _one(b"", tmp_path)
    assert _cards(reading) == {}
    assert "printed no card" in _unread(reading)["cards.nvidia-smi"]


def test_a_line_longer_than_the_bound_is_refused_before_it_is_trimmed(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    line = b"0, 7919, 0, 7919, " + b" " * 200_000 + b"Example Card\n"
    reading = _one(line, tmp_path)
    assert time.monotonic() - started < 20
    assert _cards(reading) == {}
    assert "longer than" in _unread(reading)["cards.nvidia-smi"]


def test_a_tool_that_waits_is_given_up_on_and_named(tmp_path: Path) -> None:
    started = time.monotonic()
    ran = run(
        Staged(
            first_tool=b"0, 7919, 0, 7919, Example Card\n",
            first_tool_waits=True,
            tool_seconds=1,
        ),
        tmp_path,
    )
    assert time.monotonic() - started < 20
    assert not ran.gave_up
    from mcgyvr.fleet import machine

    reading = machine.parse(ran.stdout)
    assert "did not answer within 1 s" in _unread(reading)["cards.nvidia-smi"]
    assert reading.machine_id is not None


def test_a_tool_that_leaves_a_child_holding_its_output_is_given_up_on(
    tmp_path: Path,
) -> None:
    """The tool exits, but a child it started keeps its output open."""
    started = time.monotonic()
    ran = run(
        Staged(
            first_tool=b"0, 7919, 0, 7919, Example Card\n",
            first_tool_processes={0: (b"", 0)},
            first_tool_leaves_child=True,
            tool_seconds=1,
        ),
        tmp_path,
        give_up_after=20,
    )
    assert not ran.gave_up
    assert time.monotonic() - started < 20
    from mcgyvr.fleet import machine

    reading = machine.parse(ran.stdout)
    assert "cards.nvidia-smi" in _unread(reading)


def test_a_tool_that_prints_more_than_the_byte_bound_is_named(
    tmp_path: Path,
) -> None:
    """The bound is reached long before the line bounds, on lines of 3 KB."""
    started = time.monotonic()
    text = "".join(
        f"{i}, 7919, 0, 7919, Example Card {'X' * 3000}\n" for i in range(100)
    )
    reading = _one(text.encode(), tmp_path)
    assert time.monotonic() - started < 20
    assert _cards(reading) == {}
    why = _unread(reading)["cards.nvidia-smi"]
    assert "more than" in why
    assert "bytes" in why


def test_a_tool_that_prints_more_lines_than_the_bound_is_named(
    tmp_path: Path,
) -> None:
    reading = _one(b"x\n" * 4097, tmp_path)
    assert _cards(reading) == {}
    assert "more than 4096 lines" in _unread(reading)["cards.nvidia-smi"]


def test_an_idle_card_that_says_so_has_no_holder_and_nothing_unread(
    tmp_path: Path,
) -> None:
    reading = _one(
        b"0, 7919, 0, 7919, Example Card\n",
        tmp_path,
        processes=b"No running processes found\n",
    )
    assert _cards(reading)[0].holders == ()
    assert _unread(reading) == {}


@pytest.mark.parametrize("name", ["[N/A]", "N/A"])
def test_a_name_the_tool_prints_as_not_available_is_unread(
    name: str, tmp_path: Path
) -> None:
    reading = _one(f"0, 7919, 0, 7919, {name}\n".encode(), tmp_path)
    assert _cards(reading)[0].name is None
    assert "N/A" in _unread(reading)["card.nvidia.0.name"]


def test_a_container_id_that_is_not_one_leaves_the_containers_unread(
    tmp_path: Path,
) -> None:
    """It never becomes a field name the reading cannot hold."""
    reading = _read(tmp_path, containers=b"abc/def|example-unit|example\n")
    assert reading.containers is None
    assert "containers" in _unread(reading)
    assert "reading" not in _unread(reading)


def test_a_caller_that_gives_up_still_holds_the_machine_id_and_host(
    tmp_path: Path,
) -> None:
    ran = run(
        Staged(
            first_tool=b"0, 7919, 0, 7919, Example Card\n",
            first_tool_waits=True,
            timeout_program=False,
        ),
        tmp_path,
        give_up_after=3,
    )
    assert ran.gave_up
    lines = ran.stdout.splitlines()
    assert any(line.startswith("machine_id=") and len(line) > 11 for line in lines)
    assert "host=box-1.example" in lines


@pytest.mark.parametrize("bounded", [True, False], ids=["timeout", "no-timeout"])
def test_a_tool_that_reads_standard_input_reads_nothing_of_the_reader(
    bounded: bool, tmp_path: Path
) -> None:
    ran = run(
        Staged(
            first_tool=b"0, 7919, 0, 7919, Example Card\n",
            first_tool_processes={0: (b"", 0)},
            first_tool_reads_stdin=True,
            timeout_program=bounded,
        ),
        tmp_path,
    )
    seen = tmp_path / "stubs" / ".nvidia-smi" / "stdin.seen"
    assert seen.read_bytes() == b""
    assert "card=nvidia,0,7919,0,7919,Example Card" in ran.stdout.splitlines()


def test_half_a_line_reads_what_it_holds_and_names_the_rest(tmp_path: Path) -> None:
    reading = _one(b"0, 7919", tmp_path)
    card = _cards(reading)[0]
    assert card.total_mib == 7919
    assert (card.used_mib, card.free_mib, card.name) == (None, None, None)
    unread = _unread(reading)
    assert {"card.nvidia.0.used", "card.nvidia.0.free", "card.nvidia.0.name"} <= set(
        unread
    )


@pytest.mark.parametrize(
    "total",
    [b"8 GiB", b"-5", b"7919.5", b"99999999999999999999999", b"\xd9\xa1\xd9\xa2"],
    ids=["with-unit", "negative", "fraction", "too-large", "other-digits"],
)
def test_a_size_that_is_not_a_number_is_named_unread(
    total: bytes, tmp_path: Path
) -> None:
    reading = _one(b"0, " + total + b", 100, 7819, Example Card\n", tmp_path)
    card = _cards(reading)[0]
    assert card.total_mib is None
    assert card.name == "Example Card"
    assert _unread(reading)["card.nvidia.0.total"].strip()


def test_an_index_printed_twice_gives_neither_card(tmp_path: Path) -> None:
    text = b"0, 7919, 0, 7919, Example Card A\n0, 3001, 0, 3001, Example Card B\n"
    reading = _read(tmp_path, first_tool=text, first_tool_processes={0: (b"", 0)})
    assert _cards(reading) == {}
    assert "twice" in _unread(reading)["card.nvidia.0"]


def test_a_stray_line_after_a_repeated_index_marks_no_other_cards_name(
    tmp_path: Path,
) -> None:
    text = (
        b"0, 7919, 0, 7919, Example Card A\n"
        b"1, 3001, 0, 3001, Example Card B\n"
        b"0, 2003, 0, 2003, Example Card C\n"
        b"a stray line\n"
    )
    reading = _read(tmp_path, first_tool=text, first_tool_processes={1: (b"", 0)})
    assert _cards(reading)[1].name == "Example Card B"
    assert "card.nvidia.1.name" not in _unread(reading)
    assert 0 not in _cards(reading)


def test_a_process_name_with_spaces_and_commas_is_read_exactly(
    tmp_path: Path,
) -> None:
    reading = _one(
        b"0, 7919, 300, 7619, Example Card\n",
        tmp_path,
        processes=b"4242, 300, /opt/example tool/serve --flag a,b\n",
    )
    holders = _cards(reading)[0].holders
    assert holders is not None
    (holder,) = holders
    assert (holder.pid, holder.mib, holder.name) == (
        4242,
        300,
        "/opt/example tool/serve --flag a,b",
    )


def test_a_process_whose_memory_is_not_available_names_it_unread(
    tmp_path: Path,
) -> None:
    reading = _one(
        b"0, 7919, 300, 7619, Example Card\n",
        tmp_path,
        processes=b"4242, [N/A], example-process\n",
    )
    holders = _cards(reading)[0].holders
    assert holders is not None
    (holder,) = holders
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
    reading = _one(b"0, 7919, 300, 7619, Example Card\n", tmp_path, processes)
    card = _cards(reading)[0]
    assert card.name == "Example Card"
    if b"bad" in processes:
        assert card.holders is not None
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
                "VRAM Total Memory (B)": str(3001 * MIB),
                "VRAM Total Used Memory (B)": "0",
            }
        }
    ).encode()
    reading = _read(tmp_path, second_tool=text)
    card = _cards(reading)[3]
    assert card.name is None
    assert card.total_mib == 3001
    assert "card.amd.3.name" in _unread(reading)


@pytest.mark.parametrize(
    "listing",
    [
        b"a" * 64 + b"|example\x1b[31mred|p\n",
        b"a" * 64 + b"|example\rone|p\n",
        b"a" * 64 + b"|example|" + b"L" * 5000 + b"\n",
        b"a" * 64 + b"|example|" + b"L" * 300 + b"\n",
    ],
    ids=[
        "escape-sequence",
        "carriage-return",
        "over-the-line-bound",
        "over-the-name-bound",
    ],
)
def test_a_container_value_that_is_not_text_leaves_the_containers_unread(
    listing: bytes, tmp_path: Path
) -> None:
    ran = run(Staged(containers=listing, restarts={"a" * 64: b"0\n"}), tmp_path)
    assert not [
        line for line in ran.stdout.splitlines() if line.startswith("container=")
    ]
    assert "\x1b" not in ran.stdout and "\r" not in ran.stdout
    from mcgyvr.fleet import machine

    reading = machine.parse(ran.stdout)
    assert reading.containers is None
    assert "containers" in _unread(reading)


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
        "card=nvidia,0,7919,0,7919,Example",
        "card=nvidia,x,7919,0,7919,Example",
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
        "card=nvidia,0,7919,0,7919,Exa\u2028mple",
        "card=nvidia,0,7919,0,7919,Exa\u0085mple",
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
