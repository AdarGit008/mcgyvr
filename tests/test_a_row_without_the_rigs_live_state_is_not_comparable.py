"""A row that cannot name its rig decays into a story about an afternoon.

No throughput artifact in this archive records host CPU, RAM or clock state at
measurement time, which is why the whole archive decayed: RAM swapped between
srv1 and srv2 twice in six days, a 2026-08-25 spec was quoted on 2026-08-31 and
was wrong in both directions, and srv1's max clock read 4800 MHz on 2026-08-31
and 4600 today with nobody having touched it.

Two rules. Every measurement row resolves to a complete stamp, re-read per arm
rather than once per file. And the state read at the end equals the state read at
the start, because a hard lock wipes the BIOS profile — srv1 read PL1 95 W at
05:23 and 4095 W at 05:57 — and a lock takes the ssh pipe with it, so a run that
ends silently is exactly the run whose end state is unknown.
"""

from __future__ import annotations

import pytest

from tests.sweeprows import RUN, artifact, rig_gaps

RUN_FILES = ("srv1-lcpp-arms.tsv", "srv1-moe-slots.tsv", "srv1-vllm-arms.tsv")
BEHAVIOUR = "run tools/runs/srv1-kernel-arms.sh"


@pytest.mark.xfail(strict=True, reason="2026-09-01: owed — no per-row rig stamp")
@pytest.mark.parametrize("name", RUN_FILES)
def test_every_row_resolves_to_a_complete_rig_stamp(name: str) -> None:
    sweep = artifact(RUN / name, BEHAVIOUR)
    bad = [
        (row.lineno, rig_gaps(sweep.stamped_before(row, "RIG")))
        for row in sweep.rows
        if row.kind != "SKIP" and rig_gaps(sweep.stamped_before(row, "RIG"))
    ]
    assert not bad, (
        f"{len(bad)} row(s) carry no complete rig stamp — (line, missing): {bad[:5]}"
    )


@pytest.mark.xfail(strict=True, reason="2026-09-01: owed — no PL stamp at both ends")
@pytest.mark.parametrize("name", RUN_FILES)
def test_the_rig_read_the_same_at_the_end_as_at_the_start(name: str) -> None:
    sweep = artifact(RUN / name, BEHAVIOUR)
    start, end = sweep.stamp("START"), sweep.stamp("END")
    assert end, (
        f"{name} has no ### END — the run did not close, or the pipe died with it"
    )
    for field in ("pl1_uw", "pl2_uw", "uptime_since", "cpu_max_mhz", "ram_mt_s"):
        assert start.get(field) and start[field] == end.get(field), (
            f"{name}: {field} read {start.get(field)!r} at the start and "
            f"{end.get(field)!r} at the end. The rows between them were not all "
            "produced under one machine state."
        )
    assert start.get("pl1_source") == "constraint_0_power_limit_uw", (
        "PL1 must be read from `constraint_0_power_limit_uw`. "
        "`constraint_0_max_power_uw` is the rated TDP and reads 95000000 "
        "whatever the live limit is — it looks exactly like the cap being in "
        "force when it is not."
    )
