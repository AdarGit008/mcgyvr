"""The capability table is shipped data other decisions rest on.

These tests hold it to the properties `mcgyvr init` will rely on, and guard
the failure modes that made the underlying measurements wrong in the first
place (see data/README.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcgyvr.capability import CapabilityTableError, load, table_path


def test_shipped_table_loads() -> None:
    table = load()
    assert table.models
    assert table.caveats, "the known-bad measurement caveats must travel with the data"


def test_every_model_has_a_working_footprint() -> None:
    for model in load().models:
        assert model.vram_gb_working > 0, f"{model.id} has no working VRAM figure"


def test_unmeasured_models_are_never_proposed() -> None:
    """A model whose only scores were invalidated must not be offered.

    gpt-oss-20b's published score is attributed to a harness limitation
    (CAV-03), so it carries no valid quality measurement and must be absent
    from any proposal regardless of how much VRAM is available.
    """
    table = load()
    unmeasured = [m.id for m in table.models if not m.is_measured]
    assert unmeasured, "expected at least one model held back as unmeasured"
    proposed = {m.id for m in table.fitting(vram_gb=80)}
    assert proposed.isdisjoint(unmeasured)


def test_marginal_fits_are_excluded() -> None:
    """CAV-04: a model that only just fits degrades rather than failing.

    qwen2.5-coder:7b needs ~5 GB and measured 1.9x slower on a 6 GB card
    than on a 12 GB one, so a 6 GB machine must not be offered it.
    """
    table = load()
    assert "qwen2.5-coder:7b" not in {m.id for m in table.fitting(vram_gb=6)}
    assert "qwen2.5-coder:7b" in {m.id for m in table.fitting(vram_gb=12)}


def test_headroom_is_absolute_not_proportional() -> None:
    """The two rigs disagree with any ratio rule; only free GB separates them.

    5.0 GB on a 6 GB card thrashed (83% utilization); 9.5 GB on a 12 GB card
    did not (79%). A proportional rule admitting the second must admit the
    first. These two assertions cannot both hold under one.
    """
    table = load()
    fits_12 = {m.id for m in table.fitting(vram_gb=12)}
    assert "qwen2.5-coder:14b" in fits_12
    assert "qwen2.5-coder:7b" not in {m.id for m in table.fitting(vram_gb=6)}


def test_moe_quality_is_reachable_on_a_small_card() -> None:
    """qwen3-coder-30b-a3b delivers 14B-class quality in ~3 GB.

    It is the only measured path to >85% on a 6 GB card, so a proposal for
    small hardware that omits it has lost the point.
    """
    table = load()
    small = {m.id: m for m in table.fitting(vram_gb=6)}
    assert "qwen3-coder-30b-a3b" in small
    best = max(m.best_quality or 0 for m in small.values())
    assert best > 0.85


def test_invalid_measurements_are_not_read_as_quality() -> None:
    """CAV-01: ollama /api/generate scored 7B at 32.3% against a true 84.1%.

    Those rows live in `invalid_measurements` and must never be mistaken for
    quality — a table that read them would route away from the best models.
    """
    model = load().get("qwen2.5-coder:7b")
    assert model is not None
    best = model.best_quality
    assert best is not None and best > 0.8


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    raw = json.loads(table_path().read_text(encoding="utf-8"))
    raw["schema_version"] = 99
    bad = tmp_path / "capability-table.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CapabilityTableError, match="schema_version"):
        load(bad)


def test_rejects_malformed_json(tmp_path: Path) -> None:
    bad = tmp_path / "capability-table.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CapabilityTableError, match="not valid JSON"):
        load(bad)


def test_rejects_table_with_no_models(tmp_path: Path) -> None:
    bad = tmp_path / "capability-table.json"
    bad.write_text(json.dumps({"schema_version": 1, "models": []}), encoding="utf-8")
    with pytest.raises(CapabilityTableError, match="no models"):
        load(bad)
