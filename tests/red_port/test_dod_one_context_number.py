"""The window a rung serves is what the run says, and no reader supplies its own.

**The window is what the run says, and it is not a constant.** There is no module-level
context number in :mod:`mcgyvr.serving`, and the door's ``--ctx-per-slot`` is required
rather than defaulted. A default in a module is a number nobody chose for a rig nobody
measured: the run declares the window it is bringing a ladder up with, every reader in
that run derives from that declaration, and what a unit ended up serving is read back
from the unit rather than assumed.

**Stated as behaviour, not as a search of the source.** A grep for module
constants matching ``CONTEXT|CTX`` is defeated by a rename and flags constants that
are not windows at all — ``vramfit.SCRATCH_AND_CONTEXT_MIB`` (the placement
allowance, which ``test_dod_placement_conservatism.py`` requires to exist) and
``_DEFAULT_CONTEXT`` in ``orchestrator/read.py`` (lines of source context for a file
reader).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.red_port.conftest import required

CONFIG = """\
units:
  only:
    address: http://rig:8080
    model: a-model
    rig: rig_lcp
    width: 1
    launch:
      vram_gb: 3.0
      disk_gb: 2.0
      kv_cache_dtype_k: f16
      kv_cache_dtype_v: f16
ladder:
- only
"""


def _emitted(window: int | None) -> Any:
    """The compose text a run declaring ``window`` would write.

    ``None`` is a run that declared nothing, which must be a refusal rather
    than a number somebody's module chose.
    """
    from mcgyvr.config import parse
    from mcgyvr.serving import units_for

    emit_run = required(
        "emit a ladder against the window the run declares, with no reader "
        "supplying a default of its own",
        lambda: units_for,
    )
    return emit_run(parse(CONFIG), _scans(), specs=(), ctx_per_slot=window)


def _scans() -> dict[str, Any]:
    """A machine roomy enough that only the window is in question.

    Built through :meth:`Scan.of`, the constructor this codebase offers for
    "callers that need a machine to reason about". A bare ``Scan.__new__(Scan)``
    has neither a ``machine`` nor a card: no unit can be built on it whatever
    window is declared. The figures are deliberately generous — a refusal for want
    of VRAM would be this test failing for the wrong reason.
    """
    from mcgyvr.scan import Scan

    return {"rig": Scan.of(host="rig", vram_mib=12288, ram_gb=64.0, disk_free_gb=200.0)}


def test_the_window_the_run_declares_is_the_window_emit_writes() -> None:
    """The declaration reaches the file that launches the process.

    8192 rather than 4096 on purpose: 4096 is the number a hardcoded window would
    most likely carry, so a test declaring it could pass without the declaration
    being read.
    """
    from mcgyvr.emit import _document

    units = _emitted(8192)
    text = _document(tuple(units))
    assert "8192" in text, (
        "the run declared 8192 per slot and the emitted compose does not carry "
        f"it; emit is still sizing against a number of its own:\n{text[:400]}"
    )
    assert "4096" not in text, (
        "the emitted compose still carries 4096, which no run in this test "
        "declared — a module default reached the rig"
    )


def test_the_same_declaration_sizes_the_placement_law() -> None:
    """The second reader, which is the one the door's 2048 diverged in.

    An ``--n-cpu-moe`` floor is only correct for the cache the unit will
    actually allocate, so the law and the launch must be fed one number.
    """
    sized = required(
        "size the KV cache against the window the run declared, not against a "
        "module constant",
        lambda: (
            __import__("mcgyvr.serving", fromlist=["kv_bytes_for_run"]).kv_bytes_for_run
        ),
    )
    wide = sized(ctx_per_slot=8192, slots=4)
    narrow = sized(ctx_per_slot=4096, slots=4)
    assert wide == 2 * narrow, (
        f"doubling the declared window must double the cache; got {wide} "
        f"against {narrow}"
    )


def test_a_run_that_declares_no_window_is_refused_not_defaulted() -> None:
    """The half a default hides.

    With a constant in the module, a run that forgot to say is silently sized
    against 4096 or 2048 and nobody is told. The refusal must be the product's
    own, and must name what was not declared — a bare ``KeyError`` whose text
    happens to contain "ctx" is a dict lookup, not a decision.
    """
    from mcgyvr.serving import UnitError

    with pytest.raises(UnitError) as refusal:
        _emitted(None)
    message = str(refusal.value).lower()
    assert "context" in message or "window" in message, (
        f"the refusal must name what was not declared: {refusal.value}"
    )


def test_what_a_unit_serves_is_read_from_the_unit() -> None:
    """Declared going in; measured coming back. Two different questions.

    A run declares what it is asking for. What a unit ended up serving is a
    fact about a running process, and on 2026-09-06 all three live rungs
    published it — vLLM as ``max_model_len``, llama.cpp as ``n_ctx``.
    """
    served: Any = required(
        "read the window a running unit actually serves, from the unit",
        lambda: __import__("mcgyvr.serving", fromlist=["served_window"]).served_window,
    )
    assert served({"data": [{"max_model_len": 4096}]}) == 4096, (
        "vLLM publishes it as max_model_len on /v1/models"
    )
    assert served({"n_ctx": 4096}) == 4096, "llama.cpp publishes it on /props"
    assert served({}) is None, (
        "a unit that published nothing is unknown, which is not the same "
        "answer as a window somebody assumed"
    )
