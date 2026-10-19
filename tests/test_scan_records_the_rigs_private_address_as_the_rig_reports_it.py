"""``mcgyvr scan --rig`` records the rig's private IPv4 address in its rig file.

Owner, Round 9 (2026-10-07): a chat or agent unit spans several machines over
llama.cpp RPC, and each worker listens on a private IPv4 address, never on a
name the product would have to resolve. "Setup's scan records each machine's
private IPv4 in its rig file": nothing extra for the user to type.

Promises, over invented machines behind a stub ssh:

* The rig reports the address itself, over the scan it already ships: the
  address its ssh session arrived at (``SSH_CONNECTION``), and every IPv4
  address on its interfaces (``ip -4 -o addr show``). The controller resolves
  nothing.
* The address recorded is the one the controller reached the rig at, when a
  worker may listen there (the door's own rule: an IPv4 literal, not every
  interface, not loopback, not reachable from the internet).
* Reached some other way (a tunnel to loopback, IPv6), the rig's one private
  address is recorded; with several, none is guessed, and the rig file and
  the scan say which there are.
* The rig file keeps the reading whole, and its address is picked from what
  the rig said each time it is read back: only an address a worker may listen
  on is one, and a reading with no network names none.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from mcgyvr import cli
from mcgyvr.scan import Scan
from mcgyvr.serving import rigfile, rigscan
from tests import usermode

#: The invented rig's addresses: a documentation address (RFC 5737) on its
#: LAN card, another on its container bridge, and loopback; a third on a second
#: LAN card where the rig holds two.
LAN = "192.0.2.20"
BRIDGE = "198.51.100.30"
SECOND_LAN = "203.0.113.40"
IP_ADDR = (
    "1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n"
    f"2: eth0    inet {LAN}/24 brd 192.0.2.255 scope global eth0\\       "
    "valid_lft forever\n"
    f"3: docker0    inet {BRIDGE}/24 brd 198.51.100.255 scope global docker0\\  "
    "     valid_lft forever\n"
)


def _on_path(stubs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parts = [str(stubs), str(Path(sys.executable).parent), os.environ["PATH"]]
    monkeypatch.setenv("PATH", os.pathsep.join(parts))


def _network(reached_at: str | None, *addresses: tuple[str, str]) -> dict[str, object]:
    return {
        "reached_at": reached_at,
        "ipv4": [{"interface": name, "address": ip} for name, ip in addresses],
    }


def _scan_rig(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, network: dict[str, object]
) -> rigfile.Rig:
    payload = usermode.scan_payload()
    payload["network"] = network
    _on_path(usermode.machine(tmp_path, scan=payload), monkeypatch)
    assert cli.main(["scan", "--rig", usermode.RIG]) == 0
    saved = rigfile.read(usermode.RIG)
    assert saved is not None
    return saved


def test_the_rig_reports_where_ssh_reached_it_and_the_addresses_it_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def answered(
        argv: tuple[str, ...], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        if tuple(argv) == ("ip", "-4", "-o", "addr", "show"):
            return IP_ADDR, None
        return None, None

    monkeypatch.setattr(rigscan, "_run", answered)
    monkeypatch.setenv("SSH_CONNECTION", f"198.51.100.7 52000 {LAN} 22")

    payload = rigscan.scan()

    assert payload["network"] == _network(
        LAN, ("lo", "127.0.0.1"), ("eth0", LAN), ("docker0", BRIDGE)
    )
    network = Scan.from_json(json.dumps(payload)).network
    assert network is not None
    assert network.reached_at == LAN
    assert [(one.interface, one.address) for one in network.ipv4] == [
        ("lo", "127.0.0.1"),
        ("eth0", LAN),
        ("docker0", BRIDGE),
    ]


def test_a_rig_not_reached_over_ssh_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rigscan, "_run", lambda *a, **k: (None, None))
    monkeypatch.delenv("SSH_CONNECTION", raising=False)

    payload = rigscan.scan()

    assert payload["network"] == _network(None)
    assert any(note.startswith("Network:") for note in payload["notes"])


def test_scan_rig_records_the_address_the_rig_was_reached_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    network = _network(LAN, ("lo", "127.0.0.1"), ("eth0", LAN), ("docker0", BRIDGE))

    saved = _scan_rig(tmp_path, monkeypatch, network)

    assert saved.private_ipv4 == LAN
    assert "ssh" in str(saved.private_ipv4_how)
    assert LAN in capsys.readouterr().out
    recorded = rigfile.read(usermode.RIG)
    assert recorded is not None and recorded.private_ipv4 == LAN


@pytest.mark.parametrize("reached_at", ["127.0.0.1", "2001:db8::20", None])
def test_reached_another_way_the_one_private_address_is_recorded(
    reached_at: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    network = _network(reached_at, ("lo", "127.0.0.1"), ("eth0", LAN))

    saved = _scan_rig(tmp_path, monkeypatch, network)

    assert saved.private_ipv4 == LAN
    assert "eth0" in str(saved.private_ipv4_how)


def test_an_ipv4_address_spelled_as_ipv6_is_the_ipv4_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    network = _network(f"::ffff:{LAN}", ("eth0", LAN), ("docker0", BRIDGE))

    saved = _scan_rig(tmp_path, monkeypatch, network)

    assert saved.private_ipv4 == LAN


def test_with_several_private_addresses_and_none_reached_none_is_guessed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    network = _network(
        "127.0.0.1", ("lo", "127.0.0.1"), ("eth0", LAN), ("eth1", SECOND_LAN)
    )

    saved = _scan_rig(tmp_path, monkeypatch, network)

    assert saved.private_ipv4 is None
    how = str(saved.private_ipv4_how)
    assert LAN in how and SECOND_LAN in how
    out = capsys.readouterr().out
    assert "no private IPv4" in out and LAN in out and SECOND_LAN in out


def test_a_reading_with_no_network_names_no_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _scan_rig(tmp_path, monkeypatch, _network(LAN, ("eth0", LAN)))
    reading = dict(saved.reading)
    del reading["network"]

    old = rigfile.from_json(
        json.dumps({**json.loads(saved.to_json()), "reading": reading})
    )

    assert old.private_ipv4 is None


@pytest.mark.parametrize(
    "stated", ["box-b.invalid", "0.0.0.0", "127.0.0.1", "2001:db8::20"]
)
def test_an_address_no_worker_may_listen_on_is_never_the_rigs(
    stated: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved = _scan_rig(tmp_path, monkeypatch, _network(stated, ("lo", "127.0.0.1")))

    assert saved.private_ipv4 is None
