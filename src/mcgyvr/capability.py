"""Reader for the shipped capability table, and the one question a task asks it.

The table (``data/capability-table.json``) is measured data, not estimates:
it is how ``mcgyvr init`` proposes worker bindings for detected hardware
without benchmarking the user's machine. See ``data/README.md`` for
methodology and for the harness caveats that make some published numbers
unusable.

Reading and validating is most of this module. Turning hardware into a proposed
binding is a separate concern and lives in :mod:`mcgyvr.propose`.

**What one number can and cannot decide.** Every row carries a single quality
figure — measured HumanEval+ pass@1 — and one number induces a total order, so
the only question a scalar can answer is *which model is better*. That is the
wrong question to put to a contract. Producing a loop invariant that holds and
producing prose about a loop nobody may touch are not two points on one line,
and ranking them on one line sends an implementation contract to whichever model
scored higher on a benchmark that is mostly short functions.

So a row may also carry a ``capabilities`` vector: a score per measured
*dimension*, and :func:`select_for_task` filters on the dimension the task
actually needs instead of on the scalar. Two properties keep that from being a
regression on the day it lands:

* **An absent vector is unmeasured, not unfit.** No shipped row has one yet, so a
  filter reading "no data" as "fails the floor" would empty the pool on every
  install. :meth:`Model.capability` falls back to the scalar, which is the half
  of this that is easiest to drop and most expensive to have dropped.
* **A model with no valid quality at all is still never proposed.** The table
  keeps invalidated measurements rather than substituting an estimate
  (``data/README.md``), and the fallback inherits that: unmeasured stays
  unmeasured, and there is nothing to fall back *to*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from mcgyvr.catalog import catalog

TABLE_FILENAME = "capability-table.json"

# The score a model must reach on a task's dimension before it may be asked for
# that task. 0.5 is inherited rather than measured here — it is the number
# local-ai's router enforces — and it is stated once, as the default of the one
# function that applies it, rather than as a literal at each call site. That
# shape is the defect worth not copying: there, `configs/dimensions.json`
# documented per-dimension floors that no loader ever read while `router.py:427`
# and `:714` each hardcoded 0.5, so the file stating the policy and the code
# enforcing it could never be caught disagreeing. What the floor *should* be is a
# measurement nobody has taken.
DIMENSION_FLOOR = 0.5

# The capability dimension each kind of required evidence implies, strongest
# characterisation first.
#
# A task type does not name its dimension directly, and this is deliberate. The
# catalog is the vocabulary's one definition (:mod:`mcgyvr.catalog`): adding a
# task type must be an edit to ``data/task-catalog.json`` and nothing else, and
# nothing downstream may match on a type name. A second table here keyed by type
# name would be the vocabulary written down twice, and every new type would
# arrive with no dimension until somebody remembered this file.
#
# What a type must *demonstrate* is already declared there, and it says what the
# model producing it has to be able to do:
#
#   failing_test_first  a defect has to be located and the branch that caused it
#                       changed — `branching`
#   tests_pass          the change has to actually run correctly — `simple_function`
#   type_check          a stated, machine-checked contract has to be satisfied
#                       exactly — `instruction_following`
#   no_semantic_change  prose or annotation has to be produced over logic that may
#                       not be touched — `instruction_following` again
#
# Order settles a type that requires several: the evidence saying most about what
# must be *generated* wins, so a demonstrated fix characterises `bug_fix` rather
# than the structural no-change rule it also obeys. The dimension names are
# local-ai's `configs/dimensions.json` vocabulary, kept verbatim so a score vector
# measured against that benchmark drops straight into a row.
#
# Where this really belongs is a `dimension` field on the catalog entry, next to
# the guarantee and the evidence. That is an edit to the catalog data and its
# loader, neither of which is this module's to make.
_DIMENSION_BY_EVIDENCE: tuple[tuple[str, str], ...] = (
    ("failing_test_first", "branching"),
    ("tests_pass", "simple_function"),
    ("type_check", "instruction_following"),
    ("no_semantic_change", "instruction_following"),
)


class CapabilityTableError(Exception):
    """The capability table is missing, malformed, or internally inconsistent."""


class CapabilitySelectionError(Exception):
    """No model in the table can be asked for this task, and the message says why.

    Distinct from :class:`CapabilityTableError`: the table is fine, the request
    cannot be served from it. Every message names the capability that came up
    short, because "no model is good enough" sends an operator back to the ladder
    they have already read, while "nothing scores 0.5 on 'algorithm'" tells them
    which rung to go and bind.
    """


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

    ``params_b`` is the declared parameter count in billions. It is size, not
    footprint: ``vram_gb_working`` says what the weights cost to hold at a
    quantization, while this says how big the model is regardless of how it was
    packed, which is what a *usable context window* scales with.

    ``capabilities`` is the per-dimension score vector, empty for every row
    shipped today. Read it through :meth:`capability`, never directly, so the
    fallback to the scalar happens in one place.
    """

    id: str
    family: str
    params_b: float
    vram_gb_working: float
    weights_gb: float
    quant: str
    quality: list[Measurement]
    throughput: list[Measurement]
    requires_backend: str | None
    notes: str
    capabilities: dict[str, float] = field(default_factory=dict)

    @property
    def is_measured(self) -> bool:
        """Whether this model has any valid quality measurement."""
        return bool(self.quality)

    def capability(self, dimension: str) -> float | None:
        """This model's score on ``dimension``, or its scalar quality if unscored.

        ``None`` only when there is nothing measured at all — no vector entry and
        no valid quality figure. That model is unmeasured, and an unmeasured model
        is never proposed, here as everywhere else in this file.
        """
        measured = self.capabilities.get(dimension)
        return measured if measured is not None else self.best_quality

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
            params_b=float(entry["params_b"]),
            vram_gb_working=float(entry["vram_gb_working"]),
            weights_gb=float(entry["weights_gb"]),
            quant=str(entry.get("quant", "")),
            quality=_measurements(entry.get("quality", []), "humaneval_plus_pass1"),
            throughput=_measurements(entry.get("throughput_tok_s", []), "value"),
            requires_backend=entry.get("requires_backend"),
            notes=str(entry.get("notes", "")),
            capabilities={
                str(dimension): float(score)
                for dimension, score in entry.get("capabilities", {}).items()
            },
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


_CACHED_TABLE: CapabilityTable | None = None


def shipped_table() -> CapabilityTable:
    """The shipped table, loaded once.

    The file travels with the package and cannot change under a running process,
    so re-reading and re-validating it per contract would be cost with no
    meaning. The same argument :func:`mcgyvr.catalog.catalog` makes, for the same
    reason: these are the two shipped data files, and both are read on hot paths.
    """
    global _CACHED_TABLE
    if _CACHED_TABLE is None:
        _CACHED_TABLE = load()
    return _CACHED_TABLE


# --- what a task needs, and which model has it ------------------------------


def dimension_for(task_type: str) -> str | None:
    """The capability dimension a task of this type exercises, if it names one.

    Derived from what the catalog says a change of this type must demonstrate —
    see :data:`_DIMENSION_BY_EVIDENCE` for why it is derived rather than declared
    beside the type name.

    ``None`` has two honest readings and they are not distinguished here, because
    a caller that needs to tell them apart is asking the catalog, not this
    function. A type the deterministic family executes asks no model at all, so
    it has no dimension to gate on; and a name the catalog does not hold is not a
    task type, which contract loading refuses long before anything reaches here.
    """
    entry = catalog().get(task_type)
    if entry is None or entry.deterministic:
        return None
    required = set(entry.evidence_names)
    return next(
        (
            dimension
            for evidence, dimension in _DIMENSION_BY_EVIDENCE
            if evidence in required
        ),
        None,
    )


def select_for_task(
    *,
    task_type: str,
    table: Path | None = None,
    floor: float = DIMENSION_FLOOR,
) -> Model:
    """The cheapest model measured able to do what a ``task_type`` contract asks.

    Two steps, and the order is the point. First the *gate*: a model is a
    candidate only if it scores at least ``floor`` on the dimension this task
    needs — its vector entry if it has one, its scalar quality if it does not,
    and nothing at all if it is unmeasured. Then the *choice*: among models that
    clear the gate, the smallest working footprint wins, because above the floor
    a model is good enough and more VRAM buys nothing the contract asked for.
    That is the ladder's own economics — cheapest rung that can do the job —
    applied to the rate card instead of to the config.

    Ties break on the dimension score and then on the id, so the same table and
    the same task always yield the same model. Determinism matters here for the
    reason it matters in the gate: a selection that varied run to run would make
    a comparison between two runs unreadable.

    ``table`` is a path to a table file; the shipped one is used when it is
    omitted. Raises :class:`CapabilitySelectionError` when the type is not in the
    vocabulary, when it names no dimension, or when nothing in the table reaches
    the floor on it.
    """
    entry = catalog().get(task_type)
    if entry is None:
        raise CapabilitySelectionError(
            f"{task_type!r} is not a known task type, so there is no capability to "
            f"select on. Valid: {', '.join(catalog().names)}"
        )
    dimension = dimension_for(task_type)
    if dimension is None:
        raise CapabilitySelectionError(
            f"{task_type!r} names no capability dimension: what it must "
            f"demonstrate ({', '.join(entry.evidence_names)}) does not say what a "
            f"model producing it has to be able to do. A type the deterministic "
            f"tier executes is the ordinary case — a tool does the work and no "
            f"model is asked."
        )

    loaded = shipped_table() if table is None else load(table)
    scored: list[tuple[Model, float]] = []
    for model in loaded.models:
        score = model.capability(dimension)
        if score is not None:
            scored.append((model, score))
    capable = [(model, score) for model, score in scored if score >= floor]
    if not capable:
        measured = (
            ", ".join(
                f"{model.id} {score:.2f}"
                for model, score in sorted(scored, key=lambda pair: -pair[1])
            )
            or "no model in it carries a valid quality measurement at all"
        )
        raise CapabilitySelectionError(
            f"no model scores {floor:g} or better on {dimension!r}, the capability "
            f"a {task_type!r} contract needs. The table says: {measured}. Bind a "
            f"rung on a model measured for {dimension!r}, or lower the floor "
            f"knowing which capability you are lowering it on."
        )

    capable.sort(key=lambda pair: (pair[0].vram_gb_working, -pair[1], pair[0].id))
    return capable[0][0]
