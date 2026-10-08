"""The media-gen plan: an image unit on a card, a voice on the CPU, Whisper here.

Owner, Round 2 (2026-10-07): "media-gen: IMAGE + VOICE. A quantized image
model (e.g. FLUX-schnell via ComfyUI/diffusers) on a card; TTS (e.g. Kokoro)
+ Whisper on CPU/RAM to check the speech; Jev judges. No video." Round 4:
"Media units: prompt-sized." Round 10: the image is ComfyUI with
FLUX.1-schnell's Q4_K_S GGUF, fetched one file at a time; the voice is
Kokoro in Kokoro-FastAPI's CPU image, so the cards stay free; Whisper stays
the ASR-WER gate's own tool on the machine mcgyvr runs on, listed with its
role and served on no rig.

So nothing here prices a card. Each media model is a record of the model
knowledge (:mod:`mcgyvr.knowledge.record`) whose ``working_set`` says which
of its files its unit holds on the card and which in RAM, and a unit is what
:func:`mcgyvr.serving.unit_for` builds for it from those stated figures:

* **the image unit**: on the card with the most room left beside the Jev
  unit, its card figure the bytes of the files it holds there plus
  :data:`MARGIN_GIB` (what a run holds beyond its files: activations, the
  decode, the server), its RAM the files it holds in RAM (the text
  encoders). Candidates are offered best first: the image board, then the
  larger model;
* **the voice**: CPU-only, so it claims no card; on the image unit's machine
  when its RAM holds both, else on the next machine that holds it. Its RAM
  is its files plus :data:`MARGIN_GIB`. No public board ranks a voice
  (:data:`mcgyvr.knowledge.record.UNRANKED`), so candidates are offered by
  their Hub downloads; the sample's ASR-WER gate has the last word. The
  default TTS image carries its model (:data:`mcgyvr.emit.MEDIA_IMAGES`), so
  a voice in it downloads nothing;
* **the speech check**: the recogniser the ASR-WER gate runs, best on its
  board, listed under the plan's ``local`` with role
  :data:`ROLE_LOCAL_CHECK`.

Every media unit has one slot and no context priced: a request to it is a
prompt (:data:`PROMPT_SIZED`). Which model fills each part is deterministic:
an opted-in Jev unit judges the sample, it does not pick.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from mcgyvr import emit, planner, serving
from mcgyvr.config import ROLE_ALWAYS_ON
from mcgyvr.knowledge import store as ks
from mcgyvr.knowledge.record import File, ModelRecord, Score
from mcgyvr.scan import Scan, default_weights_dir

#: The use case this module plans.
USE_CASE = "media-gen"
#: The parts of a media-gen plan, as the knowledge records name them.
IMAGE = "image"
TTS = "tts"
ASR = "asr"
#: The engine each served part runs on (owner, Round 10).
ENGINES: Mapping[str, str] = {IMAGE: "comfyui", TTS: "tts"}
#: The board that ranks each part, where one does.
BOARDS: Mapping[str, str] = {IMAGE: "lmarena-text-to-image", ASR: "open-asr"}
#: What the speech check is to the fleet: a tool the ASR-WER gate runs where
#: mcgyvr runs, not a unit on a rig.
ROLE_LOCAL_CHECK = "local-check"
#: The gate the speech check serves, and the checks a media-gen sample runs.
SPEECH_GATE = "asr_wer"
SAMPLE_CHECKS = ("media_valid", SPEECH_GATE)
#: What a media unit's context is (owner, Round 4: "Media units:
#: prompt-sized"): the prompt, with no window priced.
PROMPT_SIZED = "prompt-sized"
#: What a media unit holds beyond its files where it runs, in GiB: the image
#: unit's activations, decode and server on its card; the voice's runtime in
#: RAM. Judged, not measured (owner, Round 10); ``--media-margin`` says
#: another.
MARGIN_GIB = 1.5
_BYTES_PER_GIB = 1024**3

#: How the parts are ranked, as the plan says it.
RULE = (
    "media-gen picks are deterministic: the image model by the "
    f"{BOARDS[IMAGE]} board, then the larger model, on the roomiest card; the "
    "voice by its Hub downloads (no public board ranks a voice; the sample's "
    f"ASR-WER gate has the last word), on the CPU; the speech check by the "
    f"{BOARDS[ASR]} board"
)


@dataclass(frozen=True)
class MediaModel:
    """A media model the plan may place: one record of the knowledge."""

    record: ModelRecord

    @property
    def part(self) -> str:
        assert self.record.part is not None
        return self.record.part

    @property
    def label(self) -> str:
        return f"{self.record.model_id} {self.record.quant}"

    def _held(self, where: str) -> int:
        sizes = {one.file: int(one.bytes.value) for one in self.record.files}
        held = self.record.working_set
        if held is None:
            return self.record.total_bytes if where == "ram" else 0
        return sum(sizes[name] for name in getattr(held, where))

    @property
    def card_bytes(self) -> int:
        """The bytes of the files its unit holds on the card."""
        return self._held("card")

    @property
    def ram_bytes(self) -> int:
        """The bytes of the files its unit holds in RAM."""
        return self._held("ram")

    def score(self) -> Score | None:
        board = BOARDS.get(self.part)
        return next((s for s in self.record.scores if s.board == board), None)


def library() -> tuple[MediaModel, ...]:
    """The media models of the knowledge read offline (the cache, then the
    shipped catalog) that serve media-gen."""
    return tuple(
        MediaModel(record)
        for record in ks.offline().records
        if record.is_media and (not record.serves or USE_CASE in record.serves)
    )


def rank(part: str, models: Sequence[MediaModel]) -> list[MediaModel]:
    """``part``'s models, best first (:data:`RULE`)."""
    mine = [one for one in models if one.part == part]

    def by_board(one: MediaModel) -> tuple[int, float, int, str]:
        score = one.score()
        if score is None:
            return (1, 0.0, -one.record.total_bytes, one.label)
        lower = part == ASR
        value = float(score.value.value)
        return (0, value if lower else -value, -one.record.total_bytes, one.label)

    if part == TTS:
        return sorted(
            mine,
            key=lambda one: (
                -(int(one.record.downloads.value) if one.record.downloads else -1),
                one.label,
            ),
        )
    return sorted(mine, key=by_board)


def weights_dir(scan: Scan) -> Path:
    """The rig's weights folder: where ``serve fetch`` lands each file, and
    the folder the scan measured (:func:`mcgyvr.serving._weights_path`)."""
    return scan.disk.path if scan.disk is not None else default_weights_dir()


def _image_baked(part: str) -> bool:
    """Whether the default image of ``part``'s engine carries its model."""
    return part == TTS


def spec_of(
    model: MediaModel, scan: Scan, *, margin: float = MARGIN_GIB
) -> serving.ModelSpec:
    """The serving sizer's spec of ``model`` on ``scan``'s machine."""
    cpu_only = model.part == TTS
    card = 0.0 if cpu_only else model.card_bytes / _BYTES_PER_GIB + margin
    ram = model.ram_bytes / _BYTES_PER_GIB + (margin if cpu_only else 0.0)
    disk = 0.0 if _image_baked(model.part) else model.record.total_bytes
    return serving.ModelSpec(
        name=model.record.model_id,
        vram_gb=card,
        ram_gb=ram,
        disk_gb=disk / _BYTES_PER_GIB,
        hf_cache=str(weights_dir(scan)),
        cpu_only=cpu_only,
    )


@dataclass(frozen=True)
class Placed:
    """One media unit, sized by the serving sizer, on ``rig``."""

    rig: str
    model: MediaModel
    unit: serving.Unit
    role: str = ROLE_ALWAYS_ON


@dataclass(frozen=True)
class Media:
    """The media-gen plan: the units placed, the speech check, and each model
    that was not placed, with the sizer's reason."""

    placed: tuple[Placed, ...]
    check: MediaModel | None
    dropped: tuple[tuple[str, str, str], ...]


def _less_ram(scan: Scan, claimed_gb: float) -> Scan:
    if scan.memory is None or not claimed_gb:
        return scan
    left = max(0.0, scan.memory.available_gb - claimed_gb)
    return replace(scan, memory=replace(scan.memory, available_gb=left))


def plan(
    scans: Mapping[str, Scan],
    models: Sequence[MediaModel],
    *,
    claims: Mapping[planner.Card, float] | None = None,
    margin: float = MARGIN_GIB,
) -> Media:
    """The image unit on the roomiest card left beside ``claims`` (the Jev
    unit), the voice on the CPU, and the speech check: the first of each
    part's ranked models the sizer admits."""
    taken = dict(claims or {})
    dropped: list[tuple[str, str, str]] = []
    placed: list[Placed] = []
    card = planner._roomiest(scans, taken)
    for model in rank(IMAGE, models):
        if card is None:
            dropped.append(("fleet", model.label, "no card was read"))
            continue
        on_card = planner._card_scan(scans, card, taken)
        try:
            unit = serving.unit_for(
                on_card,
                spec_of(model, on_card, margin=margin),
                engine=ENGINES[IMAGE],
                port=planner.FIRST_PORT,
                ctx_per_slot=0,
            )
        except serving.UnitError as exc:
            dropped.append((card[0], model.label, str(exc)))
            continue
        whole = planner._gpu(scans, card).vram.free_mib / 1024
        unit = replace(unit, fit=replace(unit.fit, card_free_gb=whole))
        placed.append(Placed(rig=card[0], model=model, unit=unit))
        break
    first = [placed[0].rig] if placed else []
    order = [*first, *(rig for rig in scans if rig not in first)]
    ram_taken = {one.rig: one.unit.fit.ram_gb for one in placed}
    voice: Placed | None = None
    for model in rank(TTS, models):
        for rig in order:
            here = _less_ram(scans[rig], ram_taken.get(rig, 0.0))
            try:
                unit = serving.unit_for(
                    here,
                    spec_of(model, here, margin=margin),
                    engine=ENGINES[TTS],
                    port=planner.FIRST_PORT,
                    ctx_per_slot=0,
                )
            except serving.UnitError as exc:
                dropped.append((rig, model.label, str(exc)))
                continue
            voice = Placed(rig=rig, model=model, unit=unit)
            break
        if voice is not None:
            placed.append(voice)
            break
    checks = rank(ASR, models)
    return Media(
        placed=tuple(placed),
        check=checks[0] if checks else None,
        dropped=tuple(dropped),
    )


def lay_out(media: Media, taken: Mapping[str, Sequence[int]], first_port: int) -> Media:
    """``media``'s units, each given the next port free on its machine after
    the ports ``taken`` there (the Jev unit's)."""
    ports = {rig: max(used) + 1 for rig, used in taken.items() if used}
    laid: list[Placed] = []
    for one in media.placed:
        port = ports.get(one.rig, first_port)
        ports[one.rig] = port + 1
        unit = replace(one.unit, port=port, key=replace(one.unit.key, port=port))
        laid.append(replace(one, unit=unit))
    return replace(media, placed=tuple(laid))


def _file(one: File) -> dict[str, Any]:
    pinned = {"sha256": one.sha256} if one.sha256 else {"git_oid": one.git_oid}
    return {
        "repo": one.repo,
        "revision": one.revision,
        "file": one.file,
        **pinned,
        "bytes": int(one.bytes.value),
    }


def unit_name(one: Placed) -> str:
    """``<rig>-<model>-<port>``, as :func:`mcgyvr.planner.unit_name` spells it."""
    stem = one.model.record.model_id.rsplit("/", 1)[-1]
    return f"{one.rig}-{planner._slug(stem)}-{one.unit.port}"


def _sources(record: ModelRecord) -> dict[str, str]:
    out: dict[str, str] = {}
    if record.size_bytes is not None:
        out["size"] = record.size_bytes.source
    if record.files:
        out["size"] = "; ".join(one.bytes.source for one in record.files)
    if record.downloads is not None:
        out["downloads"] = record.downloads.source
    if record.scores:
        out["score"] = "; ".join(score.value.source for score in record.scores)
    return out


def unit_document(one: Placed) -> dict[str, Any]:
    """One planned media unit as the plan states it, every number the sizer's
    or the knowledge's."""
    unit, record = one.unit, one.model.record
    held = record.working_set
    image = emit.default_media_image(unit)
    baked = image is not None
    notes: list[str] = []
    if baked:
        notes.append(
            f"the default {unit.engine} image {image} carries the model, so "
            f"nothing is downloaded for it"
        )
    elif unit.image is None:
        notes.append(
            f"{unit.engine} has no default image: set units.<unit>.image to "
            f"the operator's {unit.engine} server image before it is started"
        )
    return {
        "name": unit_name(one),
        "role": one.role,
        "jev": False,
        "part": one.model.part,
        "engine": unit.engine,
        "image": image,
        "model": {
            "id": record.model_id,
            "quant": record.quant,
            "size_bytes": record.total_bytes,
            "files": [
                {**_file(f), "held": "card" if held and f.file in held.card else "ram"}
                for f in record.files
            ],
        },
        "ctx_per_slot": None,
        "context": PROMPT_SIZED,
        "slots": unit.width.value,
        "process": unit.role,
        "cpu_only": unit.cpu_only,
        "cards": [] if unit.cpu_only else list(unit.cards),
        "port": unit.port,
        "args": dict(unit.args),
        "fit": {
            "vram_gib": unit.fit.vram_gb,
            "ram_gib": unit.fit.ram_gb,
            "why": unit.fit.why,
        },
        "download": {
            "bytes": 0 if baked else record.total_bytes,
            "files": [] if baked else [_file(f) for f in record.files],
            "present": False,
            "to": None if baked else str(unit.weights_dir),
        },
        "sources": _sources(record),
        "notes": notes,
    }


def check_document(model: MediaModel) -> dict[str, Any]:
    """The speech check as the plan lists it: on no rig."""
    record = model.record
    return {
        "name": f"local-{planner._slug(record.model_id.rsplit('/', 1)[-1])}",
        "role": ROLE_LOCAL_CHECK,
        "part": model.part,
        "engines": list(record.engines),
        "gate": SPEECH_GATE,
        "runs": "on the machine mcgyvr runs on, on its CPU; nothing is served on a rig",
        "model": {
            "id": record.model_id,
            "quant": record.quant,
            "size_bytes": record.total_bytes,
        },
        "scores": [
            {"board": s.board, "metric": s.metric, "value": s.value.value}
            for s in record.scores
        ],
        "sources": _sources(record),
    }
