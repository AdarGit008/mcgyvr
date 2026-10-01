"""Queue pressure is read host-wide, from files, and never costs a caller anything.

The promise: a process that is *not* the one reading — a task process among
many, while a long-running manager watches — can say "I am here" and have the
reader count it, with no daemon and no socket between them; and the saying is
best-effort to the point that it cannot fail the work it is attached to.

* **A gauge counts live holders across processes.** A mark is a file whose
  ``flock`` its holder keeps, so a holder in another interpreter is counted
  while it lives. The cross-process tests spawn real interpreters for that
  reason: a count that only ever saw its own threads would pass every in-process
  test and be useless to the one reader that matters.
* **A dead holder is not counted, and its mark is cleaned up.** The kernel
  releases a ``flock`` when its process dies however it dies, so a ``SIGKILL``ed
  holder cannot leave a count behind — the one kind of exit a ``finally`` cannot
  cover.
* **A directory that is not ours is not used.** The rendezvous is a predictable
  path in a shared temporary directory; a count read from one another user made,
  or one that is a symlink, is a number somebody else chose. The gauge then has
  no reading (``None``, not zero) and a ``present`` still runs its body.
* **A board is the manager's one published answer, written atomically.** A
  reader never sees half a document, and a document that is absent, unreadable
  or of another shape is no document.
* **A reading assembles the signals and invents none.** Every host here is
  invented and every directory is under ``tmp_path``; the liveness and
  in-flight reads are injected, so nothing touches a network.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import mcgyvr.pressure as pressure
from mcgyvr.availability import PROBE_TIMEOUT_S, AvailabilityVerdict
from mcgyvr.capacity import Capacity, _slot_stem
from mcgyvr.config import parse
from mcgyvr.pool import Endpoint, UnknownRungError, source_map
from mcgyvr.pressure import Board, Gauge, Pressure, Reading, _stem, climbed_key

FAST = "local_fast"
FAST_HOST = "fast-box.example"
SMART = "local_smart"
SMART_HOST = "smart-box.example"

LADDER = f"""
units:
  {FAST}:
    address: http://{FAST_HOST}:8000
    model: qwen2.5-coder-3b
    rig: fast-rig
    width: 1
  {SMART}:
    address: http://{SMART_HOST}:8001
    model: qwen2.5-coder-7b
    rig: smart-rig
    width: 2
ladder:
- {FAST}
- {SMART}
profile: dev
"""


def marks(directory: Path, key: str) -> list[Path]:
    """The mark files one key has left in a directory, live or not."""
    return sorted(directory.glob(f"{_stem(key)}.*.mark"))


# The child: says it is present under a key until its stdin closes. It builds
# its own gauge in its own process memory, which is the point.
HOLDER = """
import sys
from pathlib import Path

from mcgyvr.pressure import Gauge

with Gauge(Path(sys.argv[1])).present(sys.argv[2]):
    print("ready", flush=True)
    sys.stdin.read()
"""


def spawn_holder(directory: Path, key: str) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(directory), key],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "ready", "the holder never got present"
    return child


# --- the gauge counts the live ----------------------------------------------


def test_a_gauge_counts_every_holder_that_is_present(tmp_path: Path) -> None:
    gauge = Gauge(tmp_path / "gauge")

    assert gauge.count("busy") == 0
    with gauge.present("busy"):
        assert gauge.count("busy") == 1
        with gauge.present("busy"):
            assert gauge.count("busy") == 2, "one holder twice is two marks"
        assert gauge.count("busy") == 1
    assert gauge.count("busy") == 0
    assert marks(tmp_path / "gauge", "busy") == [], "leaving removes the mark"


def test_a_gauge_keeps_one_key_apart_from_another(tmp_path: Path) -> None:
    gauge = Gauge(tmp_path / "gauge")

    with gauge.present("wait.fast"):
        assert gauge.count("wait.fast") == 1
        assert gauge.count("wait.smart") == 0
        assert gauge.count("wait") == 0, "a prefix of a key is not the key"


def test_two_keys_that_sanitize_alike_are_still_two_keys(tmp_path: Path) -> None:
    gauge = Gauge(tmp_path / "gauge")

    assert _stem("a/b") != _stem("a-b")
    with gauge.present("a/b"):
        assert gauge.count("a/b") == 1
        assert gauge.count("a-b") == 0


def test_a_holder_in_another_process_is_counted_while_it_lives(
    tmp_path: Path,
) -> None:
    where = tmp_path / "gauge"
    child = spawn_holder(where, "busy")
    try:
        assert Gauge(where).count("busy") == 1
        with Gauge(where).present("busy"):
            assert Gauge(where).count("busy") == 2, "this process and the child"
    finally:
        assert child.stdin is not None
        child.stdin.close()
        child.wait(timeout=30)

    assert marks(where, "busy") == [], "a holder that leaves cleanly takes its mark"
    assert Gauge(where).count("busy") == 0


def test_a_holder_killed_outright_is_not_counted_and_its_mark_goes(
    tmp_path: Path,
) -> None:
    """The kernel releases the lock; nothing a ``finally`` does is needed."""
    where = tmp_path / "gauge"
    child = spawn_holder(where, "busy")
    assert len(marks(where, "busy")) == 1

    os.kill(child.pid, signal.SIGKILL)
    child.wait(timeout=30)
    assert len(marks(where, "busy")) == 1, "a killed holder leaves its file behind"

    assert Gauge(where).count("busy") == 0
    assert marks(where, "busy") == [], "counting it dead is what removes it"


def test_a_mark_whose_holder_is_dead_is_not_counted_and_is_removed(
    tmp_path: Path,
) -> None:
    where = tmp_path / "gauge"
    gauge = Gauge(where)
    gauge.count("busy")  # makes the directory
    stale = where / f"{_stem('busy')}.999999.1.mark"
    stale.write_text("", encoding="utf-8")

    with gauge.present("busy"):
        assert gauge.count("busy") == 1, "only the live one"
        assert not stale.exists(), "the dead one was swept up"


def test_a_file_still_being_made_is_not_a_mark(tmp_path: Path) -> None:
    """A mark is renamed into place only once locked, so an unlocked file is never
    mistaken for a holder that died."""
    where = tmp_path / "gauge"
    gauge = Gauge(where)
    gauge.count("busy")
    unfinished = where / f"{_stem('busy')}.999999.1.tmp"
    unfinished.write_text("", encoding="utf-8")

    assert gauge.count("busy") == 0
    assert unfinished.exists(), "nothing here is its to remove"


def test_counting_makes_the_directory_private_so_a_first_read_is_zero(
    tmp_path: Path,
) -> None:
    where = tmp_path / "nested" / "gauge"

    assert Gauge(where).count("busy") == 0
    assert where.is_dir()
    assert where.stat().st_mode & 0o077 == 0, "nobody else may write into it"


def test_a_gauge_with_no_directory_given_uses_a_per_user_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    assert pressure.default_directory() == tmp_path / f"mcgyvr-pressure-{os.getuid()}"
    with Gauge().present("busy"):
        assert Gauge().count("busy") == 1
    assert (tmp_path / f"mcgyvr-pressure-{os.getuid()}").is_dir()


# --- a directory that is not ours is not used --------------------------------


def test_a_directory_others_can_write_into_has_no_count_and_is_not_marked(
    tmp_path: Path,
) -> None:
    where = tmp_path / "gauge"
    where.mkdir()
    where.chmod(0o777)
    ran: list[str] = []

    gauge = Gauge(where)
    assert gauge.count("busy") is None, "no reading, which is not a zero"
    with gauge.present("busy"):
        ran.append("body")

    assert ran == ["body"], "the body still ran, unmarked"
    assert list(where.iterdir()) == [], "nothing was written into it"


def test_a_directory_that_is_a_symlink_is_not_used(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real)
    ran: list[str] = []

    gauge = Gauge(link)
    assert gauge.count("busy") is None
    with gauge.present("busy"):
        ran.append("body")

    assert ran == ["body"]
    assert list(real.iterdir()) == [], "the symlink was not followed into"


# --- the gauge never fails the caller ----------------------------------------


def test_a_gauge_whose_directory_cannot_be_made_runs_the_body_and_reads_nothing(
    tmp_path: Path,
) -> None:
    in_the_way = tmp_path / "gauge"
    in_the_way.write_text("a file where the directory should be", encoding="utf-8")
    ran: list[str] = []

    gauge = Gauge(in_the_way)
    with gauge.present("busy"):
        ran.append("body")

    assert ran == ["body"]
    assert gauge.count("busy") is None


def test_a_gauge_that_cannot_lock_still_runs_the_body_and_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(fd: int, how: int) -> None:
        raise OSError("no locks here")

    monkeypatch.setattr(fcntl, "flock", refuse)
    ran: list[str] = []

    with Gauge(tmp_path / "gauge").present("busy"):
        ran.append("body")

    assert ran == ["body"]
    assert list((tmp_path / "gauge").iterdir()) == [], "no scratch file is left"


def test_an_error_in_the_body_is_not_swallowed_and_still_unmarks(
    tmp_path: Path,
) -> None:
    gauge = Gauge(tmp_path / "gauge")

    with (
        pytest.raises(RuntimeError, match="the dispatch died"),
        gauge.present("busy"),
    ):
        raise RuntimeError("the dispatch died")

    assert gauge.count("busy") == 0
    assert marks(tmp_path / "gauge", "busy") == []


def test_holders_on_many_threads_are_each_counted(tmp_path: Path) -> None:
    gauge = Gauge(tmp_path / "gauge")
    arrived = threading.Barrier(5)
    leave = threading.Event()

    def hold() -> None:
        with gauge.present("busy"):
            arrived.wait(timeout=30)
            leave.wait(timeout=30)

    threads = [threading.Thread(target=hold) for _ in range(4)]
    for each in threads:
        each.start()
    arrived.wait(timeout=30)
    try:
        assert gauge.count("busy") == 4
    finally:
        leave.set()
        for each in threads:
            each.join(timeout=30)
    assert gauge.count("busy") == 0


def test_a_name_is_held_by_one_holder_at_a_time_and_freed_on_leaving(
    tmp_path: Path,
) -> None:
    """Two managers of one ladder would each throw switches on the same card."""
    where = tmp_path / "gauge"
    with (
        pressure.exclusive("manager", where) as first,
        pressure.exclusive("manager", where) as second,
    ):
        assert first is True
        assert second is False, "a second holder is refused while the first holds"
    with pressure.exclusive("manager", where) as again:
        assert again is True, "leaving gives the name back"


def test_a_name_held_by_a_killed_process_is_free(tmp_path: Path) -> None:
    """The lock is the kernel's, so a manager that died holds nothing."""
    where = tmp_path / "gauge"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys\n"
            "from pathlib import Path\n"
            "from mcgyvr.pressure import exclusive\n"
            "with exclusive('manager', Path(sys.argv[1])) as held:\n"
            "    print(held, flush=True)\n"
            "    sys.stdin.read()\n",
            str(where),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline().strip() == "True"
    with pressure.exclusive("manager", where) as held:
        assert held is False
    os.kill(child.pid, signal.SIGKILL)
    child.wait(timeout=30)
    with pressure.exclusive("manager", where) as held:
        assert held is True


def test_a_name_in_a_directory_that_is_not_ours_cannot_be_held(
    tmp_path: Path,
) -> None:
    where = tmp_path / "gauge"
    where.mkdir()
    where.chmod(0o777)
    with pressure.exclusive("manager", where) as held:
        assert held is None, "no lock, which is not the same as nobody holding it"
    assert list(where.iterdir()) == []


def test_the_climbed_key_is_per_rung_and_is_not_a_waiting_key() -> None:
    assert climbed_key(FAST) != climbed_key(SMART)
    assert climbed_key(FAST) == climbed_key(FAST)
    assert FAST in climbed_key(FAST)
    assert _stem(climbed_key(FAST)) != _stem(f"wait.{_slot_stem(FAST)}")


# --- the board is one published answer ---------------------------------------


def test_a_published_document_reads_back_with_the_time_it_was_written(
    tmp_path: Path,
) -> None:
    board = Board(tmp_path / "gauge")
    before = time.time()

    assert board.publish({"fanout": "idle", "lead": [FAST]}) is True

    said = board.read()
    assert said is not None
    assert said["fanout"] == "idle"
    assert said["lead"] == [FAST]
    assert before <= said["written_at"] <= time.time()


def test_publishing_does_not_change_the_document_it_was_given(
    tmp_path: Path,
) -> None:
    doc: dict[str, Any] = {"fanout": "none"}

    Board(tmp_path / "gauge").publish(doc)

    assert doc == {"fanout": "none"}


def test_a_second_publish_replaces_the_first_and_leaves_no_scratch_file(
    tmp_path: Path,
) -> None:
    where = tmp_path / "gauge"
    board = Board(where)

    board.publish({"fanout": "none"})
    board.publish({"fanout": "idle"})

    said = board.read()
    assert said is not None and said["fanout"] == "idle"
    assert [p.name for p in where.iterdir()] == ["pipeline.json"]


def test_a_publish_that_cannot_finish_leaves_the_last_document_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Written beside the file and moved over it, so a reader sees one or the other."""
    where = tmp_path / "gauge"
    board = Board(where)
    board.publish({"fanout": "none"})

    def refuse(src: object, dst: object) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(os, "replace", refuse)

    assert board.publish({"fanout": "idle"}) is False
    said = board.read()
    assert said is not None and said["fanout"] == "none"
    assert [p.name for p in where.iterdir()] == ["pipeline.json"]


def test_a_document_that_is_not_json_is_refused_not_raised(tmp_path: Path) -> None:
    board = Board(tmp_path / "gauge")

    assert board.publish({"fanout": object()}) is False
    assert board.read() is None


def test_a_board_with_nothing_published_reads_none(tmp_path: Path) -> None:
    assert Board(tmp_path / "gauge").read() is None


@pytest.mark.parametrize(
    "text",
    ["", "{half a document", "\x00\x01", "[1, 2]", "null", "7", '"a string"'],
)
def test_a_board_that_is_garbage_or_not_a_mapping_reads_none(
    tmp_path: Path, text: str
) -> None:
    where = tmp_path / "gauge"
    where.mkdir(mode=0o700)
    (where / "pipeline.json").write_text(text, encoding="utf-8")

    assert Board(where).read() is None


def test_a_board_of_bytes_that_are_not_text_reads_none(tmp_path: Path) -> None:
    where = tmp_path / "gauge"
    where.mkdir(mode=0o700)
    (where / "pipeline.json").write_bytes(b"\xff\xfe\x00{")

    assert Board(where).read() is None


def test_a_board_in_a_directory_that_is_not_ours_publishes_and_reads_nothing(
    tmp_path: Path,
) -> None:
    where = tmp_path / "gauge"
    where.mkdir()
    (where / "pipeline.json").write_text('{"fanout": "full"}', encoding="utf-8")
    where.chmod(0o777)

    board = Board(where)

    assert board.read() is None, "a document another user may have written"
    assert board.publish({"fanout": "none"}) is False
    assert json.loads((where / "pipeline.json").read_text()) == {"fanout": "full"}


def test_a_board_whose_directory_cannot_be_made_publishes_false(
    tmp_path: Path,
) -> None:
    in_the_way = tmp_path / "gauge"
    in_the_way.write_text("a file", encoding="utf-8")

    assert Board(in_the_way).publish({"fanout": "none"}) is False


def test_a_board_shares_the_gauges_default_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

    assert Board().publish({"fanout": "none"}) is True
    assert (pressure.default_directory() / "pipeline.json").is_file()


# --- a reading assembles the signals -----------------------------------------


def hold_on_threads(
    capacity: Capacity, pool: Any, rung: str, count: int, release: threading.Event
) -> list[threading.Thread]:
    """Hold ``count`` slots of one rung from as many threads, until released.

    Threads because :meth:`~mcgyvr.capacity.Capacity.hold` refuses a thread that
    already holds the bound, and a width of two takes two holders.
    """

    def hold() -> None:
        with capacity.hold(pool.bind(rung), rung=rung):
            release.wait(timeout=30)

    threads = [threading.Thread(target=hold) for _ in range(count)]
    for each in threads:
        each.start()
    deadline = time.monotonic() + 30
    while capacity.in_flight(pool.bind(rung).source, rung) < count:
        assert time.monotonic() < deadline, "the holders never took their slots"
        time.sleep(0.01)
    return threads


def test_a_reading_assembles_liveness_load_queue_and_climbers(
    tmp_path: Path,
) -> None:
    config = parse(LADDER)
    pool = source_map(config)
    gauge = Gauge(tmp_path / "gauge")
    capacity = Capacity.of(config, root=tmp_path / "slots", gauge=gauge)
    asked: list[str] = []

    def live(endpoint: Endpoint) -> bool:
        asked.append(f"live {endpoint.base_url}")
        return True

    def in_flight(endpoint: Endpoint) -> int | None:
        asked.append(f"in_flight {endpoint.base_url}")
        return 3

    release = threading.Event()
    threads = hold_on_threads(capacity, pool, SMART, 2, release)
    # A dispatch with no slot to take: it queues, and the gauge counts it.
    waiter = threading.Thread(target=lambda: _queue_for(capacity, pool, SMART))
    waiter.start()
    try:
        deadline = time.monotonic() + 30
        while capacity.waiting(SMART) != 1:
            assert time.monotonic() < deadline, "the waiter never queued"
            time.sleep(0.01)
        with gauge.present(climbed_key(FAST)), gauge.present(climbed_key(FAST)):
            read = Pressure(pool, capacity, gauge, live=live, in_flight=in_flight)
            smart = read.read(SMART)
            fast = read.read(FAST)
    finally:
        release.set()
        for each in (*threads, waiter):
            each.join(timeout=30)

    assert smart == Reading(
        rung=SMART, awake=True, in_flight=3, waiting=1, climbed=0, width=2
    )
    assert fast == Reading(
        rung=FAST, awake=True, in_flight=3, waiting=0, climbed=2, width=1
    )
    assert asked == [
        f"live http://{SMART_HOST}:8001",
        f"in_flight http://{SMART_HOST}:8001",
        f"live http://{FAST_HOST}:8000",
        f"in_flight http://{FAST_HOST}:8000",
    ]


def _queue_for(capacity: Capacity, pool: Any, rung: str) -> None:
    """One dispatch that waits for a slot and then gives it straight back."""
    with capacity.hold(pool.bind(rung), rung=rung):
        pass


def test_a_reading_of_a_rung_that_is_down_says_so_and_is_still_a_reading(
    tmp_path: Path,
) -> None:
    config = parse(LADDER)
    capacity = Capacity.of(
        config, root=tmp_path / "slots", gauge=Gauge(tmp_path / "gauge")
    )

    reading = Pressure(
        source_map(config),
        capacity,
        Gauge(tmp_path / "gauge"),
        live=lambda endpoint: False,
        in_flight=lambda endpoint: None,
    ).read(FAST)

    assert reading == Reading(
        rung=FAST, awake=False, in_flight=None, waiting=0, climbed=0, width=1
    ), "a status page nobody could read is None, which is not zero in flight"


def test_a_reading_without_a_gauge_has_no_waiting_and_no_climbed(
    tmp_path: Path,
) -> None:
    """A capacity built without a gauge cannot count its waiters, and a gauge
    whose directory is not ours cannot count anything; both are no reading."""
    config = parse(LADDER)
    where = tmp_path / "gauge"
    where.mkdir()
    where.chmod(0o777)

    reading = Pressure(
        source_map(config),
        Capacity.of(config, root=tmp_path / "slots"),
        Gauge(where),
        live=lambda endpoint: True,
        in_flight=lambda endpoint: 0,
    ).read(SMART)

    assert reading.waiting is None
    assert reading.climbed is None
    assert reading.width == 2


def test_a_reading_of_a_rung_nobody_declared_raises_the_pools_own_error(
    tmp_path: Path,
) -> None:
    config = parse(LADDER)
    reader = Pressure(
        source_map(config),
        Capacity.of(config, root=tmp_path / "slots"),
        Gauge(tmp_path / "gauge"),
        live=lambda endpoint: True,
        in_flight=lambda endpoint: 0,
    )

    with pytest.raises(UnknownRungError):
        reader.read("local_ghost")


def test_a_reading_asks_the_real_probes_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing injected the reading uses the availability probe and the
    runner's in-flight reading, with the arguments those take. Both are stubbed
    here, so no network is touched."""
    config = parse(LADDER)
    pool = source_map(config)
    probed: list[tuple[str, float]] = []
    asked: list[tuple[str, str, str | None, int]] = []

    def probe(endpoint: Endpoint, timeout_s: float) -> AvailabilityVerdict:
        probed.append((endpoint.base_url, timeout_s))
        return AvailabilityVerdict(
            source=endpoint.source,
            live=True,
            reason="listed",
            how="stubbed",
            elapsed_s=0.0,
        )

    def unit_in_flight(
        source: str, base_url: str, engine: str | None, max_parallel: int
    ) -> int | None:
        asked.append((source, base_url, engine, max_parallel))
        return 1

    monkeypatch.setattr(pressure, "probe_endpoint", probe)
    monkeypatch.setattr(pressure, "unit_in_flight", unit_in_flight)

    reading = Pressure(
        pool,
        Capacity.of(config, root=tmp_path / "slots"),
        Gauge(tmp_path / "gauge"),
    ).read(SMART)

    assert reading.awake is True
    assert reading.in_flight == 1
    assert probed == [(f"http://{SMART_HOST}:8001", PROBE_TIMEOUT_S)]
    assert asked == [(SMART, f"http://{SMART_HOST}:8001", None, 2)]


def test_a_reading_is_frozen() -> None:
    reading = Reading(rung=FAST, awake=True, in_flight=0, waiting=0, climbed=0, width=1)

    with pytest.raises(AttributeError):
        reading.waiting = 1  # type: ignore[misc]
