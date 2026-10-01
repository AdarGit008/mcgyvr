"""A switch starts a spanning unit's workers before its head and stops its head first.

A head needs its workers listening, and a worker must not vanish under a head
that is still serving. So when a switch moves a unit that spans rigs, its
workers start (or wake) before its head does, and its head drains, stops or
sleeps before its workers. The verbs are the ones the switch already derives,
only ordered: a rig's own order is kept (a leaving slot's stop still precedes
its arrival's start), anything no span constrains keeps its place, and a switch
no span touches is ordered exactly as before.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.fleet.layout import actions, ordered_actions
from mcgyvr.fleet.spans import Span, spans
from tests import span_fleet as sf

#: ``big_model`` has its head on A, ``remote_head`` has its head on B.
BIG, REMOTE = sf.BIG, sf.REMOTE


def _spans() -> dict[str, Span]:
    return spans(sf.fleet())


def test_a_head_that_sorts_first_starts_after_its_worker() -> None:
    before: dict[str, list[Any]] = {sf.A: [None], sf.B: [None]}
    after = {sf.A: [(BIG, "awake")], sf.B: [(BIG, "awake")]}
    assert actions(before, after) == [(sf.A, "start", BIG), (sf.B, "start", BIG)]
    assert ordered_actions(before, after, _spans()) == [
        (sf.B, "start", BIG),
        (sf.A, "start", BIG),
    ]


def test_a_head_that_sorts_last_stops_before_its_worker() -> None:
    before = {sf.A: [(REMOTE, "awake")], sf.B: [(REMOTE, "awake")]}
    after: dict[str, list[Any]] = {sf.A: [None], sf.B: [None]}
    assert actions(before, after)[0] == (sf.A, "drain", REMOTE), (
        "by name, a worker first"
    )
    assert ordered_actions(before, after, _spans()) == [
        (sf.B, "drain", REMOTE),
        (sf.B, "stop", REMOTE),
        (sf.A, "drain", REMOTE),
        (sf.A, "stop", REMOTE),
    ]


def test_a_wake_starts_workers_first_and_a_sleep_puts_the_head_down_first() -> None:
    awake = {sf.A: [(BIG, "awake")], sf.B: [(BIG, "awake")]}
    asleep = {sf.A: [(BIG, "asleep")], sf.B: [(BIG, "asleep")]}
    assert ordered_actions(asleep, awake, _spans()) == [
        (sf.B, "wake", BIG),
        (sf.A, "wake", BIG),
    ]
    assert ordered_actions(awake, asleep, _spans()) == [
        (sf.A, "drain", BIG),
        (sf.A, "sleep", BIG),
        (sf.B, "drain", BIG),
        (sf.B, "sleep", BIG),
    ]


def test_a_rigs_own_order_and_everything_else_keep_their_place() -> None:
    """The head's slot waits for the worker's start, and nothing else moves: A's
    leaving unit still stops before the head takes its slot, and B's too."""
    before = {sf.A: [("old_a", "awake")], sf.B: [("old_b", "awake")]}
    after = {sf.A: [(BIG, "awake")], sf.B: [(BIG, "awake")]}
    assert ordered_actions(before, after, _spans()) == [
        (sf.A, "drain", "old_a"),
        (sf.A, "stop", "old_a"),
        (sf.B, "drain", "old_b"),
        (sf.B, "stop", "old_b"),
        (sf.B, "start", BIG),
        (sf.A, "start", BIG),
    ]


def test_a_switch_no_span_touches_is_ordered_as_before() -> None:
    before: dict[str, list[Any]] = {
        sf.A: [("x", "awake"), ("y", "asleep")],
        sf.B: [("z", "awake")],
    }
    after: dict[str, list[Any]] = {
        sf.A: [("x", "asleep"), ("y", "awake")],
        sf.B: [None],
    }
    assert ordered_actions(before, after, _spans()) == actions(before, after)
    assert ordered_actions(before, after, {}) == actions(before, after)


def test_two_spanning_units_that_ask_for_a_cycle_keep_each_rigs_own_order() -> None:
    """``big_model`` is first on A and last on B; ``remote_head`` is the other way. Both
    cannot have their head first, so each rig keeps its order and the switch is
    still a permutation of its verbs."""
    before = {
        sf.A: [(REMOTE, "awake"), (BIG, "awake")],
        sf.B: [(BIG, "awake"), (REMOTE, "awake")],
    }
    after: dict[str, list[Any]] = {sf.A: [None, None], sf.B: [None, None]}
    plain = actions(before, after)
    ordered = ordered_actions(before, after, _spans())
    assert sorted(ordered) == sorted(plain)
    for rig in (sf.A, sf.B):
        assert [a for a in ordered if a[0] == rig] == [a for a in plain if a[0] == rig]
