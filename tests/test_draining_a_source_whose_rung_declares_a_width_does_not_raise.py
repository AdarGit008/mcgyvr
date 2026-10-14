"""Draining a source whose rung declares a width holds every slot, not raises.

P0 of ``mcgyvr-lab/records/plans/fleet-identity.md`` §11: a switch drains a unit before
it sleeps or stops it (§3), and on box1 the drain cannot run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, RungWidth


def test_draining_a_source_with_a_width_declaring_rung_does_not_raise(
    tmp_path: Path,
) -> None:
    capacity = Capacity(
        {"box1_llamacpp": 8},
        lock_dir=tmp_path,
        rungs={"local_qwen3.6-35b-a3b": RungWidth("box1_llamacpp", 2)},
        urls={"box1_llamacpp": "http://box1:8080"},
    )
    entered = False
    try:
        with capacity.drain(["box1_llamacpp"], timeout=5):
            entered = True
    except TypeError as crashed:
        pytest.fail(
            f"draining box1 must hold the source's and its rung's slots, and it "
            f"raised: {crashed}",
            pytrace=False,
        )
    assert entered
