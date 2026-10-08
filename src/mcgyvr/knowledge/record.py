"""The model-knowledge record: a model's numbers, each with its source and date.

A record is what mcgyvr knows about one downloadable model at one
quantisation: what it weighs, how long a context it was made for, how much
cache one token of context costs, how much state a slot keeps, and how the
public boards rank it. Every one of those is a :class:`Number`, and a number
never travels without three things:

* its **kind**, from :data:`KINDS`: a *fact* (true of that file or that board
  on that day), an *estimate* (what someone says, such as a model card's
  self-reported score) or a *reading* (taken on a machine);
* its **source**, ``<source>:<where>``: one of :data:`SOURCES`, then where at
  that source (a repository at a revision, a board on a date);
* the day it was **read**, ``read_at``.

A reading is a number taken on a machine. The machines anyone could have
read a shipped number on are the project's own, so the shipped catalog holds
no reading (``shipped=True`` refuses one); the user's own cache may.

A media model (owner, Round 10) is a record whose engines are all media
engines (:data:`MEDIA_PARTS`): an image model, a voice, or the speech
recogniser the ASR-WER gate runs. Context and KV cache are a text model's, so a
media record carries none of them. It may name several ``files`` (each pinned
by its repository, revision and sha256, or by its git oid when the Hub keeps
no sha256 for it) and a stated ``working_set``: which of those files the unit
holds on its card and which in RAM. Its size is then the sum of its files.

The same document format holds the shipped catalog and every cache file:
``{"schema_version": 2, "models": [record, ...]}``. A key a record does not
have is refused rather than ignored, so a number cannot slip in under a new
key without saying where it came from.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

#: The version of the knowledge format, the shipped catalog's and each cache
#: file's. Version 1 was the catalog whose numbers said no source and no date.
SCHEMA_VERSION = 2

#: What a number may be. A *fact* is true of its source on the day read; an
#: *estimate* is what its source claims; a *reading* was taken on a machine.
KINDS: tuple[str, ...] = ("fact", "estimate", "reading")
#: The kind a reading has, and the only source it may come from.
KIND_READING = "reading"
MEASURED = "measured"
#: The kind a self-reported figure has: a model card states it, nobody checked.
KIND_ESTIMATE = "estimate"
SELF_REPORTED = "model-card"
#: The source a board's score comes from.
BOARD = "board"

#: Where a number may come from: the word before the colon of its ``source``,
#: and what it means. After the colon comes where at that source.
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
    """A public leaderboard a score may come from.

    ``ranks`` is what it ranks: a use case (``chat``, ``agent``, ``coding``)
    or a part of ``media-gen`` (``image``, ``asr``). ``metric`` is the one
    figure of it a score carries, and ``better`` says which way is better.
    ``url`` and ``format`` are where the online half reads it.
    """

    id: str
    ranks: str
    metric: str
    better: str
    url: str
    format: str


#: The boards, each verified reachable with a plain GET on 2026-10-07.
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

#: What a model may be catalogued as serving: the four use cases, and the Jev
#: role (the small model that answers typed decisions). A record that says
#: nothing serves any text use case.
SERVES: tuple[str, ...] = ("chat", "agent", "coding", "media-gen", "jev")

#: What no public board ranks, and how it is ranked instead.
UNRANKED: Mapping[str, str] = {
    "tts": (
        "no public board publishes data; ranked by mcgyvr's own ASR-WER gate "
        "and Hub downloads"
    ),
}


#: The engines a media record may name, and the part of ``media-gen`` each
#: serves (owner, Round 10): ComfyUI or diffusers paint the image, the TTS
#: engine speaks, and ``whisper`` is the speech recogniser the ASR-WER gate
#: runs on the machine mcgyvr runs on (nothing is served on a rig for it).
MEDIA_PARTS: Mapping[str, str] = {
    "comfyui": "image",
    "diffusers": "image",
    "tts": "tts",
    "whisper": "asr",
}
#: Where a media unit holds a file of its working set.
HELD_ON: tuple[str, ...] = ("card", "ram")


class KnowledgeError(Exception):
    """A knowledge document or record is unreadable, or a number in it does not
    say what it is, where it came from or when it was read."""


@dataclass(frozen=True)
class Number:
    """One number, with what it is, where it came from and when it was read."""

    value: int | float
    kind: str
    source: str
    read_at: date


@dataclass(frozen=True)
class Score:
    """One board's figure for a model, on the day it was read."""

    board: str
    metric: str
    value: Number


@dataclass(frozen=True)
class Weights:
    """The one file a pick downloads: a repository, its revision, the file and
    the file's sha256. Text, never a number."""

    repo: str
    revision: str
    file: str
    sha256: str


@dataclass(frozen=True)
class File:
    """One file of a media model: its repository, revision and path there,
    its size, and the hash it is held to. ``sha256`` is the Hub's LFS hash;
    a file the Hub keeps outside LFS (a small ``config.json``) has none, and
    is held to its ``git_oid`` instead. Exactly one of the two is set."""

    repo: str
    revision: str
    file: str
    bytes: Number
    sha256: str | None = None
    git_oid: str | None = None


@dataclass(frozen=True)
class WorkingSet:
    """Which files of a media model its unit holds on its card, and which in
    RAM: every file of the record, each named once."""

    card: tuple[str, ...]
    ram: tuple[str, ...]


#: The numbers every record carries, in the order a record is written.
_INT_FIELDS: tuple[str, ...] = (
    "size_bytes",
    "context_length",
    "kv_bytes_per_token",
    "recurrent_bytes_per_slot",
)
#: The numbers only a text model has: a media record carries none of them.
TEXT_ONLY: tuple[str, ...] = (
    "context_length",
    "kv_bytes_per_token",
    "recurrent_bytes_per_slot",
)
#: The ones of those that are never zero: a context and a cache width.
_POSITIVE = frozenset({"context_length", "kv_bytes_per_token"})
_MEDIA_KEYS = frozenset({"files", "working_set", "downloads"})
_RECORD_KEYS = frozenset(
    {
        "model_id",
        "quant",
        "engines",
        "weights",
        "scores",
        "serves",
        *_INT_FIELDS,
        *_MEDIA_KEYS,
    }
)
_NUMBER_KEYS = frozenset({"value", "kind", "source", "read_at"})
_SCORE_KEYS = _NUMBER_KEYS | {"board", "metric"}
_WEIGHTS_KEYS = ("repo", "revision", "file", "sha256")
_FILE_KEYS = frozenset({"repo", "revision", "file", "bytes", "sha256", "git_oid"})
_DOCUMENT_KEYS = frozenset({"schema_version", "models", "_purpose"})


@dataclass(frozen=True)
class ModelRecord:
    """What is known of one model at one quantisation.

    ``model_id`` is the model's repository and ``quant`` the quantisation; the
    two are the record's :attr:`key`. ``weights`` names the file a pick
    downloads, when one is known. ``engines`` are the engines that can serve
    it.

    A text record carries every number of :data:`_INT_FIELDS`. A media record
    (:attr:`is_media`) carries none of :data:`TEXT_ONLY`, and either its
    ``size_bytes`` or its ``files`` with their ``working_set``.
    """

    model_id: str
    quant: str
    engines: tuple[str, ...]
    weights: Weights | None
    size_bytes: Number | None
    context_length: Number | None
    kv_bytes_per_token: Number | None
    recurrent_bytes_per_slot: Number | None
    scores: tuple[Score, ...]
    #: What the model is catalogued as serving (:data:`SERVES`); empty when
    #: the record says nothing.
    serves: tuple[str, ...] = ()
    #: A media model's files, and where its unit holds each.
    files: tuple[File, ...] = ()
    working_set: WorkingSet | None = None
    #: The Hub's download count for the model's repository: what ranks a
    #: voice, which no public board ranks (:data:`UNRANKED`).
    downloads: Number | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.model_id, self.quant)

    @property
    def is_media(self) -> bool:
        """Whether every engine of the record is a media engine."""
        return is_media_engines(self.engines)

    @property
    def part(self) -> str | None:
        """The part of ``media-gen`` a media record serves, else ``None``."""
        return MEDIA_PARTS[self.engines[0]] if self.is_media else None

    @property
    def total_bytes(self) -> int:
        """What the model weighs: its ``size_bytes``, else its files' sum."""
        if self.size_bytes is not None:
            return int(self.size_bytes.value)
        return sum(int(one.bytes.value) for one in self.files)

    def numbers(self) -> Iterator[tuple[str, Number]]:
        """Every number of the record, with its name."""
        for name in _INT_FIELDS:
            number = getattr(self, name)
            if number is not None:
                yield name, number
        for one in self.files:
            yield f"files[{one.file}].bytes", one.bytes
        if self.downloads is not None:
            yield "downloads", self.downloads
        for score in self.scores:
            yield f"scores[{score.board}]", score.value


def is_media_engines(engines: Sequence[str]) -> bool:
    """Whether ``engines`` are all media engines (:data:`MEDIA_PARTS`) and
    name one part of ``media-gen``."""
    return bool(engines) and len({MEDIA_PARTS.get(e) for e in engines}) == 1 and (
        engines[0] in MEDIA_PARTS
    )


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


_GIT_OID = frozenset("0123456789abcdef")


def _hash(raw: Any, where: str, length: int) -> str:
    text = _text(raw, where)
    if len(text) != length or not set(text) <= _GIT_OID:
        raise KnowledgeError(f"{where} {text!r} is not {length} lower-case hex digits")
    return text


def _file(raw: Any, where: str, *, shipped: bool) -> File:
    if not isinstance(raw, dict):
        raise KnowledgeError(f"{where} is not an object")
    unknown = sorted(set(raw) - _FILE_KEYS)
    if unknown:
        raise KnowledgeError(f"{where} has keys a file does not have: {unknown}")
    hashes = [key for key in ("sha256", "git_oid") if key in raw]
    if len(hashes) != 1:
        raise KnowledgeError(
            f"{where} names {len(hashes)} of sha256 and git_oid: a file is held to "
            f"exactly one (its sha256, or its git oid when the Hub keeps no sha256)"
        )
    size = _number(raw.get("bytes"), f"{where} bytes", shipped=shipped, integer=True)
    if size.value <= 0:
        raise KnowledgeError(f"{where} bytes {size.value} is out of range")
    return File(
        repo=_text(raw.get("repo"), f"{where} repo"),
        revision=_hash(raw.get("revision"), f"{where} revision", 40),
        file=_text(raw.get("file"), f"{where} file"),
        bytes=size,
        sha256=_hash(raw["sha256"], f"{where} sha256", 64) if "sha256" in raw else None,
        git_oid=_hash(raw["git_oid"], f"{where} git_oid", 40)
        if "git_oid" in raw
        else None,
    )


def _working_set(raw: Any, where: str, files: Sequence[File]) -> WorkingSet:
    if not isinstance(raw, dict) or set(raw) != set(HELD_ON):
        raise KnowledgeError(f"{where} is not an object of exactly {list(HELD_ON)}")
    held: dict[str, tuple[str, ...]] = {}
    for place in HELD_ON:
        names = raw[place]
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise KnowledgeError(f"{where} {place} is not a list of file names")
        held[place] = tuple(names)
    named = [*held["card"], *held["ram"]]
    known = [one.file for one in files]
    if sorted(named) != sorted(known):
        raise KnowledgeError(
            f"{where} names {sorted(named)}; it names every file of the record "
            f"once ({sorted(known)})"
        )
    return WorkingSet(card=held["card"], ram=held["ram"])


def _media(raw: dict[str, Any], here: str) -> None:
    """Refuse what a media record cannot hold, and require what it must."""
    text_only = [name for name in TEXT_ONLY if name in raw]
    if text_only:
        raise KnowledgeError(
            f"{here} is a media model and carries {text_only}: context and KV "
            f"cache are a text model's"
        )
    if raw.get("weights") is not None:
        raise KnowledgeError(f"{here} is a media model: its files are `files`")
    if "files" in raw:
        if "size_bytes" in raw:
            raise KnowledgeError(
                f"{here} names its files and a size_bytes: its size is its files' sum"
            )
        if "working_set" not in raw:
            raise KnowledgeError(
                f"{here} names its files and no working_set: where its unit "
                f"holds each file is stated"
            )
    elif "size_bytes" not in raw:
        raise KnowledgeError(f"{here} has no size_bytes and no files")
    elif "working_set" in raw:
        raise KnowledgeError(f"{here} has a working_set and no files")


def parse_record(raw: Any, where: str, *, shipped: bool) -> ModelRecord:
    """One record, validated: every number says its kind, source and date."""
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
    named = tuple(_text(e, f"{here} engine") for e in engines)
    media = any(e in MEDIA_PARTS for e in named)
    if media and not is_media_engines(named):
        raise KnowledgeError(
            f"{here} engines {list(named)} mix a media engine with another engine "
            f"or with another part of media-gen"
        )
    if media:
        _media(raw, here)
    else:
        given = sorted(_MEDIA_KEYS & set(raw))
        if given:
            raise KnowledgeError(
                f"{here} is a text model and carries {given}, which describe a "
                f"media model"
            )
    numbers: dict[str, Number | None] = {}
    for name in _INT_FIELDS:
        if name not in raw:
            if not media:
                raise KnowledgeError(f"{here} has no {name}")
            numbers[name] = None
            continue
        number = _number(raw[name], f"{here} {name}", shipped=shipped, integer=True)
        if number.value < 0 or (name in _POSITIVE and number.value == 0):
            raise KnowledgeError(f"{here} {name} {number.value} is out of range")
        numbers[name] = number
    scores = raw.get("scores", [])
    if not isinstance(scores, list):
        raise KnowledgeError(f"{here} scores is not a list")
    serves = raw.get("serves", [])
    if not isinstance(serves, list) or not all(isinstance(s, str) for s in serves):
        raise KnowledgeError(f"{here} serves is not a list of names")
    unknown_uses = [s for s in serves if s not in SERVES]
    if unknown_uses:
        raise KnowledgeError(
            f"{here} serves {unknown_uses}, which is not one of {list(SERVES)}"
        )
    files_raw = raw.get("files", [])
    if not isinstance(files_raw, list) or ("files" in raw and not files_raw):
        raise KnowledgeError(f"{here} files is not a non-empty list")
    files = tuple(
        _file(f, f"{here} files[{i}]", shipped=shipped) for i, f in enumerate(files_raw)
    )
    if len({one.file for one in files}) != len(files):
        raise KnowledgeError(f"{here} names one file twice")
    downloads = (
        _number(raw["downloads"], f"{here} downloads", shipped=shipped, integer=True)
        if "downloads" in raw
        else None
    )
    return ModelRecord(
        model_id=model_id,
        quant=quant,
        engines=named,
        weights=_weights(raw.get("weights"), f"{here} weights"),
        scores=tuple(
            _score(s, f"{here} scores[{i}]", shipped=shipped)
            for i, s in enumerate(scores)
        ),
        serves=tuple(serves),
        files=files,
        working_set=(
            _working_set(raw["working_set"], f"{here} working_set", files)
            if "working_set" in raw
            else None
        ),
        downloads=downloads,
        **numbers,
    )


def parse_document(raw: Any, where: str, *, shipped: bool) -> tuple[ModelRecord, ...]:
    """The records of one knowledge document (the catalog, or a cache file).

    ``shipped`` is true for the catalog in the package, which may hold no
    reading. A document of another ``schema_version`` is refused by name.
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
    """``one`` as JSON, the shape :func:`parse_record` reads back."""
    out: dict[str, Any] = {
        "model_id": one.model_id,
        "quant": one.quant,
        "engines": list(one.engines),
    }
    if one.weights is not None:
        out["weights"] = {key: getattr(one.weights, key) for key in _WEIGHTS_KEYS}
    for name in _INT_FIELDS:
        number = getattr(one, name)
        if number is not None:
            out[name] = _dump_number(number)
    if one.files:
        out["files"] = [
            {
                "repo": f.repo,
                "revision": f.revision,
                "file": f.file,
                **({"sha256": f.sha256} if f.sha256 else {"git_oid": f.git_oid}),
                "bytes": _dump_number(f.bytes),
            }
            for f in one.files
        ]
    if one.working_set is not None:
        out["working_set"] = {
            "card": list(one.working_set.card),
            "ram": list(one.working_set.ram),
        }
    if one.downloads is not None:
        out["downloads"] = _dump_number(one.downloads)
    out["scores"] = [
        {"board": s.board, "metric": s.metric, **_dump_number(s.value)}
        for s in one.scores
    ]
    if one.serves:
        out["serves"] = list(one.serves)
    return out


def dump_document(records: Sequence[ModelRecord]) -> dict[str, Any]:
    """A knowledge document holding ``records``."""
    return {
        "schema_version": SCHEMA_VERSION,
        "models": [dump_record(one) for one in records],
    }
