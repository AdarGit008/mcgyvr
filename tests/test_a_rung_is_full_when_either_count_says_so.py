"""A local rung is full when either count says so, and free only when both say free.

Two counts know how busy a rung is, and each misses what the other sees.

* **This process's load** (:meth:`~mcgyvr.capacity.Capacity.load`): the slots it
  has granted and the attempts it has reserved. It sees a batch that is still
  choosing, which the server cannot, and it sees nothing another client sent.
* **The server's own busy count**: what the unit says it has in flight. It sees
  every client — another process, another machine, a person with ``curl`` — and
  it does not see an attempt that has chosen the rung and not yet arrived.

:meth:`~mcgyvr.capacity.Capacity.fullness` is the one definition: full when
either is at the rung's width. Where the server cannot be read, this process's
load decides alone, and the answer says that the server was not read. The
ladder manager and the climb's ``fanout: idle`` spill both ask it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity
from mcgyvr.config import Config, parse
from mcgyvr.escalate import ascent
from mcgyvr.local_pool import SourceMap, source_map

FAST = "local_fast"


def capacity(tmp_path: Path, width: int, busy: dict[str, int | None]) -> Capacity:
    return Capacity({FAST: width}, lock_dir=tmp_path / "slots", busy=busy.get)


def test_a_rung_whose_load_is_at_width_is_full_though_the_server_says_free(
    tmp_path: Path,
) -> None:
    cap = capacity(tmp_path, 2, {FAST: 0})
    cap.reserve(FAST)
    cap.reserve(FAST)

    said = cap.fullness(FAST)

    assert said.full is True
    assert (said.load, said.server, said.width) == (2, 0, 2)


def test_a_rung_whose_server_is_at_width_is_full_though_this_process_sent_nothing(
    tmp_path: Path,
) -> None:
    said = capacity(tmp_path, 2, {FAST: 2}).fullness(FAST)

    assert said.full is True
    assert said.load == 0


def test_a_rung_is_free_only_when_both_counts_say_free(tmp_path: Path) -> None:
    cap = capacity(tmp_path, 2, {FAST: 1})
    cap.reserve(FAST)

    said = cap.fullness(FAST)

    assert said.full is False
    assert (said.load, said.server) == (1, 1)


def test_a_server_that_cannot_be_read_leaves_the_load_to_decide_and_says_so(
    tmp_path: Path,
) -> None:
    cap = capacity(tmp_path, 2, {FAST: None})

    free = cap.fullness(FAST)
    cap.reserve(FAST)
    cap.reserve(FAST)
    full = cap.fullness(FAST)

    assert free.full is False and free.server is None and not free.server_read
    assert full.full is True and full.server is None
    assert "not read" in free.why


def test_a_capacity_given_no_server_reader_reads_no_server(tmp_path: Path) -> None:
    said = Capacity({FAST: 2}, lock_dir=tmp_path / "slots").fullness(FAST)

    assert said.server is None and said.full is False


def test_judging_a_given_server_count_reads_nothing_more(tmp_path: Path) -> None:
    def no_read(source: str) -> int | None:
        raise AssertionError("a count that was handed in was read again")

    cap = Capacity({FAST: 2}, lock_dir=tmp_path / "slots", busy=no_read)

    assert cap.judge(FAST, None, 2).full is True
    assert cap.judge(FAST, None, 1).full is False


# --- several independent clients ----------------------------------------------

# One client: it holds a request open on the server until its stdin closes. It
# shares nothing with the test's process — no capacity, no slot file — which is
# what another machine, or another person's client, shares with it.
CLIENT = """
import sys
from pathlib import Path

marker = Path(sys.argv[1])
marker.write_text("in flight", encoding="utf-8")
print("sent", flush=True)
sys.stdin.read()
marker.unlink()
"""


def test_only_the_server_count_sees_independent_clients(tmp_path: Path) -> None:
    """Three clients in three other processes fill a rung of width three.

    This process's load is zero throughout, so only the server's count can say
    the rung is full — and when they leave, it says it is free again.
    """
    served = tmp_path / "server"
    served.mkdir()

    def server_count(source: str) -> int | None:
        return len(list(served.iterdir()))

    cap = Capacity({FAST: 3}, lock_dir=tmp_path / "slots", busy=server_count)
    clients = [
        subprocess.Popen(
            [sys.executable, "-c", CLIENT, str(served / f"client-{n}")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        for n in range(3)
    ]
    try:
        for client in clients:
            assert client.stdout is not None
            assert client.stdout.readline().strip() == "sent"

        said = cap.fullness(FAST)
        assert said.load == 0, "this process sent nothing"
        assert said.server == 3
        assert said.full is True
    finally:
        for client in clients:
            assert client.stdin is not None
            client.stdin.close()
            client.wait(timeout=30)

    assert cap.fullness(FAST).full is False


# --- the climb's idle spill asks the same question -------------------------------


def idle_ladder(monkeypatch: pytest.MonkeyPatch) -> tuple[Config, SourceMap]:
    from tests.test_escalate_marks_a_climbed_attempt import LADDER

    monkeypatch.setenv("EXAMPLE_API_KEY", "sk-" + "0" * 12)
    config = parse(LADDER.format(fanout="fanout: idle\n"))
    return config, source_map(config)


def next_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, servers: dict[str, int | None]
) -> str | None:
    from tests.test_escalate_marks_a_climbed_attempt import contract

    config, pool = idle_ladder(monkeypatch)
    cap = Capacity.of(config, root=tmp_path / "slots", busy=servers.get)
    return ascent(config, pool, contract(), capacity=cap).next_free_rung


def test_an_idle_spill_steps_past_a_rung_whose_server_is_full(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Another client fills the cheap rung; this batch has sent it nothing."""
    assert next_free(monkeypatch, tmp_path, {"local_fast": 1}) == "local_smart"


def test_an_idle_spill_enters_the_cheap_rung_when_both_counts_say_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert next_free(monkeypatch, tmp_path, {"local_fast": 0}) == "local_fast"


def test_an_idle_spill_whose_server_cannot_be_read_goes_by_its_own_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert next_free(monkeypatch, tmp_path, {"local_fast": None}) == "local_fast"


def test_an_unknown_source_is_refused_like_every_other_question(
    tmp_path: Path,
) -> None:
    from mcgyvr.capacity import CapacityError

    with pytest.raises(CapacityError):
        capacity(tmp_path, 2, {}).fullness("no_such_unit")
