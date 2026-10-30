"""Turn a usage profile and a set of rigs into a plan naming one placement.

`plan` measures each named host (or takes scans handed in already measured) and
places the profiles that are kinds of model (`PLACEMENT_PROFILES`: code, chat,
agent; `PROFILE_OF_USE_CASE` maps each use case onto one); every other profile
returns the bare rig measurements with no placement.

The candidates come from `load_catalog`, which asks `mcgyvr.knowledge.hub` for
the use case's models: the Hugging Face Hub read now, else the cache of an
earlier read, else the shipped catalog. The plan says which answered. Each
candidate is named by its rig, its engine, its weights (and quant) and its
speculative head, so no two share a name, and the placement names the host it
is for.

- `code` first discovers GGUF checkpoints in the model stores it is given and
  sizes their weights plus per-user cache against each rig's free VRAM and host
  RAM with `vramfit`, and takes the catalog when no local checkpoint fits. The
  surviving candidates are offered by those names to the decision model on the
  local endpoint when it answers, and the largest candidate wins when it does
  not.
- `chat` and `agent` are one unit: the biggest model that fits, with the most
  context that fits up to the model's own, and never under
  `MIN_CONTEXT_PER_USER` per user. A tie goes to the candidate the Hub ranks
  first.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr import availability, decision, estimate
from mcgyvr import scan as scan_module
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S, default_launcher
from mcgyvr.decision import Choice, ChoiceAnswer
from mcgyvr.detect import host_system
from mcgyvr.fleet import lock as fleet_lock
from mcgyvr.hubwire import FIGURE_ESTIMATE, USE_CASE_CATEGORY, shares_ram
from mcgyvr.knowledge import geometry as geometry_rows
from mcgyvr.knowledge import hub
from mcgyvr.knowledge import store as knowledge_store
from mcgyvr.knowledge.record import KnowledgeError, ModelRecord
from mcgyvr.local_pool import Endpoint, Protocol
from mcgyvr.runner import RunnerError
from mcgyvr.scan import (
    BYTES_PER_GB,
    Gpu,
    Reach,
    Scan,
    ScanFailed,
    ScannerMissing,
    Unreachable,
)
from mcgyvr.serving import (
    DEFAULT_PORT,
    DEFAULT_SPEC_DRAFT_N_MAX,
    DEFAULT_UBATCH,
    _free_vram_bytes,
    _roomiest_gpu,
    gatelib,
    vramfit,
)

#: Usage profiles the CLI accepts; only PLACEMENT_PROFILES get a placement.
PROFILES = (*hub.USE_CASES, "other")
#: The profiles that are use cases, each placed from the Hub's candidates for it.
PLACEMENT_PROFILES = hub.USE_CASES
#: The one placed as a ladder's rung, with local stores and the decision model.
PLACEMENT_PROFILE = hub.CODE
#: The kind of model each use case is recommended: `mcgyvr-code` climbs a ladder
#: of coding models and `code` serves one raw, so both are placed as `code`.
PROFILE_OF_USE_CASE: Mapping[str, str] = USE_CASE_CATEGORY
#: The least context a chat or agent unit serves each user.
MIN_CONTEXT_PER_USER = 8192

#: The tail appended to a quoted model-store directory to list the .gguf files
#: sitting directly in it; `gatelib` admits exactly the `find '<dir>'` command
#: shape this completes, which is what keeps discovery read-only on a rig.
_DISCOVER_SUFFIX = " -maxdepth 1 -name '*.gguf' -print"

#: The launch flags every llama.cpp candidate starts from: offload all layers,
#: turn flash attention on, and pin both the ubatch and the batch to
#: `DEFAULT_UBATCH` so the launch matches the geometry the fit check sized.
#: `_llamacpp_flags` layers `--model`, the MTP head and `--parallel` on top.
_LLAMACPP_FLAGS = {
    "-ngl": "99",
    "-fa": "on",
    "-ub": str(DEFAULT_UBATCH),
    "-b": str(DEFAULT_UBATCH),
}


class CatalogError(Exception):
    """The model catalog could not be read, so no catalog candidates exist."""


class RecommendError(Exception):
    """Planning failed: a path was refused, a header was unreadable, or nothing
    fitted any rig."""


@dataclass(frozen=True)
class Candidate:
    """One way to serve one model on one of the rigs that were scanned.

    `host` is the rig it was sized for and would run on, and `name` carries that
    rig with the engine, the weights and the head, so it is unique among one
    plan's candidates and is what the decision answers with. A discovered local
    checkpoint fills `checkpoint` and leaves `model_id` and `quant` empty, while
    a catalog entry does the reverse; `flags` is what the chosen engine should be
    launched with, and `wake` is true when the scan found no GPU on the rig at
    all.
    """

    name: str
    host: str
    description: str
    engine: str
    checkpoint: str | None
    model_id: str | None
    quant: str | None
    size_bytes: int
    context_length: int
    flags: Mapping[str, str]
    wake: bool
    #: The weight bytes one decoded token reads (`estimate.token_bytes`): the
    #: file for a dense model, less the experts a token skips for a mixture of
    #: experts whose geometry is known. None when nothing states it.
    token_bytes: int | None = None


def discover_command(directory: str) -> str:
    """The read-only `find` command listing the .gguf files directly inside `directory`.

    A directory with an embedded single quote is refused: quoting it would need an
    escape the gate library's `find '<dir>'` shape does not allow.
    """
    if "'" in directory:
        raise RecommendError(
            "a model-store directory with an embedded single quote cannot be "
            "read read-only"
        )
    if directory.startswith("-"):
        raise RecommendError(
            f"a model-store directory starting with '-' ({directory!r}) is read "
            "by find as an expression, not a folder; name it with ./ or a path"
        )
    return f"find '{directory}'{_DISCOVER_SUFFIX}"


def _flat(
    one: ModelRecord, rows: geometry_rows.Geometries | None = None
) -> dict[str, Any]:
    """A record flattened to the fields sizing needs — id, quantisation, file
    size, the bytes a decoded token reads (from its geometry when `rows` has
    one), context length, per-token KV bytes, per-sequence recurrent bytes and
    the engines that can serve it."""
    row = rows.of(one.weights) if rows is not None else None
    return {
        "model_id": one.model_id,
        "quant": one.quant,
        "size_bytes": one.size_bytes.value,
        "token_bytes": estimate.token_bytes(
            int(one.size_bytes.value), row.row if row is not None else None
        ),
        "context_length": one.context_length.value,
        "kv_bytes_per_token": one.kv_bytes_per_token.value,
        "recurrent_bytes_per_slot": one.recurrent_bytes_per_slot.value,
        "engines": list(one.engines),
    }


def load_catalog(
    use_case: str | None = None, *, max_bytes: int | None = None
) -> dict[str, Any]:
    """The candidates as a JSON-shaped dict of flattened records under `models`.

    With a use case, `hub.candidates` answers: the Hub read now, else the cache,
    else the shipped catalog, kept to that use case, with files no larger than
    `max_bytes`; `answered` says which (`live`, `cache` or `shipped`) and
    `read_at` the oldest day any of its numbers was read. With none, every model
    the cache and the shipped catalog know, offline. A `KnowledgeError` is
    re-raised as `CatalogError`.
    """
    try:
        if use_case is None:
            merged = knowledge_store.offline()
            records = merged.records
            answered = (
                knowledge_store.CACHE
                if any(k.origin == knowledge_store.CACHE for k in merged.known)
                else knowledge_store.SHIPPED
            )
            read_at = merged.oldest_read_at
        else:
            answer = hub.candidates(use_case, max_bytes=max_bytes)
            records, answered, read_at = answer.records, answer.origin, answer.read_at
        rows = geometry_rows.load()
    except KnowledgeError as exc:
        raise CatalogError(str(exc)) from exc
    return {
        "models": [_flat(one, rows) for one in records],
        "answered": answered,
        "read_at": read_at.isoformat() if read_at is not None else None,
    }


def _read_header(host: str, path: str) -> Mapping[str, Any]:
    """Read the GGUF header of `path` on `host` through the gate library's
    header reader.

    The reader prints a JSON list whose first element is the header object, so
    output that is not JSON, is empty, or whose first element is not an object
    raises `RecommendError`, as does a header reporting its own `error`.
    """
    try:
        sent = gatelib.header_read(scan_module.shipping_os(host), path)
    except ValueError as exc:
        raise RecommendError(str(exc)) from exc
    listing = (
        scan_module._ssh(host, sent.command, sent.stdin)
        if sent.stdin is not None
        else scan_module._ssh(host, sent.command)
    )
    try:
        rows = json.loads(listing)
    except json.JSONDecodeError as exc:
        raise RecommendError(
            f"the rig's header reader printed no JSON for {path}: {exc}"
        ) from exc
    if not isinstance(rows, list) or not rows:
        raise RecommendError(f"the rig's header reader reported no header for {path}")
    header = rows[0]
    if not isinstance(header, dict):
        raise RecommendError(
            f"the rig's header reader reported a non-object header for {path}"
        )
    if "error" in header:
        raise RecommendError(
            f"the rig's header reader refused {path}: {header['error']}"
        )
    return header


def _discover(host: str, directory: str) -> tuple[str, ...]:
    """The .gguf paths sitting directly in `directory` on `host`, blank lines dropped.

    A host whose ssh reader exits non-zero raises `ScannerMissing`, and discovery
    swallows that as an empty tuple: a rig without the scanner contributes no
    local candidates instead of failing the whole plan.
    """
    try:
        if scan_module.shipping_os(host) == gatelib.WINDOWS:
            sent = gatelib.windows_discover(directory)
            listing = scan_module._ssh(host, sent.command, sent.stdin)
        else:
            listing = scan_module._ssh(host, discover_command(directory))
    except ScannerMissing:
        return ()
    return tuple(
        line for line in (part.strip() for part in listing.splitlines()) if line
    )


def _scan_host(host: str) -> Scan:
    """Measure one rig over ssh and return its scan."""
    return scan_module.scan_over(Reach.ssh(host))


def _host_ram_bytes(scan: Scan) -> int | None:
    """Available host RAM in bytes, or `None` when the scan reported no available
    memory."""
    if scan.memory is None or scan.memory.available_gb is None:
        return None
    return int(scan.memory.available_gb * BYTES_PER_GB)


def _slot_bytes(header: Mapping[str, Any], users: int) -> int | None:
    """Cache bytes a checkpoint needs for `users` sequences at its full training
    context.

    The header's `n_ctx_train` is one sequence's context and the cache totals come
    from `vramfit`: KV bytes over that context across `users` sequences plus the
    recurrent state for the same count. A header without a positive integer
    `n_ctx_train`, or a geometry `vramfit` cannot size, yields `None`, which the
    caller reads as "does not fit".
    """
    n_ctx_train = header.get("n_ctx_train")
    if not isinstance(n_ctx_train, int) or n_ctx_train <= 0:
        return None
    geometry = dict(header)
    try:
        kv = vramfit.kv_bytes(
            geometry,
            n_ctx_train,
            n_seq_max=users,
            n_ubatch=DEFAULT_UBATCH,
        )
        rs = vramfit.rs_bytes(geometry, n_seq_max=users)
    except (KeyError, TypeError, ValueError):
        return None
    return kv["total"] + rs["total"]


def _fits(scan: Scan, header: Mapping[str, Any], users: int) -> bool:
    """Whether `header`'s weights plus `users` slots of cache fit this rig.

    Weights are charged to the roomiest card's free VRAM: a mixture-of-experts
    checkpoint whose blocks are placeable counts only its non-expert bytes there
    and must keep its expert bytes inside the host's available RAM (less what
    the card holds, when the card is a unified GPU sharing that RAM), while any
    other checkpoint charges its whole file size. A rig with no free VRAM, a
    header whose cache cannot be sized, or a missing RAM figure means no fit.
    """
    free = _free_vram_bytes(scan)
    if free <= 0:
        return False
    needed = (
        int(header.get("bytes_nonexpert") or 0)
        if header.get("placeable_blocks")
        else int(header.get("size_bytes") or 0)
    )
    slots = _slot_bytes(header, users)
    if slots is None:
        return False
    if needed + slots > free:
        return False
    if header.get("placeable_blocks"):
        expert_bytes = int(header.get("bytes_experts") or 0)
        ram = _host_ram_bytes(scan)
        if ram is not None and shares_ram(_roomiest_gpu(scan).kind):
            # A unified GPU's memory is the host's: what the card holds is not
            # also there for the experts.
            ram -= needed + slots
        if ram is None or expert_bytes > ram:
            return False
    return True


def _measured(scan: Scan) -> dict[str, Any]:
    """The scan trimmed to the hardware figures the plan document reports for a rig.

    Each of memory, bandwidth and disk is `None` when the scan did not measure it.
    """
    gpus = [
        {
            "index": gpu.index,
            "name": gpu.name,
            "kind": gpu.kind,
            "vram_total_mib": gpu.vram.total_mib,
            "vram_free_mib": gpu.vram.free_mib,
            "vram_figure": gpu.figure,
            "bandwidth_gbps": _said(_bandwidth(scan, gpu)),
        }
        for gpu in scan.gpus
    ]
    return {
        "gpus": gpus,
        "memory": (
            None
            if scan.memory is None
            else {
                "total_gb": scan.memory.total_gb,
                "available_gb": scan.memory.available_gb,
            }
        ),
        "bandwidth": (
            None
            if scan.bandwidth is None
            else {
                "measured_gbps": scan.bandwidth.measured_gbps,
                "how": scan.bandwidth.how,
            }
        ),
        "disk": (
            None
            if scan.disk is None
            else {"path": str(scan.disk.path), "free_gb": scan.disk.free_gb}
        ),
    }


def _token_bytes(entry: Mapping[str, Any]) -> int | None:
    value = entry.get("token_bytes")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _memory_mib(scan: Scan) -> int | None:
    return None if scan.memory is None else int(scan.memory.total_gb * 1024)


def _bandwidth(scan: Scan, gpu: Gpu) -> estimate.Figure | estimate.NoEstimate:
    """The memory bandwidth of a card's class (`data/hardware-classes.json`): an
    estimate for this card, since the card is only matched to the class."""
    found = estimate.match(
        gpu.name, vram_mib=gpu.vram.total_mib, memory_mib=_memory_mib(scan)
    )
    if isinstance(found, estimate.NoEstimate):
        return found
    return estimate.Figure(
        found.bandwidth_gbps,
        FIGURE_ESTIMATE,
        f"class {found.id} ({found.url})",
        verified=found.verified,
    )


def _said(figure: estimate.Figure | estimate.NoEstimate) -> dict[str, Any]:
    """A figure as the plan document states it: its value and what it is, or no
    value and why."""
    if isinstance(figure, estimate.NoEstimate):
        return {"value": None, "figure": None, "why": figure.why}
    return {
        "value": round(figure.value, 1),
        "figure": figure.figure,
        "basis": figure.basis,
        "verified": figure.verified,
    }


def _model_key(name: str) -> str:
    """A model name as readings are matched by it: its last path part, lower
    case, without ``.gguf``."""
    return name.rsplit("/", 1)[-1].strip().lower().removesuffix(".gguf")


def _reading(
    candidate: Candidate, readings: Mapping[tuple[str, str], float]
) -> float | None:
    """The slowest decode the live fleet measured for this candidate's model at
    its host: a unit's model names it by repo (``org/Model``), by repo and quant
    (``Model-Q4_K_M``) or by file; hosts are matched as `fleet.lock.host_key`
    keys them."""
    names = set()
    if candidate.model_id:
        names.add(_model_key(candidate.model_id))
        if candidate.quant:
            names.add(f"{_model_key(candidate.model_id)}-{candidate.quant.lower()}")
    if candidate.checkpoint:
        names.add(_model_key(candidate.checkpoint))
    host = fleet_lock.host_key(candidate.host)
    found = [
        value
        for (at, model), value in readings.items()
        if fleet_lock.host_key(at) == host and _model_key(model) in names
    ]
    return min(found) if found else None


def _decode(
    candidate: Candidate, scan: Scan, readings: Mapping[tuple[str, str], float]
) -> estimate.Figure | estimate.NoEstimate:
    """The placement's decode speed: the reading the live fleet holds for this
    model at this host, else the estimate for the roomiest card's class."""
    reading = _reading(candidate, readings)
    if not scan.gpus:
        if reading is not None:
            return estimate.prefer(
                reading, estimate.NoEstimate(""), where=candidate.host
            )
        return estimate.NoEstimate(f"{candidate.host}: no card, so no estimate")
    gpu = _roomiest_gpu(scan)
    return estimate.device_decode(
        gpu.name,
        model_bytes=candidate.token_bytes or candidate.size_bytes,
        quant=candidate.quant,
        vram_mib=gpu.vram.total_mib,
        memory_mib=_memory_mib(scan),
        reading=reading,
        where=candidate.host,
    )


def _llamacpp_flags(*, checkpoint: str | None, mtp: bool, users: int) -> dict[str, str]:
    """The llama.cpp launch flags: the shared baseline plus this candidate's extras.

    `--model` names a local checkpoint when there is one, `mtp` turns on the
    checkpoint's grafted speculative head with its draft-token cap, and more than
    one user sets `--parallel`.
    """
    flags = dict(_LLAMACPP_FLAGS)
    if checkpoint is not None:
        flags["--model"] = checkpoint
    if mtp:
        flags["--spec-type"] = "draft-mtp"
        flags["--spec-draft-n-max"] = str(DEFAULT_SPEC_DRAFT_N_MAX)
    if users > 1:
        flags["--parallel"] = str(users)
    return flags


def _has_multi_token_prediction(header: Mapping[str, Any]) -> bool:
    return bool(header.get("nextn_blocks"))


def _local_candidates(
    host: str, scan: Scan, header: Mapping[str, Any], users: int
) -> tuple[Candidate, ...]:
    """Candidates for one discovered checkpoint that already fitted on `host`.

    A checkpoint carrying a grafted MTP head yields two candidates, one serving
    that head and one without it, so the decision can weigh speculative decode
    against the plain path; a checkpoint without one yields only the plain path.
    A path names one file on one rig, so the rig, the path and the head name
    each candidate.
    """
    checkpoint = str(header.get("file") or "")
    size_bytes = int(header.get("size_bytes") or 0)
    wake = not scan.gpus
    variants = [False, True] if _has_multi_token_prediction(header) else [False]
    candidates: list[Candidate] = []
    for mtp in variants:
        head = " with its grafted MTP head" if mtp else ""
        candidates.append(
            Candidate(
                name=f"{host}: llama.cpp {checkpoint}{' + MTP' if mtp else ''}",
                host=host,
                description=f"on {host}, llama.cpp serving {checkpoint}{head}",
                engine="llama.cpp",
                checkpoint=checkpoint,
                model_id=None,
                quant=hub.quant_of(checkpoint),
                size_bytes=size_bytes,
                context_length=int(header["n_ctx_train"]),
                flags=_llamacpp_flags(checkpoint=checkpoint, mtp=mtp, users=users),
                wake=wake,
                token_bytes=estimate.token_bytes(size_bytes, header),
            )
        )
    return tuple(candidates)


def _catalog_slot_bytes(entry: Mapping[str, Any], users: int) -> int | None:
    """Cache bytes a catalog entry needs for `users` sequences, or `None` if unsizable.

    The entry's context length is split across the sequences with
    `vramfit.context_per_sequence`, and the total is those cells times the user
    count times the per-token KV bytes, plus the per-sequence recurrent bytes. A
    context or KV figure that is not a positive integer, or a recurrent figure
    that is not a non-negative integer, makes the entry unsizable rather than
    cheap.
    """
    ctx = entry.get("context_length")
    kv_per_token = entry.get("kv_bytes_per_token")
    recurrent = entry.get("recurrent_bytes_per_slot", 0)
    if (
        not isinstance(ctx, int)
        or isinstance(ctx, bool)
        or ctx <= 0
        or not isinstance(kv_per_token, int)
        or isinstance(kv_per_token, bool)
        or kv_per_token <= 0
        or not isinstance(recurrent, int)
        or isinstance(recurrent, bool)
        or recurrent < 0
    ):
        return None
    try:
        cells = vramfit.context_per_sequence(ctx, users)
    except ValueError:
        return None
    return cells * users * kv_per_token + recurrent * users


def _catalog_fits(scan: Scan, entry: Mapping[str, Any], users: int) -> bool:
    """Whether a catalog entry's file size plus its cache fits a rig's free VRAM."""
    free = _free_vram_bytes(scan)
    if free <= 0:
        return False
    size_bytes = int(entry.get("size_bytes") or 0)
    slots = _catalog_slot_bytes(entry, users)
    if slots is None:
        return False
    return size_bytes + slots <= free


def _catalog_candidates(
    host: str, scan: Scan, catalog: Mapping[str, Any], users: int
) -> tuple[Candidate, ...]:
    """One candidate per engine that can serve a catalog entry fitting `host`.

    The rig, the engine, the model id and the quant name each candidate; the
    catalog holds one model at one quant once, so no two names are the same.

    Entries that do not fit, and entries that are not objects, are skipped, and
    `wake` follows whether the scan found any GPU on the rig.
    """
    wake = not scan.gpus
    candidates: list[Candidate] = []
    for entry in catalog.get("models", ()):
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("model_id") or "")
        quant = str(entry.get("quant") or "")
        size_bytes = int(entry.get("size_bytes") or 0)
        if not _catalog_fits(scan, entry, users):
            continue
        for engine in entry.get("engines") or ():
            if engine == "llama.cpp":
                flags = _llamacpp_flags(checkpoint=None, mtp=False, users=users)
            else:
                # Only llama.cpp has a flag spelling this module knows, so a
                # catalog entry naming another engine is planned with no flags
                # rather than with another engine's flags guessed at.
                flags = {}
            candidates.append(
                Candidate(
                    name=f"{host}: {engine} {model_id} {quant}",
                    host=host,
                    description=f"on {host}, {engine} serving {model_id} ({quant})",
                    engine=str(engine),
                    checkpoint=None,
                    model_id=model_id,
                    quant=quant,
                    size_bytes=size_bytes,
                    context_length=int(entry["context_length"]),
                    flags=flags,
                    wake=wake,
                    token_bytes=_token_bytes(entry),
                )
            )
    return tuple(candidates)


def _most_context(scan: Scan, entry: Mapping[str, Any], users: int) -> int | None:
    """The most context, over `users` sequences, a catalog entry fits on this rig
    beside its weights and recurrent state, or None when it cannot be sized or
    fits less than `MIN_CONTEXT_PER_USER` per user.

    Each user gets the same whole multiple of 256 cells, no more than the
    entry's own context, so `_catalog_slot_bytes` prices the answer exactly.
    """
    if _catalog_slot_bytes(entry, users) is None:
        return None
    room = (
        _free_vram_bytes(scan)
        - int(entry.get("size_bytes") or 0)
        - int(entry.get("recurrent_bytes_per_slot", 0)) * users
    )
    per_user = min(
        room // (int(entry["kv_bytes_per_token"]) * users),
        int(entry["context_length"]),
    )
    per_user -= per_user % 256
    if per_user < MIN_CONTEXT_PER_USER:
        return None
    return per_user * users


def _one_unit_candidates(
    host: str, scan: Scan, catalog: Mapping[str, Any], users: int
) -> tuple[Candidate, ...]:
    """The chat and agent candidates on one rig: each catalog entry priced at the
    most context it fits there (`_most_context`), then made candidates as
    `_catalog_candidates` makes them; an entry that fits too little is left out."""
    sized: list[dict[str, Any]] = []
    for entry in catalog.get("models", ()):
        if not isinstance(entry, dict):
            continue
        context = _most_context(scan, entry, users)
        if context is not None:
            sized.append({**entry, "context_length": context})
    return _catalog_candidates(host, scan, {"models": sized}, users)


def _decision_endpoint() -> Endpoint:
    """The local OpenAI-protocol endpoint a decision model is expected to answer on."""
    return Endpoint(
        source="recommend",
        base_url=f"http://127.0.0.1:{DEFAULT_PORT}",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def _deterministic_pick(candidates: tuple[Candidate, ...]) -> Candidate:
    """The pick made without a model: the candidate with the largest weights."""
    return max(candidates, key=lambda candidate: candidate.size_bytes)


def _distinct(candidates: Sequence[Candidate]) -> tuple[Candidate, ...]:
    """`candidates` with each name kept once, at its first place.

    A name carries the rig, the engine, the weights (and quant) and the head,
    so two candidates under one name are one placement listed twice, as when
    one store directory is given under two spellings that list the same file.
    """
    kept: dict[str, Candidate] = {}
    for candidate in candidates:
        kept.setdefault(candidate.name, candidate)
    return tuple(kept.values())


def _decide(
    candidates: tuple[Candidate, ...], state: Mapping[str, Any]
) -> tuple[Candidate, str]:
    """Choose one candidate, asking the local decision model when it is live.

    The probe's "not live" verdict, an error from the request, and an answer
    naming something that was not offered all fall back to `_deterministic_pick`;
    the second element says which route decided, `"model"` or `"deterministic"`.
    """
    endpoint = _decision_endpoint()
    verdict = availability.probe_endpoint(endpoint)
    if not verdict.live:
        return _deterministic_pick(candidates), "deterministic"

    by_name = {candidate.name: candidate for candidate in candidates}
    question = {
        "placement": Choice(
            instructions=(
                "Given this usage profile and the measured machine, pick the "
                "placement that best fits."
            ),
            options={candidate.name: candidate.description for candidate in candidates},
        )
    }
    try:
        answered = decision.classify(
            endpoint,
            "recommend-decision",
            dict(state),
            question,
            timeout_s=DEFAULT_REQUEST_TIMEOUT_S,
        )
    except (RunnerError, decision.DecisionError):
        return _deterministic_pick(candidates), "deterministic"
    answer = answered.answers.get("placement")
    if isinstance(answer, ChoiceAnswer) and answer.choice in by_name:
        return by_name[answer.choice], "model"
    return _deterministic_pick(candidates), "deterministic"


def _placement_document(
    candidate: Candidate, source: str, decode: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The chosen candidate as the plan document's `placement`, tagged with where
    it came from, with its decode speed: a reading, an estimate, or why neither."""
    return {
        "host": candidate.host,
        "engine": candidate.engine,
        # How the unit setup writes for this placement runs (docker on Linux;
        # native for llama.cpp on this macOS or Windows machine).
        "launcher": default_launcher(
            engine=candidate.engine,
            system=host_system(candidate.host),
        ),
        "checkpoint": candidate.checkpoint,
        "model_id": candidate.model_id,
        "quant": candidate.quant,
        "size_bytes": candidate.size_bytes,
        "context_length": candidate.context_length,
        "flags": dict(candidate.flags),
        "wake": candidate.wake,
        "source": source,
        "decode_tok_s": decode,
    }


def plan(
    *,
    profile: str,
    users: int,
    hosts: Sequence[str],
    model_stores: Sequence[str] = (),
    premeasured: Mapping[str, Scan] | None = None,
    readings: Mapping[tuple[str, str], float] | None = None,
) -> dict[str, Any]:
    """Plan one placement for `profile` and `users` across `hosts`, and return
    the document.

    Every host is taken from `premeasured` when that is given — a host it does
    not cover raises `RecommendError` — and otherwise measured over ssh, with
    hosts that were unreachable, had no scanner, or failed to scan collected by
    name instead of failing the plan. Each measured rig is reported in `rigs`, and
    a host named twice is handled once.

    Only the `PLACEMENT_PROFILES` go further. For `code`, each .gguf in
    `model_stores` is read and kept as a candidate when it fits some rig, and
    when none does, or no store was given, the use case's catalog
    (`load_catalog`) supplies candidates from every rig's scan; they are decided
    by `_decide`. For `chat` and `agent` the catalog alone supplies them, each
    at the most context it fits (`_one_unit_candidates`), and the biggest wins.
    The plan states the placement with the host it is for, which route decided
    it, the decision endpoint for a model decision, and which of the Hub, the
    cache or the shipped catalog answered (`candidates_from`, None for a local
    store). Having no candidate at all raises `RecommendError`.

    The placement states its decode speed (`decode_tok_s`): the reading in
    `readings`, by (host, model), when there is one (the live fleet's lock,
    `fleet.lock.decode_readings`, when `readings` is None), else an estimate from
    the bandwidth of the roomiest card's class, else no value and why; each rig's
    cards state their class bandwidth the same way.
    """
    rigs: list[dict[str, Any]] = []
    unreachable: list[str] = []
    no_scanner: list[str] = []
    scan_failed: list[str] = []
    scans: dict[str, Scan] = {}
    provided = (
        {str(host): found for host, found in premeasured.items()}
        if premeasured is not None
        else None
    )
    if provided is not None:
        for host in dict.fromkeys(hosts):
            found = provided.get(str(host))
            if found is None:
                raise RecommendError(
                    f"{host}: no measured scan was provided for this rig"
                )
            scans[str(host)] = found
            rigs.append({"host": str(host), "measured": _measured(found)})
    else:
        for host in dict.fromkeys(hosts):
            try:
                found = _scan_host(str(host))
            except ScannerMissing:
                no_scanner.append(str(host))
                continue
            except ScanFailed:
                scan_failed.append(str(host))
                continue
            except Unreachable:
                unreachable.append(str(host))
                continue
            scans[str(host)] = found
            rigs.append({"host": str(host), "measured": _measured(found)})

    if profile not in PLACEMENT_PROFILES:
        return {
            "profile": profile,
            "users": users,
            "source": "scaffold",
            "hosts": [str(host) for host in dict.fromkeys(hosts)],
            "unreachable": unreachable,
            "no_scanner": no_scanner,
            "scan_failed": scan_failed,
            "rigs": rigs,
            "placement": None,
            "decision": None,
        }

    # A local checkpoint says nothing of the use case it serves, so only the
    # ladder's coding rung is looked for in a store.
    stores = model_stores if profile == PLACEMENT_PROFILE else ()
    local_candidates: list[Candidate] = []
    for host, found in scans.items():
        for directory in dict.fromkeys(stores):
            for checkpoint in _discover(host, str(directory)):
                header = _read_header(host, checkpoint)
                if _fits(found, header, users):
                    local_candidates.extend(
                        _local_candidates(host, found, header, users)
                    )

    candidates_from: str | None = None
    candidates_read_at: str | None = None
    if stores and local_candidates:
        candidates = tuple(local_candidates)
        source = "local-store"
    else:
        roomiest = max((_free_vram_bytes(found) for found in scans.values()), default=0)
        catalog = load_catalog(profile, max_bytes=roomiest or None)
        candidates_from = catalog.get("answered")
        candidates_read_at = catalog.get("read_at")
        shaped = (
            _catalog_candidates
            if profile == PLACEMENT_PROFILE
            else _one_unit_candidates
        )
        candidates = tuple(
            candidate
            for host, found in scans.items()
            for candidate in shaped(host, found, catalog, users)
        )
        source = "hf-catalog"
    candidates = _distinct(candidates)

    if not candidates:
        raise RecommendError(
            "nothing to recommend: no fitting local checkpoint and no catalog "
            "model for any scanned rig"
        )

    state: dict[str, Any] = {
        "profile": profile,
        "users": users,
        "hosts": [str(host) for host in dict.fromkeys(hosts)],
        "measured": rigs,
        "candidates": [
            {
                "name": candidate.name,
                "host": candidate.host,
                "engine": candidate.engine,
                "checkpoint": candidate.checkpoint,
                "model_id": candidate.model_id,
            }
            for candidate in candidates
        ],
    }
    if profile == PLACEMENT_PROFILE:
        selected, decision_source = _decide(candidates, state)
    else:
        # The default for one chat or agent unit is the biggest model that fits,
        # which is the largest-weights pick, with no model asked.
        selected, decision_source = _deterministic_pick(candidates), "deterministic"
    plan: dict[str, Any] = {
        "profile": profile,
        "users": users,
        "source": source,
        "candidates_from": candidates_from,
        "candidates_read_at": candidates_read_at,
        "hosts": [str(host) for host in dict.fromkeys(hosts)],
        "unreachable": unreachable,
        "no_scanner": no_scanner,
        "scan_failed": scan_failed,
        "rigs": rigs,
        "placement": _placement_document(
            selected,
            source,
            _said(
                _decode(
                    selected,
                    scans[selected.host],
                    fleet_lock.decode_readings() if readings is None else readings,
                )
            ),
        ),
        "decision": decision_source,
        "decision_endpoint": (
            _decision_endpoint().base_url if decision_source == "model" else None
        ),
    }
    return plan
