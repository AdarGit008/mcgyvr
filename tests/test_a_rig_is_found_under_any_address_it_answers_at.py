"""A rig is found under any address it answers at, not only under its names.

A unit can be addressed by its rig's LAN address rather than by the rig's name
(``10.0.0.7`` for the rig filed as ``gpu-box``). The scan records the addresses
the rig answers at — the one its ssh session arrived at, and those on its
interfaces from ``ip``, or from ``hostname -I`` where ``ip`` is missing — and a
person may state one in the rig file. ``rigfile.resolve_hosts`` finds the rig by
any of them, and a name that matches no rig by the addresses it resolves to.

Nothing reaches a machine: the scan's tools and the resolver are stubbed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from mcgyvr import wake
from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile, rigscan
from tests.records import RIGS_ENV, rig_file

CARD_MIB = 12288
LAN = "10.0.0.7"


def _reading(
    host: str, *, reached_at: str | None = None, ipv4: tuple[tuple[str, str], ...] = ()
) -> dict[str, object]:
    """A reading of `host` with one card, and the network section stated."""
    reading = json.loads(
        Scan.of(host=host, vram_mib=CARD_MIB, ram_gb=64.0, cores=8).to_json()
    )
    reading["network"] = {
        "reached_at": reached_at,
        "ipv4": [{"interface": name, "address": address} for name, address in ipv4],
    }
    return dict(reading)


def _record(
    monkeypatch: pytest.MonkeyPatch, folder: Path, rig: str, reading: dict[str, object]
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = rigfile.from_reading(rig, reading, "2026-10-22T00:00:00Z").to_json()
    (folder / f"{rig}.json").write_text(text, encoding="utf-8")
    monkeypatch.setenv(RIGS_ENV, str(folder))


def test_a_unit_addressed_by_the_rigs_lan_address_finds_its_card_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reading = _reading("gpu-box", ipv4=(("lo", "127.0.0.1"), ("eth0", LAN)))
    _record(monkeypatch, tmp_path / "rigs", "gpu-box", reading)

    assert wake.saved_card_mib((LAN,)) == {LAN: {0: CARD_MIB}}


def test_the_address_the_scan_was_reached_at_finds_the_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(
        monkeypatch, tmp_path / "rigs", "gpu-box", _reading("gpu-box", reached_at=LAN)
    )

    assert wake.saved_card_mib((LAN,)) == {LAN: {0: CARD_MIB}}


def test_bridge_loopback_and_link_local_addresses_name_no_rig() -> None:
    reading = _reading(
        "gpu-box",
        ipv4=(
            ("lo", "127.0.0.1"),
            ("docker0", "172.17.0.1"),
            ("eth1", "169.254.3.4"),
            ("eth0", LAN),
        ),
    )

    scan = rigfile.from_reading("gpu-box", reading).scan
    assert rigfile.scanned_addresses(scan) == (LAN,)


def test_an_address_two_rigs_recorded_is_refused_rather_than_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "rigs"
    _record(monkeypatch, folder, "box-a", _reading("box-a", ipv4=(("eth0", LAN),)))
    _record(monkeypatch, folder, "box-b", _reading("box-b", ipv4=(("eth0", LAN),)))

    assert wake.saved_card_mib((LAN,)) == {}


def test_a_name_resolving_to_a_recorded_address_finds_the_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(
        monkeypatch, tmp_path / "rigs", "gpu-box", _reading("gpu-box", reached_at=LAN)
    )
    monkeypatch.setattr(
        rigfile, "_resolve", lambda name: (LAN,) if name == "lab-gpu" else ()
    )

    assert wake.saved_card_mib(("lab-gpu",)) == {"lab-gpu": {0: CARD_MIB}}
    assert wake.saved_card_mib(("elsewhere",)) == {}


def test_a_resolver_that_hangs_resolves_to_nothing_in_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def hang(name: str) -> tuple[str, ...]:
        time.sleep(5)
        return (LAN,)

    monkeypatch.setattr(rigfile, "_resolve", hang)
    monkeypatch.setattr(rigfile, "RESOLVE_S", 0.05)

    started = time.monotonic()
    assert rigfile.addresses_of("lab-gpu") == ()
    assert time.monotonic() - started < 2


def test_a_stated_address_finds_the_rig_and_outlives_a_new_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(monkeypatch, tmp_path / "rigs", "gpu-box", _reading("gpu-box"))
    assert wake.saved_card_mib((LAN,)) == {}

    rigfile.state_addresses("gpu-box", (LAN,))
    assert wake.saved_card_mib((LAN,)) == {LAN: {0: CARD_MIB}}

    rigfile.save("gpu-box", _reading("gpu-box"))
    saved = rigfile.read("gpu-box")
    assert saved is not None
    assert saved.addresses == (LAN,)


def test_a_stated_address_must_be_one_another_machine_reaches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record(monkeypatch, tmp_path / "rigs", "gpu-box", _reading("gpu-box"))

    for said in ("gpu-box.lan", "127.0.0.1", "169.254.1.1", "0.0.0.0"):
        with pytest.raises(rigfile.RigFileError):
            rigfile.state_addresses("gpu-box", (said,))
    with pytest.raises(rigfile.RigFileError, match="mcgyvr scan --rig nowhere"):
        rigfile.state_addresses("nowhere", (LAN,))


def test_a_rig_file_from_before_addresses_still_loads() -> None:
    text = rig_file(Scan.of(host="gpu-box", vram_mib=CARD_MIB), "gpu-box")
    assert "addresses" not in json.loads(text)

    rig = rigfile.from_json(text)

    assert rig.addresses == ()
    assert rigfile.from_json(rig.to_json()) == rig


def test_a_scan_without_ip_reads_its_addresses_from_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(argv: tuple[str, ...], *, bound: float) -> tuple[str | None, str | None]:
        if argv[0] == "ip":
            return None, None
        assert argv == rigscan.HOSTNAME_ADDR_ARGS
        return f"{LAN} 172.17.0.1 fe80::1\n", None

    monkeypatch.setattr(rigscan, "_run", run)
    monkeypatch.delenv(rigscan.SSH_CONNECTION_ENV, raising=False)

    network, facts, _ = rigscan._network(1.0)

    assert network["ipv4"] == [
        {"interface": "", "address": LAN},
        {"interface": "", "address": "172.17.0.1"},
    ]
    assert {"field": "network.ipv4", "how": "hostname -I"} in facts
    reading = _reading("gpu-box")
    reading["network"] = network
    scan = rigfile.from_reading("gpu-box", reading).scan
    assert rigfile.scanned_addresses(scan) == (LAN,)


def test_a_scan_with_neither_tool_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rigscan, "_run", lambda argv, *, bound: (None, None))
    monkeypatch.delenv(rigscan.SSH_CONNECTION_ENV, raising=False)

    network, _, notes = rigscan._network(1.0)

    assert network == {"reached_at": None, "ipv4": []}
    assert any("hostname -I" in note for note in notes)
