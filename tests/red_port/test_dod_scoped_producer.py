"""S10 — a scoped edit is not advertised while nothing can produce one.

:func:`mcgyvr.worker.scoped.apply_scoped` splices a *named definition* back into
a file, but nothing in ``src/`` ever names a definition — the reply protocol is
whole-file only (ADR-0009), and no contract carries a node. The function was
exported anyway, which is the defect: a public seam with no producer rots and
reads as a promise the worker never keeps. The fix removes it from the surface
rather than leaving a dead seam a caller could wire up by mistake.

The guard holds the one fact a caller depends on: the worker package no longer
advertises ``apply_scoped``.
"""

from __future__ import annotations


def test_the_worker_package_does_not_advertise_a_scoped_edit() -> None:
    import mcgyvr.worker as worker

    assert not hasattr(worker, "apply_scoped"), (
        "`apply_scoped` is still exported, yet nothing in src/ names a "
        "definition to call it with — a producer-less public seam"
    )
