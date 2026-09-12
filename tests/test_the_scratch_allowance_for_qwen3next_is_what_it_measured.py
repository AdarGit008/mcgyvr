"""qwen3next's scratch allowance is the 829 MiB it was measured to need.

RED. ``vramfit`` still gives qwen3next the 768 MiB allowance
(``SCRATCH_AND_CONTEXT_MIB``, ``src/mcgyvr/serving/vramfit.py:66``) it was
measured to exceed: 817-829 MiB
(``records/measurements/measuring-gaps-2026-09-10/README.md`` Q3). A llama.cpp
unit's room is its computed card need (``records/plans/fleet-identity.md`` §8),
so a room computed with 768 admits a qwen3next unit that can OOM at load.

The registry of BOUND parameters and the BOUND/EXPECTED classification this file
used to pin are gone (owner, 2026-09-10): a unit's room is proven by a dev run
and judged live, and a sizing constant is a code review, not a runtime class.
"""

from __future__ import annotations

import importlib


def test_the_scratch_allowance_for_qwen3next_is_what_it_measured() -> None:
    """Today 768: a qwen3next unit sized with it clears every gate and can OOM."""
    vramfit = importlib.import_module("mcgyvr.serving.vramfit")
    assert vramfit.allowance_mib({"arch": "qwen3next"}) >= 829
