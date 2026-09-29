"""Every card the card tool prints is reported, or named in a note that says why.

The promise: no card disappears between the card tool's output and what
detection reports. A card whose name carries a comma is a card. A card whose
memory size the tool prints as not available is a card whose size is not
determined: it is listed, a note says its size is undetermined, and it takes no
part in sizing. A row that cannot be read at all is quoted in a note, and the
quote is of bounded length, whatever the row's.

What the commands say holds to the same promise. ``mcgyvr detect`` prints every
card and every note. ``mcgyvr init`` on a machine with cards of known and of
undetermined size names the card it sized against, and states each card whose
size is not determined, in its decisions and in the comment it writes into the
setup. On a machine whose only cards are of undetermined size it refuses, and
the refusal names the fix that applies: a unit bound by hand, which states the
card room it needs.

Every card here is invented, in name and in size.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import cli, detect
from mcgyvr.capability import load as load_table
from mcgyvr.config import FLEET_FILENAME
from mcgyvr.config import load as load_config
from mcgyvr.detect import Backend, Detection, Gpu
from mcgyvr.initialize import InitError, _sources_for, initialize
from mcgyvr.propose import propose
from tests.machine_shapes import Server, detection, shape, with_server

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


def test_init_on_a_card_of_undetermined_size_refuses_and_says_so(
    tmp_path: Path,
) -> None:
    """No model is sized against a card whose size nobody read, so init has
    nothing it may bind on this machine's own card, and refuses."""
    table = load_table()
    measured = tuple(m.id for m in table.models if m.is_measured)
    found = _unsized_machine(measured)
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=found, table=table)
    text = str(refused.value)
    assert "Inventa Shared V" in text
    assert "not determined" in text
    assert not (tmp_path / "setup").exists()


def test_the_refusal_on_a_card_of_undetermined_size_names_the_fix_that_applies(
    tmp_path: Path,
) -> None:
    """A unit bound by hand states the card room it needs: that is the fix."""
    table = load_table()
    measured = tuple(m.id for m in table.models if m.is_measured)
    with pytest.raises(InitError) as refused:
        initialize(
            tmp_path / "setup", detection=_unsized_machine(measured), table=table
        )
    text = str(refused.value)
    assert "room_mib" in text
    assert "by hand" in text
    assert "start a local backend" not in text, "one is already answering"


@pytest.mark.parametrize(
    "gpus",
    [(Gpu("Inventa Shared V", NO_SIZE, "invented"),), ()],
    ids=["a card of undetermined size", "no card"],
)
def test_a_refusal_does_not_say_no_backend_holds_a_model_when_one_does(
    tmp_path: Path, gpus: tuple[Gpu, ...]
) -> None:
    table = load_table()
    measured = tuple(m.id for m in table.models if m.is_measured)
    found = Detection(
        gpus=gpus,
        backends=(
            Backend(
                "llama-server", "http://localhost:8080", "openai", measured, "probe"
            ),
        ),
    )
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=found, table=table)
    assert "none of them reports holding" not in str(refused.value)


def test_a_refusal_on_a_card_of_undetermined_size_does_not_say_there_is_no_card(
    tmp_path: Path,
) -> None:
    found = Detection(gpus=(Gpu("Inventa Shared V", NO_SIZE, "invented"),))
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=found, table=load_table())
    assert "no GPU this build can see" not in str(refused.value)
    assert "not determined" in str(refused.value)


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


# --- init names the card it sized against, and the one it could not ---------


@pytest.mark.parametrize("label", ["unreadable-size", "unreadable-size-first"])
def test_init_names_the_card_it_sized_against_and_the_cards_it_could_not(
    tmp_path: Path, label: str
) -> None:
    """In the decisions, in the comment written into the setup, and in the
    units: one card, the one sizing used, whichever order the tool prints."""
    machine = shape(label)
    kind = detect.PORT_CONVENTIONS[0][0]
    found = detection(with_server(machine, kind=kind, models=("example-model",)))
    sized = [g for g in found.gpus if g.vram_gb is not None]
    unsized = [g for g in found.gpus if g.vram_gb is None]
    assert sized and unsized, "the shape has cards of both kinds"
    largest = max(sized, key=lambda g: g.vram_gb or 0.0)

    path = tmp_path / "setup"
    result = initialize(path, detection=found, table=load_table())

    said = [d for d in result.decisions if d.startswith("GPU ")]
    assert len(said) == len(sized[:1]) + len(unsized)
    assert said[0].startswith(f"GPU {largest.name} with {largest.size}")
    for gpu in unsized:
        line = [d for d in said if d.startswith(f"GPU {gpu.name} ")]
        assert len(line) == 1
        assert line[0].startswith(f"GPU {gpu.name} with {gpu.size}")
    written = " ".join(
        line.lstrip("#").strip()
        for line in (path / FLEET_FILENAME).read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    )
    for gpu in (largest, *unsized):
        assert f"GPU {gpu.name} with {gpu.size}" in written
    units = load_config(path).data["units"]
    assert units, "a unit is sized against the card of known size"
    card_mib = (largest.vram_gb or 0.0) * MIB
    for name, unit in units.items():
        assert unit.get("room_mib", 0) <= card_mib, name


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


# --- the refusal says what is true of each backend and each card ------------


def _refusal(tmp_path: Path, found: Detection) -> str:
    """The refusal's words, with its line wrapping read as plain spaces."""
    with pytest.raises(InitError) as refused:
        initialize(tmp_path / "setup", detection=found, table=load_table())
    return " ".join(str(refused.value).split())


def test_a_refusal_over_a_remote_holder_says_why_its_model_is_not_bound(
    tmp_path: Path,
) -> None:
    """A backend on another machine is not "on this machine", and its card is
    not why nothing was bound: the refusal gives the reason the proposal gave."""
    table = load_table()
    model = next(m for m in table.models if m.is_measured and m.requires_backend)
    kind, port, _ = next(
        c for c in detect.PORT_CONVENTIONS if c[0] != model.requires_backend
    )
    far = shape("bare-remote-server")
    machine = dataclasses.replace(
        far,
        servers=(Server(kind=kind, host=far.host, port=port, models=(model.id,)),),
    )
    found = detection(machine)
    assert found.backends and not any(b.is_local for b in found.backends)
    rejected = {
        r.model: r.reason
        for r in propose(
            table, vram_gb=found.largest_vram_gb, sources=_sources_for(found)
        ).rejected
    }

    text = _refusal(tmp_path, found)
    assert "on this machine" not in text
    assert model.id in text
    assert " ".join(rejected[model.id].split()) in text


def _holders(*names_and_ports: tuple[str, int]) -> tuple[Backend, ...]:
    table = load_table()
    held = tuple(m.id for m in table.models if m.is_measured)
    return tuple(
        Backend(name, f"http://localhost:{port}", "openai", held, "probe")
        for name, port in names_and_ports
    )


def test_the_refusal_speaks_of_one_or_several_holders_and_cards(
    tmp_path: Path,
) -> None:
    one = _refusal(
        tmp_path / "one",
        Detection(
            gpus=(Gpu("Inventa P", NO_SIZE, "invented"),),
            backends=_holders(("llama-server", 8080)),
        ),
    )
    assert "llama-server reports holding" in one
    assert "the memory size of Inventa P was not determined" in one
    assert "against it." in one

    several = _refusal(
        tmp_path / "several",
        Detection(
            gpus=(
                Gpu("Inventa P", NO_SIZE, "invented"),
                Gpu("Inventa Q", NO_SIZE, "invented"),
            ),
            backends=_holders(("llama-server", 8080), ("lmstudio", 1234)),
        ),
    )
    assert "llama-server and lmstudio report holding" in several
    assert "the memory sizes of Inventa P and Inventa Q were not determined" in (
        several
    )
    assert "against them." in several
    assert "reports holding" not in several


def test_the_by_hand_fix_is_offered_beside_a_card_too_small(tmp_path: Path) -> None:
    """A sized card too small for any model, and a card of undetermined size:
    the unsized card is named, and a unit may be bound to it by hand."""
    table = load_table()
    smallest = min(m.vram_gb_working for m in table.models)
    found = Detection(
        gpus=(
            Gpu("Inventa Tiny", smallest / 4, "invented"),
            Gpu("Inventa Shared V", NO_SIZE, "invented"),
        ),
        backends=_holders(("llama-server", 8080)),
    )
    text = _refusal(tmp_path, found)
    assert "Inventa Shared V" in text
    assert "room_mib" in text
    assert "by hand" in text


def test_the_by_hand_fix_is_offered_with_no_card_and_a_local_holder(
    tmp_path: Path,
) -> None:
    text = _refusal(tmp_path, Detection(backends=_holders(("llama-server", 8080))))
    assert "room_mib" in text
    assert "by hand" in text
    # One wording for a machine without a card: the situation and the fix
    # say it alike.
    assert text.count("no GPU this build can see") == 2


def test_the_by_hand_fix_is_offered_for_an_unsized_card_with_no_backend(
    tmp_path: Path,
) -> None:
    """With no backend answering, a unit bound by hand may still name the one
    the user starts, and the card is still one init sizes nothing against."""
    text = _refusal(
        tmp_path, Detection(gpus=(Gpu("Inventa Shared V", NO_SIZE, "invented"),))
    )
    assert "bind a unit by hand" in text
    assert "room_mib" in text


def test_the_by_hand_fix_is_not_offered_with_no_card_and_no_backend(
    tmp_path: Path,
) -> None:
    text = _refusal(tmp_path, Detection())
    assert "room_mib" not in text
