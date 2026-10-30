"""A rig's docker and virtual bridge addresses are set aside before its own is chosen.

#731 item 8: a rig with a LAN card and docker running holds two private IPv4
addresses, the LAN one and docker0's, and the rig file recorded neither. No
other machine reaches the rig on a bridge, so those addresses are set aside
before the choice the rig file already makes (#624).

Promises, each from the output the scan reads on the rig (``ip -4 -o addr
show`` and ``SSH_CONNECTION``):

* An address on a docker or virtual bridge interface (docker0, br-*, virbr*,
  veth*) is set aside, the LAN address is recorded, and how it was chosen says
  which bridge addresses were set aside.
* Two LAN addresses are still two: none is guessed and the rig is to be scanned
  again over the one its other machines use.
* An overlay address (100.64.0.0/10) the rig was reached at is recorded as the
  address it was reached at, as before.
* An address with no interface name is set aside when it is in docker's default
  bridge network, 172.17.0.0/16; with a name, the name decides.
"""

from __future__ import annotations

import pytest

from mcgyvr.serving import rigfile, rigscan

#: The invented rig's LAN addresses (RFC 5737), its overlay address, and docker's
#: default bridge address.
LAN = "10.20.0.20"
SECOND_LAN = "10.30.0.30"
OVERLAY = "100.64.0.7"
DOCKER = "172.17.0.1"
#: `ip -4 -o addr show` lines as a rig prints them: loopback, its LAN card, and
#: its second LAN card.
LO_LINE = (
    "1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever "
    "preferred_lft forever\n"
)
LAN_LINE = (
    f"2: enp5s0    inet {LAN}/24 brd 10.20.0.255 scope global dynamic "
    "noprefixroute enp5s0\\       valid_lft 85000sec preferred_lft 85000sec\n"
)
SECOND_LAN_LINE = (
    f"3: wlp4s0    inet {SECOND_LAN}/24 brd 10.30.0.255 scope global dynamic "
    "noprefixroute wlp4s0\\       valid_lft 85000sec preferred_lft 85000sec\n"
)
OVERLAY_LINE = (
    f"4: tailscale0    inet {OVERLAY}/32 scope global tailscale0\\       "
    "valid_lft forever preferred_lft forever\n"
)
DOCKER_LINE = (
    f"5: docker0    inet {DOCKER}/16 brd 172.17.255.255 scope global docker0\\  "
    "     valid_lft forever preferred_lft forever\n"
)
#: One line for each kind of bridge interface, with the address it holds.
BRIDGE_LINES = {
    "docker0": (DOCKER, DOCKER_LINE),
    "br-3f2a1b4c5d6e": (
        "172.18.0.1",
        "6: br-3f2a1b4c5d6e    inet 172.18.0.1/16 brd 172.18.255.255 scope global "
        "br-3f2a1b4c5d6e\\       valid_lft forever preferred_lft forever\n",
    ),
    "virbr0": (
        "192.168.122.1",
        "7: virbr0    inet 192.168.122.1/24 brd 192.168.122.255 scope global "
        "virbr0\\       valid_lft forever preferred_lft forever\n",
    ),
    "veth1a2b3c4": (
        "10.200.0.1",
        "8: veth1a2b3c4@if7    inet 10.200.0.1/30 scope global veth1a2b3c4\\       "
        "valid_lft forever preferred_lft forever\n",
    ),
}


def _read(
    monkeypatch: pytest.MonkeyPatch, ip_addr: str | None, reached_at: str | None
) -> rigfile.Rig:
    """The rig file of a rig whose `ip` printed ``ip_addr`` (None: `ip` failed)
    and whose ssh session arrived at ``reached_at`` (None: not over ssh)."""

    def answered(
        argv: tuple[str, ...], *, bound: float = 0.0
    ) -> tuple[str | None, str | None]:
        if tuple(argv) == ("ip", *rigscan.IP_ADDR_ARGS):
            return ip_addr, None
        return None, None

    monkeypatch.setattr(rigscan, "_run", answered)
    if reached_at is None:
        monkeypatch.delenv("SSH_CONNECTION", raising=False)
    else:
        monkeypatch.setenv("SSH_CONNECTION", f"10.30.0.7 52000 {reached_at} 22")
    return rigfile.from_reading("box-a.invalid", rigscan.scan())


@pytest.mark.parametrize("bridge", sorted(BRIDGE_LINES))
def test_a_lan_address_beside_a_bridge_is_recorded_and_says_the_bridge_was_set_aside(
    bridge: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    address, line = BRIDGE_LINES[bridge]

    saved = _read(monkeypatch, LO_LINE + LAN_LINE + line, None)

    assert saved.private_ipv4 == LAN
    how = saved.private_ipv4_how
    assert "enp5s0" in how
    assert "set aside" in how and f"{address} on {bridge}" in how


def test_a_lan_address_reached_beside_docker_is_recorded_as_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _read(monkeypatch, LO_LINE + LAN_LINE + DOCKER_LINE, LAN)

    assert saved.private_ipv4 == LAN
    assert saved.private_ipv4_how == "the address the rig was reached at over ssh"


def test_two_lan_addresses_beside_docker_still_ask_for_a_scan_over_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _read(monkeypatch, LO_LINE + LAN_LINE + SECOND_LAN_LINE + DOCKER_LINE, None)

    assert saved.private_ipv4 is None
    how = saved.private_ipv4_how
    assert "several private IPv4 addresses" in how
    assert LAN in how and SECOND_LAN in how and "scan it again" in how
    assert f"{DOCKER} on docker0" in how


def test_an_overlay_address_the_rig_was_reached_at_is_recorded_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _read(monkeypatch, LO_LINE + LAN_LINE + OVERLAY_LINE + DOCKER_LINE, OVERLAY)

    assert saved.private_ipv4 == OVERLAY
    assert saved.private_ipv4_how == "the address the rig was reached at over ssh"


def test_a_bare_docker_bridge_address_with_no_interface_name_is_set_aside(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _read(monkeypatch, None, DOCKER)

    assert saved.scan.network is not None and saved.scan.network.ipv4 == ()
    assert saved.private_ipv4 is None
    assert f"reached at {DOCKER}, a docker or virtual bridge" in saved.private_ipv4_how


def test_an_address_in_dockers_network_on_a_lan_card_is_the_rigs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    numbered = "172.17.5.20"
    line = (
        f"2: enp5s0    inet {numbered}/16 brd 172.17.255.255 scope global enp5s0\\  "
        "     valid_lft forever preferred_lft forever\n"
    )

    saved = _read(monkeypatch, LO_LINE + line, numbered)

    assert saved.private_ipv4 == numbered
    assert saved.private_ipv4_how == "the address the rig was reached at over ssh"
