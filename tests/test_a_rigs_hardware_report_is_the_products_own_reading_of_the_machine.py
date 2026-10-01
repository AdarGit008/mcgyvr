"""A rig's hardware report is the product's own reading of the machine.

The report is not a second detector. The machine reader the door ships reads
the machine, :func:`mcgyvr.fleet.machine.parse` reads what it prints, and the
machine's short id names it on the hub, so a machine the product would not
name is not reported under another name: the refusal says why. Every sized
card is reported with its name and memory, at most as many as the protocol
carries; RAM is the product's memory reading. A long card name is cut to
what the protocol carries, a name the reader did not read is refused rather
than cleaned, and every report makes a hello and a heartbeat the hub's schema
takes. The reader runs as the door ships it, with no test variable,
and a reader that fails or stalls is a refusal, not a guess.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests import rig_schema
from tests.machine_shapes import Card, shape, shapes
from tests.machinereader import machine_read_text


def _memory(total_gb: float = 64.0, available_gb: float = 40.5) -> Any:
    from mcgyvr.scan import Memory

    return lambda: Memory(total_gb=total_gb, available_gb=available_gb)


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_invented_machine_is_reported_as_the_product_reads_it(
    machine: Any, tmp_path: Path
) -> None:
    from mcgyvr.fleet import machine as reader
    from mcgyvr.rig import hardware, protocol

    text = machine_read_text(machine, tmp_path)
    reading = reader.parse(text)
    try:
        expected_id = reader.short_id(reading)
    except ValueError as refusal:
        with pytest.raises(hardware.HardwareError) as refused:
            hardware.read(reader=lambda: text, memory=_memory())
        assert str(refusal) in str(refused.value)
        return
    report = hardware.read(reader=lambda: text, memory=_memory())
    assert report.machine_id == expected_id
    sized = [c for c in reading.cards if c.key not in reading.unsized]
    assert len(report.cards) == min(len(sized), protocol.MAX_CARDS)
    for card, source in zip(report.cards, sized, strict=False):
        assert card.vram_total_mb == source.total_mib
        assert 0 <= card.vram_free_mb <= card.vram_total_mb
    assert [c.index for c in report.cards] == list(range(len(report.cards)))
    assert report.ram_total_mb == 64 * 1024
    assert report.ram_free_mb == round(40.5 * 1024)

    schema = rig_schema.load()
    hello = json.loads(hardware.hello_frame(report, "h1", agent_version="0.1.0"))
    rig_schema.validate(hello, schema, "#/$defs/Hello")
    beat = json.loads(hardware.heartbeat_frame(report, "b1"))
    rig_schema.validate(beat, schema, "#/$defs/Heartbeat")
    assert [c["index"] for c in beat["body"]["cards"]] == [
        c["index"] for c in hello["body"]["cards"]
    ]


def test_a_machine_with_no_card_reports_none_and_its_memory(tmp_path: Path) -> None:
    from mcgyvr.rig import hardware

    machine = next(m for m in shapes() if not m.cards)
    text = machine_read_text(machine, tmp_path)
    report = hardware.read(reader=lambda: text, memory=_memory(15.6, 9.0))
    assert report.cards == ()
    assert report.ram_total_mb == round(15.6 * 1024)
    assert report.machine_id.startswith("mch-")


def test_memory_that_cannot_be_read_is_reported_as_none_free_and_zero_total(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import hardware

    machine = next(m for m in shapes() if not m.cards)
    text = machine_read_text(machine, tmp_path)
    report = hardware.read(reader=lambda: text, memory=lambda: None)
    assert (report.ram_total_mb, report.ram_free_mb) == (0, None)
    assert any("memory" in note.lower() for note in report.notes)


def _with_first_card_named(name: str) -> Any:
    import dataclasses

    base = next(m for m in shapes() if m.cards and all(c.total_mib for c in m.cards))
    first = dataclasses.replace(base.cards[0], name=name)
    return dataclasses.replace(base, cards=(first, *base.cards[1:]))


def test_a_long_card_name_is_cut_to_what_the_protocol_carries(tmp_path: Path) -> None:
    from mcgyvr.rig import hardware, protocol

    machine = _with_first_card_named("Example Card " + "x" * 200)
    text = machine_read_text(machine, tmp_path)
    report = hardware.read(reader=lambda: text, memory=_memory())
    assert len(report.cards[0].name) == protocol.CARD_NAME_MAX
    assert report.cards[0].name.startswith("Example Card x")
    for card in report.cards:
        assert protocol.CARD_NAME.fullmatch(card.name)
    hardware.hello_frame(report, "h1", agent_version="0.1.0")


@pytest.mark.parametrize("name", ["Card\u202e reversed", "Card\u0007 bell"])
def test_a_name_the_reader_does_not_read_is_refused_not_cleaned(
    tmp_path: Path, name: str
) -> None:
    from mcgyvr.rig import hardware

    text = machine_read_text(_with_first_card_named(name), tmp_path)
    with pytest.raises(hardware.HardwareError) as refused:
        hardware.read(reader=lambda: text, memory=_memory())
    assert ".name" in str(refused.value)


def test_more_cards_than_a_report_carries_are_cut_and_said(tmp_path: Path) -> None:
    from mcgyvr.rig import hardware, protocol

    base = shape(shapes()[0].label)
    many = tuple(
        Card(index=i, name="Example Card", vendor="vendor-a", total_mib=8192)
        for i in range(protocol.MAX_CARDS + 2)
    )
    import dataclasses

    machine = dataclasses.replace(base, cards=many, card_reader_missing=False)
    text = machine_read_text(machine, tmp_path)
    report = hardware.read(reader=lambda: text, memory=_memory())
    assert len(report.cards) == protocol.MAX_CARDS
    assert any(str(protocol.MAX_CARDS) in note for note in report.notes)


def test_the_reader_runs_as_the_door_ships_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcgyvr.rig import hardware

    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="end=\n", stderr="")

    monkeypatch.setenv("MCGYVR_TEST_MACHINE_ROOT", "/nowhere")
    monkeypatch.setenv("MCGYVR_TEST_TOOL_SECONDS", "1")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hardware.run_reader() == "end=\n"
    assert seen["argv"] == ["bash", "-s"]
    shipped = hardware.READER.read_text(encoding="utf-8")
    assert seen["input"] == shipped and "end=" in shipped
    assert not any(name.startswith("MCGYVR_TEST_") for name in seen["env"])
    assert seen["timeout"] > 0


@pytest.mark.parametrize(
    "outcome",
    [
        subprocess.CompletedProcess(["bash"], 1, stdout="", stderr="boom"),
        subprocess.TimeoutExpired(["bash"], 1),
        FileNotFoundError("bash"),
    ],
)
def test_a_reader_that_fails_or_stalls_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch, outcome: Any
) -> None:
    from mcgyvr.rig import hardware

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(hardware.HardwareError):
        hardware.run_reader()
