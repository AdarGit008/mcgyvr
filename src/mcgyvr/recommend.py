"""Read-only placement planner behind ``mcgyvr recommend``.

``mcgyvr recommend`` re-reads the rigs it is pointed at and answers one
question: for a usage profile, which checkpoint and engine should serve that
profile, sized from the measurements it just took. It writes nothing, wakes
nothing and sleeps nothing — the plan it prints is a plan, and a plan is the
whole product.

The one property this module holds, the same property :mod:`mcgyvr.compose`
holds for setup: **a model's answer can never invent a number.** Candidate
placements are assembled before :func:`mcgyvr.decision.classify` is consulted,
from the numbers the rig and the checkpoint header just measured or from
shipped constants, and the decision is asked only to name one candidate. What
the decision returns that can reach the plan is a choice among what was already
assembled, never a figure.

Models to place come from exactly one of two places, and the plan says which:

* ``--model-store <dir>`` — checkpoint files are discovered (``*.gguf`` in that
  directory, over the same read-only ssh seam :func:`mcgyvr.scan._ssh` uses)
  and each header is read through :func:`mcgyvr.serving.ggufscan.scan`. When a
  discovered checkpoint fits, the plan recommends **only** from that store.
* no store, or nothing local fits — the plan recommends from the shipped
  HuggingFace catalog ``data/model-catalog.json`` (:func:`load_catalog`), and
  marks those picks downloadable (``model_id``, ``quant``, ``size_bytes``).

Only ``coding`` makes a placement. ``chatting``, ``media_gen`` and ``other``
are accepted as scaffolds: the rigs are still read, but no checkpoint is
chosen and no decision is consulted.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from mcgyvr import decision
from mcgyvr import scan as scan_module
from mcgyvr.config import DEFAULT_REQUEST_TIMEOUT_S
from mcgyvr.decision import Choice, ChoiceAnswer
from mcgyvr.pool import Endpoint, Protocol
from mcgyvr.scan import Reach, Scan, Unreachable
from mcgyvr.serving import (
    DEFAULT_PORT,
    DEFAULT_SPEC_DRAFT_N_MAX,
    DEFAULT_UBATCH,
    ggufscan,
)

#: The filename of the shipped HuggingFace catalog, and the schema version
#: ``load_catalog`` reads. ``data/model-catalog.json`` is *data*: adding a
#: model is an edit to that file, not to this module.
MODEL_CATALOG_FILENAME = "model-catalog.json"

#: The profile values the command accepts, and the one that is placed.
PROFILES = ("coding", "chatting", "media_gen", "other")
PLACEMENT_PROFILE = "coding"

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

    ``shlex.quote`` is the whole safety story: the directory travels as one
    single-quoted token, so a metacharacter in it reaches the rig as a filename
    character and never as a command. The read-only ssh sanction refuses a
    discovery line whose directory is not quoted exactly that way.
    """
    return f"find {shlex.quote(directory)}{_DISCOVER_SUFFIX}"


def catalog_path() -> Path:
    """Locate the shipped model catalog, from a checkout or a wheel."""
    packaged = resources.files("mcgyvr") / "data" / MODEL_CATALOG_FILENAME
    if Path(str(packaged)).is_file():
        return Path(str(packaged))
    # Running from a source checkout: data/ sits at the repo root.
    checkout = Path(__file__).resolve().parents[2] / "data" / MODEL_CATALOG_FILENAME
    if checkout.is_file():
        return checkout
    raise CatalogError(f"model catalog not found (looked for {MODEL_CATALOG_FILENAME})")


def load_catalog() -> dict[str, Any]:
    """The shipped HuggingFace catalog, parsed and validated.

    A dict with ``schema_version`` and ``models``; each model entry carries
    ``model_id``, ``quant``, ``size_bytes`` and ``engines``. The command reads
    it as data, so a test can substitute a fake catalog through this seam.
    """
    path = catalog_path()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise CatalogError(f"{path}: the catalog is not an object")
    if raw.get("schema_version") != 1:
        raise CatalogError(
            f"{path} has schema_version {raw.get('schema_version')!r}; this "
            f"code reads version 1 only"
        )
    models = raw.get("models")
    if not isinstance(models, list) or not models:
        raise CatalogError(f"{path} declares no models")
    for entry in models:
        if not isinstance(entry, dict):
            raise CatalogError(f"{path}: a model entry is not an object")
        for key in ("model_id", "quant", "size_bytes"):
            if key not in entry:
                raise CatalogError(f"{path}: a model entry has no {key!r}")
        if not isinstance(entry.get("size_bytes"), int) or isinstance(
            entry.get("size_bytes"), bool
        ):
            raise CatalogError(f"{path}: a model entry's size_bytes is not an int")
        engines = entry.get("engines")
        if not isinstance(engines, list) or not engines:
            raise CatalogError(
                f"{path}: model {entry.get('model_id')!r} declares no engines"
            )
    return raw


def _read_header(path: str) -> Mapping[str, Any]:
    """Read one checkpoint's header, via the module seam the test substitutes."""
    # ggufscan is the vendored, byte-comparable reader; its own mypy override
    # ignores it, so the call is explicitly untyped here rather than annotated
    # in a way that would drift from the evidence copy.
    return ggufscan.scan(path)  # type: ignore[no-any-return,no-untyped-call]


def _discover(host: str, directory: str) -> tuple[str, ...]:
    """The ``*.gguf`` paths directly under ``directory`` on ``host``.

    Read over the same ssh seam the scan uses, so a test substitutes the
    transport once and both the scan and the discovery answer through it.
    """
    listing = scan_module._ssh(host, discover_command(directory))
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


def _fits(scan: Scan, header: Mapping[str, Any]) -> bool:
    """Whether ``header``'s checkpoint can load on the machine ``scan`` read.

    An MoE spills its experts to host RAM, so the part that must fit on the
    card is the non-expert weights; a dense checkpoint must fit whole. Both
    figures come from the header (measured) and the free VRAM comes from the
    scan (measured); no stored spec and no estimate stand in for either.
    """
    free = _free_vram_bytes(scan)
    if free <= 0:
        return False
    needed = (
        int(header.get("bytes_nonexpert") or 0)
        if header.get("placeable_blocks")
        else int(header.get("size_bytes") or 0)
    )
    return needed <= free


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


def _llamacpp_flags(*, checkpoint: str | None, mtp: bool) -> dict[str, str]:
    """The llama.cpp flags, all shipped constants or the measured checkpoint.

    ``mtp`` is only ever true when the checkpoint's own header carried a
    ``nextn_blocks`` entry, so ``--spec-type draft-mtp`` is never assumed from
    a name.
    """
    flags = dict(_LLAMACPP_FLAGS)
    if checkpoint is not None:
        flags["--model"] = checkpoint
    if mtp:
        flags["--spec-type"] = "draft-mtp"
        flags["--spec-draft-n-max"] = str(DEFAULT_SPEC_DRAFT_N_MAX)
    return flags


def _has_mtp(header: Mapping[str, Any]) -> bool:
    return bool(header.get("nextn_blocks"))


def _local_candidates(scan: Scan, header: Mapping[str, Any]) -> tuple[Candidate, ...]:
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
                flags=_llamacpp_flags(checkpoint=checkpoint, mtp=mtp),
                wake=wake,
            )
        )
    return tuple(candidates)


def _catalog_candidates(
    scan: Scan, catalog: Mapping[str, Any]
) -> tuple[Candidate, ...]:
    """The downloadable placements the shipped catalog offers.

    A catalog pick has no local header and download is out of scope, so the
    flags carry only shipped constants; nothing is invented to stand in for a
    context the command was never given.
    """
    wake = not scan.gpus
    candidates: list[Candidate] = []
    for entry in catalog.get("models", ()):
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("model_id") or "")
        quant = str(entry.get("quant") or "")
        size_bytes = int(entry.get("size_bytes") or 0)
        for engine in entry.get("engines") or ():
            if engine == "llama.cpp":
                flags = _llamacpp_flags(checkpoint=None, mtp=False)
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
    shipped default port. Flagged: a production decision source must be
    declared, not assumed from the port convention.
    """
    return Endpoint(
        source="recommend",
        base_url=f"http://127.0.0.1:{DEFAULT_PORT}",
        protocol=Protocol.OPENAI,
        max_parallel=1,
        credential_env=None,
    )


def _pick(candidates: tuple[Candidate, ...], state: Mapping[str, Any]) -> Candidate:
    """Ask :func:`mcgyvr.decision.classify` to name one candidate.

    The decision may return nothing readable; the first candidate in a
    deterministic order is then the answer, which is still a choice among what
    was already assembled and never a figure the decision supplied.
    """
    if len(candidates) == 1:
        return candidates[0]
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
    answered = decision.classify(
        _decision_endpoint(),
        "recommend-decision",
        dict(state),
        question,
        timeout_s=DEFAULT_REQUEST_TIMEOUT_S,
    )
    answer = answered.answers.get("placement")
    if isinstance(answer, ChoiceAnswer) and answer.choice in by_name:
        return by_name[answer.choice]
    return candidates[0]


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
    profile: str,
    users: int,
    hosts: Sequence[str],
    model_stores: Sequence[str] = (),
) -> dict[str, Any]:
    """Compose the one JSON plan ``mcgyvr recommend`` prints.

    ``hosts`` are re-read over ssh at this moment; ``model_stores``, when any
    is given, are the directories on those rigs to discover ``*.gguf`` in.
    """
    rigs: list[dict[str, Any]] = []
    unreachable: list[str] = []
    scans: dict[str, Scan] = {}
    for host in dict.fromkeys(hosts):
        try:
            found = _scan_host(str(host))
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
            "rigs": rigs,
            "placement": None,
        }

    local_candidates: list[Candidate] = []
    for host, found in scans.items():
        for directory in dict.fromkeys(model_stores):
            for checkpoint in _discover(host, str(directory)):
                header = _read_header(checkpoint)
                if _fits(found, header):
                    local_candidates.extend(_local_candidates(found, header))

    if model_stores and local_candidates:
        candidates = tuple(local_candidates)
        source = "local-store"
    else:
        catalog = load_catalog()
        candidates = tuple(
            candidate
            for host, found in scans.items()
            for candidate in _catalog_candidates(found, catalog)
        )
        source = "hf-catalog"

    if not candidates:
        raise RecommendError(
            "nothing to recommend: no fitting local checkpoint and no catalog "
            "model for any scanned rig"
        )

    state: dict[str, Any] = {
        "profile": profile,
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
    selected = _pick(candidates, state)
    return {
        "profile": profile,
        "users": users,
        "source": source,
        "hosts": [str(host) for host in dict.fromkeys(hosts)],
        "unreachable": unreachable,
        "rigs": rigs,
        "placement": _placement_document(selected, source),
    }
