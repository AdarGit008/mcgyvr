"""#185's acceptance: the capacity bound holds across *processes*, not threads.

The in-process suite (``test_capacity.py``) cannot see the defect this lane
fixed — a ``threading.BoundedSemaphore`` passes every one of its tests while
silently doubling the declared capacity the moment a second lane dispatches at
the same rig. So the tests here spawn real interpreter processes, each
constructing its **own** :class:`~mcgyvr.capacity.Capacity` from the same
declaration, which is exactly what two parallel worktrees do.

The shapes are the survey's (issue #185):

* the bound test is multica's ``concurrent_claim_test`` translated to slot
  semantics — N processes released from a barrier, an append-only log replayed
  for the concurrency it actually reached, never above the limit and provably
  *at* it (a bound never approached is vacuously satisfied);
* the claim test asserts one winner and N-1 fast refusals, with the exclusion
  proved **host-side**: the parent — a process mcgyvr knows nothing about —
  cannot ``flock`` the slot file while the winner holds it, so the mutual
  exclusion is the kernel's, not this module's bookkeeping agreeing with
  itself;
* the kill test is container-use's reason for ``flock``: a ``SIGKILL``ed
  holder strands nothing, because the kernel releases what the process cannot.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, CapacityError, _slot_stem
from mcgyvr.pool import Endpoint, Protocol

BASE_URL = "http://rig:11434"


def _endpoint(limit: int) -> Endpoint:
    return Endpoint(
        source="rig",
        base_url=BASE_URL,
        protocol=Protocol.OPENAI,
        max_parallel=limit,
        credential_env=None,
    )


# The child: builds its own Capacity (its own process memory — the point),
# reports ready, waits on the barrier, then holds one slot and logs the hold
# window to an append-only file the parent replays.
CHILD = """
import os, sys, time
from pathlib import Path

from mcgyvr.capacity import Capacity, CapacityError
from mcgyvr.pool import Endpoint, Protocol

lock_dir, log_file, ready_dir, go_file, limit, timeout, hold_s = sys.argv[1:8]
limit = int(limit)
timeout = None if timeout == "none" else float(timeout)

capacity = Capacity({"rig": limit}, lock_dir=Path(lock_dir))
endpoint = Endpoint(
    source="rig",
    base_url="http://rig:11434",
    protocol=Protocol.OPENAI,
    max_parallel=limit,
    credential_env=None,
)

(Path(ready_dir) / str(os.getpid())).touch()
while not Path(go_file).exists():
    time.sleep(0.001)

def log(mark: str) -> None:
    with open(log_file, "a") as handle:
        handle.write(f"{mark} {time.monotonic()}\\n")

try:
    with capacity.hold(endpoint, timeout=timeout):
        log("+")
        time.sleep(float(hold_s))
        log("-")
    print("HELD")
except CapacityError:
    print(f"REFUSED {time.monotonic()}")
"""


def _spawn(
    tmp_path: Path, count: int, limit: int, timeout: str, hold_s: str
) -> list[subprocess.Popen[str]]:
    """Start ``count`` children, wait until all stand at the barrier, release it."""
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    ready = tmp_path / "ready"
    ready.mkdir()
    go = tmp_path / "go"
    argv = [
        sys.executable,
        str(script),
        str(tmp_path / "locks"),
        str(tmp_path / "log"),
        str(ready),
        str(go),
        str(limit),
        timeout,
        hold_s,
    ]
    children = [
        subprocess.Popen(argv, stdout=subprocess.PIPE, text=True) for _ in range(count)
    ]
    deadline = time.monotonic() + 30
    while len(list(ready.iterdir())) < count:
        assert time.monotonic() < deadline, "children never reached the barrier"
        time.sleep(0.005)
    go.touch()
    return children


def _outcomes(children: list[subprocess.Popen[str]]) -> list[str]:
    lines: list[str] = []
    for child in children:
        out, _ = child.communicate(timeout=60)
        assert child.returncode == 0
        lines.append(out.strip())
    return lines


def test_processes_on_a_barrier_never_exceed_the_declared_capacity(
    tmp_path: Path,
) -> None:
    """Six processes, one source declared at 2 — the two-lanes scenario, tripled.

    Each child is a separate interpreter with its own Capacity built from the
    same declaration; before #185 each would have granted 2, admitting 6 at
    once. The log is append-only, so replaying it in write order reconstructs
    the true interleaving of hold windows.
    """
    children = _spawn(tmp_path, count=6, limit=2, timeout="none", hold_s="0.15")
    assert _outcomes(children) == ["HELD"] * 6

    inside = peak = 0
    for line in (tmp_path / "log").read_text(encoding="utf-8").splitlines():
        inside += 1 if line.startswith("+") else -1
        peak = max(peak, inside)
        assert inside <= 2, "the host-wide bound was exceeded"
    assert inside == 0  # every hold was released
    assert peak == 2  # and the ceiling was genuinely reached, not avoided


def test_a_claim_has_one_winner_and_the_losers_are_refused_fast(
    tmp_path: Path,
) -> None:
    """timeout=0 is multica's shape: one winner, no queue, silent-fast losers.

    The refusal times prove causality — every loser was refused inside the
    winner's hold window, so it was refused *because* the winner held the only
    slot, not because of some unrelated failure.
    """
    children = _spawn(tmp_path, count=6, limit=1, timeout="0", hold_s="1.5")

    # Host-side proof, taken while the winner still holds: this parent process
    # cannot take the slot file's flock, so the exclusion lives in the kernel.
    log = tmp_path / "log"
    deadline = time.monotonic() + 30
    while not log.exists():
        assert time.monotonic() < deadline
        time.sleep(0.005)
    slot = tmp_path / "locks" / f"{_slot_stem(BASE_URL)}.0.slot"
    fd = os.open(slot, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            pass  # locked by the winner, as it must be
        else:  # pragma: no cover - the failure this test exists to catch
            raise AssertionError("parent took a slot the winner was holding")
    finally:
        os.close(fd)

    outcomes = _outcomes(children)
    held = [line for line in outcomes if line == "HELD"]
    refused = [line for line in outcomes if line.startswith("REFUSED")]
    assert len(held) == 1
    assert len(refused) == 5

    marks = dict(line.split() for line in log.read_text(encoding="utf-8").splitlines())
    released = float(marks["-"])
    for line in refused:
        # Refused strictly before the winner released: the slot was held the
        # whole time a loser was told no. (No lower bound: a loser can be
        # refused in the microseconds between the winner's flock and its log
        # line — the kernel has serialized them; the log write just lags.)
        assert float(line.split()[1]) < released


def test_a_killed_holder_does_not_strand_the_capacity(tmp_path: Path) -> None:
    """SIGKILL the holder; the kernel gives the slot back. Nothing reaps.

    This is the chosen answer to \"no acquisition can block forever\": the
    parent — a different process, arriving after the death — takes the slot
    within its own short timeout, which the old in-memory semaphore could
    never have granted.
    """
    (holder,) = _spawn(tmp_path, count=1, limit=1, timeout="none", hold_s="60")
    log = tmp_path / "log"
    deadline = time.monotonic() + 30
    while not log.exists():
        assert time.monotonic() < deadline
        time.sleep(0.005)
    holder.send_signal(signal.SIGKILL)
    holder.wait(timeout=30)

    capacity = Capacity({"rig": 1}, lock_dir=tmp_path / "locks")
    with capacity.hold(_endpoint(1), timeout=5.0):
        pass  # acquiring at all is the assertion


def test_two_capacity_instances_in_one_process_share_the_bound(
    tmp_path: Path,
) -> None:
    """The bound belongs to the rig, not to the Capacity object observing it.

    Two instances — a stand-in for any two dispatch stacks that were built
    separately — see one slot, because the slot is a file, not a field.
    """
    endpoint = _endpoint(1)
    first = Capacity({"rig": 1}, lock_dir=tmp_path / "locks")
    second = Capacity({"rig": 1}, lock_dir=tmp_path / "locks")
    with (
        first.hold(endpoint),
        pytest.raises(CapacityError, match="host-wide"),
        second.hold(endpoint, timeout=0),
    ):
        pass  # pragma: no cover - must not be reached
