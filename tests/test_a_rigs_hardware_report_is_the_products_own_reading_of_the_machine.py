"""A rig's hardware report is the product's own reading of the machine.

The report is not a second detector. The one reader
(:mod:`mcgyvr.serving.rigscan`) reads the machine — its short reading, which
asks for no raised rights — and the machine's rig id
(:func:`mcgyvr.fleet.ids.rig_id`) names it on the hub, so a machine the
product would not name is not reported under another name: the refusal says
why. Every sized card is reported with its name and memory, at most as many
as the protocol carries; RAM is the reading's own memory section. A long card
name is cut to what the protocol carries, a name the reader did not read is
refused rather than cleaned, and every report makes a hello and a heartbeat
the hub's schema takes. A reader that fails is a refusal, not a guess.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests import rig_schema
from tests.machine_shapes import Card, shape, shapes
from tests.machinereader import machine_reading


def _with_memory(
    document: dict[str, Any], total_gb: float = 64.0, available_gb: float | None = 40.5
) -> dict[str, Any]:
    return {**document, "memory": {"total_gb": total_gb, "available_gb": available_gb}}


@pytest.mark.parametrize("machine", shapes(), ids=lambda m: m.label)
def test_every_invented_machine_is_reported_as_the_product_reads_it(
    machine: Any, tmp_path: Path
) -> None:
    from mcgyvr.fleet import ids
    from mcgyvr.rig import hardware, protocol

    document = _with_memory(machine_reading(machine, tmp_path))
    try:
        expected_id = ids.rig_id(document)
    except ValueError as refusal:
        with pytest.raises(hardware.HardwareError) as refused:
            hardware.read(reader=lambda: document)
        assert str(refusal) in str(refused.value)
        return
    report = hardware.read(reader=lambda: document)
    assert report.machine_id == expected_id
    assert report.machine_id.startswith("rig-")
    unsized = set(document["unsized"])
    sized = [
        c
        for c in document["cards"]
        if f"card.{c['vendor']}.{c['index']}" not in unsized
    ]
    assert len(report.cards) == min(len(sized), protocol.MAX_CARDS)
    for card, source in zip(report.cards, sized, strict=False):
        assert card.vram_total_mb == source["total_mib"]
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
    document = _with_memory(machine_reading(machine, tmp_path), 15.6, 9.0)
    report = hardware.read(reader=lambda: document)
    assert report.cards == ()
    assert report.ram_total_mb == round(15.6 * 1024)
    assert report.machine_id.startswith("rig-")


def test_memory_that_cannot_be_read_is_reported_as_none_free_and_zero_total(
    tmp_path: Path,
) -> None:
    from mcgyvr.rig import hardware

    machine = next(m for m in shapes() if not m.cards)
    document = {**machine_reading(machine, tmp_path), "memory": None}
    report = hardware.read(reader=lambda: document)
    assert (report.ram_total_mb, report.ram_free_mb) == (0, None)
    assert any("memory" in note.lower() for note in report.notes)


def test_a_total_without_an_available_figure_reports_none_free(
    tmp_path: Path,
) -> None:
    """Where only the total is read (sysctl on a Mac), nothing free is promised."""
    from mcgyvr.rig import hardware

    machine = next(m for m in shapes() if not m.cards)
    document = _with_memory(machine_reading(machine, tmp_path), 16.0, None)
    report = hardware.read(reader=lambda: document)
    assert (report.ram_total_mb, report.ram_free_mb) == (16 * 1024, None)


def _with_first_card_named(name: str) -> Any:
    base = next(m for m in shapes() if m.cards and all(c.total_mib for c in m.cards))
    first = dataclasses.replace(base.cards[0], name=name)
    return dataclasses.replace(base, cards=(first, *base.cards[1:]))


def test_a_long_card_name_is_cut_to_what_the_protocol_carries(tmp_path: Path) -> None:
    from mcgyvr.rig import hardware, protocol

    machine = _with_first_card_named("Example Card " + "x" * 200)
    document = _with_memory(machine_reading(machine, tmp_path))
    report = hardware.read(reader=lambda: document)
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

    document = machine_reading(_with_first_card_named(name), tmp_path)
    with pytest.raises(hardware.HardwareError) as refused:
        hardware.read(reader=lambda: document)
    assert ".name" in str(refused.value)


def test_more_cards_than_a_report_carries_are_cut_and_said(tmp_path: Path) -> None:
    from mcgyvr.rig import hardware, protocol

    base = shape(shapes()[0].label)
    many = tuple(
        Card(index=i, name="Example Card", vendor="vendor-a", total_mib=8192)
        for i in range(protocol.MAX_CARDS + 2)
    )
    machine = dataclasses.replace(base, cards=many, card_reader_missing=False)
    document = _with_memory(machine_reading(machine, tmp_path))
    report = hardware.read(reader=lambda: document)
    assert len(report.cards) == protocol.MAX_CARDS
    assert any(str(protocol.MAX_CARDS) in note for note in report.notes)


def test_the_report_is_read_by_the_one_readers_short_reading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With no reader named, the report is :func:`rigscan.read_machine`'s, the
    reading that asks for no raised rights and times no copy."""
    from mcgyvr.rig import hardware
    from mcgyvr.serving import rigscan

    document = _with_memory(machine_reading(shape("one-card"), tmp_path))
    asked: list[bool] = []

    def short(**_: Any) -> dict[str, Any]:
        asked.append(True)
        return document

    monkeypatch.setattr(rigscan, "read_machine", short)
    monkeypatch.setattr(rigscan, "scan", lambda *a, **k: pytest.fail("a whole scan"))
    report = hardware.read()
    assert asked == [True]
    assert report.cards


@pytest.mark.parametrize(
    "outcome",
    [OSError("the reader could not start"), {"cards": [], "unread": []}],
    ids=["reader-raises", "no-machine-id"],
)
def test_a_reader_that_fails_or_names_no_machine_is_a_refusal(outcome: Any) -> None:
    from mcgyvr.rig import hardware

    def reader() -> Any:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    with pytest.raises(hardware.HardwareError):
        hardware.read(reader=reader)
