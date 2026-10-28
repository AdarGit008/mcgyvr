"""`capacity.run_eager` keeps up to `workers` jobs in flight, refilled one by one.

`run_batch` runs a fixed list of jobs to its end. `run_eager` is its sibling
for work whose next job depends on what came of the last: it asks `ready`
again after every settle, so a job that ends early frees its worker for the
next one while a slow one is still running. Every ordering below is driven by
events, never by sleeping.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

from mcgyvr.capacity import CapacityError, run_eager

WAIT = 10.0


class Queue:
    """Items to hand out, in order; one is out of `ready` once started."""

    def __init__(self, *items: str) -> None:
        self.waiting = list(items)
        self.settled: list[tuple[str, str]] = []
        self.abandoned: list[tuple[str, str]] = []
        self.started: list[str] = []
        self.threads: dict[str, threading.Thread] = {}

    def ready(self) -> tuple[str, ...]:
        return tuple(self.waiting)

    def start(self, job: Callable[[str], str]) -> Callable[[str], Callable[[], str]]:
        def started(item: str) -> Callable[[], str]:
            self.waiting.remove(item)
            self.started.append(item)

            def run() -> str:
                self.threads[item] = threading.current_thread()
                return job(item)

            return run

        return started

    def settle(self, item: str, value: str) -> None:
        self.settled.append((item, value))

    def abandon(self, item: str, value: str) -> None:
        self.abandoned.append((item, value))


def test_one_worker_runs_each_job_on_the_calling_thread_in_order() -> None:
    queue = Queue("a", "b", "c")

    run_eager(
        queue.ready,
        queue.start(lambda item: item.upper()),
        queue.settle,
        workers=1,
    )

    assert queue.settled == [("a", "A"), ("b", "B"), ("c", "C")]
    assert {t for t in queue.threads.values()} == {threading.current_thread()}


def test_a_job_that_ends_early_frees_its_worker_while_a_slow_one_runs() -> None:
    """Two workers, three jobs: `c` starts once `b` ends, while `a` still runs."""
    queue = Queue("a", "b", "c")
    c_settled = threading.Event()

    def job(item: str) -> str:
        if item == "a":
            # `a` ends only once `c` has been settled: had the pool waited for
            # a whole wave, `c` would never start and this would time out.
            assert c_settled.wait(WAIT)
        return item

    def settle(item: str, value: str) -> None:
        queue.settle(item, value)
        if item == "c":
            c_settled.set()

    run_eager(queue.ready, queue.start(job), settle, workers=2)

    assert queue.started == ["a", "b", "c"]
    assert [item for item, _ in queue.settled] == ["b", "c", "a"]
    assert all(t is not threading.current_thread() for t in queue.threads.values())


def test_ready_is_asked_again_after_every_settle() -> None:
    """What a settle makes ready is started without waiting for the others."""
    queue = Queue("a", "b")
    asked: list[tuple[str, ...]] = []
    later_settled = threading.Event()

    def ready() -> tuple[str, ...]:
        asked.append(queue.ready())
        return queue.ready()

    def settle(item: str, value: str) -> None:
        queue.settle(item, value)
        if item == "a":
            queue.waiting.append("after-a")
        if item == "after-a":
            later_settled.set()

    def job(item: str) -> str:
        if item == "b":
            assert later_settled.wait(WAIT)
        return item

    run_eager(ready, queue.start(job), settle, workers=2)

    assert [item for item, _ in queue.settled] == ["a", "after-a", "b"]
    assert asked[0] == ("a", "b")
    assert ("after-a",) in asked


def test_a_job_that_raises_is_raised_once_the_one_in_flight_has_ended() -> None:
    """Whichever of the two ends first, the error is raised and nothing is lost:
    the other job is settled (it ended first) or abandoned (it ended after)."""
    queue = Queue("bad", "slow")
    slow_started = threading.Event()

    def job(item: str) -> str:
        if item == "bad":
            assert slow_started.wait(WAIT)
            raise RuntimeError("the job broke")
        slow_started.set()
        return item

    with pytest.raises(RuntimeError, match="the job broke"):
        run_eager(
            queue.ready,
            queue.start(job),
            queue.settle,
            workers=2,
            abandon=queue.abandon,
        )

    assert queue.started == ["bad", "slow"]
    assert queue.settled + queue.abandoned == [("slow", "slow")]


def test_a_settle_that_raises_starts_nothing_new_and_abandons_what_runs() -> None:
    queue = Queue("a", "b", "c")
    b_may_end = threading.Event()

    def job(item: str) -> str:
        if item == "b":
            assert b_may_end.wait(WAIT)
        return item

    def settle(item: str, value: str) -> None:
        b_may_end.set()
        raise RuntimeError("the settle broke")

    with pytest.raises(RuntimeError, match="the settle broke"):
        run_eager(
            queue.ready,
            queue.start(job),
            settle,
            workers=2,
            abandon=queue.abandon,
        )

    assert queue.started == ["a", "b"]
    assert queue.abandoned == [("b", "b")]


def test_an_interrupt_while_settling_starts_nothing_new() -> None:
    queue = Queue("a", "b", "c")
    b_may_end = threading.Event()

    def job(item: str) -> str:
        if item == "b":
            assert b_may_end.wait(WAIT)
        return item

    def settle(item: str, value: str) -> None:
        b_may_end.set()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_eager(
            queue.ready,
            queue.start(job),
            settle,
            workers=2,
            abandon=queue.abandon,
        )

    assert queue.started == ["a", "b"]
    assert queue.abandoned == [("b", "b")]


def test_no_worker_is_refused() -> None:
    queue = Queue("a")
    with pytest.raises(CapacityError, match="workers=0"):
        run_eager(queue.ready, queue.start(str), queue.settle, workers=0)
