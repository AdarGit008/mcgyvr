"""The online half of the model knowledge: the Hugging Face Hub and the boards.

Owner, 2026-10-07: "Online when a network is available: Hugging Face Hub API
(sizes, quants, architecture incl. MoE/MTP) plus public leaderboards
(benchmarks). Every number records its source and date. Offline falls back to
the shipped catalog."

* :class:`HubLookup` is the :class:`mcgyvr.knowledge.store.Lookup` the store
  names. Asked for a repository, it reads the Hub's model API for the files,
  their bytes and sha256 at the repository's revision, then each GGUF file's
  **header over HTTP Range** (never a weight), and answers one record per
  single-file quantisation. The header row it read is kept
  (:meth:`HubLookup.header`): ``ggufscan``'s own row, which says the experts
  per block (an MoE) and the multi-token-prediction head (MTP), so an online
  pick is sized by the same law as a file on a rig.
* :func:`refresh` is what a command runs: for each model already known (the
  cache, then the shipped catalog), the Hub is asked whether its revision
  moved, a moved one is read again, the boards of the use case score it
  (:mod:`mcgyvr.knowledge.boards`), and the record is filed in the cache with
  :func:`mcgyvr.knowledge.store.write`. The offline read then finds it first.

The network is optional and never trusted to answer. ``--offline`` or
``HF_HUB_OFFLINE`` asks it nothing (:func:`offline_asked`). Every request has
a timeout and a byte ceiling. A failure is named, never raised past the
refresh: an HTTP refusal costs the one model or board it was for, and a
network that does not answer stops every lookup at once, so a black hole
costs one timeout and not one per model. Either way, the cache and the shipped
catalog answer.

Only model ids and file names are sent. Tests inject the transport (``get``);
the default one is :func:`urllib_get`, looked up when it is called so a test
can stand in for it.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import mcgyvr
from mcgyvr.knowledge import store
from mcgyvr.knowledge.record import (
    KnowledgeError,
    ModelRecord,
    Number,
    Weights,
    dump_record,
    parse_record,
)
from mcgyvr.serving import ggufscan, vramfit

#: The Hub every model lookup asks.
HUB = "https://huggingface.co"
#: How long, in seconds, one request waits for an answer before the network
#: is taken as not answering.
TIMEOUT_S = 20.0
#: The first slice of a GGUF file read for its header, and the most ever
#: read: the slice doubles until the tensor table parses, up to the ceiling.
#: A header is the metadata, the tokenizer's vocabulary and the tensor table;
#: a vocabulary of a few hundred thousand tokens is a few MiB.
HEADER_FIRST_BYTES = 1 << 20
HEADER_MAX_BYTES = 64 << 20
#: The most read of any other answer: an API document, a config.json, a
#: board. The largest board, SWE-bench's, was 4 MiB on 2026-10-07.
DOCUMENT_MAX_BYTES = 32 << 20
#: The bytes one cached element takes at an f16 cache, the width the
#: record's ``kv_bytes_per_token`` is stated at.
F16_BYTES = 2

#: The variable that asks for no network, as the Hub's own tools read it.
OFFLINE_ENV = "HF_HUB_OFFLINE"
_SAID_YES = frozenset({"1", "true", "yes", "on"})

#: What :attr:`Refreshed.mode` says.
ONLINE = "online"
OFFLINE = "offline"

#: A quantisation as GGUF file names spell it, at the end of the name.
_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)


class OnlineError(Exception):
    """A request was refused or its answer could not be read. The message
    names the URL and why."""


class NoNetworkError(OnlineError):
    """The network did not answer at all: no name, no route, a timeout. Every
    other lookup would fail the same way, so the refresh stops."""


class Get(Protocol):
    """A transport: ``url`` with ``headers``, answering at most ``limit`` bytes
    or raising :class:`OnlineError`."""

    def __call__(
        self, url: str, *, headers: Mapping[str, str], limit: int
    ) -> bytes: ...


def urllib_get(url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
    """The transport: one GET, with a timeout and a byte ceiling.

    At most ``limit`` bytes are read. An answer longer than that is refused
    and the rest is never read, so a server that ignores ``Range`` and starts
    sending a whole weights file costs one slice.
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"mcgyvr/{mcgyvr.__version__}", **headers},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body: bytes = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise OnlineError(f"{url} answered HTTP {exc.code}") from exc
    except (OSError, http.client.HTTPException, ValueError) as exc:
        # URLError and the socket timeout are both OSError: nothing answered.
        reason = getattr(exc, "reason", None) or exc
        raise NoNetworkError(f"{url} did not answer: {reason}") from exc
    if len(body) > limit:
        raise OnlineError(
            f"{url} answered more than {limit} bytes; the rest was not read"
        )
    return body


def _transport(get: Get | None) -> Get:
    return get if get is not None else urllib_get


def offline_asked(flag: bool) -> bool:
    """Whether the network is off: ``--offline``, or ``HF_HUB_OFFLINE`` said yes."""
    return flag or os.environ.get(OFFLINE_ENV, "").strip().lower() in _SAID_YES


def get_json(get: Get | None, url: str) -> Any:
    """``url``'s answer as JSON."""
    body = _transport(get)(url, headers={}, limit=DOCUMENT_MAX_BYTES)
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OnlineError(f"{url} answered no JSON: {exc}") from exc


def get_text(get: Get | None, url: str) -> str:
    """``url``'s answer as text."""
    body = _transport(get)(url, headers={}, limit=DOCUMENT_MAX_BYTES)
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OnlineError(f"{url} answered no UTF-8 text: {exc}") from exc


def api_url(repo: str) -> str:
    """The Hub's model API for ``repo``, with each file's bytes and sha256."""
    return f"{HUB}/api/models/{urllib.parse.quote(repo)}?blobs=true"


def resolve_url(repo: str, revision: str, file: str) -> str:
    """One file of ``repo`` at ``revision``."""
    return (
        f"{HUB}/{urllib.parse.quote(repo)}/resolve/"
        f"{urllib.parse.quote(revision)}/{urllib.parse.quote(file)}"
    )


@dataclass(frozen=True)
class HubFile:
    """One file of a repository, as the Hub API lists it."""

    name: str
    size: int
    sha256: str | None


@dataclass(frozen=True)
class HubRepo:
    """A repository at its current revision: its files and its base model."""

    id: str
    sha: str
    base_model: str | None
    files: tuple[HubFile, ...]


def repo_info(get: Get | None, repo: str) -> HubRepo:
    """What the Hub API says of ``repo`` now."""
    raw = get_json(get, api_url(repo))
    if not isinstance(raw, dict):
        raise OnlineError(f"{api_url(repo)} answered no model object")
    sha = raw.get("sha")
    if not isinstance(sha, str) or not sha:
        raise OnlineError(f"{api_url(repo)} names no revision")
    card = raw.get("cardData")
    base = card.get("base_model") if isinstance(card, dict) else None
    if isinstance(base, list):
        base = base[0] if len(base) == 1 else None
    files: list[HubFile] = []
    for sibling in raw.get("siblings") or ():
        if not isinstance(sibling, dict):
            continue
        name, size = sibling.get("rfilename"), sibling.get("size")
        if not isinstance(name, str) or not isinstance(size, int):
            continue
        lfs = sibling.get("lfs")
        sha256 = lfs.get("sha256") if isinstance(lfs, dict) else None
        files.append(HubFile(name, size, sha256 if isinstance(sha256, str) else None))
    return HubRepo(
        id=str(raw.get("id") or repo),
        sha=sha,
        base_model=base if isinstance(base, str) and base else None,
        files=tuple(files),
    )


def _scan_prefix(prefix: bytes) -> dict[str, Any]:
    """``ggufscan``'s row for a file that begins with ``prefix``."""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-header-") as folder:
        path = Path(folder) / "header.gguf"
        path.write_bytes(prefix)
        try:
            row: dict[str, Any] = ggufscan.scan(str(path))  # type: ignore[no-untyped-call]
        except Exception as exc:  # the scanner raises what struct raises
            return {"error": repr(exc)}
    return row


def read_header(
    get: Get | None, repo: str, revision: str, file: HubFile
) -> dict[str, Any]:
    """The header row of ``file``, read over HTTP Range and never past it.

    A slice that ends inside the header does not parse; the next slice is
    asked for and appended, each twice as long as what is held, up to
    :data:`HEADER_MAX_BYTES` or the file's size. No byte is asked for twice.
    The row then names the file and the size the Hub states, as a scan of the
    downloaded file would.
    """
    url = resolve_url(repo, revision, file.name)
    ceiling = min(HEADER_MAX_BYTES, file.size)
    held = b""
    want = min(HEADER_FIRST_BYTES, ceiling)
    while True:
        asked = want - len(held)
        held += _transport(get)(
            url, headers={"Range": f"bytes={len(held)}-{want - 1}"}, limit=asked
        )
        row = _scan_prefix(held)
        if "error" not in row:
            row["file"] = file.name
            row["size_bytes"] = file.size
            return row
        if len(held) < want or want >= ceiling:
            raise OnlineError(
                f"{url}: no GGUF header parses in its first {len(held)} bytes "
                f"({row['error']})"
            )
        want = min(want * 2, ceiling)


def _context(
    get: Get | None, base: str | None, row: Mapping[str, Any], at: str, today: date
) -> Number:
    """The context a pick is priced at: the base model's config.json, as the
    shipped catalog states it, or the header's own when that does not answer."""
    if base is not None:
        try:
            info = repo_info(get, base)
            config = get_json(get, resolve_url(base, info.sha, "config.json"))
        except NoNetworkError:
            raise
        except OnlineError:
            config = None
        if isinstance(config, dict):
            text = config.get("text_config")
            value = config.get("max_position_embeddings")
            if value is None and isinstance(text, dict):
                value = text.get("max_position_embeddings")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return Number(
                    value,
                    "fact",
                    f"hub-config:{base}@{info.sha}/config.json#max_position_embeddings",
                    today,
                )
    n_ctx = row.get("n_ctx_train")
    if not isinstance(n_ctx, int) or n_ctx <= 0:
        raise OnlineError(f"{at}: the header states no context length")
    return Number(n_ctx, "fact", f"gguf-header-range:{at}", today)


def _record(
    get: Get | None,
    model_id: str,
    repo: HubRepo,
    file: HubFile,
    quant: str,
    row: Mapping[str, Any],
    engines: Sequence[str],
    today: date,
) -> ModelRecord:
    at = f"{repo.id}@{repo.sha}/{file.name}"
    header = f"gguf-header-range:{at}"
    kv = sum(
        (int(layer["k_elems"]) + int(layer["v_elems"])) * F16_BYTES
        for layer in row.get("kv_layers") or ()
    )
    try:
        recurrent = vramfit.rs_bytes(dict(row), n_seq_max=1)["total"]
    except (KeyError, TypeError, ValueError) as exc:
        raise OnlineError(f"{at}: the header prices no recurrent state: {exc}") from exc
    if file.sha256 is None:
        raise OnlineError(f"{at}: the Hub states no sha256 for it")
    built = ModelRecord(
        model_id=model_id,
        quant=quant,
        engines=tuple(engines),
        weights=Weights(
            repo=repo.id, revision=repo.sha, file=file.name, sha256=file.sha256
        ),
        size_bytes=Number(file.size, "fact", f"hub-api:{at}", today),
        context_length=_context(get, repo.base_model, row, at, today),
        kv_bytes_per_token=Number(kv, "fact", header, today),
        recurrent_bytes_per_slot=Number(recurrent, "fact", header, today),
        scores=(),
    )
    # Through the same reader the cache is read with, so a record that says
    # less than a record must is refused here, by name.
    try:
        return parse_record(dump_record(built), at, shipped=False)
    except KnowledgeError as exc:
        raise OnlineError(str(exc)) from exc


def quant_of(name: str) -> str | None:
    """The quantisation a GGUF file name spells, upper case, or None."""
    matched = _QUANT.search(name)
    return matched[1].upper() if matched else None


@dataclass
class HubLookup:
    """The Hub as a :class:`mcgyvr.knowledge.store.Lookup`.

    Called with a model id, it reads the repository that holds its GGUF files:
    ``weights_repo[model_id]`` when given, else the id itself. A repository
    whose model card names one base model answers records of that base model.
    ``quants``, when given, are the only quantisations read. ``engines`` are
    what serves the records it answers.

    What it read is kept: :attr:`headers` (each file's header row) and
    :attr:`skipped` (each file or repository it answered no record for, and
    why).
    """

    get: Get | None = None
    today: date = field(default_factory=date.today)
    quants: Collection[str] | None = None
    weights_repo: Mapping[str, str] = field(default_factory=dict)
    engines: Sequence[str] = ("llama.cpp",)
    headers: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, model_id: str) -> tuple[ModelRecord, ...]:
        repo = repo_info(self.get, self.weights_repo.get(model_id, model_id))
        named = model_id if model_id != repo.id else (repo.base_model or repo.id)
        wanted = {q.upper() for q in self.quants} if self.quants is not None else None
        answered: list[ModelRecord] = []
        for file in repo.files:
            if not file.name.lower().endswith(".gguf"):
                continue
            where = f"{repo.id}/{file.name}"
            if "mmproj" in file.name.lower():
                self.skipped.append((where, "a vision projector, not a model"))
                continue
            if _SPLIT.search(file.name):
                self.skipped.append(
                    (where, "split across files; a record names one file")
                )
                continue
            quant = quant_of(file.name)
            if quant is None:
                self.skipped.append((where, "its name spells no quantisation"))
                continue
            if wanted is not None and quant not in wanted:
                continue
            try:
                row = read_header(self.get, repo.id, repo.sha, file)
                one = _record(
                    self.get, named, repo, file, quant, row, self.engines, self.today
                )
            except NoNetworkError:
                raise
            except OnlineError as exc:
                self.skipped.append((where, str(exc)))
                continue
            self.headers[(repo.id, repo.sha, file.name)] = row
            answered.append(one)
        return tuple(answered)

    def header(self, one: ModelRecord) -> dict[str, Any] | None:
        """The header row this lookup read for ``one``'s file, if it read one."""
        if one.weights is None:
            return None
        weights = one.weights
        return self.headers.get((weights.repo, weights.revision, weights.file))


@dataclass(frozen=True)
class Refreshed:
    """What a refresh did: ``mode`` (:data:`ONLINE` or :data:`OFFLINE`), the
    cache files it wrote, and each thing it could not read, with why."""

    mode: str
    written: tuple[Path, ...] = ()
    failed: tuple[tuple[str, str], ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "written": [str(path) for path in self.written],
            "failed": [{"what": what, "why": why} for what, why in self.failed],
        }


def _again(get: Get | None, one: ModelRecord, today: date) -> ModelRecord:
    """``one`` as the Hub has it now: unchanged when its revision has not
    moved, read again when it has."""
    assert one.weights is not None
    repo = repo_info(get, one.weights.repo)
    if repo.sha == one.weights.revision:
        return one
    lookup = HubLookup(
        get=get,
        today=today,
        quants=(one.quant,),
        weights_repo={one.model_id: one.weights.repo},
        engines=one.engines,
    )
    answered = lookup(one.model_id)
    same_file = [
        r for r in answered if r.weights and r.weights.file == one.weights.file
    ]
    again = same_file or list(answered)
    if not again:
        why = "; ".join(f"{what}: {reason}" for what, reason in lookup.skipped)
        raise OnlineError(
            f"{one.weights.repo} moved to {repo.sha} and holds no {one.quant} file "
            f"that reads{': ' + why if why else ''}"
        )
    return replace(again[0], model_id=one.model_id, scores=one.scores)


def refresh(
    known: Sequence[ModelRecord],
    *,
    use_case: str | None,
    offline: bool,
    get: Get | None = None,
    today: date | None = None,
) -> Refreshed:
    """Ask the Hub and the use case's boards about every known model, and file
    what was read in the cache.

    Asked offline (:func:`offline_asked`), nothing is asked and nothing is
    written. Online, each model whose weights file is known is asked for at
    its repository; the boards of ``use_case`` are read once each and score
    every model they list. A model or board that cannot be read is named in
    :attr:`Refreshed.failed`; a network that does not answer stops the refresh
    there, named the same way.
    """
    from mcgyvr.knowledge import boards

    if offline_asked(offline):
        return Refreshed(mode=OFFLINE)
    day = today or date.today()
    written: list[Path] = []
    failed: list[tuple[str, str]] = []
    try:
        read: dict[str, tuple[boards.Row, ...]] = {}
        for board in boards.boards_for(use_case):
            try:
                read[board.id] = boards.read(board, get=get, today=day)
            except NoNetworkError:
                raise
            except OnlineError as exc:
                failed.append((f"board {board.id}", str(exc)))
        for one in dict.fromkeys(known):
            what = f"{one.model_id} {one.quant}"
            if one.weights is None:
                failed.append((what, "names no weights file to look up"))
                continue
            try:
                now = _again(get, one, day)
            except NoNetworkError:
                raise
            except OnlineError as exc:
                failed.append((what, str(exc)))
                continue
            try:
                written.append(store.write(boards.scored(now, read, today=day)))
            except (KnowledgeError, OSError) as exc:
                failed.append((what, f"not filed in the cache: {exc}"))
    except NoNetworkError as exc:
        failed.append(
            (
                "network",
                f"{exc}; nothing more was asked, and the cache and the shipped "
                f"catalog answer",
            )
        )
    return Refreshed(mode=ONLINE, written=tuple(written), failed=tuple(failed))
