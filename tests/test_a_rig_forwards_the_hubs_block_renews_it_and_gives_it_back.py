"""A rig forwards the hub's block of ports on its router, renews it, gives it back.

The hub asks (``port_map``) only after the owner agreed; the agent maps the
block on to its first tunnel ports at the LAN address its tunnel is published
on, by the first router way that takes every port (UPnP before NAT-PMP),
rolls back a block half taken, renews before half a lease is gone, and
releases on a null ask and when it stops. Each outcome is one
``port_map_report``. A check (``port_check``) answers the hub's pings with
the check's secret, a few at most, on a tunnel port only.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from mcgyvr.rig import portmap, protocol, sessionwire, udpwire

LAN = "192.168.1.20"
PORTS = (51820, 51821, 51822, 51823)
SECRET = bytes(range(16))


@dataclass
class FakeRouter:
    method: str = "upnp"
    host: str = LAN
    refuse_at: dict[int, str] = field(default_factory=dict)  # external -> error
    lease: int | None = None  # what it grants, else what is asked
    held: dict[int, tuple[str, int, int]] = field(default_factory=dict)
    adds: list[int] = field(default_factory=list)

    def lan_host(self) -> str:
        return self.host

    def external_address(self) -> str | None:
        return "198.51.100.7"

    def add(self, *, lan_host: str, internal: int, external: int, lease_s: int) -> int:
        self.adds.append(external)
        if external in self.refuse_at:
            raise portmap.MapError(self.refuse_at[external], "no")
        granted = lease_s if self.lease is None else self.lease
        self.held[external] = (lan_host, internal, granted)
        return granted

    def remove(self, *, internal: int, external: int) -> None:
        self.held.pop(external, None)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class World:
    routers: list[FakeRouter]
    sent: list[dict[str, Any]] = field(default_factory=list)
    clock: Clock = field(default_factory=Clock)
    ports: tuple[int, ...] = PORTS
    hosts: tuple[str, ...] = (LAN,)

    def send(self, frame: str) -> bool:
        self.sent.append(json.loads(frame))
        return True

    def mapper(self) -> portmap.Mapper:
        return portmap.Mapper(
            send=self.send,
            tunnel_ports=lambda: self.ports,
            hosts=lambda: self.hosts,
            routers=lambda: self.routers,
            bind_host="127.0.0.1",
            clock=self.clock,
        )

    def reports(self) -> list[dict[str, Any]]:
        return [m["body"] for m in self.sent if m["type"] == "port_map_report"]


def ask(mapper: portmap.Mapper, **body: Any) -> str | None:
    frame = {"v": 1, "type": "port_map", "id": "a1", "body": body}
    return mapper.ask(protocol.decode(json.dumps(frame)))


def test_the_block_is_mapped_in_order_and_reported_once() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    answer = ask(mapper, external_port=52000, ports=4, lease_s=3600)
    assert answer is not None and json.loads(answer)["type"] == "ack"
    mapper.tick()
    assert upnp.held == {52000 + i: (LAN, 51820 + i, 3600) for i in range(4)}
    assert world.reports() == [
        {
            "state": "mapped",
            "method": "upnp",
            "lan_host": LAN,
            "internal_port": 51820,
            "external_port": 52000,
            "ports": 4,
            "router_host": "198.51.100.7",
            "lease_s": 3600,
        }
    ]
    mapper.tick()  # nothing new: nothing said
    assert len(world.reports()) == 1


def test_a_block_half_taken_is_rolled_back_and_the_next_way_tried() -> None:
    upnp = FakeRouter(refuse_at={52002: "refused"})
    natpmp = FakeRouter(method="natpmp")
    world = World([upnp, natpmp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert upnp.held == {}
    assert sorted(natpmp.held) == [52000, 52001, 52002, 52003]
    assert world.reports()[-1]["method"] == "natpmp"


def test_a_conflict_is_what_the_report_says_when_no_way_maps() -> None:
    upnp = FakeRouter(refuse_at={52001: "conflict"})
    natpmp = FakeRouter(method="natpmp", refuse_at={52000: "timeout"})
    world = World([upnp, natpmp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert world.reports() == [
        {
            "state": "failed",
            "error": "conflict",
            "message": "no",
            "lan_host": LAN,
            "internal_port": 51820,
            "external_port": 52000,
            "ports": 4,
        }
    ]
    assert upnp.held == natpmp.held == {}


def test_no_router_at_all_fails_with_no_gateway() -> None:
    world = World([])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert world.reports()[0]["error"] == "no_gateway"


def test_a_lan_address_the_tunnel_is_not_published_on_is_never_forwarded_to() -> None:
    upnp = FakeRouter(host="10.9.9.9")
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert upnp.adds == []
    assert world.reports()[0]["error"] == "no_lan_host"


def test_the_lease_is_renewed_before_half_of_it_is_gone() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000, lease_s=600)
    wait = mapper.tick()
    assert wait == pytest.approx(60.0)  # the idle cap is under half the lease
    world.clock.now += 299
    mapper.tick()
    assert len(upnp.adds) == 4
    world.clock.now += 1
    assert mapper.tick() == pytest.approx(60.0)
    assert len(upnp.adds) == 8
    assert len(world.reports()) == 1


def test_a_renewal_refused_is_retried_then_the_forward_given_up_and_said() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000, lease_s=600)
    mapper.tick()
    upnp.refuse_at[52000] = "timeout"
    world.clock.now += 300
    for _ in range(portmap.RENEW_TRIES - 1):
        mapper.tick()
        assert len(world.reports()) == 1  # a miss, retried
        world.clock.now += portmap.RENEW_RETRY_S
    del upnp.refuse_at[52000]
    mapper.tick()  # the router answers again: kept
    assert len(world.reports()) == 1 and len(upnp.held) == 4
    upnp.refuse_at[52000] = "timeout"
    for _ in range(portmap.RENEW_TRIES):
        world.clock.now += 300
        mapper.tick()
    assert world.reports()[-1]["state"] == "failed"
    assert world.reports()[-1]["error"] == "timeout"
    assert upnp.held == {}  # what was left of it is given back


def test_a_lease_longer_than_the_wire_carries_is_held_to_it() -> None:
    upnp = FakeRouter(lease=10**9)
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert world.reports()[0]["lease_s"] == sessionwire.MAX_PORT_MAP_LEASE_S


def test_a_permanent_lease_is_never_renewed() -> None:
    upnp = FakeRouter(lease=0)
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    world.clock.now += 100_000
    mapper.tick()
    assert len(upnp.adds) == 4
    assert world.reports()[0]["lease_s"] == 0


def test_a_null_ask_releases_and_a_new_block_moves_the_forward() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    ask(mapper, external_port=52004)
    mapper.tick()
    assert sorted(upnp.held) == [52004, 52005, 52006, 52007]
    ask(mapper, external_port=None)
    mapper.tick()
    assert upnp.held == {}
    assert [r["state"] for r in world.reports()] == ["mapped", "mapped", "released"]


def test_the_same_block_asked_again_is_reported_again_not_remapped() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert len(upnp.adds) == 4
    assert [r["state"] for r in world.reports()] == ["mapped", "mapped"]


def test_a_rig_with_fewer_tunnel_ports_maps_only_those() -> None:
    upnp = FakeRouter()
    world = World([upnp], ports=(65534, 65535))
    mapper = world.mapper()
    ask(mapper, external_port=52000)
    mapper.tick()
    assert world.reports()[0]["ports"] == 2
    assert sorted(upnp.held) == [52000, 52001]


def test_stopping_gives_the_forward_back() -> None:
    upnp = FakeRouter()
    world = World([upnp])
    mapper = world.mapper()
    mapper.start()
    ask(mapper, external_port=52000)
    deadline = time.monotonic() + 5
    while not world.reports() and time.monotonic() < deadline:
        time.sleep(0.01)
    mapper.close()
    assert upnp.held == {}
    assert [r["state"] for r in world.reports()] == ["mapped", "released"]


# --- the check -----------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port


def check(mapper: portmap.Mapper, port: int, ttl_s: int = 5) -> dict[str, Any]:
    frame = {
        "v": 1,
        "type": "port_check",
        "id": "k1",
        "body": {
            "check_id": "k1",
            "secret": SECRET.hex(),
            "port": port,
            "ttl_s": ttl_s,
        },
    }
    answer = mapper.check(protocol.decode(json.dumps(frame)))
    assert answer is not None
    found: dict[str, Any] = json.loads(answer)
    return found


def _pings(port: int, secret: bytes, count: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.3)
        answered = 0
        for seq in range(count):
            ping = udpwire.probe_packet(udpwire.PING, secret, seq, seq)
            sock.sendto(ping, ("127.0.0.1", port))
            try:
                data, _ = sock.recvfrom(2048)
            except TimeoutError:
                continue
            got = udpwire.read_probe(data)
            if got is not None and got.kind == udpwire.PONG and got.seq == seq:
                answered += 1
    return answered


def test_a_check_answers_its_own_pings_and_no_more_than_its_cap() -> None:
    port = _free_port()
    world = World([], ports=(port,))
    mapper = world.mapper()
    assert check(mapper, port)["type"] == "ack"
    assert _pings(port, bytes(16), 2) == 0  # another secret: silence
    assert _pings(port, SECRET, 12) == udpwire.PORT_CHECK_MAX_PONGS
    mapper.close()


def test_a_check_on_a_port_not_tunnelled_on_or_held_is_refused() -> None:
    port = _free_port()
    world = World([], ports=(port,))
    mapper = world.mapper()
    refused = check(mapper, port + 1 if port < 65535 else port - 1)
    assert refused["type"] == "error"
    assert refused["body"]["code"] == "not_capable"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as holder:
        holder.bind(("127.0.0.1", port))
        busy = check(mapper, port)
    assert busy["body"]["code"] == "busy"


def test_a_session_about_to_take_the_port_closes_the_check() -> None:
    port = _free_port()
    world = World([], ports=(port,))
    mapper = world.mapper()
    check(mapper, port, ttl_s=30)
    mapper.release_check(port)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(("127.0.0.1", port))
            break
        except OSError:
            time.sleep(0.02)
    else:
        pytest.fail("the check kept the port")
