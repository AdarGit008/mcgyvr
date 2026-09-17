"""S10 — a scoped edit is not advertised while nothing can produce one.

The reply protocol is whole-file only, and no contract carries a node, so nothing
in ``src/`` can produce a scoped edit. A public seam with no producer reads as a
promise the worker never keeps.

The guard holds the one fact a caller depends on: the worker package does not
advertise ``apply_scoped``.
"""

from __future__ import annotations


def test_the_worker_package_does_not_advertise_a_scoped_edit() -> None:
    import mcgyvr.worker as worker

    assert not hasattr(worker, "apply_scoped"), (
        "`apply_scoped` is still exported, yet nothing in src/ names a "
        "definition to call it with — a producer-less public seam"
    )
