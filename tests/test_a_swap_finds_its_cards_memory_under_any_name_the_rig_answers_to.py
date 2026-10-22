"""A swap finds its card's memory under any name the rig answers to.

A swap reckons room from the card memory the rig file records, and a unit's
address need not spell the rig's name: it can be the hostname the scan
recorded, its full form, or a name for this machine. The card is found as
sizing finds a scan (`rigfile.resolve_hosts`), so a unit addressed as
`gpu-box.lan` swaps on the rig filed as `swapbox`. A host no rig file answers
for is refused with a reason naming that host, not a hint to scan again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import mcgyvr.scan as scan_module
from mcgyvr import wake
from mcgyvr.scan import Scan
from tests.records import RIGS_ENV, rig_file
from tests.test_a_full_top_rung_swaps_the_ram_rung_in_and_the_fast_ones_back import (
    CARD_MIB,
    FAST_M,
    FAST_S,
    RAM,
    SWAP_HOST,
    emitted,
    home,
)

__all__ = ["home"]


def _record(
    monkeypatch: pytest.MonkeyPatch, folder: Path, scan: Scan, rig: str
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{rig}.json").write_text(rig_file(scan, rig), encoding="utf-8")
    monkeypatch.setenv(RIGS_ENV, str(folder))


def _scan(host: str) -> Scan:
    return Scan.of(host=host, vram_mib=CARD_MIB, ram_gb=64.0, cores=8)


def test_a_host_spelled_as_the_scans_hostname_finds_the_rig_filed_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(monkeypatch, tmp_path / "rigs", _scan("gpu-box.lan"), "swapbox")

    assert wake.saved_card_mib(("gpu-box.lan",)) == {"gpu-box.lan": {0: CARD_MIB}}
    assert wake.saved_card_mib(("gpu-box",)) == {"gpu-box": {0: CARD_MIB}}
    assert wake.saved_card_mib(("swapbox",)) == {"swapbox": {0: CARD_MIB}}


def test_a_name_for_this_machine_finds_the_rig_this_machine_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = _scan("workstation")
    _record(monkeypatch, tmp_path / "rigs", recorded, "workstation")
    monkeypatch.setattr(scan_module, "local_machine_id", lambda: recorded.machine.id)

    assert wake.saved_card_mib(("127.0.0.1",)) == {"127.0.0.1": {0: CARD_MIB}}


def test_a_host_no_rig_answers_for_is_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(monkeypatch, tmp_path / "rigs", _scan("gpu-box.lan"), "swapbox")

    assert wake.saved_card_mib(("other-box.lan",)) == {}


def test_the_swap_rig_filed_under_another_name_still_makes_room(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge

    _record(monkeypatch, tmp_path / "rigs", _scan(SWAP_HOST), "swapbox")
    config, _ = emitted(tmp_path)

    card = wake.CardSwitches(
        config,
        Capacity.of(config, gauge=Gauge()),
        card_mib=wake.saved_card_mib((SWAP_HOST,)),
    )

    assert card.why_no_room(RAM) is None
    assert card.room_for(RAM) == (FAST_S, FAST_M)


def test_a_swap_no_rig_answers_for_names_the_host_it_could_not_match(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.capacity import Capacity
    from mcgyvr.pressure import Gauge

    _record(monkeypatch, tmp_path / "rigs", _scan("elsewhere.lan"), "elsewhere")
    config, _ = emitted(tmp_path)

    card = wake.CardSwitches(
        config,
        Capacity.of(config, gauge=Gauge()),
        card_mib=wake.saved_card_mib((SWAP_HOST,)),
    )

    why = card.why_no_room(RAM)
    assert why is not None
    assert f"no rig file answers for {SWAP_HOST}" in why
    assert f"mcgyvr scan --rig {SWAP_HOST}" in why
