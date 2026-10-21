"""Queue pressure is read host-wide, from files, and never costs a caller anything.

The promise: a process that is *not* the one reading — a task process among
many — can say "I am here" and have the
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

Every directory here is under ``tmp_path``.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

import mcgyvr.pressure as pressure
from mcgyvr.pressure import Gauge, _stem


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
    unfinished = where / f"{_stem('busy')}.{os.getpid()}.1.tmp"
    unfinished.write_text("", encoding="utf-8")

    assert gauge.count("busy") == 0
    assert unfinished.exists(), "its maker is alive, so it is not its to remove"


def a_dead_pid() -> int:
    """The pid of a process that has exited and been reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    return child.pid


def test_scratch_files_a_dead_process_left_are_swept_by_the_next_count(
    tmp_path: Path,
) -> None:
    """A process killed between making a scratch file and renaming it would
    otherwise leave the file there for good: nothing else ever names it."""
    where = tmp_path / "gauge"
    gauge = Gauge(where)
    gauge.count("busy")
    dead = a_dead_pid()
    left = [
        where / f"{_stem('busy')}.{dead}.1.tmp",
        where / f"pipeline.json.{dead}.2.tmp",
    ]
    for path in left:
        path.write_text("", encoding="utf-8")

    assert gauge.count("busy") == 0
    assert [path for path in left if path.exists()] == []


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
