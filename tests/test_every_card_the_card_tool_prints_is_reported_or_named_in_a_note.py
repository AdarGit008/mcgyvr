"""Every card the card tool prints is reported, or named in a note that says why.

The promise: no card disappears between the card tool's output and what
detection reports. A card whose name carries a comma is a card. A card whose
memory size the tool prints as not available is a card whose size is not
determined: it is listed, a note says its size is undetermined, and it takes no
part in sizing. A row that cannot be read at all is quoted in a note, and the
quote is of bounded length, whatever the row's.

What the commands say holds to the same promise. ``mcgyvr detect`` prints every
card and every note. ``mcgyvr init`` names every card it found, of known size or
not, in its decisions and in the comment it writes into the setup, and binds
what a server lists whatever the cards. When nothing is listed it refuses, the
refusal names each card whose size is not determined as such, and it offers
the fix that applies: a unit bound by hand, which states the card room it needs.

Every card here is invented, in name and in size; the machines init runs on
are the generator's (:mod:`tests.machine_shapes`).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, detect
from mcgyvr.config import FLEET_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.detect import Detection, Gpu
from mcgyvr.initialize import InitError, initialize
from tests.machine_shapes import Card, Shape, detection, shape, shapes, with_server

MIB = detect.MIB_PER_GB
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
    assert "by hand" in said[0]
    assert "room_mib" in said[0], "the note says how, as the refusal does"


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
    unread = [n for n in notes if n.startswith(detect.GPU_ROW_NOT_READ)]
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
    assert any(n.startswith(detect.GPU_ROW_NOT_READ) for n in found.notes)


# --- a quoted row is of bounded length --------------------------------------


def test_a_note_quotes_a_bounded_part_of_a_huge_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = detect.ROW_QUOTED_AT_MOST
    huge = "x" * 100_000
    _gpus, notes = read(monkeypatch, f"{huge}\n{huge}, [N/A]\n")
    assert len(notes) == 2
    for note in notes:
        assert len(note) <= bound * 2 + 300, note[:120]


# --- the detect command prints every card and every note --------------------


def test_the_detect_command_prints_every_card_and_every_note(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = (
        rows(("Plain X8", str(8 * MIB)), ("Inventa Shared V", "[N/A]"))
        + "Inventa Broken, not-a-size\n"
    )
    monkeypatch.setattr(
        detect,
        "_run",
        lambda command: output if command[0] == "nvidia-smi" else None,
        raising=True,
    )
    monkeypatch.setattr(detect, "_get_json", lambda url, timeout: None, raising=True)
    monkeypatch.setattr(
        detect, "detect_ram_gb", lambda: (None, "invented"), raising=True
    )
    monkeypatch.setattr(
        detect, "detect_docker", lambda: (False, "invented"), raising=True
    )
    gpus, notes = detect.detect_gpus()

    assert cli.main(["detect"]) == 0
    printed = capsys.readouterr().out.splitlines()

    assert [g.name for g in gpus] == ["Plain X8", "Inventa Shared V"]
    assert gpus[1].size == Gpu("Inventa Shared V", NO_SIZE, "invented").size
    for gpu in gpus:
        assert f"  {gpu.name} — {gpu.size}  ({gpu.how})" in printed
    assert any(n.startswith(detect.GPU_SIZE_UNDETERMINED) for n in notes)
    assert any(n.startswith(detect.GPU_ROW_NOT_READ) for n in notes)
    for note in notes:
        assert f"  - {note}" in printed


# --- what init says of the cards ---------------------------------------------


def _card_of_undetermined_size() -> Card:
    """A card of the generator whose size the card tool prints as not available."""
    return next(
        card
        for machine in shapes()
        for card in machine.cards
        if card.card_reader_reads and card.total_mib is None
    )


def _only_unsized(count: int = 1) -> Shape:
    """A machine here whose only cards are of undetermined size."""
    card = _card_of_undetermined_size()
    return dataclasses.replace(
        shape("one-card"),
        cards=tuple(dataclasses.replace(card, index=i) for i in range(count)),
    )


def _serving(machine: Shape, *models: str) -> Shape:
    """The machine with one more server, listing ``models`` (maybe none)."""
    taken = {server.kind for server in machine.servers}
    kind = next(k for k, _, _ in detect.PORT_CONVENTIONS if k not in taken)
    return with_server(machine, kind=kind, models=models)


def _refusal(tmp_path: Path, found: Detection) -> str:
    """The refusal's words, with its line wrapping read as plain spaces."""
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=found)
    assert not (tmp_path / "setup").exists()
    return " ".join(str(refused.value).split())


@pytest.mark.parametrize(
    "label", ["unreadable-size", "unreadable-size-first", "several-sizes"]
)
def test_init_names_every_card_it_found_whatever_its_size(
    tmp_path: Path, label: str
) -> None:
    """In the decisions and in the comment written into the setup, in the
    order the card tool printed them, with no claim that a card sizes a unit."""
    found = detection(_serving(shape(label), "example-model"))
    assert found.gpus

    path = tmp_path / "setup"
    result = initialize(path, detection=found)

    said = [d for d in result.decisions if d.startswith("GPU ")]
    assert said == [f"GPU {g.name} with {g.size}, via {g.how}." for g in found.gpus]
    assert not any("sized against" in d for d in result.decisions)
    written = " ".join(
        line.lstrip("#").strip()
        for line in (path / FLEET_FILENAME).read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    )
    for gpu in found.gpus:
        assert f"GPU {gpu.name} with {gpu.size}" in written


@pytest.mark.parametrize("remote_lists", [False, True], ids=["nothing", "a-model"])
def test_a_card_line_speaks_of_remote_rungs_only_when_a_rung_is_remote(
    tmp_path: Path, remote_lists: bool
) -> None:
    """A card here beside a server on another machine: the card lines say the
    remote rungs do not run on this card exactly when a remote rung is bound."""
    here = _serving(shape("unreadable-size"), "example-model-here")
    far = next(m for m in shapes() if not m.local and m.servers)
    models = ("example-model-there",) if remote_lists else ()
    far = dataclasses.replace(
        far, servers=tuple(dataclasses.replace(s, models=models) for s in far.servers)
    )
    found = detection(here, reached=(far,))
    assert found.gpus and found.has_remote_backend

    result = initialize(tmp_path / "setup", detection=found)
    cards = [d for d in result.decisions if d.startswith("GPU ")]
    assert len(cards) == len(found.gpus)
    for line in cards:
        assert ("remote rungs" in line) is remote_lists, line


@pytest.mark.parametrize(
    "machine",
    [_only_unsized(), shape("bare")],
    ids=["a card of undetermined size", "no card"],
)
def test_init_does_not_refuse_while_a_server_lists_a_model(
    tmp_path: Path, machine: Shape
) -> None:
    result = initialize(
        tmp_path / "setup", detection=detection(_serving(machine, "example-model"))
    )
    assert result.written
    units = load_config(result.path).units
    assert [u.model for u in units.values()] == ["example-model"]


# --- the refusal says what is true of each server and each card -------------


def test_a_refusal_on_a_card_of_undetermined_size_names_the_card(
    tmp_path: Path,
) -> None:
    """Nothing is listed, so init refuses; the card is named as it is."""
    card = _card_of_undetermined_size()
    text = _refusal(tmp_path, detection(_serving(_only_unsized())))
    assert card.name in text
    assert "not determined" in text


def test_the_refusal_on_a_card_of_undetermined_size_names_the_fix_that_applies(
    tmp_path: Path,
) -> None:
    """A unit bound by hand states the card room it needs: that is a fix."""
    text = _refusal(tmp_path, detection(_serving(_only_unsized())))
    assert "room_mib" in text
    assert "by hand" in text
    assert "start a local backend" not in text, "one is already answering"


def test_a_refusal_on_a_card_of_undetermined_size_does_not_say_there_is_no_card(
    tmp_path: Path,
) -> None:
    text = _refusal(tmp_path, detection(_only_unsized()))
    assert "no GPU this build can see" not in text
    assert "not determined" in text


def test_a_refusal_over_a_remote_server_says_it_lists_nothing(tmp_path: Path) -> None:
    """A server on another machine is not "on this machine", and its card is
    not why nothing was bound: it lists no model, and the refusal says so."""
    far = next(m for m in shapes() if not m.local and m.servers)
    far = dataclasses.replace(
        far, servers=tuple(dataclasses.replace(s, models=()) for s in far.servers)
    )
    found = detection(far)
    assert found.backends and not any(b.is_local for b in found.backends)

    text = _refusal(tmp_path, found)
    assert "on this machine" not in text
    named = ", ".join(f"{b.name} at {b.base_url}" for b in found.backends)
    assert f"Reachable model servers: {named} — but none of them lists a model." in text


def test_the_refusal_speaks_of_one_or_several_servers_and_cards(
    tmp_path: Path,
) -> None:
    card = _card_of_undetermined_size().name
    one = _refusal(tmp_path / "one", detection(_serving(_only_unsized(1))))
    assert f"the memory size of {card} was not determined" in one
    assert "against it" not in one, "init sizes nothing against any card"

    machine = _serving(_serving(_only_unsized(2)))
    found = detection(machine)
    several = _refusal(tmp_path / "several", found)
    assert f"the memory sizes of {card} and {card} were not determined" in several
    named = ", ".join(f"{b.name} at {b.base_url}" for b in found.backends)
    assert f"Reachable model servers: {named} —" in several


def test_the_by_hand_fix_is_offered_beside_a_card_of_known_size(
    tmp_path: Path,
) -> None:
    """A card of known size and a card of undetermined size, and nothing
    listed: the unsized card is named, and a unit may be bound by hand."""
    text = _refusal(tmp_path, detection(_serving(shape("unreadable-size"))))
    assert _card_of_undetermined_size().name in text
    assert "room_mib" in text
    assert "by hand" in text


def test_the_by_hand_fix_is_offered_with_no_card_and_a_local_server(
    tmp_path: Path,
) -> None:
    text = _refusal(tmp_path, detection(_serving(shape("bare"))))
    assert "room_mib" in text
    assert "by hand" in text
    # One wording for a machine without a card: the situation and the fix
    # say it alike.
    assert text.count("no GPU this build can see") == 2


def test_the_by_hand_fix_is_offered_for_an_unsized_card_with_no_backend(
    tmp_path: Path,
) -> None:
    """With no backend answering, a unit bound by hand may still name the one
    the user starts, and the card is still named as of undetermined size."""
    text = _refusal(tmp_path, detection(_only_unsized()))
    assert "bind a unit by hand" in text
    assert "room_mib" in text


def test_the_by_hand_fix_is_not_offered_with_no_card_and_no_backend(
    tmp_path: Path,
) -> None:
    text = _refusal(tmp_path, detection(shape("bare")))
    assert "room_mib" not in text
