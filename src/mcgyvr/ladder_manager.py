"""Swapping a sleeping rung onto a card and back, through a card's switches.

:func:`wake_making_room` sleeps the units whose memory a rung needs and wakes the
rung into it, waking them back when the wake fails; :func:`give_back` wakes such
units back once the rung sleeps again. A fleet's sample swaps a sleeper in and
back with them (:mod:`mcgyvr.fleet.sampler`), over the switches
:class:`mcgyvr.wake.CardSwitches` gives.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Switches(Protocol):
    """The power to sleep and wake rungs, and the card each rung sits on.

    ``sleep`` and ``wake`` answer whether the switch happened. ``room_for`` names
    the units that must sleep to give ``rung`` its card's memory, and ``card_of``
    names the units sharing ``rung``'s card, ``rung`` among them.
    """

    def wake(self, rung: str) -> bool: ...

    def sleep(self, rung: str) -> bool: ...

    def room_for(self, rung: str) -> tuple[str, ...]: ...

    def card_of(self, rung: str) -> tuple[str, ...]: ...


def _ok(ok: bool) -> str:
    return "done" if ok else "failed"


class Record(Protocol):
    """Takes down how one switch call on ``rung`` turned out: whether it worked,
    and whether it was a wake (``awake``) or a sleep."""

    def __call__(self, rung: str, ok: bool, *, awake: bool) -> None: ...


def _unrecorded(rung: str, ok: bool, *, awake: bool) -> None:
    """Take down nothing: the record of a caller that keeps no account of switches."""


def wake_making_room(
    switches: Switches,
    rung: str,
    room: tuple[str, ...],
    record: Record = _unrecorded,
) -> tuple[list[str], tuple[str, ...] | None]:
    """Sleep the units in ``room``, in order, then wake ``rung`` into their memory.

    The lines say what each switch call did. The second item is the units slept
    for ``rung``, to wake back once it sleeps again, or ``None`` when ``rung`` was
    not woken: a room unit that would not sleep stops the wake there, and either
    that or a wake that failed wakes back every unit slept for it first.
    """
    lines: list[str] = []
    slept: list[str] = []
    for unit in room:
        ok = switches.sleep(unit)
        lines.append(f"sleep {unit} to make room for {rung}: {_ok(ok)}")
        record(unit, ok, awake=False)
        if not ok:
            lines.extend(give_back(switches, slept, record))
            return lines, None
        slept.append(unit)
    ok = switches.wake(rung)
    lines.append(f"wake {rung}: {_ok(ok)}")
    record(rung, ok, awake=True)
    if not ok:
        lines.extend(give_back(switches, slept, record))
        return lines, None
    return lines, tuple(slept)


def give_back(
    switches: Switches, units: Sequence[str], record: Record = _unrecorded
) -> list[str]:
    """Wake each of ``units`` back, in order: one line per wake, saying how it went."""
    lines: list[str] = []
    for unit in units:
        ok = switches.wake(unit)
        lines.append(f"wake {unit} back: {_ok(ok)}")
        record(unit, ok, awake=True)
    return lines
