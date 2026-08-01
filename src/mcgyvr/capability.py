"""Reader for the shipped capability table.

The table (``data/capability-table.json``) is measured data, not estimates:
it is how ``mcgyvr init`` proposes worker bindings for detected hardware
without benchmarking the user's machine. See ``data/README.md`` for
methodology and for the harness caveats that make some published numbers
unusable.

This module only reads and validates. Turning hardware into a proposed
binding is a separate concern and does not live here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

TABLE_FILENAME = "capability-table.json"


class CapabilityTableError(Exception):
    """The capability table is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class Measurement:
    """One measured value with the conditions that produced it."""

    value: float
    backend: str
    rig: str
    date: str


@dataclass(frozen=True)
class Model:
    """A model the table knows about.

    ``quality`` holds only VALID measurements. A model whose measurements
    were all invalidated by a harness caveat has an empty list — the table
    never substitutes an estimate, so neither does this.
    """

    id: str
    family: str
    vram_gb_working: float
    weights_gb: float
    quant: str
    quality: list[Measurement]
    throughput: list[Measurement]
    requires_backend: str | None
    notes: str

    @property
    def is_measured(self) -> bool:
        """Whether this model has any valid quality measurement."""
        return bool(self.quality)

    @property
    def best_quality(self) -> float | None:
        """Highest valid HumanEval+ pass@1 measured, or None if unmeasured."""
        return max((m.value for m in self.quality), default=None)

    @property
    def best_throughput(self) -> float | None:
        """Highest tok/s measured on a backend this model can actually run on.

        A model pinned to one backend must not borrow a throughput figure
        taken on another, because the other run was a different quantization
        of different weights: qwen3-coder-30b-a3b's ollama measurement is Q4
        at 8.9 GB, not the Q2_K entry this row describes (CAV-02). Filtering
        by backend keeps a number attached to the thing it measured.
        """
        relevant = [
            m.value
            for m in self.throughput
            if self.requires_backend is None or m.backend == self.requires_backend
        ]
        return max(relevant, default=None)


@dataclass(frozen=True)
class Caveat:
    """A known way of producing wrong numbers for this table."""

    id: str
    severity: str
    summary: str
    consequence: str


@dataclass(frozen=True)
class CapabilityTable:
    models: list[Model]
    caveats: list[Caveat]

    def get(self, model_id: str) -> Model | None:
        return next((m for m in self.models if m.id == model_id), None)

    def fitting(self, vram_gb: float, headroom_gb: float = 2.0) -> list[Model]:
        """Measured models that fit in ``vram_gb`` with room to work.

        ``headroom_gb`` guards CAV-04: a marginal fit degrades badly rather
        than failing outright, which makes it look like a working binding.
        The headroom is ABSOLUTE, not a fraction of the card, because what
        it reserves — KV cache for the context window — is sized by tokens,
        not by GPU. The two measurements bear this out: a 5.0 GB model on a
        6 GB card (1.0 GB free) ran 1.9x slower than the same weights on a
        12 GB card, while a 9.5 GB model on that 12 GB card (2.5 GB free)
        held its expected rate. As a fraction those are 83% and 79%
        utilization — indistinguishable, and the wrong way round.

        Unmeasured models are never proposed.
        """
        return [
            m
            for m in self.models
            if m.is_measured and m.vram_gb_working + headroom_gb <= vram_gb
        ]


def _measurements(rows: list[dict[str, Any]], key: str) -> list[Measurement]:
    return [
        Measurement(
            value=float(row[key]),
            backend=str(row.get("backend", "")),
            rig=str(row.get("rig", "")),
            date=str(row.get("date", "")),
        )
        for row in rows
        if key in row
    ]


def table_path() -> Path:
    """Locate the shipped table, whether running from a checkout or a wheel."""
    packaged = resources.files("mcgyvr") / "data" / TABLE_FILENAME
    if packaged.is_file():
        return Path(str(packaged))
    # Running from a source checkout: data/ sits at the repo root.
    checkout = Path(__file__).resolve().parents[2] / "data" / TABLE_FILENAME
    if checkout.is_file():
        return checkout
    raise CapabilityTableError(
        f"capability table not found (looked for {TABLE_FILENAME})"
    )


def load(path: Path | None = None) -> CapabilityTable:
    """Load and validate the capability table."""
    path = path or table_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CapabilityTableError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CapabilityTableError(f"{path} is not valid JSON: {exc}") from exc

    if raw.get("schema_version") != 1:
        raise CapabilityTableError(
            f"unsupported capability table schema_version {raw.get('schema_version')!r}"
        )

    models = [
        Model(
            id=str(entry["id"]),
            family=str(entry["family"]),
            vram_gb_working=float(entry["vram_gb_working"]),
            weights_gb=float(entry["weights_gb"]),
            quant=str(entry.get("quant", "")),
            quality=_measurements(entry.get("quality", []), "humaneval_plus_pass1"),
            throughput=_measurements(entry.get("throughput_tok_s", []), "value"),
            requires_backend=entry.get("requires_backend"),
            notes=str(entry.get("notes", "")),
        )
        for entry in raw.get("models", [])
    ]
    if not models:
        raise CapabilityTableError(f"{path} declares no models")

    caveats = [
        Caveat(
            id=str(c["id"]),
            severity=str(c["severity"]),
            summary=str(c["summary"]),
            consequence=str(c["consequence"]),
        )
        for c in raw.get("harness_caveats", [])
    ]
    return CapabilityTable(models=models, caveats=caveats)
