"""Every card the card tool prints is reported, or named in a note that says why.

The promise: no card disappears between the card tool's output and what
detection reports. A card whose name carries a comma is a card. A card whose
memory size the tool prints as not available is a card whose size is not
determined: it is listed, a note says its size is undetermined, and it takes no
part in sizing. A row that cannot be read at all is quoted in a note.

Every card here is invented, in name and in size.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcgyvr import detect
from mcgyvr.capability import load as load_table
from mcgyvr.detect import Backend, Detection, Gpu
from mcgyvr.initialize import InitError, initialize

MIB = 1024
#: The size of a card whose size is not determined. Typed loosely so this file
#: states the promise before the reader's types can carry it.
NO_SIZE: Any = None


def rows(*cards: tuple[str, str]) -> str:
    """The card tool's ``name,memory.total`` rows, without header or units."""
    return "".join(f"{name}, {size}\n" for name, size in cards)


def cards_read(monkeypatch: pytest.MonkeyPatch, output: str) -> tuple[Gpu, ...]:
    gpus, _notes = read(monkeypatch, output)
    return gpus


def read(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> tuple[tuple[Gpu, ...], tuple[str, ...]]:
    monkeypatch.setattr(
        detect,
        "_run",
        lambda command: output if command[0] == "nvidia-smi" else None,
        raising=True,
    )
    return detect.detect_gpus()


def accounted(gpus: tuple[Gpu, ...], notes: tuple[str, ...], row: str) -> bool:
    """Whether a printed row is a reported card or quoted in a note."""
    name = row.rsplit(",", 1)[0].strip()
    return any(g.name == name for g in gpus) or any(row.strip() in n for n in notes)


# --- a name with a comma is a card -----------------------------------------


def test_a_card_whose_name_has_a_comma_is_a_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpus = cards_read(monkeypatch, rows(("Inventa, Model Q-20", str(20 * MIB))))
    assert [(g.name, g.vram_gb) for g in gpus] == [("Inventa, Model Q-20", 20.0)]


def test_a_name_with_several_commas_is_one_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = rows(
        ("Inventa, Model Q, Rev 2", str(24 * MIB)), ("Plain X8", str(8 * MIB))
    )
    gpus = cards_read(monkeypatch, output)
    assert [(g.name, g.vram_gb) for g in gpus] == [
        ("Inventa, Model Q, Rev 2", 24.0),
        ("Plain X8", 8.0),
    ]


# --- a size that is not available is a card of undetermined size ------------


def test_a_card_whose_size_is_not_available_is_listed_without_a_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpus, notes = read(monkeypatch, rows(("Inventa Shared V", "[N/A]")))
    assert [(g.name, g.vram_gb) for g in gpus] == [("Inventa Shared V", None)]
    said = [n for n in notes if n.startswith(detect.GPU_SIZE_UNDETERMINED)]
    assert len(said) == 1
    assert "Inventa Shared V" in said[0]


def test_a_card_of_undetermined_size_takes_no_part_in_sizing() -> None:
    sized = Gpu("Inventa Q-20", 20.0, "invented")
    unsized = Gpu("Inventa Shared V", NO_SIZE, "invented")
    assert Detection(gpus=(unsized, sized)).largest_vram_gb == 20.0
    assert Detection(gpus=(sized, unsized)).largest_vram_gb == 20.0
    assert Detection(gpus=(unsized,)).largest_vram_gb is None
    assert Detection(gpus=(unsized, unsized)).largest_vram_gb is None


def test_a_machine_whose_only_card_has_no_size_still_has_a_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpus, notes = read(monkeypatch, rows(("Inventa Shared V", "[N/A]")))
    found = Detection(gpus=gpus, notes=notes)
    assert found.has_gpu
    assert found.largest_vram_gb is None
    assert not any("reported no device" in n for n in notes)


# --- a row that cannot be read is quoted, never dropped ---------------------


def test_a_row_that_cannot_be_read_is_quoted_in_a_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = rows(("Plain X8", str(8 * MIB))) + "a row with no size at all\n"
    gpus, notes = read(monkeypatch, output)
    assert [g.name for g in gpus] == ["Plain X8"]
    unread = [n for n in notes if n.startswith(detect.GPU_ROW_UNREAD)]
    assert len(unread) == 1
    assert "a row with no size at all" in unread[0]


def test_a_mix_accounts_for_every_printed_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    printed = [
        f"Plain X8, {8 * MIB}",
        f"Inventa, Model Q-20, {20 * MIB}",
        "Inventa Shared V, [N/A]",
        f"Inventa W-24, {24 * MIB}",
        "Inventa Broken, not-a-size",
    ]
    gpus, notes = read(monkeypatch, "\n".join(printed) + "\n")
    for row in printed:
        assert accounted(gpus, notes, row), f"{row!r} disappeared"
    assert len(gpus) == 4
    assert Detection(gpus=gpus).largest_vram_gb == 24.0


def test_rows_that_parse_today_read_as_they_did(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gpus, notes = read(
        monkeypatch, rows(("Plain X8", str(8 * MIB)), ("Inventa W-24", str(24 * MIB)))
    )
    assert notes == ()
    assert [(g.name, g.vram_gb) for g in gpus] == [
        ("Plain X8", 8.0),
        ("Inventa W-24", 24.0),
    ]


def test_the_notes_travel_into_the_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = rows(("Inventa Shared V", "[N/A]")) + "garbled\n"
    monkeypatch.setattr(
        detect,
        "_run",
        lambda command: output if command[0] == "nvidia-smi" else None,
        raising=True,
    )
    monkeypatch.setattr(detect, "_get_json", lambda url, timeout: None, raising=True)
    found = detect.detect()
    assert [g.name for g in found.gpus] == ["Inventa Shared V"]
    assert any(n.startswith(detect.GPU_SIZE_UNDETERMINED) for n in found.notes)
    assert any(n.startswith(detect.GPU_ROW_UNREAD) for n in found.notes)


# --- the callers say it too -------------------------------------------------


def _unsized_machine(models: tuple[str, ...]) -> Detection:
    return Detection(
        gpus=(Gpu("Inventa Shared V", NO_SIZE, "invented"),),
        cpu_count=3,
        ram_gb=20.0,
        backends=(
            Backend("llama-server", "http://localhost:8080", "openai", models, "probe"),
        ),
    )


def test_init_on_a_card_of_undetermined_size_says_so(tmp_path: Path) -> None:
    table = load_table()
    measured = tuple(m.id for m in table.models if m.is_measured)
    found = _unsized_machine(measured)
    try:
        result = initialize(tmp_path / "setup", detection=found, table=table)
    except InitError as refused:
        text = str(refused)
    else:
        text = " ".join(result.decisions)
    assert "Inventa Shared V" in text
    assert "not determined" in text


def test_a_refusal_on_a_card_of_undetermined_size_does_not_say_there_is_no_card(
    tmp_path: Path,
) -> None:
    found = Detection(gpus=(Gpu("Inventa Shared V", NO_SIZE, "invented"),))
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=found, table=load_table())
    assert "no GPU this build can see" not in str(refused.value)
    assert "not determined" in str(refused.value)
