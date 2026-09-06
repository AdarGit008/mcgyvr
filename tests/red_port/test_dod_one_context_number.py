"""The window a rung serves is one number, and the door owns it.

``mcgyvr.serving.DEFAULT_CONTEXT`` is 4096 and reaches the rig two ways: as
``-c 4096 x width`` in the compose file ``mcgyvr emit`` writes, and as the
``ctx_per_slot`` the placement law sizes a KV cache against. Its comment claims
"One number, two readers, no drift".

There is a third reader and it disagrees. The door's ``--ctx-per-slot`` defaults
to 2048, and ``data-30-placement.py`` feeds that into the same
``vramfit.kv_bytes``. So an ``--n-cpu-moe`` floor derived through the door is
computed against half the cache the compose file it was derived for actually
launches with — the same class of error as the ``VLLM_MAX_MODEL_LEN`` of 8192
against a llama.cpp rung serving 4096, which the first live day found.

Owner's ruling, 2026-09-06: **the door wins.** The door is the actual setup, and
the number every reader derives from is the door's. Measured the same day, all
three live rungs agree with each other and with the product, not with the door's
default: srv2:8001 and srv2:8002 report ``max_model_len 4096``, srv1:8080 reports
``n_ctx 4096``. So making the door authoritative moves the door's default to
4096; it does not move the product to 2048.

What must be observably true: one constant, and no reader carrying a second copy
of it as a default.
"""

from __future__ import annotations

from typing import Any

from tests.red_port.conftest import required

#: What all three rungs of the live ladder reported on 2026-09-06.
LIVE_WINDOW = 4096


def _door() -> Any:
    import importlib

    return importlib.import_module("mcgyvr.serving.run")


def _door_default() -> Any:
    """The door's own ``--ctx-per-slot`` default, as argparse holds it."""
    door = _door()
    parser = required(
        "expose the door's per-slot context as a value one reader owns",
        lambda: door.CTX_PER_SLOT,
    )
    return parser


def test_the_door_and_the_product_serve_one_window() -> None:
    """The drift, stated as the equality it breaks."""
    from mcgyvr.serving import DEFAULT_CONTEXT

    assert _door_default() == DEFAULT_CONTEXT, (
        "the door sizes a placement against one window and emit launches the "
        "unit with another; an --n-cpu-moe floor derived from the first is "
        "wrong for the second"
    )


def test_that_window_is_the_one_the_rigs_report() -> None:
    """Not merely equal — equal to what the machines actually serve.

    Two readers agreeing on 2048 would pass the test above and still be wrong
    about every rig in the ladder.
    """
    from mcgyvr.serving import DEFAULT_CONTEXT

    assert DEFAULT_CONTEXT == LIVE_WINDOW, (
        f"srv2:8001, srv2:8002 and srv1:8080 all served {LIVE_WINDOW} on "
        f"2026-09-06; the product carries {DEFAULT_CONTEXT}"
    )
