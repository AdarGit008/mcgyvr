"""ADR-0016's golden corpus: every captured worker reply, asserted whole.

The corpus is the raw reply files the measurement rigs write under
``records/measurements/``; ``records/corpora/worker-replies/golden.json`` pins
what ``parse_reply`` said about each one, with the stop reason it said it
under. These tests recompute the whole document from disk — every file found,
every sha, every verdict — and diff it against the pinned copy, which is one
golden comparison over the full set rather than a curated fixture per test:
a per-test selection drifts toward the shapes the curator understood.

What a failure means: a new run captured replies nobody pinned (run
``tools/replies/pin.py`` and commit the diff), a reply file was edited or lost
(corpus rot — restore it), or the parser's verdict on a real reply moved
(re-pin *deliberately*, with the change in review). All three are events this
suite exists to make loud.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "records" / "corpora" / "worker-replies" / "golden.json"


def _pin() -> types.ModuleType:
    """The pin tool, imported by path — ``tools/`` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "replies_pin", REPO / "tools" / "replies" / "pin.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pinned() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return doc


@pytest.fixture(scope="module")
def recomputed() -> dict[str, Any]:
    doc: dict[str, Any] = _pin().compute()
    return doc


def test_the_corpus_replays_whole(
    pinned: dict[str, Any], recomputed: dict[str, Any]
) -> None:
    """Every captured reply, found, byte-identical, and parsing to its verdict.

    Compared entry by entry before the whole so a failure names the reply that
    moved instead of printing two hundred entries of diff.
    """
    pinned_by_key = {(e["run"], e["file"]): e for e in pinned["entries"]}
    recomputed_by_key = {(e["run"], e["file"]): e for e in recomputed["entries"]}

    unpinned = sorted(recomputed_by_key.keys() - pinned_by_key.keys())
    assert not unpinned, f"captured but not pinned (tools/replies/pin.py): {unpinned}"
    lost = sorted(pinned_by_key.keys() - recomputed_by_key.keys())
    assert not lost, f"pinned but no longer on disk: {lost}"

    for key, entry in sorted(pinned_by_key.items()):
        assert recomputed_by_key[key] == entry, f"drift at {key}"
    assert recomputed == pinned


def test_refusals_are_corpus_not_noise(pinned: dict[str, Any]) -> None:
    """The unhandleable shapes are the ones worth the most (#174, ADR-0016).

    A corpus from which every refusal has vanished has been curated back to
    the author-imagination bound it exists to escape.
    """
    totals = pinned["totals"]
    entries = pinned["entries"]
    refusals = [e for e in entries if "refusal" in e["expect"]]
    assert totals["refusals"] == len(refusals)
    assert totals["replies"] == len(entries)
    assert refusals, "no refusal is pinned; the corpus has been curated clean"


def test_a_run_with_no_provenance_cannot_be_pinned(tmp_path: Path) -> None:
    """#230: the guard sits at the point of entry, and it is not optional.

    Everything under ``records/measurements/`` is walked into this corpus and
    from there into the training path. A run that states neither a tier nor
    contract digests nor a task id cannot be classified against
    ``tools/instruments.json``, and an unclassifiable run is not a clean one —
    it would reach the dataset builder as drawable material.
    """
    pin = _pin()
    run = tmp_path / "mystery"
    run.mkdir()
    (run / "run.json").write_text("{}", encoding="utf-8")

    with pytest.raises(pin.PinError, match="provenance cannot be decided"):
        pin._provenance(run, set())


def test_every_pinned_run_states_which_instrument_it_came_from(
    pinned: dict[str, Any],
) -> None:
    """The stamp the training path reads, present for every run in the corpus."""
    runs = pinned["instruments"]["runs"]
    assert pinned["record"] == "reply-corpus/2"
    for entry in pinned["entries"]:
        stamp = runs[entry["run"]]
        assert "sets" in stamp and "why" in stamp
    # The floor instrument is most of this corpus. Keeping those replies is
    # deliberate — the parser must be measured on the population it faces —
    # and the count is what makes the exclusion downstream auditable.
    assert pinned["totals"]["instrument_replies"] == sum(
        1 for e in pinned["entries"] if runs[e["run"]]["sets"]
    )
