"""`mcgyvr.cli.streams`: runs beside each other write their output whole.

Inside `routed()`, a thread inside `held()` keeps what it writes to stdout and
stderr, in order, and writes it out in one go when its block ends; any other
thread's writes go out a whole line at a time, so a held block never lands
inside one of them. Outside `routed()` nothing is held.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from mcgyvr.cli import streams


def test_a_held_block_is_written_whole_after_the_line_it_found_half_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def worker() -> None:
        with streams.held():
            print("held one")
            print("held err", file=sys.stderr)
            print("held two")

    with streams.routed():
        sys.stdout.write("this line ")
        other = threading.Thread(target=worker)
        other.start()
        other.join()
        sys.stdout.write("is whole\n")
        sys.stdout.write("left open")

    out = capsys.readouterr()
    assert out.out == "held one\nheld two\nthis line is whole\nleft open"
    assert out.err == "held err\n"


def test_a_held_block_that_raises_is_still_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def worker() -> None:
        with pytest.raises(RuntimeError), streams.held():
            print("said before it broke")
            raise RuntimeError("broke")

    with streams.routed():
        other = threading.Thread(target=worker)
        other.start()
        other.join()

    assert capsys.readouterr().out == "said before it broke\n"


def test_outside_routed_nothing_is_held(capsys: pytest.CaptureFixture[str]) -> None:
    out = sys.stdout
    with streams.held():
        print("as always")
        assert sys.stdout is out
    assert capsys.readouterr().out == "as always\n"


def test_routed_puts_the_streams_back() -> None:
    out, err = sys.stdout, sys.stderr
    with streams.routed():
        assert sys.stdout is not out
        assert sys.stdout.encoding == out.encoding
    assert (sys.stdout, sys.stderr) == (out, err)


def test_what_a_held_run_s_own_batch_writes_is_held_with_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run's draws go to `run_batch` threads; they write into its block."""
    from mcgyvr.capacity import Capacity, run_batch

    capacity = Capacity({"unit": 2}, lock_dir=tmp_path / "slots")

    def draw(name: str) -> Callable[[Capacity], None]:
        def job(_: Capacity) -> None:
            print(f"note: {name}")

        return job

    def worker() -> None:
        with streams.held():
            print("run starts")
            run_batch([draw("one"), draw("two")], capacity, workers=2)
            print("run ends")

    with streams.routed():
        sys.stdout.write("outside ")
        other = threading.Thread(target=worker)
        other.start()
        other.join()
        sys.stdout.write("whole\n")

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "run starts"
    assert sorted(lines[1:3]) == ["note: one", "note: two"]
    assert lines[3:] == ["run ends", "outside whole"]
