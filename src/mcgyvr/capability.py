"""Reader for the shipped capability table, and the one question a task asks it.

The table (``data/capability-table.json``) is estimates by card class, not
readings of the user's machine: it is how ``mcgyvr init`` proposes worker
bindings for detected hardware without benchmarking that machine. See
``data/README.md`` for what a card class is and for the harness caveats that
make some published numbers unusable.

Reading and validating is most of this module. Turning hardware into a proposed
binding is a separate concern and lives in :mod:`mcgyvr.propose`.

**What one number can and cannot decide.** Every row carries a single quality
figure — an estimated HumanEval+ pass@1 — and one number induces a total order, so
the only question a scalar can answer is *which model is better*. That is the
wrong question to put to a contract. Producing a loop invariant that holds and
producing prose about a loop nobody may touch are not two points on one line,
and ranking them on one line sends an implementation contract to whichever model
scored higher on a benchmark that is mostly short functions.

So a row may also carry a ``capabilities`` vector: a score per
*dimension*, and :func:`select_for_task` filters on the dimension the task
actually needs instead of on the scalar. Two properties keep that from being a
regression on the day it lands:

* **An absent vector is unscored, not unfit.** No shipped row has one yet, so a
  filter reading "no data" as "fails the floor" would empty the pool on every
  install. :meth:`Model.capability` falls back to the scalar, which is the half
  of this that is easiest to drop and most expensive to have dropped.
* **A model with no valid quality at all is still never proposed.** The table
  keeps invalidated readings aside rather than filling the gap with a figure
  from elsewhere (``data/README.md``), and the fallback inherits that: a model
  with no quality estimate stays without one, and there is nothing to fall
  back *to*.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mcgyvr.catalog import catalog

TABLE_FILENAME = "capability-table.json"

#: The one table version this code reads. A table of any other version is
#: refused by name rather than read: a reader that skipped keys it did not know
#: would take an older table's rows to mean what this version's rows mean.
SCHEMA_VERSION = 2

#: What every figure in the shipped table is, in the words the product prints
#: above them.
ESTIMATES_NOTICE = (
    "Estimates by card class, one card read per class; none is a reading of "
    "your machine."
)

# The table's ``*_gb`` figures are decimal gigabytes; the sizing code is in GiB
# (:data:`mcgyvr.detect.MIB_PER_GB` is 1024). Divide by this wherever a table
# figure crosses into the sizing code, and nowhere else.
GB_PER_GIB = 1.073741824

# The score a model must reach on a task's dimension before it may be asked for
# that task. 0.5 is a starting value, not a reading, and it is stated
# once, as the default of the one function that applies it, rather than as a
# literal at each call site.
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
# Order settles a type that requires several: the first kind listed here wins.
# The dimension names are a coding benchmark's vocabulary, kept verbatim so a
# score vector taken against that benchmark drops straight into a row.
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
    cannot be served from it. The floor message names the dimension that came up
    short, because "no model is good enough" sends an operator back to the ladder
    they have already read, while "nothing scores 0.5 on 'algorithm'" tells them
    which rung to go and bind.
    """


@dataclass(frozen=True)
class CardClass:
    """A class of card the table's estimates are given for.

    ``memory_gb`` is the class's nominal card memory. A class is a rough guide:
    one card was read for it, and speed depends on the card, not only on its
    memory.
    """

    id: str
    label: str
    memory_gb: float


@dataclass(frozen=True)
class Measurement:
    """One figure of the table: an estimate for a card class.

    ``backend`` is the server program the figure was taken through, and
    ``card_class`` the id of the declared :class:`CardClass` it is given for.
    """

    value: float
    backend: str
    card_class: str


@dataclass(frozen=True)
class Model:
    """A model the table knows about.

    ``quality`` holds only VALID estimates. A model whose readings were all
    invalidated by a harness caveat has an empty list — the table never fills
    that gap with a figure from elsewhere, so neither does this.

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
    quality: tuple[Measurement, ...]
    throughput: tuple[Measurement, ...]
    requires_backend: str | None
    notes: str
    capabilities: Mapping[str, float] = field(default_factory=dict)

    @property
    def is_measured(self) -> bool:
        """Whether this model has any valid quality estimate."""
        return bool(self.quality)

    def capability(self, dimension: str) -> float | None:
        """This model's score on ``dimension``, or its scalar quality if unscored.

        ``None`` only when there is no estimate at all — no vector entry and no
        valid quality figure. A model without one is never proposed, here as
        everywhere else in this file.
        """
        measured = self.capabilities.get(dimension)
        return measured if measured is not None else self.best_quality

    @property
    def best_quality(self) -> float | None:
        """Highest valid HumanEval+ pass@1 estimate, or None if there is none."""
        return max((m.value for m in self.quality), default=None)

    @property
    def best_throughput(self) -> float | None:
        """Highest tok/s estimate taken on a backend this model can actually run on.

        A model pinned to one backend must not borrow a throughput figure
        taken on another, because the other run was a different quantization
        of different weights: qwen3-coder-30b-a3b's ollama figure is not
        of the Q2_K entry this row describes (CAV-02). Filtering
        by backend keeps a number attached to the thing it was taken of.
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
    models: tuple[Model, ...]
    caveats: tuple[Caveat, ...]
    card_classes: tuple[CardClass, ...] = ()

    def get(self, model_id: str) -> Model | None:
        return next((m for m in self.models if m.id == model_id), None)

    def fitting(self, vram_gb: float, headroom_gb: float = 2.0) -> list[Model]:
        """Models with a quality estimate that fit in ``vram_gb`` with room to work.

        ``headroom_gb`` guards CAV-04: a marginal fit degrades badly rather
        than failing outright, which makes it look like a working binding.
        The headroom is ABSOLUTE, not a fraction of the card, because what
        it reserves — KV cache for the context window — is sized by tokens,
        not by GPU. The table's own figures bear this out: a 5.0 GB model on
        a card of the 6 GB class (1.0 GB free) ran 1.9x slower than the same
        weights on one of the 12 GB class (CAV-04).

        Models with no quality estimate are never proposed.
        """
        return [
            m
            for m in self.models
            if m.is_measured and m.vram_gb_working + headroom_gb <= vram_gb
        ]


#: The lists on a model row whose entries are readings, each keyed by a class.
READING_LISTS = (
    "quality",
    "throughput_tok_s",
    "invalid_measurements",
    "disputed_measurements",
)

#: Every key the table may carry, level by level, and no other.
#:
#: The loader refuses a key its level does not declare, by name, rather than
#: skipping it. A key this code does not know is either a misspelling of one it
#: reads, whose value would be lost without a word, or a fact nobody reads, and
#: a fact nobody reads in a table of estimates is how a machine's description,
#: or where and when a figure was taken, would come back in. Refusing it keeps a
#: new kind of fact out until it is declared here, where a reviewer reads it:
#: the same reason a table of another version is refused rather than read.
#:
#: Two places hold names that are data rather than keys, and are not declared:
#: under ``backends`` every key but the block's own notes names a backend, and a
#: model row's ``capabilities`` maps a dimension name to a score.
#:
#: A declared key that is not one of its level's :data:`CONTAINER_KEYS` holds a
#: value, never an object and never a list holding one, and the loader refuses
#: it otherwise: an object there would carry keys no level declares.
DECLARED_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "table": frozenset(
            {
                "schema_version",
                "_purpose",
                "quality_metric",
                "card_classes",
                "harness_caveats",
                "models",
                "backends",
                "concurrency_findings",
            }
        ),
        "quality metric": frozenset(
            {"name", "dataset", "decoding", "framework", "_caveat"}
        ),
        "card class": frozenset({"id", "label", "memory_gb"}),
        "harness caveat": frozenset(
            {"id", "severity", "summary", "detail", "consequence"}
        ),
        "model row": frozenset(
            {
                "id",
                "family",
                "params_b",
                "active_params_b",
                "architecture",
                "quant",
                "weights_gb",
                "vram_gb_working",
                "requires_backend",
                *READING_LISTS,
                "capabilities",
                "notes",
            }
        ),
        "reading": frozenset(
            {
                "humaneval_plus_pass1",
                "humaneval_pass1",
                "value",
                "backend",
                "card_class",
                "caveat",
                "note",
            }
        ),
        "backends block": frozenset({"_doc"}),
        "backend": frozenset({"wire_protocol", "strengths", "limits", "card_class"}),
        "concurrency finding": frozenset(
            {"id", "summary", "detail", "consequence", "card_class"}
        ),
    }
)


#: The declared keys whose value holds the entries of another level, or a
#: ``capabilities`` map, level by level. Every other declared key holds a value.
CONTAINER_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        **{level: frozenset[str]() for level in DECLARED_KEYS},
        "table": frozenset(
            {
                "quality_metric",
                "card_classes",
                "harness_caveats",
                "models",
                "backends",
                "concurrency_findings",
            }
        ),
        "model row": frozenset({*READING_LISTS, "capabilities"}),
    }
)


def _kind(value: Any) -> str:
    """What a JSON value is, in the words a refusal uses."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "a list"
    return "an object"


def _object(value: Any, path: Path, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CapabilityTableError(f"{path}: {where} is {_kind(value)}, not an object")
    return value


def _entries(value: Any, path: Path, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise CapabilityTableError(f"{path}: {where} is {_kind(value)}, not a list")
    return value


def _closed(entry: Mapping[str, Any], level: str, path: Path, where: str) -> None:
    """Refuse a key ``level`` does not declare, naming it and what is declared."""
    stray = sorted(str(key) for key in entry if key not in DECLARED_KEYS[level])
    if stray:
        raise CapabilityTableError(
            f"{path}: {where} carries {', '.join(repr(k) for k in stray)}, which "
            f"this code does not declare for a {level} (declared: "
            f"{', '.join(sorted(DECLARED_KEYS[level]))})"
        )
    _values(entry, level, path, where)


def _holds_object(value: Any) -> bool:
    if isinstance(value, dict):
        return True
    return isinstance(value, list) and any(_holds_object(item) for item in value)


def _values(entry: Mapping[str, Any], level: str, path: Path, where: str) -> None:
    """Refuse an object, at any depth, under a key ``level`` gives a value."""
    for key in sorted(DECLARED_KEYS[level] - CONTAINER_KEYS[level]):
        if key in entry and _holds_object(entry[key]):
            raise CapabilityTableError(
                f"{path}: {where} has an object under {key!r}; a {level}'s "
                f"{key!r} holds a value, not entries, and an object there would "
                f"carry keys this code does not declare"
            )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(value)
    )


#: The keys a model row cannot do without, and those of its keys that are numbers.
_MODEL_REQUIRED = ("id", "family", "params_b", "vram_gb_working", "weights_gb")
_MODEL_NUMBERS = ("params_b", "active_params_b", "vram_gb_working", "weights_gb")

#: The keys of a reading that carry its figure.
_READING_FIGURES = ("humaneval_plus_pass1", "humaneval_pass1", "value")

#: The keys a harness caveat cannot do without.
_CAVEAT_REQUIRED = ("id", "severity", "summary", "consequence")


def _required(
    entry: Mapping[str, Any], keys: tuple[str, ...], path: Path, where: str
) -> None:
    for key in keys:
        if key not in entry:
            raise CapabilityTableError(
                f"{path}: {where} is missing required key {key!r}"
            )


def _card_classes(raw: Mapping[str, Any], path: Path) -> tuple[CardClass, ...]:
    """The declared classes, each with an id, a label and its nominal memory."""
    declared = raw.get("card_classes")
    if not isinstance(declared, list):
        raise CapabilityTableError(
            f"{path}: the capability table declares no 'card_classes' list, so "
            f"no reading in it can say which card class it is an estimate for"
        )
    classes: list[CardClass] = []
    for index, value in enumerate(declared):
        where = f"card_classes[{index}]"
        entry = _object(value, path, where)
        _closed(entry, "card class", path, where)
        for key in ("id", "label", "memory_gb"):
            if key not in entry:
                raise CapabilityTableError(
                    f"{path}: {where} is missing required key {key!r}"
                )
        for key in ("id", "label"):
            if not _text(entry[key]):
                raise CapabilityTableError(
                    f"{path}: {where} has {key} {entry[key]!r}; a card class's "
                    f"{key} is non-empty text"
                )
        memory = entry["memory_gb"]
        if (
            isinstance(memory, bool)
            or not isinstance(memory, int | float)
            or not math.isfinite(memory)
            or memory <= 0
        ):
            raise CapabilityTableError(
                f"{path}: {where} ({entry['id']!r}) has memory_gb {memory!r}; a "
                f"card class's memory is a positive number of GB"
            )
        card_class = CardClass(
            id=entry["id"], label=entry["label"], memory_gb=float(memory)
        )
        if any(c.id == card_class.id for c in classes):
            raise CapabilityTableError(
                f"{path}: {where}: card class {card_class.id!r} is declared twice"
            )
        classes.append(card_class)
    return tuple(classes)


def _given_for(
    entry: Mapping[str, Any], declared: frozenset[str], path: Path, where: str
) -> None:
    """A ``card_class`` an entry carries is one the table declares."""
    if "card_class" not in entry:
        return
    named = entry["card_class"]
    if not isinstance(named, str) or named not in declared:
        raise CapabilityTableError(
            f"{path}: {where} is keyed by card class {named!r}, which the table "
            f"does not declare (declared: {', '.join(sorted(declared)) or 'none'})"
        )


def _check_readings(
    index: int, value: Any, declared: frozenset[str], path: Path
) -> None:
    """A model row carries only declared keys, and every reading of it names a
    declared card class, or the table is refused."""
    entry = _object(value, path, f"models[{index}]")
    row = f"models[{index}] ({entry.get('id')!r})"
    _closed(entry, "model row", path, row)
    _required(entry, _MODEL_REQUIRED, path, row)
    for key in _MODEL_NUMBERS:
        if key in entry and not _number(entry[key]):
            raise CapabilityTableError(
                f"{path}: {row} gives {key!r} as {entry[key]!r}; a model's "
                f"{key!r} is a number"
            )
    if "capabilities" in entry:
        scores = _object(entry["capabilities"], path, f"{row} capabilities")
        for dimension, score in scores.items():
            if not _number(score):
                raise CapabilityTableError(
                    f"{path}: {row} capabilities gives {dimension!r} the score "
                    f"{score!r}; a capability score is a number"
                )
    for field_name in READING_LISTS:
        if field_name not in entry:
            continue
        readings = _entries(entry[field_name], path, f"{row} {field_name}")
        for place, reading in enumerate(readings):
            where = f"{row} {field_name}[{place}]"
            reading = _object(reading, path, where)
            _closed(reading, "reading", path, where)
            if "card_class" not in reading:
                raise CapabilityTableError(
                    f"{path}: {where} names no 'card_class'; every figure is an "
                    f"estimate for a declared card class"
                )
            _given_for(reading, declared, path, where)
            for key in _READING_FIGURES:
                if key in reading and not _number(reading[key]):
                    raise CapabilityTableError(
                        f"{path}: {where} gives {key!r} as {reading[key]!r}; a "
                        f"reading's figure is a number"
                    )


def _check_shape(raw: Mapping[str, Any], path: Path) -> tuple[CardClass, ...]:
    """Refuse, by name, every entry of a shape or a key this code does not read.

    Returns the declared card classes, which everything else is keyed by.
    """
    _closed(raw, "table", path, "the table")
    if "quality_metric" in raw:
        metric = _object(raw["quality_metric"], path, "quality_metric")
        _closed(metric, "quality metric", path, "quality_metric")
    card_classes = _card_classes(raw, path)
    declared = frozenset(c.id for c in card_classes)
    for index, value in enumerate(
        _entries(raw.get("harness_caveats", []), path, "harness_caveats")
    ):
        where = f"harness_caveats[{index}]"
        caveat = _object(value, path, where)
        _closed(caveat, "harness caveat", path, where)
        _required(caveat, _CAVEAT_REQUIRED, path, where)
    for index, value in enumerate(_entries(raw.get("models", []), path, "models")):
        _check_readings(index, value, declared, path)
    backends = _object(raw.get("backends", {}), path, "backends")
    _values(backends, "backends block", path, "backends")
    for name, value in backends.items():
        if name in DECLARED_KEYS["backends block"]:
            continue
        where = f"backends[{name!r}]"
        backend = _object(value, path, where)
        _closed(backend, "backend", path, where)
        _given_for(backend, declared, path, where)
    for index, value in enumerate(
        _entries(raw.get("concurrency_findings", []), path, "concurrency_findings")
    ):
        where = f"concurrency_findings[{index}]"
        finding = _object(value, path, where)
        _closed(finding, "concurrency finding", path, where)
        _given_for(finding, declared, path, where)
    return card_classes


def _measurements(rows: list[dict[str, Any]], key: str) -> tuple[Measurement, ...]:
    return tuple(
        Measurement(
            value=float(row[key]),
            backend=str(row.get("backend", "")),
            card_class=str(row["card_class"]),
        )
        for row in rows
        if key in row
    )


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
    except UnicodeDecodeError as exc:
        raise CapabilityTableError(f"{path} is not UTF-8 text: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CapabilityTableError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise CapabilityTableError(f"{path}: the table is {_kind(raw)}, not an object")
    found = raw.get("schema_version")
    if type(found) is not int or found != SCHEMA_VERSION:
        raise CapabilityTableError(
            f"{path} has capability table schema_version {found!r}; this code "
            f"reads version {SCHEMA_VERSION} only"
        )

    # Every shape the parse below relies on (each required key, each number) is
    # refused by name here first, so nothing below raises out of the loader.
    card_classes = _check_shape(raw, path)

    models = tuple(
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
            capabilities=MappingProxyType(
                {
                    str(dimension): float(score)
                    for dimension, score in entry.get("capabilities", {}).items()
                }
            ),
        )
        for entry in raw.get("models", [])
    )
    if not models:
        raise CapabilityTableError(f"{path} declares no models")

    caveats = tuple(
        Caveat(
            id=str(c["id"]),
            severity=str(c["severity"]),
            summary=str(c["summary"]),
            consequence=str(c["consequence"]),
        )
        for c in raw.get("harness_caveats", [])
    )
    return CapabilityTable(models=models, caveats=caveats, card_classes=card_classes)


@cache
def shipped_table() -> CapabilityTable:
    """The shipped table, loaded once.

    The file travels with the package and cannot change under a running process,
    so re-reading and re-validating it per contract would be cost with no
    meaning. The same argument :func:`mcgyvr.catalog.catalog` makes, for the same
    reason: these are the two shipped data files, and both are read on hot paths.

    Memoised rather than held in a module variable, so no assignable name can
    replace the table under a running process. Reloading, which only a test
    wants, is ``shipped_table.cache_clear()`` after repointing
    :func:`table_path`.
    """
    return load()


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
    """The cheapest model estimated able to do what a ``task_type`` contract asks.

    Two steps, and the order is the point. First the *gate*: a model is a
    candidate only if it scores at least ``floor`` on the dimension this task
    needs — its vector entry if it has one, its scalar quality if it does not,
    and nothing at all if it has no estimate. Then the *choice*: among models that
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
            or "no model in it carries a valid quality estimate at all"
        )
        raise CapabilitySelectionError(
            f"no model scores {floor:g} or better on {dimension!r}, the capability "
            f"a {task_type!r} contract needs. The table says: {measured}. Bind a "
            f"rung on a model whose estimate on {dimension!r} reaches the floor, "
            f"or lower the floor knowing which capability you are lowering it on."
        )

    capable.sort(key=lambda pair: (pair[0].vram_gb_working, -pair[1], pair[0].id))
    return capable[0][0]
