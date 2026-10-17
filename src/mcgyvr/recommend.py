""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr import availability, decision
from mcgyvr import scan as scan_module
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import Choice, ChoiceAnswer
from mcgyvr.knowledge import store as knowledge_store
from mcgyvr.knowledge.record import KnowledgeError
from mcgyvr.local_pool import Endpoint, Protocol
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
    _free_vram_bytes,
    gatelib,
    vramfit,
)

#
PROFILES = ("coding", "chatting", "media_gen", "other")
PLACEMENT_PROFILE = "coding"

#
#
#
_DISCOVER_SUFFIX = " -maxdepth 1 -name '*.gguf' -print"

#
#
#
#
_LLAMACPP_FLAGS = {
    "-ngl": "99",
    "-fa": "on",
    "-ub": str(DEFAULT_UBATCH),
    "-b": str(DEFAULT_UBATCH),
}


class CatalogError(Exception):
    ""


class RecommendError(Exception):
    ""


@dataclass(frozen=True)
class Candidate:
    ""

    name: str
    description: str
    engine: str
    checkpoint: str | None
    model_id: str | None
    quant: str | None
    size_bytes: int
    context_length: int
    flags: Mapping[str, str]
    wake: bool


def discover_command(directory: str) -> str:
    ""
    if "'" in directory:
        raise RecommendError(
            "a model-store directory with an embedded single quote cannot be "
            "read read-only"
        )
    return f"find '{directory}'{_DISCOVER_SUFFIX}"


def load_catalog() -> dict[str, Any]:
    ""
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


def _read_header(host: str, path: str) -> Mapping[str, Any]:
    ""
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
    ""
    try:
        listing = scan_module._ssh(host, discover_command(directory))
    except ScannerMissing:
        return ()
    return tuple(
        line for line in (part.strip() for part in listing.splitlines()) if line
    )


def _scan_host(host: str) -> Scan:
    ""
    return scan_module.scan_over(Reach.ssh(host))


def _host_ram_bytes(scan: Scan) -> int | None:
    ""
    if scan.memory is None:
        return None
    return int(scan.memory.available_gb * BYTES_PER_GB)


def _slot_bytes(header: Mapping[str, Any], users: int) -> int | None:
    ""
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
    ""
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
    ""
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
    ""
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
    ""
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
                context_length=int(header["n_ctx_train"]),
                flags=_llamacpp_flags(checkpoint=checkpoint, mtp=mtp, users=users),
                wake=wake,
            )
        )
    return tuple(candidates)


def _catalog_slot_bytes(entry: Mapping[str, Any], users: int) -> int | None:
    ""
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
    ""
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
    ""
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
                #
                #
                #
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
                    context_length=int(entry["context_length"]),
                    flags=flags,
                    wake=wake,
                )
            )
    return tuple(candidates)


def _decision_endpoint() -> Endpoint:
    ""
    return Endpoint(
        source="recommend",
        base_url=f"http://127.0.0.1:{DEFAULT_PORT}",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def _deterministic_pick(candidates: tuple[Candidate, ...]) -> Candidate:
    ""
    return max(candidates, key=lambda candidate: candidate.size_bytes)


def _decide(
    candidates: tuple[Candidate, ...], state: Mapping[str, Any]
) -> tuple[Candidate, str]:
    ""
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


def _placement_document(candidate: Candidate, source: str) -> dict[str, Any]:
    ""
    return {
        "engine": candidate.engine,
        "checkpoint": candidate.checkpoint,
        "model_id": candidate.model_id,
        "quant": candidate.quant,
        "size_bytes": candidate.size_bytes,
        "context_length": candidate.context_length,
        "flags": dict(candidate.flags),
        "wake": candidate.wake,
        "source": source,
    }


def plan(
    *,
    profile: str,
    users: int,
    hosts: Sequence[str],
    model_stores: Sequence[str] = (),
    premeasured: Mapping[str, Scan] | None = None,
) -> dict[str, Any]:
    ""
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

    if profile != PLACEMENT_PROFILE:
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

    local_candidates: list[Candidate] = []
    for host, found in scans.items():
        for directory in dict.fromkeys(model_stores):
            for checkpoint in _discover(host, str(directory)):
                header = _read_header(host, checkpoint)
                if _fits(found, header, users):
                    local_candidates.extend(_local_candidates(found, header, users))

    if model_stores and local_candidates:
        candidates = tuple(local_candidates)
        source = "local-store"
    else:
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
        "profile": profile,
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
        "profile": profile,
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
    }
    return plan
