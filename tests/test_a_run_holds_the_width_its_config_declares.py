"""A run holds the width its config declares, so two runs cannot exceed it.

``mcgyvr pool`` prints ``max_parallel`` as a ceiling and :mod:`mcgyvr.capacity`
enforces one — a host-wide ``flock`` on one of that many slot files, which
:meth:`~mcgyvr.capacity.Capacity.hold` blocks on rather than raising, so a
queue is a wait and not a failure. Every layer between the command and the
dispatch already carries a ``capacity``: :func:`~mcgyvr.escalate.ascent` and
:func:`~mcgyvr.escalate.escalate` take one, :class:`~mcgyvr.route.Try` carries
it to the attempt, and :func:`~mcgyvr.runner.dispatch` holds it around the
request.

Nothing built one. ``cli.py`` named ``capacity`` nowhere, so both calls took
the default of ``None`` and ``dispatch`` took the branch that sends unbounded.
The ceiling was printed and never applied, which is the failure the 2026-09-06
live e2e found: 26 concurrent contracts opened 21 requests at an eight-slot
rung and 19 of them died on the client's own timeout, waiting in a queue
inside the engine that a slot file would have kept them out of.

Two properties, and the second is the one an operator can see:

* a run's dispatch is made under a capacity built from *its own config*, so
  the bound enforced is the declared one and not a number this module chose;
* two runs against a one-wide source do not have their dispatches in flight at
  the same time, which is what the bound is *for*. The slot file is the
  rendezvous, so this holds across processes; two threads are how a test can
  watch it happen.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tests import livejournal as lj

ONE_WIDE = """
version: 1
sources:
  workstation:
    base_url: http://localhost:11434
    api: openai
    max_parallel: 1
ladder:
  tiers:
    - name: local_qwen-7b
      source: workstation
      model: qwen2.5-coder:7b
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "home").mkdir(exist_ok=True)
    lj.clean_env(monkeypatch, tmp_path / "home")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    lj.claude_transcript(tmp_path / "home", "s1")
    # The slot files are a host-wide rendezvous by design; a test needs its own.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "rendezvous"))
    (tmp_path / "rendezvous").mkdir(exist_ok=True)
    return tmp_path / "home"


def _config(path: Path, journal: Path) -> Path:
    path.write_text(ONE_WIDE + f"journal:\n  dir: {journal}\n", encoding="utf-8")
    return path


def test_a_dispatch_is_made_under_the_capacity_the_config_declares(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mcgyvr.capacity import Capacity

    seen: list[Any] = []

    def capture(source_map: Any, rung: str, request: Any, **kw: Any) -> Any:
        seen.append(kw.get("capacity"))
        return lj.completion(lj.GOOD_REPLY, request)

    lj.patch_dispatch(monkeypatch, capture)
    repo = lj.make_repo(tmp_path / "repo")
    config = _config(tmp_path / "mcgyvr.yaml", tmp_path / "journal")
    contract = lj.make_contract(tmp_path / "impl.yaml")

    lj.main(lj.run_args(contract, repo, config))

    assert seen, "no dispatch was made"
    capacity = seen[0]
    assert isinstance(capacity, Capacity), (
        "the run dispatched with capacity=None: the ceiling `mcgyvr pool` "
        "prints was never applied to the request"
    )
    assert capacity.limits["workstation"] == 1


def test_two_runs_against_a_one_wide_source_do_not_dispatch_at_once(
    tmp_path: Path, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spans: list[tuple[float, float]] = []
    guard = threading.Lock()

    def slow(model: str, request: Any) -> Any:
        entered = time.monotonic()
        time.sleep(0.3)
        left = time.monotonic()
        with guard:
            spans.append((entered, left))
        return lj.completion(lj.GOOD_REPLY, request)

    # Below the hold, not above it: `patch_dispatch` would replace the very
    # function that takes the slot.
    lj.patch_backend(monkeypatch, slow)
    config = _config(tmp_path / "mcgyvr.yaml", tmp_path / "journal")
    repos = [lj.make_repo(tmp_path / f"repo{i}") for i in (0, 1)]
    contracts = [lj.make_contract(tmp_path / f"impl{i}.yaml") for i in (0, 1)]

    threads = [
        threading.Thread(target=lj.main, args=(lj.run_args(c, r, config),))
        for c, r in zip(contracts, repos, strict=True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert len(spans) == 2, f"expected two dispatches, saw {len(spans)}"
    first, second = sorted(spans)
    assert first[1] <= second[0], (
        "two dispatches to a source declared one wide overlapped: "
        f"{first} and {second}. The slot file did not keep the second out, "
        "so `max_parallel` bounds nothing a caller can rely on"
    )
