"""Read-only placement planner behind ``mcgyvr recommend``.

``mcgyvr recommend`` re-reads the rigs it is pointed at and answers one
question: for a use case, which checkpoint and engine should serve that use
case, sized from the measurements it just took. It writes nothing, wakes
nothing and sleeps nothing — the plan it prints is a plan, and a plan is the
whole product.

The one property this module holds, the same property :mod:`mcgyvr.compose`
holds for setup: **a model's answer can never invent a number.** Candidate
placements are assembled before :func:`mcgyvr.decision.classify` is consulted,
from the numbers the rig and the checkpoint header just measured or from
shipped constants, and the decision is asked only to name one candidate. What
the decision returns that can reach the plan is a choice among what was already
assembled, never a figure. When no decision backend is reachable, the choice is
made deterministically — the largest checkpoint among the candidates that
already fit the measured machine — and the plan says so.

Models to place come from exactly one of two places, and the plan says which:

* ``--model-store <dir>`` — checkpoint files are discovered (``*.gguf`` in that
  directory, over the same read-only ssh seam :func:`mcgyvr.scan._ssh` uses)
  and each header is read ON the rig, over the same seam, by shipping
  :mod:`mcgyvr.serving.ggufscan` to the rig as ``python3 -`` (the blob never
  comes back). When a discovered checkpoint fits, the plan recommends **only**
  from that store.
* no store, or nothing local fits — the plan recommends from the model
  knowledge read offline (:func:`load_catalog`: the user's cache, then the
  shipped catalog ``data/model-catalog.json``), after refreshing that cache
  online unless ``--offline`` or ``HF_HUB_OFFLINE`` says not to
  (:func:`mcgyvr.knowledge.online.refresh`), and marks those picks
  downloadable (``model_id``, ``quant``, ``size_bytes``). A
  catalog pick has no header, so it fits only when its shipped ``size_bytes``
  plus the KV and recurrent state its shipped geometry prices for ``--users``
  slots fit the measured free VRAM.

The use case is one of the catalog's four (``chat``, ``agent``, ``coding``,
``media-gen``), the same names ``mcgyvr init --use-case`` takes. Only
``coding`` makes a placement. The other three are accepted as scaffolds: the
rigs are still read, but no checkpoint is chosen and no decision is consulted.
The old ``--profile`` spellings map through :data:`OLD_PROFILES`; ``other``
maps to no use case and is scaffolded the same way.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr import availability, decision
from mcgyvr import scan as scan_module
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import Choice, ChoiceAnswer
from mcgyvr.knowledge import online as knowledge_online
from mcgyvr.knowledge import store as knowledge_store
from mcgyvr.knowledge.record import KnowledgeError
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.runner import RunnerError
from mcgyvr.scan import (
    BYTES_PER_GB,
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
    gatelib,
    vramfit,
)

#: The use case that is placed. The others the catalog names are scaffolds.
PLACEMENT_USE_CASE = "coding"

#: The deprecated ``--profile`` spellings, read for one release, and the use
#: case each one means. ``other`` names no use case, so nothing is planned.
OLD_PROFILES: dict[str, str | None] = {
    "coding": "coding",
    "chatting": "chat",
    "media_gen": "media-gen",
    "other": None,
}

#: The read-only remote line that discovers ``*.gguf`` one level under a
#: directory on the rig. The directory is always single-quoted by
#: :func:`discover_command`, which the read-only ssh sanction requires.
_DISCOVER_SUFFIX = " -maxdepth 1 -name '*.gguf' -print"

#: Flags every llama.cpp placement carries. ``-ngl 99`` and ``-fa on`` are the
#: same shipped conventions :func:`mcgyvr.serving.unit_for` writes; ``-ub`` and
#: ``-b`` are :data:`mcgyvr.serving.DEFAULT_UBATCH`, the shipped micro-batch the
#: cache law is priced at. None of these is a number this module invents.
_LLAMACPP_FLAGS = {
    "-ngl": "99",
    "-fa": "on",
    "-ub": str(DEFAULT_UBATCH),
    "-b": str(DEFAULT_UBATCH),
}


class CatalogError(Exception):
    """The model catalog is missing, malformed, or internally inconsistent."""


class RecommendError(Exception):
    """``mcgyvr recommend`` was asked something it cannot honestly answer."""


@dataclass(frozen=True)
class Candidate:
    """One placement, assembled from measured inputs before any decision.

    ``checkpoint`` is set for a local-store pick; ``model_id``/``quant`` are
    set for a catalog pick. Exactly one of the two shapes is present.
    """

    name: str
    description: str
    engine: str
    checkpoint: str | None
    model_id: str | None
    quant: str | None
    size_bytes: int
    flags: Mapping[str, str]
    wake: bool


def discover_command(directory: str) -> str:
    """The one read-only remote line that lists ``*.gguf`` under ``directory``.

    The directory travels as one single-quoted token, so a metacharacter in it
    reaches the rig as a filename character and never as a command. The
    read-only ssh sanction admits a discovery line only when the directory is
    quoted exactly that way, so a directory with an embedded single quote is
    refused rather than shipped in a shape the sanction cannot prove.
    """
    if "'" in directory:
        raise RecommendError(
            "a model-store directory with an embedded single quote cannot be "
            "read read-only"
        )
    return f"find '{directory}'{_DISCOVER_SUFFIX}"


def load_catalog() -> dict[str, Any]:
    """The catalog the plan prices catalog picks from: the model knowledge as
    it reads offline, the user's cache first and then the shipped catalog
    (:func:`mcgyvr.knowledge.store.offline`).

    A dict whose ``models`` are flat entries carrying ``model_id``, ``quant``,
    ``size_bytes``, ``context_length``, ``kv_bytes_per_token``,
    ``recurrent_bytes_per_slot`` and ``engines``: each number's value, with
    its source and date left in the knowledge it was read from. The command
    reads it as data, so a test can substitute a fake catalog through this
    seam.
    """
    try:
        known = knowledge_store.offline()
    except KnowledgeError as exc:
        raise CatalogError(str(exc)) from exc
    return {
        "models": [
            {
                "model_id": one.model_id,
                "quant": one.quant,
                "size_bytes": one.size_bytes.value,
                "context_length": one.context_length.value,
                "kv_bytes_per_token": one.kv_bytes_per_token.value,
                "recurrent_bytes_per_slot": one.recurrent_bytes_per_slot.value,
                "engines": list(one.engines),
            }
            for one in known.records
        ]
    }


def _refresh_knowledge(use_case: str | None, offline: bool) -> dict[str, Any]:
    """Refresh the models the knowledge holds, online unless asked not to.

    Never raises for the network: what could not be read is named in the
    answer, and the cache and the shipped catalog still answer
    :func:`load_catalog`.
    """
    try:
        known = knowledge_store.offline().records
    except KnowledgeError as exc:
        raise CatalogError(str(exc)) from exc
    done = knowledge_online.refresh(known, use_case=use_case, offline=offline)
    return done.as_json()


def _read_header(host: str, path: str) -> Mapping[str, Any]:
    """Read one checkpoint's header ON ``host``, over the read-only ssh seam.

    The reader (:mod:`mcgyvr.serving.ggufscan`) ships to the rig as ``python3
    -`` through :func:`mcgyvr.serving.gatelib.header_read_command` and reads
    the header there; the blob never comes back and nothing lands on the
    rig's disk. ``mcgyvr.scan._ssh`` is the same read-only ssh seam the scan
    and the discovery use, so a test substitutes the transport once and all
    three answer through it.
    """
    try:
        command = gatelib.header_read_command(path)
    except ValueError as exc:
        raise RecommendError(str(exc)) from exc
    listing = scan_module._ssh(host, command)
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
    """The ``*.gguf`` paths directly under ``directory`` on ``host``.

    Read over the same ssh seam the scan uses, so a test substitutes the
    transport once and both the scan and the discovery answer through it.
    A directory that does not exist on the rig makes ``find`` exit non-zero,
    which the seam reports as :class:`ScannerMissing`; that is absence — this
    store holds zero checkpoints — and never a failure. A rig that stops
    answering ssh still raises :class:`Unreachable` here, so a lost connection
    is never read as an empty store.
    """
    try:
        listing = scan_module._ssh(host, discover_command(directory))
    except ScannerMissing:
        return ()
    return tuple(
        line for line in (part.strip() for part in listing.splitlines()) if line
    )


def _scan_host(host: str) -> Scan:
    """Re-read one rig at this moment. Never a stored spec."""
    return scan_module.scan_over(Reach.ssh(host))


def _free_vram_bytes(scan: Scan) -> int:
    """Free VRAM on the roomiest card, or zero when no card is visible."""
    if not scan.gpus:
        return 0
    return max(gpu.vram.free_mib for gpu in scan.gpus) << 20


def _host_ram_bytes(scan: Scan) -> int | None:
    """Measured host RAM available, or None when the scan could not read it.

    ``Memory.available_gb`` is the kernel's own estimate of what a new workload
    could get without swapping, which is the figure an MoE's resident expert
    spill is held against. A scan that could not read memory returns None, and
    :func:`_fits` reads that as "does not fit" rather than guessing a ceiling.
    """
    if scan.memory is None:
        return None
    return int(scan.memory.available_gb * BYTES_PER_GB)


def _slot_bytes(header: Mapping[str, Any], users: int) -> int | None:
    """KV and recurrent-state bytes for ``users`` slots, from the measured header.

    ``n_ctx_train`` is the measured context the checkpoint declares and is used
    as the total context across slots; ``users`` is the slot count the placement
    serves. Returns None when the header lacks the geometry the cache law
    needs, which :func:`_fits` reads as "does not fit" rather than guessing.
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
    """Whether ``header``'s checkpoint can load for ``users`` slots on ``scan``.

    An MoE spills its experts to host RAM, so the part that must fit on the
    card is the non-expert weights; a dense checkpoint must fit whole. To that
    weight term the cache law adds the KV cache and the recurrent state the
    header implies for ``users`` concurrent slots, so a wider placement is
    priced as a wider process, not as the same weights. For an MoE the spilled
    experts are then held against the measured host RAM available: a rig whose
    RAM cannot hold what the checkpoint keeps resident is not offered the
    model. Every figure comes from the header or the scan (measured); no
    stored spec and no estimate stand in for any of them.
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
        if ram is None or expert_bytes > ram:
            return False
    return True


def _measured(scan: Scan) -> dict[str, Any]:
    """The measured facts of one scan, for the plan and for the decision state."""
    gpus = [
        {
            "index": gpu.index,
            "name": gpu.name,
            "vram_total_mib": gpu.vram.total_mib,
            "vram_free_mib": gpu.vram.free_mib,
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


def _llamacpp_flags(*, checkpoint: str | None, mtp: bool, users: int) -> dict[str, str]:
    """The llama.cpp flags, all shipped constants or the measured checkpoint.

    ``mtp`` is only ever true when the checkpoint's own header carried a
    ``nextn_blocks`` entry, so ``--spec-type draft-mtp`` is never assumed from
    a name. ``users`` above one states ``--parallel``, the width the fit was
    priced at.
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


def _has_mtp(header: Mapping[str, Any]) -> bool:
    return bool(header.get("nextn_blocks"))


def _local_candidates(
    scan: Scan, header: Mapping[str, Any], users: int
) -> tuple[Candidate, ...]:
    """The placements a fitting local checkpoint can be served under.

    A local store holds ``.gguf`` files, so llama.cpp is the engine that serves
    them; vLLM loads a repository id from a HuggingFace cache, not a file. The
    header decides whether the grafted MTP head is one of the candidates.
    """
    checkpoint = str(header.get("file") or "")
    size_bytes = int(header.get("size_bytes") or 0)
    wake = not scan.gpus
    variants: list[tuple[str, bool]] = [(checkpoint, False)]
    if _has_mtp(header):
        variants.append((checkpoint, True))
    candidates: list[Candidate] = []
    for _name, mtp in variants:
        flag = "--spec-type draft-mtp" if mtp else "no speculative head"
        candidates.append(
            Candidate(
                name=f"llama.cpp:{flag}",
                description=(
                    f"llama.cpp serving {checkpoint}"
                    f"{' with its grafted MTP head' if mtp else ''}"
                ),
                engine="llama.cpp",
                checkpoint=checkpoint,
                model_id=None,
                quant=None,
                size_bytes=size_bytes,
                flags=_llamacpp_flags(checkpoint=checkpoint, mtp=mtp, users=users),
                wake=wake,
            )
        )
    return tuple(candidates)


def _catalog_slot_bytes(entry: Mapping[str, Any], users: int) -> int | None:
    """KV + recurrent-state bytes for ``users`` slots, from the shipped entry.

    Mirrors :func:`_slot_bytes` as far as a catalog entry (no measured header)
    allows: the cache is the shipped ``context_length`` priced across ``users``
    slots at the shipped ``kv_bytes_per_token`` width, and recurrent state is
    the shipped ``recurrent_bytes_per_slot`` per slot. Returns None when the
    entry lacks any figure, which :func:`_catalog_fits` reads as "does not fit".
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
    """Whether a catalog entry fits the measured machine.

    A catalog pick has no header, so no MoE split is known; the conservative
    bound is the whole shipped size plus the KV and recurrent state the entry's
    shipped geometry prices for ``users`` slots, all against the roomiest
    card's free VRAM. It fails closed: an entry whose geometry is missing or
    does not fit is left out rather than placed from an assumed split.
    """
    free = _free_vram_bytes(scan)
    if free <= 0:
        return False
    size_bytes = int(entry.get("size_bytes") or 0)
    slots = _catalog_slot_bytes(entry, users)
    if slots is None:
        return False
    return size_bytes + slots <= free


def _catalog_candidates(
    scan: Scan, catalog: Mapping[str, Any], users: int
) -> tuple[Candidate, ...]:
    """The downloadable placements the shipped catalog offers.

    Only entries whose shipped size plus their shipped KV/state budget fit the
    measured free VRAM are assembled; a catalog pick has no local header and
    download is out of scope, so the flags carry only shipped constants and
    nothing is invented to stand in for a context the command was never given.
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
                # vLLM's ceiling figures need a declared context and cache
                # dtype this command does not have; an empty flag set is the
                # honest answer, not a plausible one.
                flags = {}
            candidates.append(
                Candidate(
                    name=f"{engine}:{model_id}",
                    description=f"{engine} serving {model_id} ({quant})",
                    engine=str(engine),
                    checkpoint=None,
                    model_id=model_id,
                    quant=quant,
                    size_bytes=size_bytes,
                    flags=flags,
                    wake=wake,
                )
            )
    return tuple(candidates)


def _decision_endpoint() -> Endpoint:
    """The decision source for the coding placement.

    ``mcgyvr recommend`` is read-only and has no config, so it cannot resolve a
    ladder rung the way :mod:`mcgyvr.compose` does. The least it can name
    without inventing a machine is the keyless local backend at llama.cpp's
    shipped default port. When that backend is not reachable, the plan does
    not consult it: the pick is deterministic, and the plan says so.
    """
    return Endpoint(
        source="recommend",
        base_url=f"http://127.0.0.1:{DEFAULT_PORT}",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def _deterministic_pick(candidates: tuple[Candidate, ...]) -> Candidate:
    """The deterministic fallback: the largest checkpoint among the candidates.

    Every candidate here already fit the measured machine when it was
    assembled — local store by :func:`_fits`, catalog by :func:`_catalog_fits`
    — so "largest" is "largest that fits", and no model and no invented
    number stand in for the measurements. Ties keep the assembly order.
    """
    return max(candidates, key=lambda candidate: candidate.size_bytes)


def _decide(
    candidates: tuple[Candidate, ...], state: Mapping[str, Any]
) -> tuple[Candidate, str]:
    """Name one candidate, and say where the choice came from.

    When no decision backend is reachable the pick is deterministic
    (:func:`_deterministic_pick`) and the answer is ``"deterministic"``. When
    a backend answers, :func:`mcgyvr.decision.classify` names one candidate and
    the answer is ``"model"``. A backend that answers without a readable
    placement also falls back deterministically, because the actual choice
    still came from the fixed rule.
    """
    endpoint = _decision_endpoint()
    verdict = availability.probe_endpoint(endpoint)
    if not verdict.live:
        return _deterministic_pick(candidates), "deterministic"

    by_name = {candidate.name: candidate for candidate in candidates}
    question = {
        "placement": Choice(
            instructions=(
                "Given this use case and the measured machine, pick the "
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


def _placement_document(candidate: Candidate, source: str) -> dict[str, Any]:
    """The plan's placement object, nothing the decision returned but a name."""
    return {
        "engine": candidate.engine,
        "checkpoint": candidate.checkpoint,
        "model_id": candidate.model_id,
        "quant": candidate.quant,
        "size_bytes": candidate.size_bytes,
        "flags": dict(candidate.flags),
        "wake": candidate.wake,
        "source": source,
    }


def plan(
    *,
    use_case: str | None,
    users: int,
    hosts: Sequence[str],
    model_stores: Sequence[str] = (),
    offline: bool = False,
) -> dict[str, Any]:
    """Compose the one JSON plan ``mcgyvr recommend`` prints.

    ``use_case`` is one of the catalog's use cases, or ``None`` for the old
    ``--profile other``, which names none and is scaffolded. ``hosts`` are
    re-read over ssh at this moment; ``model_stores``, when any is given, are
    the directories on those rigs to discover ``*.gguf`` in. Before catalog
    picks are priced, the model knowledge is refreshed online
    (:func:`mcgyvr.knowledge.online.refresh`) unless ``offline`` or
    ``HF_HUB_OFFLINE`` says not to; the plan's ``knowledge`` says which, and
    names what could not be read.
    """
    rigs: list[dict[str, Any]] = []
    unreachable: list[str] = []
    no_scanner: list[str] = []
    scan_failed: list[str] = []
    scans: dict[str, Scan] = {}
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

    if use_case != PLACEMENT_USE_CASE:
        return {
            "use_case": use_case,
            "users": users,
            "source": "scaffold",
            "hosts": [str(host) for host in dict.fromkeys(hosts)],
            "unreachable": unreachable,
            "no_scanner": no_scanner,
            "scan_failed": scan_failed,
            "rigs": rigs,
            "placement": None,
            "decision": None,
            "knowledge": None,
        }

    local_candidates: list[Candidate] = []
    for host, found in scans.items():
        for directory in dict.fromkeys(model_stores):
            for checkpoint in _discover(host, str(directory)):
                header = _read_header(host, checkpoint)
                if _fits(found, header, users):
                    local_candidates.extend(_local_candidates(found, header, users))

    knowledge: dict[str, Any] | None = None
    if model_stores and local_candidates:
        candidates = tuple(local_candidates)
        source = "local-store"
    else:
        knowledge = _refresh_knowledge(use_case, offline)
        catalog = load_catalog()
        candidates = tuple(
            candidate
            for host, found in scans.items()
            for candidate in _catalog_candidates(found, catalog, users)
        )
        source = "hf-catalog"

    if not candidates:
        raise RecommendError(
            "nothing to recommend: no fitting local checkpoint and no catalog "
            "model for any scanned rig"
        )

    state: dict[str, Any] = {
        "use_case": use_case,
        "users": users,
        "hosts": [str(host) for host in dict.fromkeys(hosts)],
        "measured": rigs,
        "candidates": [
            {
                "name": candidate.name,
                "engine": candidate.engine,
                "checkpoint": candidate.checkpoint,
                "model_id": candidate.model_id,
            }
            for candidate in candidates
        ],
    }
    selected, decision_source = _decide(candidates, state)
    plan: dict[str, Any] = {
        "use_case": use_case,
        "users": users,
        "source": source,
        "hosts": [str(host) for host in dict.fromkeys(hosts)],
        "unreachable": unreachable,
        "no_scanner": no_scanner,
        "scan_failed": scan_failed,
        "rigs": rigs,
        "placement": _placement_document(selected, source),
        "decision": decision_source,
        "decision_endpoint": (
            _decision_endpoint().base_url if decision_source == "model" else None
        ),
        "knowledge": knowledge,
    }
    return plan
