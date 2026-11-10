"""A rig claims no ``backend_select``: its worker starts the same on every backend.

The hub names each worker card's backend (``cuda``, ``cuda_notc``, ``rocm``,
...) and trusts a rig that lists ``backend_select`` to honor it; for a rig
that does not, it names only the backends every fork speaks. The agent reads
the card's ``backend`` and starts the worker exactly as it would without one,
so it does not list the feature: what it claims is what it does.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tests import rig_pool_fakes as fakes
from tests.rig_pool_fakes import make_pool


def test_no_offer_names_backend_select() -> None:
    from mcgyvr.rig import session

    assert "backend_select" not in session.FEATURES
    assert "backend_select" not in session.NATIVE_FEATURES


def _worker_argv(tmp_path: Path, card: dict[str, Any]) -> list[str]:
    """The ``docker run`` of the worker a ``worker_start`` naming ``card`` starts."""
    from mcgyvr.rig import pooled

    pool = make_pool(tmp_path)
    try:
        prepared = fakes.prepared(pool)
        pool.up(
            "t1",
            **fakes.tunnel_up_body(listen_port=prepared["body"]["listen_port"]),
        )
        ack = pool.ask("worker_start", "w1", session_id="s1", cards=[card])
        assert ack is not None and ack["type"] == "ack", ack
        deadline = time.monotonic() + 5.0
        while pool.sessions.state_of("s1")[0] != "ready":
            assert time.monotonic() < deadline, pool.sessions.state_of("s1")
            time.sleep(0.005)
        argv: list[str] = pool.docker.containers[
            pooled.container_name("s1", "worker-0")
        ].argv
        return argv
    finally:
        pool.sessions.close()


@pytest.mark.parametrize("backend", ["cuda", "cuda_notc", "rocm", "vulkan"])
def test_a_worker_card_starts_the_same_whatever_backend_it_names(
    backend: str, tmp_path: Path
) -> None:
    plain = _worker_argv(tmp_path / "plain", {"card_index": 0, "port": 50052})
    named = _worker_argv(
        tmp_path / "named", {"card_index": 0, "port": 50052, "backend": backend}
    )

    def same(argv: list[str], root: Path) -> list[str]:
        return [part.replace(str(root), "<root>") for part in argv]

    assert same(named, tmp_path / "named") == same(plain, tmp_path / "plain")
