"""A ride reaches only the shared unit's own address, and the host goes first.

The hub relays a rider's request to a unit this host advertised
(``unit_relay_request``): a head relay in every frame (:mod:`mcgyvr.rig.relay`),
aimed at an advertised unit's id rather than a session. The agent serves it
through the head relay's own code, its target the unit's address:

* **Only the unit's own address.** The hub names a unit id and nothing else;
  the address is the host's own setup's, joined to the one path the relayed
  endpoint maps to as a run joins it (a unit address ending ``/v1`` is not
  doubled). An id no advert named is ``unknown_unit``, and reaches nothing.
* **Unchanged both ways.** The body goes to the unit byte for byte (the hub
  put the unit's model in it) and the answer comes back as the unit gives it,
  so it names the unit's real model.
* **The host goes first.** A unit takes at most its ``rider_slots`` rides at
  once, and a ride is refused ``busy`` when the host's own requests and the
  rides leave no slot free, by the unit's own count at that moment (a ride the
  agent serves is not the host's;
  ``tests/test_a_ride_is_admitted_while_the_unit_has_a_free_slot.py``). A ride
  holds one of the unit's slots, host-wide, for as long as it
  runs, so the host's own dispatches see it; with none free it is ``busy``.
* **Like a head relay.** Rides count in the rig's own bound of relays at
  once, share the relays' request ids, end on the hub's cancel, and a
  session's end leaves them be. A ride that ends asks for a check of the
  advert, since the unit's free slots may have moved.

The unit is a scripted server on loopback; its in-flight count, the slots'
lock directory and the clock are the test's.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes

PROMPT = "the rider's secret words"
MODEL = "qwen-coder-7b.gguf"
SERVED = "Qwen2.5-Coder-7B-Instruct-Q5_K_M"


@dataclass
class UnitServer:
    """A host's own model server on loopback, answering as its weights name it."""

    hold: bool = False
    release: threading.Event = field(default_factory=threading.Event)
    seen: list[tuple[str, bytes]] = field(default_factory=list)
    running: int = 0
    hung_up: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    server: ThreadingHTTPServer | None = None

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.server_address[1])

    def answer(self) -> bytes:
        return json.dumps(
            {"model": SERVED, "choices": [{"message": {"content": "ok"}}]}
        ).encode()


def _serve(unit: UnitServer) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            with unit.lock:
                unit.seen.append((self.path, body))
                unit.running += 1
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                # While held, a space now and then: writing is how a hang-up
                # is found, and a few of them stay well inside the window.
                while unit.hold and not unit.release.wait(0.25):
                    self.wfile.write(b"1\r\n \r\n")
                    self.wfile.flush()
                chunk = unit.answer()
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError:
                unit.hung_up.set()
            finally:
                with unit.lock:
                    unit.running -= 1

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Now:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class NoHeads:
    def head_port(self, session_id: str) -> int | None:
        return None

    def head_slots(self, session_id: str) -> int:
        return 1

    def state_of(self, session_id: str) -> tuple[str, str | None]:
        return ("absent", None)


@dataclass
class Host:
    unit: UnitServer
    box: fakes.Box
    units: Any
    relays: Any
    dispatcher: Any
    capacity: Any
    busy: dict[str, int | None]
    now: Now
    checks: list[float]

    def send(self, kind: str, message_id: str = "r1", **body: Any) -> None:
        reply = self.dispatcher.dispatch(
            fakes.frame(kind, message_id, **body), fakes.Stub()
        )
        if reply is not None:
            self.box.put(reply)

    def ride(self, body: bytes, request_id: str = "q1", **changes: Any) -> None:
        fields: dict[str, Any] = {
            "unit_id": "coder",
            "request_id": request_id,
            "endpoint": "chat_completions",
            "body_bytes": len(body),
            "stream": False,
            "timeout_s": 10,
            "max_response_bytes": 1 << 20,
            "window": 64,
        }
        fields.update(changes)
        self.send("unit_relay_request", f"r-{request_id}", **fields)
        if body:
            self.send(
                "relay_data",
                f"d-{request_id}",
                request_id=request_id,
                seq=0,
                data_b64=base64.b64encode(body).decode(),
            )

    def ended(self, request_id: str = "q1", timeout: float = 5.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ends = [
                f["body"]
                for f in self.box.of_type("relay_end")
                if f["body"]["request_id"] == request_id
            ]
            if ends:
                found: dict[str, Any] = ends[0]
                return found
            time.sleep(0.005)
        raise AssertionError(f"no relay_end for {request_id} in {self.box.frames}")

    def running(self, count: int, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.unit.lock:
                if self.unit.running == count:
                    return
            time.sleep(0.005)
        raise AssertionError(f"the unit runs {self.unit.running}, not {count}")

    def answer(self, request_id: str = "q1") -> bytes:
        frames = [
            f["body"]
            for f in self.box.of_type("relay_data")
            if f["body"]["request_id"] == request_id
        ]
        return b"".join(base64.b64decode(f["data_b64"]) for f in frames).strip()


def _host(
    tmp_path: Path,
    *,
    width: int = 4,
    rider_slots: int = 2,
    max_active: int = 16,
    second: bool = False,
) -> Host:
    from mcgyvr.capacity import Capacity
    from mcgyvr.config import parse
    from mcgyvr.rig import commands, hitchhike, relay

    unit = UnitServer()
    unit.server = _serve(unit)
    text = (
        "units:\n"
        "  coder:\n"
        f"    address: http://127.0.0.1:{unit.port}/v1\n"
        f"    model: {MODEL}\n"
        f"    width: {width}\n"
        "    window: 8192\n"
    )
    if second:
        text += (
            "  other:\n"
            f"    address: http://127.0.0.1:{unit.port}\n"
            "    model: other.gguf\n"
            "    width: 2\n"
            "    window: 4096\n"
        )
    text += "ladder: [coder" + (", other" if second else "") + "]\n"
    text += f"rider_slots: {{coder: {rider_slots}" + (", other: 1" if second else "")
    text += "}\n"
    config = parse(text)
    capacity = Capacity.of(config, root=tmp_path / "slots")
    busy: dict[str, int | None] = {"coder": 0, "other": 0}
    checks: list[float] = []
    now = Now()

    def setup() -> hitchhike.Setup:
        checks.append(now.now)
        shared, notes = hitchhike.shared_units(config)
        return hitchhike.Setup(
            units=shared,
            notes=notes,
            in_flight=lambda shared_unit: busy[shared_unit.name],
            hold=lambda shared_unit: capacity.hold(shared_unit.name, timeout=0),
        )

    box = fakes.Box()
    units = hitchhike.Units(
        setup=setup,
        send=box.put,
        clock=now,
        say=lambda line: None,
        start=lambda work: work(),
    )
    units.online()
    made = relay.Relays(
        heads=NoHeads(),
        send=box.put,
        units=units,
        max_active=max_active,
    )
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, made)
    return Host(unit, box, units, made, dispatcher, capacity, busy, now, checks)


@pytest.fixture
def host(tmp_path: Path) -> Iterator[Host]:
    made = _host(tmp_path)
    yield made
    made.unit.release.set()
    made.relays.cancel_all()
    assert made.unit.server is not None
    made.unit.server.shutdown()


def _body(model: str = MODEL) -> bytes:
    return json.dumps(
        {"model": model, "messages": [{"role": "user", "content": PROMPT}]}
    ).encode()


# --- only the unit's own address, unchanged both ways ---------------------------------


def test_a_ride_goes_unchanged_to_the_units_own_path_and_its_answer_names_the_unit(
    host: Host, capsys: pytest.CaptureFixture[str]
) -> None:
    host.ride(_body())

    assert host.ended() == {"request_id": "q1", "outcome": "complete"}
    assert host.unit.seen == [("/v1/chat/completions", _body())]
    (response,) = host.box.of_type("relay_response")
    assert response["body"] == {
        "request_id": "q1",
        "status": 200,
        "content_type": "application/json",
    }
    assert json.loads(host.answer())["model"] == SERVED
    said = capsys.readouterr()
    assert PROMPT not in said.out + said.err
    assert all(PROMPT not in json.dumps(f) for f in host.box.frames)


def test_the_hub_names_a_unit_and_never_where_it_is(host: Host) -> None:
    host.ride(_body(), address="http://198.51.100.9:9/x", path="/admin", port=1)

    assert host.ended()["outcome"] == "complete"
    assert [path for path, _ in host.unit.seen] == ["/v1/chat/completions"]


def test_a_unit_no_advert_named_is_unknown_and_reaches_nothing(
    host: Host, tmp_path: Path
) -> None:
    from mcgyvr.rig import commands, relay

    host.ride(_body(), unit_id="nobody")
    assert host.ended() == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "unknown_unit",
    }

    host.units.offline()  # the hub forgets the adverts of a link that dropped
    host.ride(_body(), request_id="q2")
    assert host.ended("q2")["error_code"] == "unknown_unit"

    alone = relay.Relays(heads=NoHeads(), send=host.box.put)
    dispatcher = commands.Dispatcher()
    relay.register(dispatcher, alone)
    reply = dispatcher.dispatch(
        fakes.frame(
            "unit_relay_request",
            "r9",
            unit_id="coder",
            request_id="q9",
            endpoint="chat_completions",
            body_bytes=0,
            stream=False,
            timeout_s=5,
            max_response_bytes=10,
            window=1,
        ),
        fakes.Stub(),
    )
    assert reply is not None
    assert json.loads(reply)["body"]["error_code"] == "unknown_unit"
    time.sleep(0.1)
    assert host.unit.seen == []


def test_a_ride_the_schema_refuses_ends_bad_message(host: Host) -> None:
    host.ride(b"{}", endpoint="../admin")
    assert host.ended() == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "bad_message",
    }
    assert host.unit.seen == []


# --- the host goes first -------------------------------------------------------------


def test_a_unit_takes_no_more_rides_at_once_than_its_rider_slots(host: Host) -> None:
    host.unit.hold = True
    host.ride(_body(), "q1")
    host.ride(_body(), "q2")
    host.running(2)
    host.busy["coder"] = 2  # its server counts the two rides

    host.ride(_body(), "q3")
    assert host.ended("q3") == {
        "request_id": "q3",
        "outcome": "error",
        "error_code": "busy",
    }

    host.unit.release.set()
    assert host.ended("q1")["outcome"] == "complete"
    assert host.ended("q2")["outcome"] == "complete"
    host.busy["coder"] = 0
    host.unit.hold = False
    host.ride(_body(), "q4")
    assert host.ended("q4")["outcome"] == "complete"
    assert len(host.unit.seen) == 3


@pytest.mark.parametrize(
    ("own", "admitted"),
    [
        (0, 2),  # all four free: up to the rider cap
        (1, 2),
        (2, 2),  # the host busy on two: the two free are lent
        (3, 1),  # one free: one ride
        (4, 0),  # none free: the host's own take them all
    ],
)
def test_a_ride_is_busy_where_the_unit_has_no_slot_free(
    host: Host, own: int, admitted: int
) -> None:
    host.unit.hold = True
    taken = 0
    for index in range(3):
        request_id = f"q{index}"
        host.busy["coder"] = own + taken  # the unit's count: the host's and the rides
        host.ride(_body(), request_id)
        if taken < admitted:
            host.running(taken + 1)
            taken += 1
        else:
            assert host.ended(request_id)["error_code"] == "busy"
    assert len(host.unit.seen) == admitted


def test_a_ride_holds_a_slot_the_hosts_own_dispatches_see(host: Host) -> None:
    from mcgyvr.capacity import SlotUnavailableError

    host.unit.hold = True
    host.ride(_body())
    host.running(1)

    with (
        pytest.raises(SlotUnavailableError),
        host.capacity.drain(["coder"], timeout=0.2),
    ):
        pass

    host.unit.release.set()
    assert host.ended()["outcome"] == "complete"
    with host.capacity.drain(["coder"], timeout=1.0):
        pass


def test_a_ride_with_no_slot_free_host_wide_is_busy(host: Host) -> None:
    with host.capacity.drain(["coder"], timeout=1.0):
        host.ride(_body())
        assert host.ended()["error_code"] == "busy"
    assert host.unit.seen == []


# --- like a head relay ---------------------------------------------------------------


def test_rides_count_in_the_rigs_own_bound_of_relays(tmp_path: Path) -> None:
    built = _host(tmp_path, max_active=1, second=True)
    try:
        built.unit.hold = True
        built.ride(_body(), "q1")
        built.running(1)
        built.ride(_body("other.gguf"), "q2", unit_id="other")
        assert built.ended("q2")["error_code"] == "busy"
    finally:
        built.unit.release.set()
        built.relays.cancel_all()
        assert built.unit.server is not None
        built.unit.server.shutdown()


def test_a_ride_and_a_relay_share_one_id_space(host: Host) -> None:
    host.ride(_body())
    assert host.ended()["outcome"] == "complete"
    host.send(
        "relay_request",
        "r2",
        session_id="s1",
        request_id="q1",
        endpoint="chat_completions",
        body_bytes=0,
        stream=False,
        timeout_s=5,
        max_response_bytes=10,
        window=1,
    )
    ends = [f["body"] for f in host.box.of_type("relay_end")]
    assert ends[-1] == {
        "request_id": "q1",
        "outcome": "error",
        "error_code": "duplicate",
    }


def test_a_cancel_ends_a_ride_and_a_sessions_end_does_not(host: Host) -> None:
    host.unit.hold = True
    host.ride(_body())
    host.running(1)

    host.relays.session_ended("s1")
    time.sleep(0.1)
    assert not host.box.of_type("relay_end")

    host.send("relay_cancel", "c1", request_id="q1", reason="client_gone")
    assert host.ended() == {
        "request_id": "q1",
        "outcome": "cancelled",
        "error_code": "cancelled",
    }
    assert host.unit.hung_up.wait(5.0)


def test_a_ride_that_ends_asks_for_a_check_of_the_advert(host: Host) -> None:
    checked = len(host.checks)
    host.now.now = 10.0
    host.ride(_body())
    assert host.ended()["outcome"] == "complete"
    deadline = time.monotonic() + 5.0
    while len(host.checks) == checked and time.monotonic() < deadline:
        time.sleep(0.005)
    assert host.checks[checked:] == [10.0]


def test_the_advert_counts_a_ride_as_no_slot_of_the_hosts(host: Host) -> None:
    host.unit.hold = True
    host.ride(_body())
    host.running(1)
    host.busy["coder"] = 2  # one ride, and one request of the host's own

    host.now.now = 10.0
    host.units.soon()

    advert = host.box.of_type("unit_advert")[-1]["body"]["units"]
    assert advert[0]["free_slots"] == 3
    host.unit.release.set()
    assert host.ended()["outcome"] == "complete"
