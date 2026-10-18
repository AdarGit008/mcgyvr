"""Time one link through the door, and read the timing back as transfers.

Every timing is a link run of the door, ``mcgyvr.serving.run link --host H``: two
cards of one rig are a single ``--peer`` run on that rig, while two rigs are a
``--sink`` started on the worker at the address the head reaches it at plus a
``--send`` run on the head, the sink reaped whether or not the sender ran. Each
run answers one JSON object on its last line of stdout, which :func:`time_link`
reads as a non-empty list of ``[bytes, seconds]`` transfers; a non-zero exit, an
``error``, or a transfer that is not such a pair raises :class:`LinkReadError`
naming the link that could not be timed.
"""

from __future__ import annotations

import ipaddress
import json
import math
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from mcgyvr.fleet.links import PCIE, link_class
from mcgyvr.serving import linktime

#: How long a started link run may hold before `_Started.wait` kills it and
#: answers 124: the timer's whole bound, and a minute of slack for the spawn.
DOOR_WAIT_S = linktime.WHOLE_S + 60.0
#: The most transfers one answer may carry; a longer list is refused, not read.
MOST_TRANSFERS = 64


class LinkReadError(ValueError):
    """A link could not be timed, or its timer answered nothing readable.

    The message names the link, so a refusal says which of the links a probe
    timed is the one that failed.
    """


@dataclass(frozen=True)
class LinkEnds:
    """The two ends of one link: a rig and a card on each side, plus the address.

    ``address`` is the IPv4 address the head reaches the worker at, and only a
    link between two rigs carries one: two cards of one rig talk to each other
    without it, so the ends a probe builds for them leave it None.
    """

    host_a: str
    gpu_a: int
    host_b: str
    gpu_b: int
    address: str | None = None

    @property
    def link_class(self) -> str:
        return link_class(self.host_a, self.host_b)

    @property
    def key(self) -> str:
        """The link as one line: a probe sorts ends by it, a refusal quotes it.

        Two cards of one rig name both cards, since which pair of cards shares the
        bus is what is being read; two rigs name only the two rigs.
        """
        if self.link_class == PCIE:
            return f"{self.host_a} card {self.gpu_a} -> card {self.gpu_b}"
        return f"{self.host_a} -> {self.host_b}"


#: What `door_timer` answers and what a probe holds as its link reader: one link
#: in, the transfers its timer measured out.
LinkTimer = Callable[[LinkEnds], Sequence[tuple[int, float]]]


@dataclass(frozen=True)
class Ran:
    """What one link run left behind: its exit code and the text of both streams.

    ``stdout`` carries the timer's JSON on its last line, and ``stderr`` the
    door's own prose, whose last line a refusal quotes.
    """

    code: int
    stdout: str
    stderr: str


class Pending(Protocol):
    """A link run already under way, kept so it can be waited for and reaped.

    A sink is started this way: it must be listening before the sender connects,
    so `Door.start` answers before the run has finished.
    """

    def wait(self) -> Ran:
        """Wait for the run to end, and answer what it left."""


class Door(Protocol):
    """How a link run is spawned, so a timing can be driven without a rig.

    `DoorLinks` is the real one, spawning the door's ``link`` verb for the named
    host; a test passes a door of its own that answers as the timer would.
    """

    def run(self, host: str, args: Sequence[str]) -> Ran:
        """Run one link command on ``host`` to the end, and answer what it left."""

    def start(self, host: str, args: Sequence[str]) -> Pending:
        """Start one link command on ``host``, answering before it has finished.

        The sink is what needs this: what it leaves is waited for once the
        sender has answered.
        """


class _Started:
    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self._proc = proc

    def wait(self) -> Ran:
        try:
            out, err = self._proc.communicate(timeout=DOOR_WAIT_S)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            out, err = self._proc.communicate()
            return Ran(124, out, err + "\nthe link run outlasted its bound")
        return Ran(self._proc.returncode, out, err)


class DoorLinks:
    """The door itself: every run is ``python -m mcgyvr.serving.run link``.

    ``--host`` names the rig the timer runs on, and the rest of the argv is the
    timer's own mode, one of ``--peer``, ``--sink`` or ``--send``. Both pipes are
    captured and stdin is closed, so a run neither blocks on input nobody meant
    to give it nor writes over the caller's own streams.
    """

    def start(self, host: str, args: Sequence[str]) -> Pending:
        from mcgyvr.serving.gatelib import DOOR_MODULE

        argv = [sys.executable, "-m", DOOR_MODULE, "link"]
        argv += ["--host", host, *args]
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return _Started(proc)

    def run(self, host: str, args: Sequence[str]) -> Ran:
        return self.start(host, args).wait()


def _said(ran: Ran, what: str) -> dict[str, object]:
    """The JSON object a link run answered, or a refusal naming the link.

    The timer prints its reading on the last non-blank line of stdout. An
    ``error`` in that object is raised whether or not the run exited 0, and any
    other reading is refused unless the run exited 0 and answered an object, with
    the run's code and the last line of its stderr, cut short, in the message.
    """
    lines = [line for line in ran.stdout.splitlines() if line.strip()]
    said: object = None
    if lines:
        try:
            said = json.loads(lines[-1])
        except ValueError:
            said = None
    if isinstance(said, dict) and isinstance(said.get("error"), str):
        raise LinkReadError(f"{what}: {said['error']}")
    if ran.code != 0 or not isinstance(said, dict):
        tail = (ran.stderr.strip().splitlines() or ["(nothing on stderr)"])[-1]
        raise LinkReadError(f"{what}: the link run exited {ran.code}: {tail[:300]}")
    return said


def _transfers(said: dict[str, object], what: str) -> list[tuple[int, float]]:
    raw = said.get("transfers")
    if not isinstance(raw, list) or not raw or len(raw) > MOST_TRANSFERS:
        raise LinkReadError(f"{what}: the timer answered no list of transfers")
    out: list[tuple[int, float]] = []
    for item in raw:
        if not (isinstance(item, list) and len(item) == 2):
            raise LinkReadError(f"{what}: a transfer is [bytes, seconds], not {item!r}")
        size, seconds = item
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or isinstance(seconds, bool)
            or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds)
        ):
            raise LinkReadError(f"{what}: a transfer is [bytes, seconds], not {item!r}")
        out.append((size, float(seconds)))
    return out


def worker_address(rig: str, bind: str | None) -> str | None:
    """The IPv4 address the head reaches this worker at, or None if it states none.

    The worker shard's own ``bind`` is tried first and the rig name second, since
    a rig named by its address already says where it is. A name that is no IPv4
    literal answers None rather than being resolved: the sender is handed an
    address to aim at, never a name to look up.
    """
    for candidate in (bind, rig):
        if candidate is None:
            continue
        try:
            return str(ipaddress.IPv4Address(candidate))
        except ValueError:
            continue
    return None


def time_link(
    door: Door, ends: LinkEnds, *, port: int = linktime.LINK_PORT
) -> list[tuple[int, float]]:
    """Time one link, and answer the transfers its timer measured.

    Two cards of one rig are a single ``--peer`` run on that rig. Two rigs are a
    ``--sink`` started on the worker at ``ends.address`` and ``port`` and then a
    ``--send`` run from the head at that same address, the sink waited for in a
    ``finally`` whatever became of the sender. A worker that states no address is
    refused before anything runs, because the sender needs one to aim at. The
    sender's transfers are what answers; the sink's own word is only checked, so
    a receiver that failed fails the timing.
    """
    what = f"the link {ends.key}"
    if ends.link_class == PCIE:
        ran = door.run(ends.host_a, ["--peer", str(ends.gpu_a), str(ends.gpu_b)])
        return _transfers(_said(ran, what), what)
    if ends.address is None:
        raise LinkReadError(
            f"{what}: {ends.host_b} states no IPv4 address the head reaches it at; "
            "state it as the worker shard's `bind`"
        )
    sink = door.start(ends.host_b, ["--sink", ends.address, str(port)])
    try:
        sent = door.run(ends.host_a, ["--send", ends.address, str(port)])
    finally:
        received = sink.wait()
    transfers = _transfers(_said(sent, what), what)
    _said(received, f"{what} (its sink on {ends.host_b})")
    return transfers


def door_timer(door: Door | None = None) -> LinkTimer:
    """A `LinkTimer` that times links through ``door``, the real door by default.

    The door is held here instead of being passed per call, so a caller asks once
    for a timer and every link that timer is asked to time goes through the same
    door.
    """
    through = door if door is not None else DoorLinks()

    def timer(ends: LinkEnds) -> list[tuple[int, float]]:
        return time_link(through, ends)

    return timer
