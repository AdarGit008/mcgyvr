"""qwen3next's scratch allowance is the 829 MiB it was measured to need.

A unit's room is proven by a dev run and judged live, and a sizing constant is
a code review, not a runtime class.
"""

from __future__ import annotations

import importlib


def test_the_scratch_allowance_for_qwen3next_is_what_it_measured() -> None:
    """Below 829, a qwen3next unit sized with it clears every gate and can OOM."""
    vramfit = importlib.import_module("mcgyvr.serving.vramfit")
    charged = vramfit.allowance({"arch": "qwen3next"}, n_ctx=4096, n_ubatch=512)
    assert charged.measured and charged.total >= 829 * (1 << 20)
