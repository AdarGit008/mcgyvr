"""Whatever a card tool prints ends as a value or as a named unread field.

What a tool on the machine prints is untrusted, and so is a reading that comes
back from another machine. A card name with a comma, a quote, a line break,
control characters or no end; a tool that prints nothing, garbage or half a
line, that waits, or that leaves a child holding its output; a size that is
not a number: each ends in the one reader's document
(:mod:`mcgyvr.serving.rigscan`) as a value read exactly, or as an empty field
listed as unread with a reason. No card is reported with a figure it did not
read, and the rig id (:func:`mcgyvr.fleet.ids.rig_id`), handed any document at
all, either names the machine or refuses by name — it never raises anything
else and never hashes a field that was not read.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any

import pytest

from tests.machinereader import MIB, Staged, reading, run, unread

#: A card as the reading holds it.
Card = dict[str, Any]


def _read(where: Path, **staged: Any) -> dict[str, Any]:
    ran = run(Staged(**staged), where)
    assert ran.returncode == 0, ran.stderr
    assert ran.unexpected == (), ran.unexpected
    return reading(ran.stdout)


def _cards(document: dict[str, Any]) -> dict[int, Card]:
    return {c["index"]: c for c in document["cards"]}


def _one(text: bytes, where: Path) -> dict[str, Any]:
    return _read(where, first_tool=text)


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
    document = _one(f"0, 7919, 100, 7819, {name}\n".encode(), tmp_path)
    card = _cards(document)[0]
    assert card["name"] == name.strip()
    assert card["total_mib"] == 7919
    assert unread(document) == {}


@pytest.mark.parametrize(
    ("line", "why"),
    [
        (b"0, 7919, 100, 7819, Example\x1bCard\n", "characters a name does not"),
        (b"0, 7919, 100, 7819, Example\x7fCard\n", "characters a name does not"),
        (b"0, 7919, 100, 7819, Exa\x00mple Card\n", "characters a name does not"),
        (b"0, 7919, 100, 7819, " + b"X" * 300 + b"\n", "longer"),
        (b"0, 7919, 100, 7819, \n", "no name"),
        (b"0, 7919, 100, 7819, Example\nCard\n", "line"),
    ],
    ids=["escape", "delete", "nul", "very-long", "empty", "line-break"],
)
def test_a_card_name_that_is_not_text_is_named_unread(
    line: bytes, why: str, tmp_path: Path
) -> None:
    document = _one(line, tmp_path)
    card = _cards(document)[0]
    assert card["name"] is None
    assert card["total_mib"] == 7919
    assert why in unread(document)["card.nvidia.0.name"]
    assert set(_cards(document)) == {0}


def test_the_reader_itself_prints_no_name_longer_than_its_bound(
    tmp_path: Path,
) -> None:
    """The reader, not only the rig id after it, holds back an over-long name:
    its document may be read by something other than the rig id."""
    long_name = "Example Card " + "X" * 300
    ran = run(
        Staged(first_tool=f"0, 7919, 100, 7819, {long_name}\n".encode()), tmp_path
    )
    assert ran.returncode == 0, ran.stderr
    assert "X" * 300 not in ran.stdout
    assert "longer than" in unread(reading(ran.stdout))["card.nvidia.0.name"]


def test_a_size_with_a_nul_byte_is_named_unread(tmp_path: Path) -> None:
    """A NUL a shell would drop is taken as the character it is."""
    document = _one(b"0, 79\x0019, 0, 7919, Example Card\n", tmp_path)
    assert _cards(document)[0]["total_mib"] is None
    assert "card.nvidia.0.total" in unread(document)


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
    document = _one(text, tmp_path)
    assert _cards(document) == {}
    assert "cards.nvidia-smi" in unread(document)


def test_a_tool_that_prints_nothing_gives_no_card_and_is_named(
    tmp_path: Path,
) -> None:
    document = _one(b"", tmp_path)
    assert _cards(document) == {}
    assert "printed no card" in unread(document)["cards.nvidia-smi"]


def test_a_line_longer_than_the_bound_is_refused_before_it_is_trimmed(
    tmp_path: Path,
) -> None:
    started = time.monotonic()
    line = b"0, 7919, 0, 7919, " + b" " * 200_000 + b"Example Card\n"
    document = _one(line, tmp_path)
    assert time.monotonic() - started < 20
    assert _cards(document) == {}
    assert "longer than" in unread(document)["cards.nvidia-smi"]


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
    document = reading(ran.stdout)
    assert "did not answer within 1 s" in unread(document)["cards.nvidia-smi"]
    assert document["machine"]["id"]


def test_a_tool_that_leaves_a_child_holding_its_output_is_given_up_on(
    tmp_path: Path,
) -> None:
    """The tool exits, but a child it started keeps its output open."""
    started = time.monotonic()
    ran = run(
        Staged(
            first_tool=b"0, 7919, 0, 7919, Example Card\n",
            first_tool_leaves_child=True,
            tool_seconds=1,
        ),
        tmp_path,
        give_up_after=20,
    )
    assert not ran.gave_up
    assert time.monotonic() - started < 20
    assert "cards.nvidia-smi" in unread(reading(ran.stdout))


def test_a_tool_that_prints_more_than_the_byte_bound_is_named(
    tmp_path: Path,
) -> None:
    """The bound is reached long before the line bounds, on lines of 3 KB."""
    started = time.monotonic()
    text = "".join(
        f"{i}, 7919, 0, 7919, Example Card {'X' * 3000}\n" for i in range(100)
    )
    document = _one(text.encode(), tmp_path)
    assert time.monotonic() - started < 20
    assert _cards(document) == {}
    why = unread(document)["cards.nvidia-smi"]
    assert "more than" in why
    assert "bytes" in why


def test_a_tool_that_prints_more_lines_than_the_bound_is_named(
    tmp_path: Path,
) -> None:
    document = _one(b"x\n" * 4097, tmp_path)
    assert _cards(document) == {}
    assert "more than 4096 lines" in unread(document)["cards.nvidia-smi"]


@pytest.mark.parametrize("name", ["[N/A]", "N/A"])
def test_a_name_the_tool_prints_as_not_available_is_unread(
    name: str, tmp_path: Path
) -> None:
    document = _one(f"0, 7919, 0, 7919, {name}\n".encode(), tmp_path)
    card = _cards(document)[0]
    assert (card["name"], card["total_mib"], card["used_mib"], card["free_mib"]) == (
        None,
        7919,
        0,
        7919,
    )
    assert "N/A" in unread(document)["card.nvidia.0.name"]


def test_a_tool_that_reads_standard_input_reads_nothing_of_the_reader(
    tmp_path: Path,
) -> None:
    document = _read(
        tmp_path,
        first_tool=b"0, 7919, 0, 7919, Example Card\n",
        first_tool_reads_stdin=True,
    )
    seen = tmp_path / "stubs" / ".nvidia-smi" / "stdin.seen"
    assert seen.read_bytes() == b""
    assert _cards(document)[0]["name"] == "Example Card"


def test_half_a_line_reads_what_it_holds_and_names_the_rest(tmp_path: Path) -> None:
    document = _one(b"0, 7919", tmp_path)
    card = _cards(document)[0]
    assert card["total_mib"] == 7919
    assert (card["used_mib"], card["free_mib"], card["name"]) == (None, None, None)
    assert {"card.nvidia.0.used", "card.nvidia.0.free", "card.nvidia.0.name"} <= set(
        unread(document)
    )


@pytest.mark.parametrize(
    "total",
    [b"8 GiB", b"-5", b"7919.5", b"99999999999999999999999", b"\xd9\xa1\xd9\xa2"],
    ids=["with-unit", "negative", "fraction", "too-large", "other-digits"],
)
def test_a_size_that_is_not_a_number_is_named_unread(
    total: bytes, tmp_path: Path
) -> None:
    document = _one(b"0, " + total + b", 100, 7819, Example Card\n", tmp_path)
    card = _cards(document)[0]
    assert card["total_mib"] is None
    assert card["name"] == "Example Card"
    assert unread(document)["card.nvidia.0.total"].strip()


def test_an_index_printed_twice_gives_neither_card(tmp_path: Path) -> None:
    text = b"0, 7919, 0, 7919, Example Card A\n0, 3001, 0, 3001, Example Card B\n"
    document = _one(text, tmp_path)
    assert _cards(document) == {}
    assert "twice" in unread(document)["card.nvidia.0"]


def test_a_stray_line_after_a_repeated_index_marks_no_other_cards_name(
    tmp_path: Path,
) -> None:
    text = (
        b"0, 7919, 0, 7919, Example Card A\n"
        b"1, 3001, 0, 3001, Example Card B\n"
        b"0, 2003, 0, 2003, Example Card C\n"
        b"a stray line\n"
    )
    document = _one(text, tmp_path)
    assert _cards(document)[1]["name"] == "Example Card B"
    assert "card.nvidia.1.name" not in unread(document)
    assert 0 not in _cards(document)


@pytest.mark.parametrize(
    "text",
    [b"not json", b"[1, 2]", b'{"card0": "flat"}', b'{"card0": {"x": 1}}', b""],
    ids=["not-json", "a-list", "flat-entry", "no-fields", "empty"],
)
def test_a_second_tool_that_prints_garbage_never_gives_a_wrong_card(
    text: bytes, tmp_path: Path
) -> None:
    document = _read(tmp_path, second_tool=text)
    for card in _cards(document).values():
        assert card["name"] is None
        assert card["total_mib"] is None
    assert unread(document)


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
    document = _read(tmp_path, second_tool=text)
    card = _cards(document)[3]
    assert card["name"] is None
    assert card["total_mib"] == 3001
    assert "card.amd.3.name" in unread(document)


def test_a_second_tool_reporting_more_used_than_total_names_free_unread(
    tmp_path: Path,
) -> None:
    text = json.dumps(
        {
            "card0": {
                "Card series": "Example Card S",
                "VRAM Total Memory (B)": str(3001 * MIB),
                "VRAM Total Used Memory (B)": str(3002 * MIB),
            }
        }
    ).encode()
    document = _read(tmp_path, second_tool=text)
    card = _cards(document)[0]
    assert (card["total_mib"], card["used_mib"], card["free_mib"]) == (3001, 3002, None)
    assert "more memory used" in unread(document)["card.amd.0.free"]


# The rig id, fed directly: a reading from another machine is untrusted.


def test_the_rig_id_never_raises_but_a_refusal_and_never_hashes_a_gap() -> None:
    """Over readings no reader printed, the rig id names the machine only from
    values a reading takes, and otherwise refuses with a ValueError."""
    from mcgyvr.fleet import ids

    good = {"vendor": "nvidia", "index": 0, "name": "Example", "total_mib": 7919}
    cards_: list[Any] = [
        good,
        {**good, "index": 1, "name": None},
        {**good, "index": 2, "total_mib": None},
        {**good, "index": 3, "total_mib": True},
        {**good, "index": 4, "total_mib": -5},
        {**good, "index": 5, "total_mib": "7919"},
        {**good, "index": 6, "name": "Exa\u2028mple"},
        {**good, "index": 7, "name": "Exa\u0085mple"},
        {**good, "index": 8, "name": "[N/A]"},
        {**good, "index": 9, "name": 12},
        "a card that is text",
        None,
    ]
    machines: list[Any] = [
        {"id": "0123456789abcdef"},
        {"id": "zz"},
        {"id": None},
        {},
        "a machine that is text",
        None,
    ]
    unreads: list[Any] = [
        [],
        [{"field": "machine_id", "why": "x"}],
        [{"field": "cards.nvidia-smi", "why": "x"}],
        [{"field": "card.nvidia.0", "why": "x"}],
        [{"field": "card.nvidia.0.total", "why": "x"}],
        ["not an entry"],
        "not a list",
    ]
    rng = random.Random(20260929)
    named = 0
    for _ in range(2000):
        chosen = rng.sample(cards_, rng.randint(0, 3))
        document: dict[str, Any] = {
            "machine": rng.choice(machines),
            "cards": chosen,
            "unread": rng.choice(unreads),
            "unsized": rng.choice([[], ["card.nvidia.2"], None]),
        }
        try:
            rig_id = ids.rig_id(document)
        except ValueError:
            continue
        named += 1
        assert rig_id.startswith("rig-")
        assert document["machine"] == {"id": "0123456789abcdef"}
        assert all(isinstance(c, dict) for c in chosen)
        for card in chosen:
            left_out = card["index"] == 2 and document["unsized"] == ["card.nvidia.2"]
            assert card == good or left_out, (card, document)
    assert named
