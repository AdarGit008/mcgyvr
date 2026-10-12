"""A unit that failed for anyone on this host is held out for everyone.

A cooldown used to live in one process: the ladder manager's failed wakes held a
unit out from the manager alone, and a task's failed dispatches held it out from
that task alone, so the next ``mcgyvr run`` sent work straight back to it. Each
process still counts its own failures in a row. When one of them earns the
sentence, it also writes it to a small host-wide record
(:class:`mcgyvr.pressure.HostCooling`), and every process's cooldown reads it.

The record follows the gauge's and the board's rules: a directory only this
user can have written into, a write that is renamed into place whole, and a
scratch file a dead writer left is swept. Its clock is the wall clock, because
the processes that read it do not share a monotonic one.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.availability import AvailabilityVerdict
from mcgyvr.config import parse
from mcgyvr.cooldown import Cooldown
from mcgyvr.local_pool import source_map
from mcgyvr.pressure import Gauge, HostCooling, RungCooling

FAST = "local_fast"
BIG = "local_big"

LADDER = f"""
units:
  {FAST}:
    address: http://fast-box.example:8000
    model: small-coder
    rig: fast-rig
  {BIG}:
    address: http://big-box.example:8001
    model: large-coder
    rig: big-rig
ladder:
- {FAST}
- {BIG}
"""


def live(endpoint: Any, timeout_s: float) -> AvailabilityVerdict:
    return AvailabilityVerdict(
        source=endpoint.source, live=True, reason="", how="stub", elapsed_s=0.0
    )


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def test_a_hold_written_by_one_record_is_read_by_another(tmp_path: Path) -> None:
    clock = Clock()
    writer = HostCooling(tmp_path / "pressure", clock=clock)
    reader = HostCooling(tmp_path / "pressure", clock=clock)

    writer.hold(BIG, 60.0)

    assert reader.held(BIG) == pytest.approx(60.0)
    assert reader.held(FAST) is None
    clock.t += 61
    assert reader.held(BIG) is None, "a sentence served is no hold"


def test_a_shorter_hold_does_not_cut_a_longer_one(tmp_path: Path) -> None:
    clock = Clock()
    record = HostCooling(tmp_path / "pressure", clock=clock)

    record.hold(BIG, 600.0)
    record.hold(BIG, 60.0)

    assert record.held(BIG) == pytest.approx(600.0)


def test_a_hold_leaves_no_scratch_file(tmp_path: Path) -> None:
    where = tmp_path / "pressure"
    HostCooling(where).hold(BIG, 60.0)

    assert [p.name for p in where.iterdir() if p.name.endswith(".tmp")] == []


def test_a_directory_that_is_not_ours_holds_nothing(tmp_path: Path) -> None:
    where = tmp_path / "pressure"
    where.mkdir()
    where.chmod(0o777)
    record = HostCooling(where)

    record.hold(BIG, 60.0)

    assert record.held(BIG) is None
    assert list(where.iterdir()) == []


def test_a_scratch_file_a_dead_writer_left_is_swept(tmp_path: Path) -> None:
    where = tmp_path / "pressure"
    HostCooling(where).hold(BIG, 60.0)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    left = where / f"held.{BIG}.json.{child.pid}.1.tmp"
    left.write_text("{", encoding="utf-8")

    Gauge(where).count("anything")

    assert not left.exists()


# --- the cooldowns that read it -------------------------------------------------

CHILD = """
import sys
from pathlib import Path

from mcgyvr.cooldown import Cooldown
from mcgyvr.pressure import HostCooling

cooldown = Cooldown(shared=HostCooling(Path(sys.argv[1])))
for _ in range(3):
    cooldown.record_failure(sys.argv[2])
print("held", flush=True)
"""


def test_a_unit_another_process_saw_fail_is_held_out_here(tmp_path: Path) -> None:
    where = tmp_path / "pressure"
    child = subprocess.run(
        [sys.executable, "-c", CHILD, str(where), BIG],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert child.stdout.strip() == "held", child.stderr

    pool = source_map(parse(LADDER))
    here = Cooldown(probe=live, shared=HostCooling(where))
    out = here.unavailable([pool.bind(FAST), pool.bind(BIG)])

    assert set(out) == {BIG}
    assert "host" in out[BIG]


def test_a_failure_streak_short_of_the_threshold_holds_nobody_out(
    tmp_path: Path,
) -> None:
    where = tmp_path / "pressure"
    pool = source_map(parse(LADDER))
    one = Cooldown(probe=live, shared=HostCooling(where))
    one.record_failure(BIG)
    one.record_failure(BIG)

    other = Cooldown(probe=live, shared=HostCooling(where))

    assert other.unavailable([pool.bind(BIG)]) == {}


def test_the_managers_failed_switches_hold_a_unit_out_from_tasks(
    tmp_path: Path,
) -> None:
    where = tmp_path / "pressure"
    pool = source_map(parse(LADDER))
    manager = RungCooling(pool, hold_s=600.0, shared=HostCooling(where))
    for _ in range(3):
        manager.failed(BIG)

    task = Cooldown(probe=live, shared=HostCooling(where))

    assert set(task.unavailable([pool.bind(BIG)])) == {BIG}


def test_a_tasks_failed_dispatches_hold_a_unit_out_from_the_manager(
    tmp_path: Path,
) -> None:
    where = tmp_path / "pressure"
    pool = source_map(parse(LADDER))
    task = Cooldown(probe=live, shared=HostCooling(where))
    for _ in range(3):
        task.record_failure(BIG)

    manager = RungCooling(pool, hold_s=600.0, shared=HostCooling(where))

    assert manager.cooled((FAST, BIG)) == frozenset({BIG})


def test_a_cooldown_with_no_shared_record_is_its_own_process_alone(
    tmp_path: Path,
) -> None:
    pool = source_map(parse(LADDER))
    one = Cooldown(probe=live)
    for _ in range(3):
        one.record_failure(BIG)

    assert Cooldown(probe=live).unavailable([pool.bind(BIG)]) == {}
