"""The schema of the model knowledge document: every number says where it came from.

A document is an object with a `schema_version` and a `models` list, plus an
optional `_purpose` note; each entry of `models` is one model at one
quantisation, so the pair `(model_id, quant)` is its identity. A record holds
`engines` that can serve it, `weights` naming one file at one revision when the
record is about a downloadable file, and four whole-number fields (`size_bytes`,
`context_length`, `kv_bytes_per_token`, `recurrent_bytes_per_slot`). It may
also hold the `use_cases` it is a candidate for, the `architecture` of its
weights (one of `ARCHITECTURES`, read from the file's header; every shipped
record states it), and the Hub's `downloads` (its 30-day count) and `likes` of
the repository its weights come from. Every number is a `Number`: a value, a
kind from `KINDS`, a source written `<origin>:<where>` whose origin is one of
`SOURCES`, and the day it was read.

`parse_document` reads such a document and `parse_record` one entry of it; both
refuse a key the record does not have, a missing field, a kind, source or date
that does not fit, and raise `KnowledgeError` with the `where` they were given.
With `shipped=True`, a `reading` is refused as well, because a reading is a
number taken on a machine and the shipped catalog carries none. `dump_document`
writes records back in the shape the parsers accept."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

#: The version of the document format these readers accept and the writer
#: writes. A document that states any other version is refused rather than read
#: on a guess, save `_SCORES_VERSION`.
SCHEMA_VERSION = 3
#: The version before: its records also carried a `scores` list of leaderboard
#: figures, which nothing read. A document of this version is still read, and
#: each record's `scores` list is skipped unread, so a cache written by an older
#: mcgyvr keeps loading.
_SCORES_VERSION = 2

#: The shapes a model's weights may take, as the capability table and a record
#: state them: `dense`, every weight read for every token, or `moe`, a mixture
#: of experts whose expert blocks `--n-cpu-moe` can move to the host. A model
#: with a recurrent (state-space) part is still one of these; its state is
#: priced by `recurrent_bytes_per_slot`, not named here.
DENSE = "dense"
MOE = "moe"
ARCHITECTURES: tuple[str, ...] = (DENSE, MOE)


def architecture_of(row: Mapping[str, Any]) -> str:
    """The architecture a GGUF header row's tensors make: `MOE` when the scan
    found expert blocks `--n-cpu-moe` can move (``placeable_blocks``), `DENSE`
    otherwise. A name, a parameter count or a file size never decides it. The
    one law for it: placement (`serving.ModelSpec`), recommend and a Hub read
    all read a header's architecture here."""
    return MOE if row.get("placeable_blocks") else DENSE


#: The closed list of kinds a number may claim: a fact stated by the source it
#: names, an estimate the model card makes about itself, or a reading taken on a
#: machine.
KINDS: tuple[str, ...] = ("fact", "estimate", "reading")
#: A reading, and the origin a reading alone comes from: a machine of the user's.
KIND_READING = "reading"
MEASURED = "measured"
#: An estimate, and the origin that is always self-reported: the model card.
KIND_ESTIMATE = "estimate"
SELF_REPORTED = "model-card"

#: Every origin a number's source may name, with what a number from that
#: origin is a reading of. A source is `<origin>:<where>`, so what follows the colon
#: says where at that origin the number was read, and is never empty.
SOURCES: Mapping[str, str] = {
    "hub-api": (
        "the Hugging Face Hub model API (/api/models/<repo>), at the revision "
        "the locator names: file names, bytes, sha256"
    ),
    "hub-search": (
        "the Hugging Face Hub model search (/api/models?...), whose full URL is "
        "the locator: a repository's 30-day downloads and its likes on the day read"
    ),
    "hub-config": (
        "a file of the model's repository, such as config.json, at the revision "
        "the locator names"
    ),
    "gguf-header-range": (
        "a GGUF file's header, read over HTTP Range before any download, at the "
        "revision the locator names"
    ),
    "safetensors-header-range": (
        "a safetensors file's header, read over HTTP Range before any download, "
        "at the revision the locator names"
    ),
    SELF_REPORTED: "the model card's own model-index: self-reported, an estimate",
    MEASURED: "a reading on the user's own machine: never shipped",
}


class KnowledgeError(Exception):
    """A knowledge document, or one number in it, does not say what it must."""


@dataclass(frozen=True)
class Number:
    """One number of the knowledge: its value, the kind it claims, the source it
    was read from and the day it was read."""

    value: int | float
    kind: str
    source: str
    read_at: date


@dataclass(frozen=True)
class Weights:
    """The one file a record is about: its repository, the revision read, the file
    name at that revision, and the file's sha256."""

    repo: str
    revision: str
    file: str
    sha256: str


#: The whole-number fields of a record, each held as a `Number`.
_INT_FIELDS: tuple[str, ...] = (
    "size_bytes",
    "context_length",
    "kv_bytes_per_token",
    "recurrent_bytes_per_slot",
)
#: The whole-number fields a record may leave out: what the Hub search said of the
#: repository the weights come from. Each is held as a `Number` when present.
_OPTIONAL_INT_FIELDS: tuple[str, ...] = ("downloads", "likes")
#: Of those fields, the two that must be strictly positive; the others may be zero.
_POSITIVE = frozenset({"context_length", "kv_bytes_per_token"})
_RECORD_KEYS = frozenset(
    {
        "model_id",
        "quant",
        "architecture",
        "engines",
        "use_cases",
        "weights",
        *_INT_FIELDS,
        *_OPTIONAL_INT_FIELDS,
    }
)
_NUMBER_KEYS = frozenset({"value", "kind", "source", "read_at"})
_WEIGHTS_KEYS = ("repo", "revision", "file", "sha256")
_DOCUMENT_KEYS = frozenset({"schema_version", "models", "_purpose"})


@dataclass(frozen=True)
class ModelRecord:
    """One model at one quantisation: what serves it, the file it names, its four
    whole-number fields, the use cases it is a candidate for (empty when nothing
    said), the architecture of its weights (None when a cache written before
    records carried one says nothing), and the Hub's downloads and likes of its
    weights repository when they were read."""

    model_id: str
    quant: str
    engines: tuple[str, ...]
    weights: Weights | None
    size_bytes: Number
    context_length: Number
    kv_bytes_per_token: Number
    recurrent_bytes_per_slot: Number
    use_cases: tuple[str, ...] = ()
    downloads: Number | None = None
    likes: Number | None = None
    architecture: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.quant)

    def numbers(self) -> Iterator[tuple[str, Number]]:
        """Every number of the record, named: the four whole-number fields by their
        field name, then the downloads and likes when held."""
        for name in _INT_FIELDS:
            number = getattr(self, name)
            assert isinstance(number, Number)
            yield name, number
        for name in _OPTIONAL_INT_FIELDS:
            held = getattr(self, name)
            if held is not None:
                yield name, held


def _text(raw: Any, where: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise KnowledgeError(f"{where} is not a non-empty string")
    return raw


def _number(
    raw: Any,
    where: str,
    *,
    shipped: bool,
    integer: bool,
) -> Number:
    if not isinstance(raw, dict):
        raise KnowledgeError(
            f"{where} is not an object with its value, kind, source and read_at: "
            f"every number says where it came from and when"
        )
    unknown = sorted(set(raw) - _NUMBER_KEYS)
    if unknown:
        raise KnowledgeError(f"{where} has keys it does not have: {unknown}")
    for key in sorted(_NUMBER_KEYS):
        if key not in raw:
            raise KnowledgeError(f"{where} says no {key}")
    value = raw["value"]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise KnowledgeError(f"{where} value {value!r} is not a number")
    if integer and not isinstance(value, int):
        raise KnowledgeError(f"{where} value {value!r} is not a whole number")
    kind = raw["kind"]
    if kind not in KINDS:
        raise KnowledgeError(f"{where} kind {kind!r} is not one of {list(KINDS)}")
    source = _text(raw["source"], f"{where} source")
    origin, _, locator = source.partition(":")
    if origin not in SOURCES:
        raise KnowledgeError(
            f"{where} source {source!r} names no source the knowledge layer "
            f"knows ({sorted(SOURCES)})"
        )
    if not locator:
        raise KnowledgeError(f"{where} source {source!r} says no where after its colon")
    if kind == KIND_READING and shipped:
        raise KnowledgeError(
            f"{where} is a reading, a number taken on a machine; the shipped "
            f"catalog carries no machine's reading"
        )
    if (kind == KIND_READING) != (origin == MEASURED):
        raise KnowledgeError(
            f"{where} is a {kind} from {origin!r}: a reading comes from "
            f"{MEASURED!r}, and only a reading does"
        )
    if origin == SELF_REPORTED and kind != KIND_ESTIMATE:
        raise KnowledgeError(
            f"{where} comes from {SELF_REPORTED!r}, which is self-reported, so it "
            f"is an {KIND_ESTIMATE}, not a {kind}"
        )
    read_at = raw["read_at"]
    try:
        day = date.fromisoformat(read_at) if isinstance(read_at, str) else None
    except ValueError:
        day = None
    if day is None or len(read_at) != len("YYYY-MM-DD"):
        raise KnowledgeError(f"{where} read_at {read_at!r} is not a day (YYYY-MM-DD)")
    return Number(value=value, kind=kind, source=source, read_at=day)


def _weights(raw: Any, where: str) -> Weights | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != set(_WEIGHTS_KEYS):
        raise KnowledgeError(
            f"{where} is not an object of exactly {list(_WEIGHTS_KEYS)}"
        )
    return Weights(*(_text(raw[key], f"{where} {key}") for key in _WEIGHTS_KEYS))


def parse_record(raw: Any, where: str, *, shipped: bool) -> ModelRecord:
    """Read one entry of a knowledge document into a `ModelRecord`.

    `where` names the document the entry came from and prefixes every error;
    `shipped` marks the packaged catalog, where a reading is refused and an
    architecture must be stated. A key the record does not have, a missing
    field, a number out of range or an architecture not in `ARCHITECTURES`
    raises `KnowledgeError`.
    """
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{where}: a model entry is not an object")
    model_id = _text(raw.get("model_id"), f"{where} model_id")
    here = f"{where} {model_id}"
    unknown = sorted(set(raw) - _RECORD_KEYS)
    if unknown:
        raise KnowledgeError(f"{here} has keys a record does not have: {unknown}")
    quant = _text(raw.get("quant"), f"{here} quant")
    engines = raw.get("engines")
    if not isinstance(engines, list) or not engines:
        raise KnowledgeError(f"{here} declares no engines")
    numbers: dict[str, Number] = {}
    for name in _INT_FIELDS:
        if name not in raw:
            raise KnowledgeError(f"{here} has no {name}")
        number = _number(raw[name], f"{here} {name}", shipped=shipped, integer=True)
        if number.value < 0 or (name in _POSITIVE and number.value == 0):
            raise KnowledgeError(f"{here} {name} {number.value} is out of range")
        numbers[name] = number
    optional: dict[str, Number | None] = {}
    for name in _OPTIONAL_INT_FIELDS:
        held = None
        if name in raw:
            held = _number(raw[name], f"{here} {name}", shipped=shipped, integer=True)
            if held.value < 0:
                raise KnowledgeError(f"{here} {name} {held.value} is out of range")
        optional[name] = held
    use_cases = raw.get("use_cases", [])
    if not isinstance(use_cases, list):
        raise KnowledgeError(f"{here} use_cases is not a list")
    architecture = raw.get("architecture")
    if architecture is None and shipped:
        raise KnowledgeError(
            f"{here} states no architecture; every shipped record says which of "
            f"{list(ARCHITECTURES)} its weights are"
        )
    if architecture is not None and architecture not in ARCHITECTURES:
        raise KnowledgeError(
            f"{here} architecture {architecture!r} is not one of {list(ARCHITECTURES)}"
        )
    return ModelRecord(
        model_id=model_id,
        quant=quant,
        engines=tuple(_text(e, f"{here} engine") for e in engines),
        weights=_weights(raw.get("weights"), f"{here} weights"),
        use_cases=tuple(dict.fromkeys(_text(u, f"{here} use case") for u in use_cases)),
        **numbers,
        downloads=optional["downloads"],
        likes=optional["likes"],
        architecture=architecture,
    )


def parse_document(raw: Any, where: str, *, shipped: bool) -> tuple[ModelRecord, ...]:
    """Read a whole knowledge document into its records.

    The document must be an object at `SCHEMA_VERSION` (or `_SCORES_VERSION`,
    whose records' `scores` lists are skipped) whose keys are all in
    `_DOCUMENT_KEYS` and whose `models` is a list; `where` prefixes every error
    and `shipped` marks the packaged catalog. Two records for one
    `(model_id, quant)` raise `KnowledgeError`.
    """
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{where}: the document is not an object")
    version = raw.get("schema_version")
    if version not in (SCHEMA_VERSION, _SCORES_VERSION):
        raise KnowledgeError(
            f"{where} has schema_version {version!r}; this code reads version "
            f"{SCHEMA_VERSION}, and {_SCORES_VERSION} before it"
        )
    unknown = sorted(set(raw) - _DOCUMENT_KEYS)
    if unknown:
        raise KnowledgeError(
            f"{where} has keys a knowledge document does not have: {unknown}"
        )
    models = raw.get("models")
    if not isinstance(models, list):
        raise KnowledgeError(f"{where} declares no models list")
    if version == _SCORES_VERSION:
        models = [_without_scores(m, where) for m in models]
    records = tuple(parse_record(m, where, shipped=shipped) for m in models)
    keys = [one.key for one in records]
    if len(set(keys)) != len(keys):
        raise KnowledgeError(f"{where} holds one model at one quantisation twice")
    return records


def _without_scores(raw: Any, where: str) -> Any:
    """A version-2 entry without its `scores` list, which is skipped unread.

    The list must still be a list, as version 2 had it; what it holds is not
    read, because nothing reads a score.
    """
    if not isinstance(raw, dict) or "scores" not in raw:
        return raw
    if not isinstance(raw["scores"], list):
        raise KnowledgeError(f"{where} {raw.get('model_id')} scores is not a list")
    return {key: value for key, value in raw.items() if key != "scores"}


def _dump_number(number: Number) -> dict[str, Any]:
    return {
        "value": number.value,
        "kind": number.kind,
        "source": number.source,
        "read_at": number.read_at.isoformat(),
    }


def dump_record(one: ModelRecord) -> dict[str, Any]:
    """The object a document holds for one record: its identity, its architecture
    when stated, engines and use cases, the weights when it has some, its four
    numbers, and the downloads and likes when held, each number written as
    value, kind, source and `read_at` day."""
    out: dict[str, Any] = {
        "model_id": one.model_id,
        "quant": one.quant,
    }
    if one.architecture is not None:
        out["architecture"] = one.architecture
    out["engines"] = list(one.engines)
    out["use_cases"] = list(one.use_cases)
    if one.weights is not None:
        out["weights"] = {key: getattr(one.weights, key) for key in _WEIGHTS_KEYS}
    for name in _INT_FIELDS:
        out[name] = _dump_number(getattr(one, name))
    for name in _OPTIONAL_INT_FIELDS:
        held = getattr(one, name)
        if held is not None:
            out[name] = _dump_number(held)
    return out


def dump_document(records: Sequence[ModelRecord]) -> dict[str, Any]:
    """A whole knowledge document of `records` at `SCHEMA_VERSION`."""
    return {
        "schema_version": SCHEMA_VERSION,
        "models": [dump_record(one) for one in records],
    }
