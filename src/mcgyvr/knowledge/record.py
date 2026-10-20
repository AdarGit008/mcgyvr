"""The schema of the model knowledge document: every number says where it came from.

A document is an object with a `schema_version` and a `models` list, plus an
optional `_purpose` note; each entry of `models` is one model at one
quantisation, so the pair `(model_id, quant)` is its identity. A record holds
`engines` that can serve it, `weights` naming one file at one revision when the
record is about a downloadable file, four whole-number fields (`size_bytes`,
`context_length`, `kv_bytes_per_token`, `recurrent_bytes_per_slot`) and the
`scores` filed under the boards in `BOARDS`. It may also hold the `use_cases`
it is a candidate for, and the Hub's `downloads` (its 30-day count) and `likes`
of the repository its weights come from. Every number is a `Number`: a value, a
kind from `KINDS`, a source written `<origin>:<where>` whose origin is one of
`SOURCES`, and the day it was read.

`parse_document` reads such a document and `parse_record` one entry of it; both
refuse a key the record does not have, a missing field, a kind, source, date or
board metric that does not fit, and raise `KnowledgeError` with the `where` they
were given. With `shipped=True`, a `reading` is refused as well, because a
reading is a number taken on a machine and the shipped catalog carries none.
`dump_document` writes records back in the shape the parsers accept."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

#: The version of the document format these readers accept. A document that
#: states any other version is refused rather than read on a guess.
SCHEMA_VERSION = 2

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
#: The origin of a score: the leaderboard whose published figures it was read from.
BOARD = "board"

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
    BOARD: "a public leaderboard of BOARDS, on the date the locator names",
    SELF_REPORTED: "the model card's own model-index: self-reported, an estimate",
    MEASURED: "a reading on the user's own machine: never shipped",
}


@dataclass(frozen=True)
class Board:
    """One leaderboard scores can be read from: what it ranks, the metric name its
    rows carry, whether a higher value is better, and where and as what format
    its rows are fetched."""

    id: str
    ranks: str
    metric: str
    better: str
    url: str
    format: str


#: The boards a score may name, each with the one metric its rows carry.
BOARDS: tuple[Board, ...] = (
    Board(
        id="lmarena-text",
        ranks="chat",
        metric="rating",
        better="higher",
        url=(
            "https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/"
            "leaderboard-dataset&config=text&split=latest"
        ),
        format="json",
    ),
    Board(
        id="bfcl",
        ranks="agent",
        metric="overall_acc",
        better="higher",
        url="https://gorilla.cs.berkeley.edu/data_overall.csv",
        format="csv",
    ),
    Board(
        id="swe-bench-verified-bash-only",
        ranks="coding",
        metric="resolved",
        better="higher",
        url=(
            "https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/"
            "master/data/leaderboards.json"
        ),
        format="json",
    ),
    Board(
        id="evalplus",
        ranks="coding",
        metric="humaneval+ pass@1",
        better="higher",
        url="https://evalplus.github.io/results.json",
        format="json",
    ),
)


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
class Score:
    """One board figure: the board and metric it is filed under, and the value
    itself, which carries its own source and date."""

    board: str
    metric: str
    value: Number


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
        "engines",
        "use_cases",
        "weights",
        "scores",
        *_INT_FIELDS,
        *_OPTIONAL_INT_FIELDS,
    }
)
_NUMBER_KEYS = frozenset({"value", "kind", "source", "read_at"})
_SCORE_KEYS = _NUMBER_KEYS | {"board", "metric"}
_WEIGHTS_KEYS = ("repo", "revision", "file", "sha256")
_DOCUMENT_KEYS = frozenset({"schema_version", "models", "_purpose"})


@dataclass(frozen=True)
class ModelRecord:
    """One model at one quantisation: what serves it, the file it names, its four
    whole-number fields and the scores read for it, the use cases it is a
    candidate for (empty when nothing said), and the Hub's downloads and likes of
    its weights repository when they were read."""

    model_id: str
    quant: str
    engines: tuple[str, ...]
    weights: Weights | None
    size_bytes: Number
    context_length: Number
    kv_bytes_per_token: Number
    recurrent_bytes_per_slot: Number
    scores: tuple[Score, ...]
    use_cases: tuple[str, ...] = ()
    downloads: Number | None = None
    likes: Number | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.quant)

    def numbers(self) -> Iterator[tuple[str, Number]]:
        """Every number of the record, named: the four whole-number fields by their
        field name, the downloads and likes when held, then each score as
        `scores[<board>]`."""
        for name in _INT_FIELDS:
            number = getattr(self, name)
            assert isinstance(number, Number)
            yield name, number
        for name in _OPTIONAL_INT_FIELDS:
            held = getattr(self, name)
            if held is not None:
                yield name, held
        for score in self.scores:
            yield f"scores[{score.board}]", score.value


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
    keys: frozenset[str] = _NUMBER_KEYS,
) -> Number:
    if not isinstance(raw, dict):
        raise KnowledgeError(
            f"{where} is not an object with its value, kind, source and read_at: "
            f"every number says where it came from and when"
        )
    unknown = sorted(set(raw) - keys)
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


def _score(raw: Any, where: str, *, shipped: bool) -> Score:
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{where} is not an object")
    boards = {board.id: board for board in BOARDS}
    board = boards.get(str(raw.get("board")))
    if board is None:
        raise KnowledgeError(
            f"{where} board {raw.get('board')!r} is not a board the knowledge "
            f"layer names ({sorted(boards)})"
        )
    if raw.get("metric") != board.metric:
        raise KnowledgeError(
            f"{where} metric {raw.get('metric')!r} is not {board.id}'s metric "
            f"{board.metric!r}"
        )
    value = _number(raw, where, shipped=shipped, integer=False, keys=_SCORE_KEYS)
    origin, _, locator = value.source.partition(":")
    if origin == BOARD and not locator.startswith(board.id):
        raise KnowledgeError(
            f"{where} source {value.source!r} is another board than {board.id!r}"
        )
    if origin not in (BOARD, SELF_REPORTED):
        raise KnowledgeError(
            f"{where} source {value.source!r}: a score comes from its board or "
            f"from the model card"
        )
    return Score(board=board.id, metric=board.metric, value=value)


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
    `shipped` marks the packaged catalog, where a reading is refused. A key the
    record does not have, a missing field, a number out of range, a score from a
    board not in `BOARDS` or under another metric than that board's, raises
    `KnowledgeError`.
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
    scores = raw.get("scores", [])
    if not isinstance(scores, list):
        raise KnowledgeError(f"{here} scores is not a list")
    return ModelRecord(
        model_id=model_id,
        quant=quant,
        engines=tuple(_text(e, f"{here} engine") for e in engines),
        weights=_weights(raw.get("weights"), f"{here} weights"),
        scores=tuple(
            _score(s, f"{here} scores[{i}]", shipped=shipped)
            for i, s in enumerate(scores)
        ),
        use_cases=tuple(dict.fromkeys(_text(u, f"{here} use case") for u in use_cases)),
        **numbers,
        downloads=optional["downloads"],
        likes=optional["likes"],
    )


def parse_document(raw: Any, where: str, *, shipped: bool) -> tuple[ModelRecord, ...]:
    """Read a whole knowledge document into its records.

    The document must be an object at `SCHEMA_VERSION` whose keys are all in
    `_DOCUMENT_KEYS` and whose `models` is a list; `where` prefixes every error
    and `shipped` marks the packaged catalog. Two records for one
    `(model_id, quant)` raise `KnowledgeError`.
    """
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{where}: the document is not an object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeError(
            f"{where} has schema_version {raw.get('schema_version')!r}; this code "
            f"reads version {SCHEMA_VERSION} only"
        )
    unknown = sorted(set(raw) - _DOCUMENT_KEYS)
    if unknown:
        raise KnowledgeError(
            f"{where} has keys a knowledge document does not have: {unknown}"
        )
    models = raw.get("models")
    if not isinstance(models, list):
        raise KnowledgeError(f"{where} declares no models list")
    records = tuple(parse_record(m, where, shipped=shipped) for m in models)
    keys = [one.key for one in records]
    if len(set(keys)) != len(keys):
        raise KnowledgeError(f"{where} holds one model at one quantisation twice")
    return records


def _dump_number(number: Number) -> dict[str, Any]:
    return {
        "value": number.value,
        "kind": number.kind,
        "source": number.source,
        "read_at": number.read_at.isoformat(),
    }


def dump_record(one: ModelRecord) -> dict[str, Any]:
    """The object a document holds for one record: its identity, engines and use
    cases, the weights when it has some, its four numbers, the downloads and likes
    when held, and its scores, each number written as value, kind, source and
    `read_at` day."""
    out: dict[str, Any] = {
        "model_id": one.model_id,
        "quant": one.quant,
        "engines": list(one.engines),
        "use_cases": list(one.use_cases),
    }
    if one.weights is not None:
        out["weights"] = {key: getattr(one.weights, key) for key in _WEIGHTS_KEYS}
    for name in _INT_FIELDS:
        out[name] = _dump_number(getattr(one, name))
    for name in _OPTIONAL_INT_FIELDS:
        held = getattr(one, name)
        if held is not None:
            out[name] = _dump_number(held)
    out["scores"] = [
        {"board": s.board, "metric": s.metric, **_dump_number(s.value)}
        for s in one.scores
    ]
    return out


def dump_document(records: Sequence[ModelRecord]) -> dict[str, Any]:
    """A whole knowledge document of `records` at `SCHEMA_VERSION`."""
    return {
        "schema_version": SCHEMA_VERSION,
        "models": [dump_record(one) for one in records],
    }
