"""A heartbeat's machine reading never holds the agent's sending thread.

Reading the machine takes a second or two on a real rig (the reader is a
subprocess). The agent reads it for a heartbeat on a thread of its own,
before the beat is due, so while a read runs the agent still answers the hub
and sends what its sessions say. A heartbeat goes on time whatever the read:
one whose read is not done carries the latest whole reading, and the read
still running serves a later beat, no second read begun beside it. A
heartbeat carries one read's reading whole, its memory and its cards
together. A read that fails gives a heartbeat with no reading, and the agent
says so. A heartbeat asked for early (a session ended and freed memory)
carries a reading begun after it was asked, and while that read runs the
agent keeps answering the hub and beats on time.

The fake hub's clock moves only when the agent waits on its channel, so the
fake world holds it, in real time, while a read it needs runs on its thread.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from tests.test_a_rig_agent_says_hello_keeps_beating_and_backs_off_when_the_hub_drops import (  # noqa: E501
    Channel,
    Clock,
    Hub,
    _frame,
)

#: The longest real wait for a read the fake world needs, in seconds: far
#: above what a read takes here, so it is only reached when a read never comes.
PATIENCE_S = 2.0
#: A fake clock past this many seconds means the agent never did what the
#: test waits for.
RAN_AWAY_S = 1000.0


class Machine:
    """The machine as the agent reads it, read ``n`` (the hello's is 1) saying
    ``1000 + n`` MiB of RAM free and ``n`` MiB free on its card, so a
    heartbeat names the read it came from twice. A read in ``gated`` waits
    until :meth:`open`; one in ``failing`` fails.

    :meth:`aside` runs a job on a thread of its own, as the agent does, and
    :meth:`settle` waits until every such job has ended or waits at a gate
    the test keeps shut: in that fake world a read takes no time, unless the
    test holds it."""

    def __init__(
        self,
        clock: Clock,
        *,
        gated: tuple[int, ...] = (),
        failing: tuple[int, ...] = (),
    ) -> None:
        self.clock = clock
        self.cond = threading.Condition()
        self.gates = {n: threading.Event() for n in gated}
        self.failing = set(failing)
        self.began: dict[int, float] = {}
        self.ended: set[int] = set()
        self.threads: dict[int, threading.Thread] = {}
        self.reading = 0
        self.most = 0
        self.jobs = 0
        self.at_gate: set[int] = set()

    def read(self) -> Any:
        from mcgyvr.rig import hardware, protocol

        with self.cond:
            n = len(self.began) + 1
            self.began[n] = self.clock.now
            self.threads[n] = threading.current_thread()
            self.reading += 1
            self.most = max(self.most, self.reading)
            self.cond.notify_all()
        try:
            gate = self.gates.get(n)
            if gate is not None:
                with self.cond:
                    self.at_gate.add(n)
                    self.cond.notify_all()
                gate.wait(PATIENCE_S)
            if n in self.failing:
                raise hardware.HardwareError("the machine reader exited 1")
            return hardware.Report(
                machine_id="mch-example",
                ram_total_mb=65536,
                ram_free_mb=1000 + n,
                cards=(
                    protocol.CardReport(
                        index=0,
                        name="Example Card",
                        vram_total_mb=8192,
                        vram_free_mb=n,
                    ),
                ),
                notes=(),
            )
        finally:
            with self.cond:
                self.reading -= 1
                self.ended.add(n)
                self.cond.notify_all()

    def running(self, n: int) -> bool:
        with self.cond:
            return n in self.began and n not in self.ended

    def has_ended(self, n: int) -> Callable[[], bool]:
        return lambda: n in self.ended

    def open(self, n: int) -> None:
        with self.cond:
            self.gates[n].set()
            self.cond.notify_all()

    def aside(self, job: Callable[[], None]) -> None:
        with self.cond:
            self.jobs += 1

        def run() -> None:
            try:
                job()
            finally:
                with self.cond:
                    self.jobs -= 1
                    self.cond.notify_all()

        threading.Thread(target=run, name="test-aside", daemon=True).start()

    def settle(self) -> None:
        def held() -> int:
            return sum(1 for n in self.at_gate if not self.gates[n].is_set())

        self.until(lambda: self.jobs <= held(), "a read that was not held ended")

    def until(self, ready: Callable[[], bool], what: str) -> None:
        with self.cond:
            assert self.cond.wait_for(ready, timeout=PATIENCE_S), f"never: {what}"


class World(Channel):
    """The fake hub's channel. Before fake time passes ``at`` it waits until
    ``ready`` (each of :attr:`holds`), and with :attr:`settled` until the
    machine settles; :attr:`before` is told of each receive, :attr:`after` of
    each frame sent."""

    def __init__(self, hub: Hub, clock: Clock, machine: Machine) -> None:
        super().__init__(hub, clock)
        self.machine = machine
        self.settled = False
        self.holds: list[tuple[float, Callable[[], bool], str]] = []
        self.before: Callable[[], None] = lambda: None
        self.after: Callable[[dict[str, Any]], None] = lambda message: None

    def receive(self, timeout: float) -> str | bytes | None:
        assert self.clock.now < RAN_AWAY_S, "the agent never did what was waited for"
        if self.settled:
            self.machine.settle()
        for at, ready, what in self.holds:
            if self.clock.now + max(timeout, 0.001) >= at:
                self.machine.until(ready, f"{what}, before {at:g} s")
        self.before()
        return super().receive(timeout)

    def send_text(self, text: str) -> None:
        super().send_text(text)
        self.after(self.sent[-1][1])

    def beats(self) -> list[tuple[float, dict[str, Any]]]:
        return [(t, m) for t, m in self.sent if m["type"] == "heartbeat"]


def _agent(world: World, machine: Machine, *, aside: bool, **more: Any) -> Any:
    from mcgyvr.rig import agent, websocket

    worlds = [world]

    def connect() -> World:
        if not worlds:
            raise websocket.HandshakeError("the plan is over", status=401)
        return worlds.pop()

    if aside:
        more["aside"] = machine.aside
    return agent.Agent(
        connect=connect,
        read_hardware=machine.read,
        agent_version="0.1.0",
        clock=world.clock,
        wall=world.clock,
        wait=world.clock.wait,
        draw=lambda: 1.0,
        **more,
    )


def _read_of(heartbeat: dict[str, Any]) -> int:
    """The read a heartbeat's reading came from: its RAM and its card agree."""
    body = heartbeat["body"]
    n = body["cards"][0]["vram_free_mb"]
    assert isinstance(n, int)
    assert body["ram_free_mb"] == 1000 + n, f"a torn reading: {body}"
    return n


def test_while_a_slow_read_runs_the_hub_is_answered_and_the_sessions_are_heard() -> (
    None
):
    from mcgyvr.rig import outbox, sessionwire

    clock = Clock()
    machine = Machine(clock, gated=(2,))
    world = World(Hub(interval=15), clock, machine)
    box = outbox.Outbox()
    status = sessionwire.session_status(None, session_id="s1", state="ready")
    while_reading: dict[str, bool] = {}
    agent = _agent(world, machine, aside=False, outbox=box, say=lambda line: None)
    # the read for the beat at 15 s is under way before the beat is due
    world.holds.append((15.0, lambda: 2 in machine.began, "read 2 began"))

    def hub_asks_and_a_session_speaks() -> None:
        if machine.running(2) and not while_reading:
            while_reading["asked"] = True
            world.inbox.append(_frame("start_worker", model="x"))
            assert box.put(status)

    def sent(message: dict[str, Any]) -> None:
        if message["type"] in ("error", "session_status"):
            while_reading[message["type"]] = machine.running(2)
        if len(world.beats()) == 2 and len(while_reading) == 3:
            machine.open(2)
            agent.stop()

    world.before = hub_asks_and_a_session_speaks
    world.after = sent
    ended = agent.run()

    assert ended.stopped
    assert while_reading == {"asked": True, "error": True, "session_status": True}
    beats = world.beats()[:2]
    # on time, each with the latest whole reading: the hello's
    assert [t for t, _ in beats] == [15.0, 30.0]
    assert [_read_of(m) for _, m in beats] == [1, 1]
    # the read still running served both: none was begun beside it
    assert sorted(machine.began) == [1, 2]
    assert machine.most == 1
    assert machine.threads[2] is not threading.current_thread()


def test_each_heartbeat_carries_a_reading_taken_for_it_when_reads_are_quick() -> None:
    from mcgyvr.rig import agent as rig_agent

    clock = Clock()
    machine = Machine(clock)
    world = World(Hub(interval=15, beats=3), clock, machine)
    agent = _agent(world, machine, aside=False, say=lambda line: None)
    for n, due in ((2, 15.0), (3, 30.0), (4, 45.0)):
        world.holds.append((due, machine.has_ended(n), f"read {n} ended"))
    agent.run()
    beats = world.beats()
    assert [t for t, _ in beats] == [15.0, 30.0, 45.0]
    assert [_read_of(m) for _, m in beats] == [2, 3, 4]
    for (due, _), n in zip(beats, (2, 3, 4), strict=True):
        assert due - rig_agent.READ_AHEAD_S <= machine.began[n] < due
    assert all(machine.threads[n] is not threading.current_thread() for n in (2, 3, 4))


def test_a_read_that_fails_gives_a_heartbeat_with_no_reading_and_a_note() -> None:
    clock = Clock()
    machine = Machine(clock, failing=(2,))
    world = World(Hub(interval=15, beats=2), clock, machine)
    said: list[tuple[str, threading.Thread]] = []
    agent = _agent(
        world,
        machine,
        aside=False,
        say=lambda line: said.append((line, threading.current_thread())),
    )
    world.holds.append((15.0, lambda: 2 in machine.ended, "read 2 ended"))
    world.holds.append((30.0, lambda: 3 in machine.ended, "read 3 ended"))
    agent.run()
    beats = [m for _, m in world.beats()]
    assert beats[0]["body"] == {"cards": []}
    assert _read_of(beats[1]) == 3
    notes = [(line, by) for line, by in said if "carries no reading" in line]
    assert [line for line, _ in notes] == [
        "note: this heartbeat carries no reading: the machine reader exited 1"
    ]
    # said where the agent runs, not on the reader's thread
    assert all(by is threading.current_thread() for _, by in notes)


def test_an_early_heartbeat_carries_a_reading_begun_after_it_was_asked() -> None:
    from mcgyvr.rig import agent as rig_agent

    clock = Clock()
    machine = Machine(clock, gated=(3,))
    world = World(Hub(interval=15), clock, machine)
    world.settled = True
    asked: dict[str, Any] = {}
    agent = _agent(world, machine, aside=True, say=lambda line: None)

    def a_session_ends_while_read_3_runs() -> None:
        if clock.now >= 26.0 and not asked:
            assert machine.running(3)
            asked["at"] = clock.now
            agent.beat_soon()
            world.inbox.append(_frame("start_worker", model="x"))

    def sent(message: dict[str, Any]) -> None:
        if message["type"] == "error":
            asked["answered while read 3 ran"] = machine.running(3)
        beats = world.beats()
        if len(beats) == 2 and not machine.gates[3].is_set():
            machine.open(3)  # the regular beat at 30 s went meanwhile
        if len(beats) == 3:
            agent.stop()

    world.before = a_session_ends_while_read_3_runs
    world.after = sent
    agent.run()

    (t1, b1), (t2, b2), (t3, b3) = world.beats()
    assert asked["answered while read 3 ran"] is True
    assert (t1, _read_of(b1)) == (15.0, 2)
    # due while the early beat's read waited on read 3: on time, read 2's
    assert (t2, _read_of(b2)) == (30.0, 2)
    # the early beat: a read begun after the ask, a second after the last beat
    n = _read_of(b3)
    assert machine.began[n] >= asked["at"]
    assert n == 4  # read 3 had begun before the ask
    assert t2 + rig_agent.EARLY_BEAT_S <= t3 < 45.0
    assert machine.most == 1
