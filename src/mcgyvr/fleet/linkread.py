""

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

#
#
DOOR_WAIT_S = linktime.WHOLE_S + 60.0
#
MOST_TRANSFERS = 64


class LinkReadError(ValueError):
    ""


@dataclass(frozen=True)
class LinkEnds:
    ""

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
        ""
        if self.link_class == PCIE:
            return f"{self.host_a} card {self.gpu_a} -> card {self.gpu_b}"
        return f"{self.host_a} -> {self.host_b}"


#
LinkTimer = Callable[[LinkEnds], Sequence[tuple[int, float]]]


@dataclass(frozen=True)
class Ran:
    ""

    code: int
    stdout: str
    stderr: str


class Pending(Protocol):
    ""

    def wait(self) -> Ran:
        ""


class Door(Protocol):
    ""

    def run(self, host: str, args: Sequence[str]) -> Ran:
        ""

    def start(self, host: str, args: Sequence[str]) -> Pending:
        ""


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
    ""

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
    ""
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
    ""
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
    ""
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
    ""
    through = door if door is not None else DoorLinks()

    def timer(ends: LinkEnds) -> list[tuple[int, float]]:
        return time_link(through, ends)

    return timer
