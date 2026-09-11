"""Draining a source whose rung declares a width holds every slot, not raises.

RED, and the one test here against code that exists. ``Capacity.drain``
(``src/mcgyvr/capacity.py:1288``) sorts the bounds of the named sources, and
``_bounds`` keys a source's pool ``(source, None)`` and a width-declaring rung
``(source, rung)`` (``:568-572``). srv1's live rung ``local_qwen3.6-35b-a3b``
declares ``max_parallel: 2``, so ``sorted()`` compares ``None`` with a ``str``
and ``mcgyvr serve sleep`` crashes on srv1 (flexibility-2026-09-09, Defects: "`mcgyvr
serve sleep` crashes on srv1").

P0 of ``records/plans/fleet-identity.md`` §11: a switch drains a unit before
it sleeps or stops it (§3), and on srv1 the drain cannot run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcgyvr.capacity import Capacity, RungWidth


def test_draining_a_source_with_a_width_declaring_rung_does_not_raise(
    tmp_path: Path,
) -> None:
    capacity = Capacity(
        {"srv1_llamacpp": 8},
        lock_dir=tmp_path,
        rungs={"local_qwen3.6-35b-a3b": RungWidth("srv1_llamacpp", 2)},
        urls={"srv1_llamacpp": "http://srv1:8080"},
    )
    entered = False
    try:
        with capacity.drain(["srv1_llamacpp"], timeout=5):
            entered = True
    except TypeError as crashed:
        pytest.fail(
            f"draining srv1 must hold the source's and its rung's slots, and it "
            f"raised: {crashed}",
            pytrace=False,
        )
    assert entered
