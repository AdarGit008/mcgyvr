"""Model candidates for a use case, read from the Hugging Face Hub and nothing else.

`candidates` answers the records a use case (`USE_CASES`: code, chat, agent)
may be served by, and says which of three places answered: the Hub, asked now
(`LIVE`); the cache an earlier Hub read left under ``$MCGYVR_HOME/knowledge``
(`store.CACHE`); or the catalog the package ships (`store.SHIPPED`). The Hub is
asked first. When it cannot be (``HF_HUB_OFFLINE`` says so, the network does
not answer, its search answers nothing usable), the cache and the shipped
catalog answer, merged as `store.offline` merges them, and the answer is
`CACHE` when any of its records came from the cache.

How the Hub's answer is found and ranked. These rules are the product's:

1. **List.** One search of the Hub's model API per use case: GGUF
   repositories (``filter=gguf``) sorted by the Hub's ``downloads``, which is
   its 30-day count, one page of `LIST_LIMIT`. Code searches the ids that
   hold ``code``; chat and agent search every GGUF repository.
2. **Classify,** from the Hub's own metadata, never from a leaderboard:
   - *chat-capable*: the pipeline is text-generation or image-text-to-text, or
     the Hub states none, and the repository states a chat template (or the Hub
     tags it ``conversational``);
   - *code*: chat-capable, and the repository or its base model names code
     (`names_code`: a word that begins with ``code`` or ends in ``coder``) or
     the Hub tags it ``code``;
   - *chat*: chat-capable and not code;
   - *agent*: chat, and its chat template handles ``tools``, or the Hub tags it
     for tool or function calling. A chat model whose template the Hub does not
     show anywhere is chat only.
   The search shows most templates; a repository it shows none for is looked up
   when the template could still make it fit the use case.
3. **Rank** by downloads, then likes, then id. A base model is offered once,
   from its most downloaded repository that qualifies (the base model is the
   one the Hub's ``base_model:quantized:`` tag names, else the repository
   itself).
4. **Pick one file** per repository: the first quantisation of `QUANTS` it
   holds as a single GGUF file (no ``-0000n-of-0000m`` split, no vision
   projector) for which the Hub states an LFS sha256, no larger than the
   roomiest card. A file the Hub states no sha256 for is never offered: weights
   may come from any repository, so the Hub's own hash is what the download is
   held to.
5. **Read its header** over HTTP Range (`serving.ggufscan`, never a weight):
   the context length, every caching layer's width, the recurrent state, the
   experts and an MTP head. The row is filed with `geometry.write` and read
   back from there next time, so a file is read once.

At most `MAX_LOOKUPS` repositories are looked up and `MAX_RECORDS` records
answered per use case. Every record is filed in the cache with `store.write`,
which is what answers next time the Hub cannot be asked.

Every number carries its source and day: the file's bytes from the model API
(``hub-api:<repo>@<revision>/<file>``), the context, KV and recurrent figures
from its header (``gguf-header-range:...``), and downloads and likes from the
search URL that listed it (``hub-search:<url>``).

All network reads go through `fetch`, one GET with a timeout and a byte
ceiling, so a test stands a recorded answer where it stands.
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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import mcgyvr
from mcgyvr.knowledge import geometry, store
from mcgyvr.knowledge.record import (
    KnowledgeError,
    ModelRecord,
    Number,
    Weights,
    dump_record,
    parse_record,
)
from mcgyvr.serving import fetchlist, ggufscan, vramfit

#: The use cases the Hub is asked about, by the task catalog's names.
USE_CASES: tuple[str, ...] = ("code", "chat", "agent")
CODE, CHAT, AGENT = USE_CASES
#: The answer's origin when the Hub was asked now; the other two are the store's.
LIVE = "live"

#: One page of the search, the most repositories a use case is ranked among.
LIST_LIMIT = 100
#: The most repositories looked up (their files and hashes) per use case.
MAX_LOOKUPS = 24
#: The most records answered per use case.
MAX_RECORDS = 8
#: The quantisations a file is picked at, in order of preference.
QUANTS: tuple[str, ...] = (
    "Q4_K_M",
    "Q4_K_S",
    "IQ4_XS",
    "Q4_0",
    "MXFP4",
    "Q5_K_M",
    "Q6_K",
    "Q8_0",
)
#: The pipelines a chat model is listed under, None being a repository the Hub
#: states no pipeline for; a GGUF of a vision-language model serves text
#: through llama.cpp all the same.
CHAT_PIPELINES = frozenset({"text-generation", "image-text-to-text", None})
#: Hub tags that say a model calls tools.
TOOL_TAGS = frozenset({"tool-use", "tool-call", "tool-calling", "function-calling"})
#: A template that stands for one the search did not show, at its most: one that
#: handles tools.
_UNSEEN_TEMPLATE = "tools"
#: The engines a GGUF record is served by.
ENGINES: tuple[str, ...] = ("llama.cpp",)
#: The bytes one cached element takes at an f16 cache, the width a record's
#: `kv_bytes_per_token` is stated at, as the shipped catalog states it.
F16_BYTES = 2

#: Seconds one request waits for an answer before the network is taken as gone.
TIMEOUT_S = 20.0
#: The first slice of a GGUF read for its header, and the most ever read: the
#: slice doubles until the tensor table parses. A header is the metadata, the
#: tokenizer's vocabulary and the tensor table, a few MiB at most.
HEADER_FIRST_BYTES = 1 << 20
HEADER_MAX_BYTES = 64 << 20
#: The most read of any API answer.
DOCUMENT_MAX_BYTES = 32 << 20

#: The variable that asks for no network, as the Hub's own tools read it.
OFFLINE_ENV = "HF_HUB_OFFLINE"
_SAID_YES = frozenset({"1", "true", "yes", "on"})

#: A quantisation as GGUF file names spell it, at the end of the name.
_QUANT = re.compile(
    r"[-_.]((?:I?Q\d+(?:_[A-Z0-9]+)*)|BF16|FP16|F16|F32|MXFP4(?:_MOE)?)\.gguf$",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"-\d{5}-of-\d{5}\.gguf$", re.IGNORECASE)
_BASE_QUANTIZED = "base_model:quantized:"
_BASE = "base_model:"


class HubError(Exception):
    """A request was refused or its answer could not be read; the message names
    the URL and why."""


class NoNetworkError(HubError):
    """The network did not answer at all, so nothing more is asked."""


def fetch(url: str, *, headers: Mapping[str, str], limit: int) -> bytes:
    """One GET of `url` with `headers`, answering at most `limit` bytes.

    The one place this module reaches the network. An HTTP refusal is a
    `HubError`; no answer at all (no name, no route, a timeout) is a
    `NoNetworkError`. An answer longer than `limit` is refused and the rest is
    never read, so a server that ignores ``Range`` costs one slice.
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
        raise HubError(f"{url} answered HTTP {exc.code}") from exc
    except (OSError, http.client.HTTPException, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise NoNetworkError(f"{url} did not answer: {reason}") from exc
    if len(body) > limit:
        raise HubError(f"{url} answered more than {limit} bytes; the rest was not read")
    return body


def offline_asked() -> bool:
    """Whether ``HF_HUB_OFFLINE`` says the Hub is not to be asked."""
    return os.environ.get(OFFLINE_ENV, "").strip().lower() in _SAID_YES


def _json(url: str) -> Any:
    body = fetch(url, headers={}, limit=DOCUMENT_MAX_BYTES)
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HubError(f"{url} answered no JSON: {exc}") from exc


def search_url(use_case: str, hub: str = fetchlist.HUB) -> str:
    """The Hub search a use case's candidates are listed from (rule 1)."""
    query: list[tuple[str, str]] = [
        ("filter", "gguf"),
        ("sort", "downloads"),
        ("direction", "-1"),
        ("limit", str(LIST_LIMIT)),
    ]
    if use_case == CODE:
        query.append(("search", "code"))
    query += [
        ("expand[]", what)
        for what in ("downloads", "likes", "tags", "pipeline_tag", "gguf")
    ]
    return f"{hub}/api/models?{urllib.parse.urlencode(query)}"


def repo_url(repo: str, hub: str = fetchlist.HUB) -> str:
    """The model API of `repo`, with each file's bytes and LFS sha256."""
    return f"{hub}/api/models/{urllib.parse.quote(repo)}?blobs=true"


def names_code(name: str) -> bool:
    """Whether an id names a coding model: a word of it (split at ``/``, ``-``,
    ``_`` and ``.``) begins with ``code`` (code, coder, codestral, codellama) or,
    trailing digits aside, ends in ``coder`` (starcoder2), encoder and decoder
    aside."""
    for word in re.split(r"[/\-_.]", name.lower()):
        stem = word.rstrip("0123456789")
        if word.startswith("code"):
            return True
        if stem.endswith("coder") and stem not in ("encoder", "decoder"):
            return True
    return False


def base_model(repo: str, tags: Iterable[str]) -> str:
    """The model a repository is a quantisation of, as its Hub tags name it, or
    the repository itself when they name none."""
    tags = tuple(tags)
    for tag in tags:
        if tag.startswith(_BASE_QUANTIZED):
            return tag[len(_BASE_QUANTIZED) :]
    for tag in tags:
        rest = tag[len(_BASE) :] if tag.startswith(_BASE) else ""
        if "/" in rest and ":" not in rest:
            return rest
    return repo


def use_cases_of(
    repo: str,
    model_id: str,
    *,
    tags: Iterable[str],
    pipeline_tag: str | None,
    chat_template: str | None,
) -> tuple[str, ...]:
    """The use cases a repository is a candidate for, by rule 2 of this module."""
    tags = frozenset(tags)
    chat_capable = pipeline_tag in CHAT_PIPELINES and (
        bool(chat_template) or "conversational" in tags
    )
    if not chat_capable:
        return ()
    if names_code(repo) or names_code(model_id) or "code" in tags:
        return (CODE,)
    tools = "tools" in (chat_template or "") or bool(tags & TOOL_TAGS)
    return (CHAT, AGENT) if tools else (CHAT,)


@dataclass(frozen=True)
class Listed:
    """One repository as the search listed it."""

    id: str
    model_id: str
    downloads: int
    likes: int
    tags: tuple[str, ...]
    pipeline_tag: str | None
    chat_template: str | None

    def may_serve(self, use_case: str) -> bool:
        """Whether this repository could be a candidate for `use_case` once looked
        up: by what the search shows, a template it did not show standing for
        one that handles tools."""
        return use_case in use_cases_of(
            self.id,
            self.model_id,
            tags=self.tags,
            pipeline_tag=self.pipeline_tag,
            chat_template=self.chat_template or _UNSEEN_TEMPLATE,
        )


def _count(raw: Any) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else 0


def _gguf(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    held = raw.get("gguf")
    return held if isinstance(held, dict) else {}


def _template(gguf: Mapping[str, Any]) -> str | None:
    held = gguf.get("chat_template")
    return held if isinstance(held, str) and held else None


def listed(raw: Any) -> tuple[Listed, ...]:
    """The search's answer read into `Listed` rows, in the order it gave them;
    a row that names no repository is left out."""
    if not isinstance(raw, list):
        raise HubError("the search answered no list of models")
    rows: list[Listed] = []
    for one in raw:
        if not isinstance(one, dict) or not isinstance(one.get("id"), str):
            continue
        tags = tuple(t for t in one.get("tags") or () if isinstance(t, str))
        pipeline = one.get("pipeline_tag")
        rows.append(
            Listed(
                id=one["id"],
                model_id=base_model(one["id"], tags),
                downloads=_count(one.get("downloads")),
                likes=_count(one.get("likes")),
                tags=tags,
                pipeline_tag=pipeline if isinstance(pipeline, str) else None,
                chat_template=_template(_gguf(one)),
            )
        )
    return tuple(rows)


def rank(rows: Iterable[Listed]) -> tuple[Listed, ...]:
    """Rule 3's order: by downloads, then likes, then id. A base model is kept to
    its first qualifying repository as the records are built."""
    return tuple(sorted(rows, key=lambda one: (-one.downloads, -one.likes, one.id)))


@dataclass(frozen=True)
class HubFile:
    """One file of a repository as the model API lists it."""

    name: str
    size: int
    sha256: str | None


@dataclass(frozen=True)
class HubRepo:
    """A repository at the revision the model API answered for."""

    id: str
    sha: str
    files: tuple[HubFile, ...]
    tags: tuple[str, ...]
    chat_template: str | None


def repo_info(repo: str, hub: str = fetchlist.HUB) -> HubRepo:
    """What the model API says of `repo` now: its revision, its files with their
    bytes and LFS sha256, its tags and its chat template."""
    url = repo_url(repo, hub)
    raw = _json(url)
    if not isinstance(raw, dict):
        raise HubError(f"{url} answered no model object")
    sha = raw.get("sha")
    if not isinstance(sha, str) or not sha:
        raise HubError(f"{url} names no revision")
    files: list[HubFile] = []
    for sibling in raw.get("siblings") or ():
        if not isinstance(sibling, dict):
            continue
        name, size = sibling.get("rfilename"), _count(sibling.get("size"))
        if not isinstance(name, str) or not size:
            continue
        lfs = sibling.get("lfs")
        sha256 = lfs.get("sha256") if isinstance(lfs, dict) else None
        files.append(HubFile(name, size, sha256 if isinstance(sha256, str) else None))
    return HubRepo(
        id=str(raw.get("id") or repo),
        sha=sha,
        files=tuple(files),
        tags=tuple(t for t in raw.get("tags") or () if isinstance(t, str)),
        chat_template=_template(_gguf(raw)),
    )


def quant_of(name: str) -> str | None:
    """The quantisation a GGUF file name spells, upper case, or None."""
    matched = _QUANT.search(name)
    return matched[1].upper() if matched else None


def pick_file(
    files: Sequence[HubFile], max_bytes: int | None
) -> tuple[HubFile, str] | None:
    """Rule 4: the file to offer and its quantisation, or None."""
    for quant in QUANTS:
        for one in sorted(files, key=lambda f: f.name):
            name = one.name.lower()
            if (
                not name.endswith(".gguf")
                or "mmproj" in name
                or _SPLIT.search(name)
                or quant_of(one.name) != quant
                or one.sha256 is None
                or (max_bytes is not None and one.size > max_bytes)
            ):
                continue
            return one, quant
    return None


def _scan_prefix(prefix: bytes) -> dict[str, Any]:
    """`ggufscan`'s row for a file that begins with `prefix`."""
    with tempfile.TemporaryDirectory(prefix="mcgyvr-header-") as folder:
        path = Path(folder) / "header.gguf"
        path.write_bytes(prefix)
        try:
            row: dict[str, Any] = ggufscan.scan(str(path))  # type: ignore[no-untyped-call]
        except Exception as exc:  # the scanner raises what struct raises
            return {"error": repr(exc)}
    return row


def read_header(
    repo: str, revision: str, file: HubFile, hub: str = fetchlist.HUB
) -> dict[str, Any]:
    """The header row of `file`, read over HTTP Range and never past it.

    A slice that ends inside the header does not parse; the next slice is asked
    for and appended, each twice as long as what is held, up to
    `HEADER_MAX_BYTES` or the file's size, and no byte is asked for twice. The
    row then names the file and the size the Hub states, as a scan of the
    downloaded file would.
    """
    url = fetchlist.url(
        fetchlist.Want(repo, revision, file.name, file.sha256 or "", file.size, "-"),
        hub,
    )
    ceiling = min(HEADER_MAX_BYTES, file.size)
    held = b""
    want = min(HEADER_FIRST_BYTES, ceiling)
    while True:
        asked = want - len(held)
        held += fetch(
            url, headers={"Range": f"bytes={len(held)}-{want - 1}"}, limit=asked
        )
        row = _scan_prefix(held)
        if "error" not in row:
            row["file"] = file.name
            row["size_bytes"] = file.size
            return row
        if len(held) < want or want >= ceiling:
            raise HubError(
                f"{url}: no GGUF header parses in its first {len(held)} bytes "
                f"({row['error']})"
            )
        want = min(want * 2, ceiling)


def _kv_bytes_per_token(row: Mapping[str, Any]) -> int:
    """The bytes one token of context takes over every caching layer of a header
    row at an f16 cache (`F16_BYTES` an element), 0 when the row states none."""
    total = 0
    for layer in row.get("kv_layers") or ():
        k = layer.get("k_elems") if isinstance(layer, dict) else None
        v = layer.get("v_elems") if isinstance(layer, dict) else None
        if type(k) is not int or type(v) is not int:
            return 0
        total += (k + v) * F16_BYTES
    return total


def build_record(
    one: Listed,
    repo: HubRepo,
    file: HubFile,
    quant: str,
    row: Mapping[str, Any],
    *,
    use_cases: Sequence[str],
    searched: str,
    today: date,
) -> ModelRecord:
    """The record of one file: its bytes and hash from the model API, its
    context, KV and recurrent figures from its header, the downloads and likes
    from the search, each with its source and `today`."""
    at = geometry.locator(repo.id, repo.sha, file.name)
    header = f"{geometry.SOURCE}:{at}"
    if file.sha256 is None:
        raise HubError(f"{at}: the Hub states no sha256 for it")
    kv = _kv_bytes_per_token(row)
    if not kv:
        raise HubError(f"{at}: the header prices no KV cache")
    try:
        recurrent = vramfit.rs_bytes(dict(row), n_seq_max=1)["total"]
    except (KeyError, TypeError, ValueError) as exc:
        raise HubError(f"{at}: the header prices no recurrent state: {exc}") from exc
    n_ctx = row.get("n_ctx_train")
    if not isinstance(n_ctx, int) or isinstance(n_ctx, bool) or n_ctx <= 0:
        raise HubError(f"{at}: the header states no context length")
    built = ModelRecord(
        model_id=one.model_id,
        quant=quant,
        engines=ENGINES,
        weights=Weights(
            repo=repo.id, revision=repo.sha, file=file.name, sha256=file.sha256
        ),
        size_bytes=Number(file.size, "fact", f"hub-api:{at}", today),
        context_length=Number(n_ctx, "fact", header, today),
        kv_bytes_per_token=Number(kv, "fact", header, today),
        recurrent_bytes_per_slot=Number(recurrent, "fact", header, today),
        scores=(),
        use_cases=tuple(use_cases),
        downloads=Number(one.downloads, "fact", f"hub-search:{searched}", today),
        likes=Number(one.likes, "fact", f"hub-search:{searched}", today),
    )
    # Through the reader the cache is read with, so a record that says less than
    # a record must is refused here, by name.
    try:
        return parse_record(dump_record(built), at, shipped=False)
    except KnowledgeError as exc:
        raise HubError(str(exc)) from exc


@dataclass(frozen=True)
class Answer:
    """The records a use case may be served by, in rank order, and where they
    came from: `LIVE`, `store.CACHE` or `store.SHIPPED`. `skipped` names each
    repository, file or cache write that answered nothing, with why."""

    use_case: str
    records: tuple[ModelRecord, ...]
    origin: str
    skipped: tuple[tuple[str, str], ...] = ()

    @property
    def read_at(self) -> date | None:
        """The oldest day any number of the answer was read."""
        days = [n.read_at for one in self.records for _name, n in one.numbers()]
        return min(days) if days else None


@dataclass
class _Live:
    """What one live read gathered: the records and what it passed over."""

    records: list[ModelRecord] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _header_row(
    repo: HubRepo, file: HubFile, hub: str, today: date, read: _Live
) -> dict[str, Any]:
    """The header row of a file: the geometry already filed for it, else read
    over Range and filed."""
    known = geometry.load().rows.get((repo.id, repo.sha, file.name))
    if known is not None:
        return dict(known.row)
    row = read_header(repo.id, repo.sha, file, hub)
    try:
        geometry.write(repo.id, repo.sha, file.name, row, today=today)
    except (KnowledgeError, OSError) as exc:
        read.skipped.append((f"{repo.id}/{file.name}", f"header not filed: {exc}"))
    return row


def _live(use_case: str, max_bytes: int | None, today: date) -> _Live:
    """Rules 1 to 5 against the Hub. Raises `HubError` (or `NoNetworkError`)
    when the search itself answers nothing usable; a repository that fails is
    passed over, and a network that stops answering part-way ends the read with
    what it had."""
    hub = fetchlist.endpoint(os.environ)
    searched = search_url(use_case, hub)
    read = _Live()
    lookups = 0
    answered: set[str] = set()
    for one in rank(listed(_json(searched))):
        if len(read.records) >= MAX_RECORDS or lookups >= MAX_LOOKUPS:
            break
        if one.model_id in answered or not one.may_serve(use_case):
            continue
        lookups += 1
        try:
            repo = repo_info(one.id, hub)
            uses = use_cases_of(
                repo.id,
                one.model_id,
                tags=repo.tags or one.tags,
                pipeline_tag=one.pipeline_tag,
                chat_template=repo.chat_template or one.chat_template,
            )
            if use_case not in uses:
                continue
            picked = pick_file(repo.files, max_bytes)
            if picked is None:
                read.skipped.append(
                    (
                        repo.id,
                        "no single GGUF file of a known quantisation with a "
                        "sha256 that fits the roomiest card",
                    )
                )
                continue
            file, quant = picked
            row = _header_row(repo, file, hub, today, read)
            read.records.append(
                build_record(
                    one,
                    repo,
                    file,
                    quant,
                    row,
                    use_cases=uses,
                    searched=searched,
                    today=today,
                )
            )
            answered.add(one.model_id)
        except NoNetworkError as exc:
            # The network stopped answering part-way: what was read stands, and
            # nothing more is asked.
            read.skipped.append((one.id, f"{exc}; nothing more was asked"))
            break
        except HubError as exc:
            read.skipped.append((one.id, str(exc)))
    return read


def _filed(records: Iterable[ModelRecord], read: _Live) -> None:
    """File each record in the cache, naming a write that failed."""
    for one in records:
        try:
            store.write(one)
        except (KnowledgeError, OSError) as exc:
            read.skipped.append((f"{one.model_id} {one.quant}", f"not cached: {exc}"))


def known(use_case: str, skipped: Sequence[tuple[str, str]] = ()) -> Answer:
    """The answer without the Hub: the cache over the shipped catalog, as
    `store.offline` merges them, kept to the records of `use_case`."""
    merged = store.offline()
    held = [k for k in merged.known if use_case in k.record.use_cases]
    origin = (
        store.CACHE if any(k.origin == store.CACHE for k in held) else store.SHIPPED
    )
    return Answer(
        use_case=use_case,
        records=tuple(k.record for k in held),
        origin=origin,
        skipped=tuple(skipped)
        + tuple((str(path), why) for path, why in merged.skipped),
    )


def candidates(
    use_case: str, *, max_bytes: int | None = None, today: date | None = None
) -> Answer:
    """The records `use_case` may be served by: the Hub's, read now and filed in
    the cache, else `known`. `max_bytes` is the roomiest card's free VRAM, the
    most a file offered may weigh."""
    if use_case not in USE_CASES:
        raise KnowledgeError(
            f"{use_case!r} is not a use case the Hub is asked about "
            f"({', '.join(USE_CASES)})"
        )
    if offline_asked():
        return known(use_case, ((OFFLINE_ENV, "the Hub was not asked"),))
    try:
        read = _live(use_case, max_bytes, today or date.today())
    except (HubError, fetchlist.FetchListError) as exc:
        return known(use_case, (("hub", f"{exc}; the cache and catalog answer"),))
    if not read.records:
        read.skipped.append(
            ("hub", "it answered no record; the cache and catalog answer")
        )
        return known(use_case, read.skipped)
    _filed(read.records, read)
    return Answer(
        use_case=use_case,
        records=tuple(read.records),
        origin=LIVE,
        skipped=tuple(read.skipped),
    )
