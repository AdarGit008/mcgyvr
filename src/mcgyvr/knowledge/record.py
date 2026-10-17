""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

#
#
SCHEMA_VERSION = 2

#
#
KINDS: tuple[str, ...] = ("fact", "estimate", "reading")
#
KIND_READING = "reading"
MEASURED = "measured"
#
KIND_ESTIMATE = "estimate"
SELF_REPORTED = "model-card"
#
BOARD = "board"

#
#
SOURCES: Mapping[str, str] = {
    "hub-api": (
        "the Hugging Face Hub model API (/api/models/<repo>), at the revision "
        "the locator names: file names, bytes, sha256"
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
    ""

    id: str
    ranks: str
    metric: str
    better: str
    url: str
    format: str


#
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
    Board(
        id="lmarena-text-to-image",
        ranks="image",
        metric="rating",
        better="higher",
        url=(
            "https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/"
            "leaderboard-dataset&config=text_to_image&split=latest"
        ),
        format="json",
    ),
    Board(
        id="open-asr",
        ranks="asr",
        metric="avg_wer",
        better="lower",
        url=(
            "https://huggingface.co/datasets/hf-audio/open-asr-leaderboard-results/"
            "resolve/main/english_short_latest.csv"
        ),
        format="csv",
    ),
)

#
UNRANKED: Mapping[str, str] = {
    "tts": (
        "no public board publishes data; ranked by mcgyvr's own ASR-WER gate "
        "and Hub downloads"
    ),
}


class KnowledgeError(Exception):
    ""


@dataclass(frozen=True)
class Number:
    ""

    value: int | float
    kind: str
    source: str
    read_at: date


@dataclass(frozen=True)
class Score:
    ""

    board: str
    metric: str
    value: Number


@dataclass(frozen=True)
class Weights:
    ""

    repo: str
    revision: str
    file: str
    sha256: str


#
_INT_FIELDS: tuple[str, ...] = (
    "size_bytes",
    "context_length",
    "kv_bytes_per_token",
    "recurrent_bytes_per_slot",
)
#
_POSITIVE = frozenset({"context_length", "kv_bytes_per_token"})
_RECORD_KEYS = frozenset(
    {"model_id", "quant", "engines", "weights", "scores", *_INT_FIELDS}
)
_NUMBER_KEYS = frozenset({"value", "kind", "source", "read_at"})
_SCORE_KEYS = _NUMBER_KEYS | {"board", "metric"}
_WEIGHTS_KEYS = ("repo", "revision", "file", "sha256")
_DOCUMENT_KEYS = frozenset({"schema_version", "models", "_purpose"})


@dataclass(frozen=True)
class ModelRecord:
    ""

    model_id: str
    quant: str
    engines: tuple[str, ...]
    weights: Weights | None
    size_bytes: Number
    context_length: Number
    kv_bytes_per_token: Number
    recurrent_bytes_per_slot: Number
    scores: tuple[Score, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.quant)

    def numbers(self) -> Iterator[tuple[str, Number]]:
        ""
        for name in _INT_FIELDS:
            number = getattr(self, name)
            assert isinstance(number, Number)
            yield name, number
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
    ""
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
        **numbers,
    )


def parse_document(raw: Any, where: str, *, shipped: bool) -> tuple[ModelRecord, ...]:
    ""
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
    ""
    out: dict[str, Any] = {
        "model_id": one.model_id,
        "quant": one.quant,
        "engines": list(one.engines),
    }
    if one.weights is not None:
        out["weights"] = {key: getattr(one.weights, key) for key in _WEIGHTS_KEYS}
    for name in _INT_FIELDS:
        out[name] = _dump_number(getattr(one, name))
    out["scores"] = [
        {"board": s.board, "metric": s.metric, **_dump_number(s.value)}
        for s in one.scores
    ]
    return out


def dump_document(records: Sequence[ModelRecord]) -> dict[str, Any]:
    ""
    return {
        "schema_version": SCHEMA_VERSION,
        "models": [dump_record(one) for one in records],
    }
