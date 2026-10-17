"""Size serving units: what a model costs on a scanned rig, which card it lands on with
how many slots, and the argv that serves it."""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcgyvr import derived
from mcgyvr.config import ROLE_SLEEPER, Config
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Gpu, Scan, default_weights_dir
from mcgyvr.serving import vramfit

# The engine a unit is served by when units.<unit>.engine states none:
# units_for() falls back to it, and the sleeper role, the weights path
# and the llama.cpp argument list are all written for this engine.
DEFAULT_ENGINE = "llama.cpp"

# Every engine this module will size and render a unit for: the two with
# a launch spec (llama.cpp, vllm) and the three media engines, sized from
# declared figures. fit() refuses any other engine by name.
KNOWN_ENGINES = ("llama.cpp", "vllm", "diffusers", "tts", "comfyui")

# Engines whose server is their container image's entrypoint, so no
# argument list is built for them here: fit() sizes them from the spec's
# vram_gb, ram_gb, disk_gb and cpu_only rather than from a geometry,
# adding vae_decode_gb as a decode spike for diffusers alone.
MEDIA_ENGINES = ("diffusers", "tts", "comfyui")

# Media engines this build cannot actually render. Empty today, and read
# as a gate: emit.py refuses a unit listed here rather than write a
# service it has no default image or command for. It stays a named
# tuple so an engine whose wiring is pulled is disabled in one place.
MEDIA_ENGINES_NOT_WIRED: tuple[str, ...] = ()

# The llama.cpp micro-batch (-ub) and physical batch (-b) every unit is
# launched with, and the n_ubatch every cache, recurrent-state and
# scratch figure in this module is priced at. vramfit's per-micro-batch
# readings are what turn a geometry and a window into bytes, so sizing
# and the command line have to agree on one value, and nothing reads it
# back off a running unit. Changing it here moves the prediction and the
# flag together, which is why it is one constant rather than two, and
# why it is stated here rather than taken from a unit's launch block.

# 512 is the micro-batch vramfit's scratch readings were taken at, and
# the only one this build sizes or launches at: a card that cannot hold
# 512 tokens of scratch has no room figure this module can stand behind,
# so the unit is refused rather than sized at a batch nobody measured.
DEFAULT_UBATCH = 512

# The port a unit listens on when its address carries none. port_of()
# falls back to it, and UnitKey, Unit and unit_for all default to it, so
# `http://rig` and `http://rig:8080` name one process and group into one
# unit instead of two.
DEFAULT_PORT = 8080

# A host's launch spec is written to `compose.<host>.yml`, or to
# `compose.<host>.<model>.yml` when the host's units cannot all be up at
# once and are emitted as alternatives. These two halves are the whole
# naming contract: spec_name() builds a name from them and spec_files()
# looks a host's files up by them.
COMPOSE_PREFIX = "compose."
COMPOSE_SUFFIX = ".yml"
# The compose profile a service is put under when its unit starts
# asleep: emit.py writes `profiles: [asleep]` for it, so `serve up`
# leaves it down until something names the profile. This is how the
# `sleeps-until-needed` role reaches the rendered file.
SLEEPER_PROFILE = "asleep"

# Every character a host or model name may not carry into a file name:
# each run of them collapses to one hyphen, so safe_host(), safe_model()
# and _ipv6() produce a name that needs no quoting and cannot climb out
# of the compose directory with a separator or a `..`.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

# Host RAM is charged in two currencies because llama.cpp can read a GGUF
# either mapped or not. Left alone it memory-maps the blob, and the
# resident pages of a mapped file count against the host's available
# RAM, so a unit read that way wants its disk_gb held. Launched with
# --load-mode none it reads the file through instead, holding only the
# non-expert weights and the expert blocks that --n-cpu-moe leaves in
# RAM, which is placed.ram_gb. _sized() weighs both of those against the
# available RAM the scan reports, picks the mode that fits, and refuses
# the unit outright when neither does, rather than emit a server the
# kernel would kill part-way through loading. Each comparison has its
# own margin below, and they differ because they answer different
# questions.

# The mapped-blob margin. If disk_gb plus this much still fits the host's
# available RAM, the unit keeps llama.cpp's default loading and _sized()
# charges disk_gb rather than the placed.ram_gb it would take unmapped.
# The mapped answer wins whenever it is affordable at all: the page cache
# already holds most of a blob that was just written or scanned, and a
# unit that does fit is not made to read through for no gain. Where it is
# not affordable, the unmapped branch below is taken instead.

# Half a gigabyte, held back rather than spent. Available RAM measured
# at sizing time is not what it will be once the server is up, the page
# cache is warm and the host's other services have grown into what was
# reported. Charging the full disk_gb against a host with barely more
# available than that would leave the unit a few hundred megabytes from
# the kernel's OOM killer, and an underestimate there costs a load, not
# a launch flag. Keeping the margin above zero also keeps the mapped
# branch from being chosen on a hair and then paged out under load.
MODE_RAM_HEADROOM_GB = 0.5

# The refusal margin. When disk_gb does not fit mapped, _sized() picks
# --load-mode none, and the unit then has to hold placed.ram_gb of
# experts in RAM for real; if even that plus this margin exceeds the
# available RAM, no loading mode fits and the unit is refused with both
# figures side by side. The margin is four times the mapped one because
# this memory is actually allocated: the block data has to be present
# before the first token, and a host that only just fits it will spend
# the run swapping. It is also the margin hold_together() holds back
# when it sums several units' host RAM on one rig.
REFUSAL_RAM_HEADROOM_GB = 2.0

# The ceiling on the slot count _placement() searches for on one card.
MAX_WIDTH = 32
# The sequence count a vLLM unit is given when its unit states no width:
# --max-num-seqs, and the slot count its KV cache is sized at. The cache
# grows with concurrent sequences, so the default is a modest stated
# figure rather than the whole window handed to one slot, and a unit
# that states a width gets that instead. The split path in
# _sharded_units() takes this same default when the width is unstated,
# so a split vLLM unit and a single-card one start out with the same
# number of sequences. The window each slot serves is ctx_per_slot,
# passed separately, so the two figures move apart only when a unit
# asks them to.
VLLM_DEFAULT_SEQS = 8
# Where the rig's HuggingFace cache is mounted read-only inside a unit's
# container: emit.py mounts unit.weights_dir here for the engine to read.
HF_CACHE_MOUNT = "/root/.cache/huggingface"

# How far a declared disk_gb may sit from the size its geometry scan
# measured before ModelSpec refuses it. GiB and GB, a hand-written
# figure and a byte count all differ in the last digits; a real
# disagreement is gigabytes, not half a hundredth of one.
SIZE_TOLERANCE_GB = 0.005

# The values units.<unit>.launch.speculative may take. `none` is the
# default and means no draft head; `mtp` is llama.cpp's --spec-type
# draft-mtp, which runs the MTP head grafted into the GGUF itself as the
# draft. Anything else is refused by ModelSpec, so neither a vLLM
# speculative config nor a name nobody scanned can be expressed here.
# The choice is read by _placement() to budget the head's bytes on the
# card and by unit_for() to write --spec-type, and _sharded_units()
# refuses it outright for a unit split across cards.
SPECULATIVE_NONE = "none"
SPECULATIVE_MTP = "mtp"
SPECULATIVE_CHOICES = (SPECULATIVE_NONE, SPECULATIVE_MTP)
# The --spec-draft-n-max a unit is launched with when nothing states one:
# how many tokens the grafted MTP head drafts per step.
DEFAULT_SPEC_DRAFT_N_MAX = 2

_BYTES_PER_GIB = 1024**3

# The process roles a unit's parts can carry: the process that answers,
# llama.cpp's rpc-server workers and vLLM's headless ranks. emit.py
# checks that an engine has the role it is asked to render.
ROLE_SERVE = "serve"
ROLE_RPC = "rpc"
ROLE_HEADLESS = "headless"
ROLES = (ROLE_SERVE, ROLE_RPC, ROLE_HEADLESS)

# The launch key that splits one unit across cards: a list of {rig, gpu}
# entries, the first on the host the unit's address points at.
SHARDS_KEY = "shards"
# The port a llama.cpp rpc-server worker listens on when a unit's launch
# block states no rpc_port. Workers on one host take successive ports
# from it, and the head's --rpc list names each of them.
RPC_DEFAULT_PORT = 50052
# The rendezvous port a vLLM launch uses when no master_port is stated.
# It is handed to every rank as --master-port and must differ from the
# serving port on the head's machine.
VLLM_MASTER_PORT = 29501


class UnitError(Exception):
    """A model or unit that cannot be sized or rendered as stated, carrying the reason
    as its message."""


@dataclass(frozen=True)
class ModelSpec:
    """What one model costs, from the shipped catalogue or from a unit's own launch
    block, plus the checks that a stated figure agrees with the scan it came from."""

    name: str
    vram_gb: float
    ram_gb: float
    disk_gb: float
    vae_decode_gb: float = 0.0
    cpu_only: bool = False
    moe: bool = False
    geometry: Mapping[str, Any] | None = field(default=None, compare=False)
    hf_cache: str = ""
    serve_args: tuple[str, ...] = ()
    kv_cache_dtype_k: str | None = None
    kv_cache_dtype_v: str | None = None
    speculative: str = SPECULATIVE_NONE
    spec_draft_n_max: int = DEFAULT_SPEC_DRAFT_N_MAX

    def __post_init__(self) -> None:
        if self.speculative not in SPECULATIVE_CHOICES:
            raise UnitError(
                f"{self.name}: units.<unit>.launch.speculative is "
                f"{self.speculative!r}, which this build does not know. Valid: "
                f"{', '.join(SPECULATIVE_CHOICES)} -- `mtp` is llama.cpp's "
                f"--spec-type draft-mtp, the GGUF's own grafted head as the draft"
            )
        if (
            isinstance(self.spec_draft_n_max, bool)
            or not isinstance(self.spec_draft_n_max, int)
            or self.spec_draft_n_max < 1
        ):
            raise UnitError(
                f"{self.name}: units.<unit>.launch.spec_draft_n_max is "
                f"{self.spec_draft_n_max!r}; --spec-draft-n-max is how many "
                f"tokens the head drafts per step and must be at least 1 "
                f"(the default is {DEFAULT_SPEC_DRAFT_N_MAX})"
            )
        if self.geometry is None:
            return
        scanned = Path(str(self.geometry.get("file") or "")).name
        wanted = _weights_file_name(self.name)
        if scanned != wanted:
            raise UnitError(
                f"{self.name}: its geometry was scanned from {scanned!r} and this "
                f"model serves {wanted!r}. A scan describes one file and this is "
                f"not it; re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
            )
        size_bytes = self.geometry.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
            raise UnitError(
                f"{self.name}: its geometry states no size_bytes, so it is not a "
                f"ggufscan row; re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
            )
        measured = size_bytes / _BYTES_PER_GIB
        if self.disk_gb and abs(self.disk_gb - measured) > SIZE_TOLERANCE_GB:
            raise UnitError(
                f"{self.name}: disk_gb says {self.disk_gb!r} GiB and the geometry "
                f"says {measured:.3f} GiB ({size_bytes} bytes). Each deviation "
                f"from a scan requires a new scan: drop disk_gb, or re-scan: "
                f"python -m mcgyvr.serving.ggufscan <gguf>"
            )
        object.__setattr__(self, "disk_gb", measured)
        object.__setattr__(self, "moe", bool(self.geometry.get("placeable_blocks")))


@dataclass(frozen=True)
class Width:
    """A slot count and where it came from: `written` when a unit states it, `derived`
    when the placement search settled on it, `default` otherwise."""

    value: int
    how: str


# What a Fit's notes say about host memory beyond the weights for an
# engine whose runtime-resident figure is not read here: the number is
# not measured on this machine, so none of it is charged to the sizing.
# The two sentences below are appended to it when a figure the operator
# might expect to be in play turns out not to be.
HOST_FIGURE_NOT_READ = (
    "vLLM host memory beyond the weights: not read on this machine; "
    "none is charged for it"
)

# Appended when the operator's own numbers file sets the runtime-resident
# figure for this engine: the sizing does not read that setting.
HOST_FIGURE_SETTING_NOT_USED = "your setting in {where} is not used by the sizing"

# Appended when whether the figure came from the operator cannot be read
# at all: the derived-numbers error says why in place of an answer.
HOST_FIGURE_SETTING_UNKNOWN = "whether your own numbers set it is not known: {why}"


@dataclass(frozen=True)
class Fit:
    """Whether a model fits a card, how much of the card and the host it takes if it
    does, and the sentence that says why."""

    fits: bool
    headroom_gb: float
    why: str
    # The VRAM the unit takes on its card, in GiB: vramfit's prediction at
    # the offload and slot count the placement chose, or the spec's own
    # vram_gb when there is no geometry to price it from. 0.0 on a fit that
    # failed, and for a unit that runs on the CPU.
    vram_gb: float = 0.0
    # The host RAM the unit holds, in GiB, charged as the loading mode it
    # was sized for reads it: placed.ram_gb of spilled experts when the
    # blob is read through, the whole disk_gb when it stays mapped, and
    # 0.0 when no expert block left the card, since llama.cpp then holds
    # nothing beyond the runtime this machine did not read. A media unit
    # carries the spec's own ram_gb, and a split unit's RAM is not
    # recorded at all. hold_together() sums this across the units that are
    # up on one host and refuses a set that fits only one at a time, which
    # is why the figure is the RAM actually allocated rather than the size
    # of the file.
    ram_gb: float = 0.0
    # `none` when the unit was priced as reading its blob through instead
    # of mapping it, and None when it keeps llama.cpp's default mapping.
    # _sized() sets it only after comparing both modes against the host's
    # available RAM, and unit_for() writes --load-mode into the argv when
    # it is set. A media unit never carries one.
    load_mode: str | None = None
    # The free VRAM the card had when the unit was sized, in GiB, as the
    # scan reported it. alternate() and hold_together() sum units' vram_gb
    # against it to decide whether two units can share one card, and
    # _card_free_gb() takes the smallest figure across a group of units, or
    # the largest when one of them claims its card before the others are
    # sized, since those others were then sized from a scan reduced by that
    # claim and would otherwise be counted free against it. It is 0.0 when
    # the scan read no card and for a unit that runs on the CPU, and
    # _card_free_gb() treats a group with no positive figure as unjudgeable,
    # which _co_resident() reads as fitting. A CPU-only media unit carries
    # 0.0 too, which is what keeps such a unit out of the card arithmetic
    # without a branch at every call site, and a vLLM unit carries the free
    # VRAM of the card it was placed on like any other.
    card_free_gb: float = 0.0
    # Sentences about host memory that belong beside the fit rather than in
    # it, from _host_figure_notes(): an engine whose host figure is not read
    # says so here, with what the operator's own setting for it did and did
    # not do. They are repeated inside why as well, so a caller that prints
    # only the reason still shows them.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnitKey:
    """The identity of one serving process: host, model, engine and port. Two units
    sharing a key are one process, sized and rendered as one."""

    host: str
    model: str
    engine: str
    port: int = DEFAULT_PORT

    @property
    def slug(self) -> str:
        return f"{self.host}:{self.port}/{self.model}/{self.engine}"


@dataclass(frozen=True)
class Unit:
    """One serving process as it will run: the card it lands on, the weights it loads,
    the argv that starts it, and the fit and rungs that put it there."""

    key: UnitKey
    host: str
    model: str
    engine: str
    gpu: int
    weights: Path
    width: Width
    args: Mapping[str, str]
    fit: Fit
    port: int = DEFAULT_PORT
    rungs: tuple[str, ...] = ()
    # The container image to run, when the unit's own config states one.
    # emit.py falls back to the engine's default image and refuses where it
    # has none, so this is the way in for a media server or a locally built
    # llama.cpp with rpc support.
    image: str | None = None
    extra: tuple[str, ...] = ()
    # True when the model runs on the CPU rather than on a card: a media
    # unit then lands with gpu -1 and claims no VRAM, and alternate()
    # refuses to pair a CPU unit with anything else on its host.
    cpu_only: bool = False
    # The VRAM the orchestrator unit claims on its host before anything
    # else there is sized: units_for() places it first, hands its fit to
    # _remaining_scan() so later units on that host see what is left, and
    # records the figure here so the claim is visible on the unit itself.
    resident_claim_gb: float = 0.0
    # Every card the unit holds, for a split head that spans several of
    # them; empty for a unit on one card, where gpu names it. The cards
    # property reads this first and falls back to (gpu,), so callers never
    # branch on which kind of unit they have.
    gpus: tuple[int, ...] = ()
    # What this process does in a split: `serve` for the process that
    # answers, `rpc` for a llama.cpp rpc-server worker, `headless` for a
    # vLLM rank that is not the first. emit.py checks an engine can render
    # the role, and a worker's serve_args are withheld from an rpc-server.
    role: str = ROLE_SERVE
    # Environment this process needs set for it, such as the device order
    # that keeps a card's index stable across processes.
    env: Mapping[str, str] = field(default_factory=dict)
    # True when the unit starts asleep: emit.py puts its service under the
    # sleeper profile so `serve up` does not start it, and launch_specs()
    # leaves it out of the set that has to fit the card together. Only a
    # llama.cpp unit on one card can be told to.
    asleep: bool = False

    @property
    def cards(self) -> tuple[int, ...]:
        """The cards this unit holds: its gpus when it has them, the single gpu
        otherwise."""
        return self.gpus or (self.gpu,)

    @property
    def weights_dir(self) -> Path:
        """The directory mounted as the HuggingFace cache: the weights path itself for
        vLLM and the media engines, its parent for a llama.cpp GGUF file."""
        if self.engine == "vllm" or self.engine in MEDIA_ENGINES:
            return self.weights
        return self.weights.parent


def fit(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str,
    width: int | None = None,
    ctx_per_slot: int,
) -> Fit:
    """Whether the model fits the rig as this engine would run it: media engines from
    declared figures, process engines from a placement on the freest card, with the
    host-figure notes appended to the reason."""
    if engine not in KNOWN_ENGINES:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=_engine_not_wired(spec.name, engine),
        )
    if engine in MEDIA_ENGINES:
        return _sized_media(scan, spec, engine=engine)
    sized = _sized(scan, spec, engine=engine, width=width, ctx_per_slot=ctx_per_slot)
    notes = _host_figure_notes(engine)
    if not notes:
        return sized
    said = sized.why if sized.why.endswith(".") else f"{sized.why}."
    return replace(sized, notes=notes, why=" ".join((said, *notes)))


def _host_figure_notes(engine: str) -> tuple[str, ...]:
    """The sentences to append to a fit's reason where an engine's host memory beyond
    the weights is not read here, and what the operator's own setting for it did."""
    if engine not in derived.RUNTIME_RESIDENT_READ:
        return ()
    try:
        where = derived.user_setting(derived.RUNTIME_RESIDENT, engine)
    except (derived.DerivedNumbersError, RuntimeError) as exc:
        unknown = HOST_FIGURE_SETTING_UNKNOWN.format(why=exc)
        return (f"{HOST_FIGURE_NOT_READ}; {unknown}",)
    if where is None:
        return (HOST_FIGURE_NOT_READ,)
    unused = HOST_FIGURE_SETTING_NOT_USED.format(where=where)
    return (f"{HOST_FIGURE_NOT_READ}; {unused}",)


def _sized(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str,
    width: int | None,
    ctx_per_slot: int,
) -> Fit:
    """Size a llama.cpp or vLLM unit: refuse the cases that cannot be sized at all,
    place it on the freest card, pick a loading mode, and return the Fit."""
    free_bytes = _free_vram_bytes(scan)
    free_vram = free_bytes / _BYTES_PER_GIB
    available_ram = scan.memory.available_gb if scan.memory else 0.0

    if spec.speculative == SPECULATIVE_MTP and not _mtp_head_blocks(spec):
        return Fit(fits=False, headroom_gb=DEFAULT_HEADROOM_GB, why=_no_mtp_head(spec))
    if spec.moe and spec.geometry is None:
        return Fit(
            fits=False, headroom_gb=DEFAULT_HEADROOM_GB, why=_needs_geometry(spec)
        )
    if scan.disk is not None and spec.disk_gb > scan.disk.free_gb:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {spec.disk_gb:.1f} GB of disk, "
                f"{scan.disk.free_gb:.1f} GB free at {scan.disk.path}"
            ),
        )

    try:
        placed = _placement(
            spec,
            free_bytes,
            width,
            engine=engine,
            host=scan.machine.host,
            ctx_per_slot=ctx_per_slot,
        )
    except UnitError as exc:
        return Fit(fits=False, headroom_gb=_allowance_gb(spec), why=str(exc))
    # With the model placed on the card, host RAM decides how its blob is
    # read, and the mode it is read in decides what the host is charged.
    # Left alone, llama.cpp memory-maps the file: the resident pages of a
    # mapped file count against available RAM, so a unit that keeps that
    # default wants its disk_gb held. When the host cannot hold that much,
    # the unit falls back to reading the file through with --load-mode
    # none, which holds only the expert blocks spilled off the card,
    # placed.ram_gb, in memory for real. When neither figure fits, the
    # unit is refused here with both of them side by side rather than
    # emitted for the kernel to kill part-way through loading.
    # The comparison is made only when an expert actually spills: a model
    # that fits whole holds no host RAM beyond its runtime. It is made
    # against the available RAM the scan reported, never the total, and
    # the mapped branch wins whenever it is affordable, because the page
    # cache already holds most of a blob that was just written or scanned.
    # load_mode stays None unless the unmapped branch is taken, and
    # unit_for() writes --load-mode into the argv only when it is set, so a
    # unit sized as mapped launches exactly as llama.cpp would by default
    # and one sized as unmapped says so on its command line.
    load_mode: str | None = None
    if placed.ram_gb and spec.disk_gb + MODE_RAM_HEADROOM_GB > available_ram:
        if placed.ram_gb + REFUSAL_RAM_HEADROOM_GB > available_ram:
            return Fit(
                fits=False,
                headroom_gb=DEFAULT_HEADROOM_GB,
                why=(
                    f"{spec.name}: needs {placed.ram_gb:.1f} GB of RAM for "
                    f"the experts it spills{_offload_note(spec, placed)} with "
                    f"{REFUSAL_RAM_HEADROOM_GB:.1f} GB held back, or "
                    f"{spec.disk_gb:.1f} GB to hold its blob mapped with "
                    f"{MODE_RAM_HEADROOM_GB:.1f} GB held back, against "
                    f"{available_ram:.1f} GB available. No loading mode "
                    f"fits this host"
                ),
            )
        load_mode = "none"
    if spec.geometry is None and placed.vram_gb + DEFAULT_HEADROOM_GB > free_vram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {placed.vram_gb:.1f} GB on the card plus "
                f"{DEFAULT_HEADROOM_GB:.1f} GB headroom, "
                f"{free_vram:.1f} GB free"
            ),
        )

    if spec.geometry is None:
        held = f"{DEFAULT_HEADROOM_GB:.1f} GB headroom held back"
    else:
        held = (
            f"{placed.width} slot(s) at {ctx_per_slot} context each, "
            f"{placed.headroom_gb:.2f} GB of it scratch allowance"
        )
    spilled = (
        f", {placed.ram_gb:.1f} GB of experts in RAM{_offload_note(spec, placed)}"
        if spec.moe and placed.ram_gb
        else ""
    )
    head = (
        f", {placed.head_bytes >> 20} MiB of MTP head on the card"
        if placed.head_bytes
        else ""
    )
    unmapped = (
        f", read with --load-mode none because its {spec.disk_gb:.1f} GB blob "
        f"does not fit {available_ram:.1f} GB of RAM mapped"
        if load_mode
        else ""
    )
    # What the host RAM figure on the returned Fit should be: nothing when
    # no expert is off the card, since llama.cpp then holds no more than
    # its runtime, the spilled experts alone when the unit reads unmapped,
    # and the whole blob when it stays mapped.
    if not placed.ram_gb:
        wants_ram = 0.0
    elif load_mode == "none":
        wants_ram = placed.ram_gb
    else:
        wants_ram = spec.disk_gb
    return Fit(
        fits=True,
        vram_gb=placed.vram_gb,
        ram_gb=wants_ram,
        headroom_gb=placed.headroom_gb,
        load_mode=load_mode,
        card_free_gb=free_vram,
        why=(
            f"{spec.name}: {placed.vram_gb:.1f} GB on the card of "
            f"{free_vram:.1f} GB free, {held}{head}{spilled}{unmapped}"
        ),
    )


def _sized_media(scan: Scan, spec: ModelSpec, *, engine: str) -> Fit:
    """Size a media engine from the spec's declared figures: the card holding vram_gb
    plus, for diffusers, the VAE decode spike, and the host holding ram_gb unless
    it runs on the CPU."""
    free_vram = _free_vram_bytes(scan) / _BYTES_PER_GIB
    available_ram = scan.memory.available_gb if scan.memory else 0.0
    if scan.disk is not None and spec.disk_gb > scan.disk.free_gb:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {spec.disk_gb:.1f} GB of disk, "
                f"{scan.disk.free_gb:.1f} GB free at {scan.disk.path}"
            ),
        )
    spike = spec.vae_decode_gb if engine == "diffusers" else 0.0
    peak = 0.0 if spec.cpu_only else spec.vram_gb + spike
    if not spec.cpu_only and peak + DEFAULT_HEADROOM_GB > free_vram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {peak:.1f} GB on the card plus "
                f"{DEFAULT_HEADROOM_GB:.1f} GB headroom, "
                f"{free_vram:.1f} GB free"
            ),
        )
    if spec.ram_gb > available_ram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {spec.ram_gb:.1f} GB of RAM for the "
                f"offloaded components, against {available_ram:.1f} GB available"
            ),
        )
    ram_clause = f", {spec.ram_gb:.1f} GB in RAM" if spec.ram_gb else ""
    if spec.cpu_only:
        card_clause = "runs on the CPU"
    else:
        card_clause = f"{peak:.1f} GB on the card of {free_vram:.1f} GB free"
    return Fit(
        fits=True,
        vram_gb=peak,
        ram_gb=spec.ram_gb,
        headroom_gb=0.0 if spec.cpu_only else DEFAULT_HEADROOM_GB,
        card_free_gb=0.0 if spec.cpu_only else free_vram,
        why=(f"{spec.name}: {card_clause}{ram_clause}"),
    )


def _require_cache_types(engine: str, spec: ModelSpec) -> tuple[str, str]:
    """The K and V cache dtypes the engine's cache is sized from, refusing a unit
    that states none: vLLM sizes from one dtype, so the V side comes back empty,
    while llama.cpp needs both."""
    kv_k = spec.kv_cache_dtype_k
    kv_v = spec.kv_cache_dtype_v
    if engine == "vllm":
        if kv_k is None:
            raise UnitError(
                f"{spec.name}: served by vLLM, which sizes its KV cache from "
                f"the dtype the model declares, and nothing states one — set "
                f"units.<unit>.launch.kv_cache_dtype_k (`--kv-cache-dtype`) on "
                f"the unit that serves it"
            )
        return kv_k, ""
    missing: list[str] = []
    if kv_k is None:
        missing.append("kv_cache_dtype_k (`-ctk`/`cache_type_k`)")
    if kv_v is None:
        missing.append("kv_cache_dtype_v (`-ctv`/`cache_type_v`)")
    if missing:
        raise UnitError(
            f"{spec.name}: served by llama.cpp, which sizes its cache from "
            f"the K and V dtypes the model declares, and nothing states "
            f"{' and '.join(missing)} — set them under units.<unit>.launch on "
            f"the unit that serves it"
        )
    assert kv_k is not None and kv_v is not None
    return kv_k, kv_v


def _engine_not_wired(name: str, engine: str) -> str:
    """The reason an unknown engine is refused: this build has no sizing law or launch
    spec for it, so it is named rather than sized as a text engine."""
    return (
        f"{name}: engine {engine!r} is not wired in this build; mcgyvr will not "
        "size or render a unit for an engine it has no law or launch spec for "
        "rather than apply a text engine's law or invent a number nobody measured."
    )


def unit_for(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str = DEFAULT_ENGINE,
    width: int | None = None,
    port: int = DEFAULT_PORT,
    ctx_per_slot: int,
) -> Unit:
    """Build the Unit for one model on one rig: size it, place it, and write the
    engine's argv, with the media, vLLM and llama.cpp paths each taking their
    own figures."""
    if engine not in KNOWN_ENGINES:
        raise UnitError(_engine_not_wired(spec.name, engine))
    if engine in MEDIA_ENGINES:
        if not spec.hf_cache:
            raise UnitError(
                f"{spec.name}: served by {engine}, which loads its weights from "
                f"the rig's weights directory, and nothing says where it is — "
                f"set units.<unit>.hf_cache to its absolute path on the rig"
            )
        sized = fit(scan, spec, engine=engine, width=1, ctx_per_slot=ctx_per_slot)
        if not sized.fits:
            raise UnitError(f"{scan.machine.host}: {sized.why}")
        weights = Path(spec.hf_cache)
        gpu_index = -1 if spec.cpu_only else _roomiest_gpu(scan).index
        return Unit(
            key=UnitKey(
                host=scan.machine.host, model=spec.name, engine=engine, port=port
            ),
            host=scan.machine.host,
            model=spec.name,
            engine=engine,
            gpu=gpu_index,
            weights=weights,
            width=Width(value=1, how="default"),
            args={"--model": str(weights)},
            fit=sized,
            port=port,
            rungs=(),
            extra=spec.serve_args,
            cpu_only=spec.cpu_only,
        )
    cache_type_k, cache_type_v = _require_cache_types(engine, spec)
    if engine == "vllm" and spec.speculative != SPECULATIVE_NONE:
        raise UnitError(
            f"{spec.name}: units.<unit>.launch.speculative is "
            f"{spec.speculative!r}, and this unit is served by vLLM. That key is "
            f"llama.cpp's --spec-type draft-mtp, the GGUF's own grafted head "
            f"run as the draft; vLLM's speculative decoding is "
            f"--speculative-config, a different mechanism with its own knobs "
            f"that this key does not express. Set it to none here, or serve "
            f"the model under llama.cpp"
        )
    if engine == "vllm" and not spec.hf_cache:
        raise UnitError(
            f"{spec.name}: served by vLLM, which loads a repository id from the "
            f"rig's HuggingFace cache, and nothing says where that cache is — "
            f"set units.<unit>.hf_cache to its absolute path on the rig"
        )
    sized = fit(scan, spec, engine=engine, width=width, ctx_per_slot=ctx_per_slot)
    if not sized.fits:
        raise UnitError(f"{scan.machine.host}: {sized.why}")

    gpu = _roomiest_gpu(scan)
    if engine == "vllm":
        # vLLM's slot count is --max-num-seqs: the width the unit states,
        # or this module's default when it states none. Each slot's window
        # is --max-model-len, so the cache is priced at slots x ctx_per_slot.
        if width is not None:
            seqs = Width(value=width, how="written")
        else:
            seqs = Width(value=VLLM_DEFAULT_SEQS, how="default")
        host = scan.machine.host
        return Unit(
            key=UnitKey(host=host, model=spec.name, engine=engine, port=port),
            host=host,
            model=spec.name,
            engine=engine,
            gpu=gpu.index,
            weights=Path(spec.hf_cache),
            width=seqs,
            args={
                "--max-num-seqs": str(seqs.value),
                "--max-model-len": str(ctx_per_slot),
                "--kv-cache-dtype": cache_type_k,
            },
            fit=sized,
            port=port,
            rungs=(),
            extra=spec.serve_args,
        )
    # Placed a second time to get what the argv needs from it: the
    # --n-cpu-moe floor and the slot count. It is the same card and the
    # same figures the fit used, so this placement cannot refuse.
    placed = _placement(
        spec,
        gpu.vram.free_mib << 20,
        width,
        engine=engine,
        host=scan.machine.host,
        ctx_per_slot=ctx_per_slot,
    )
    if width is not None:
        chosen = Width(value=width, how="written")
    elif spec.geometry is not None:
        chosen = Width(value=placed.width, how="derived")
    else:
        chosen = Width(value=placed.width, how="default")
    weights = _weights_path(scan, spec)

    # The llama.cpp argv: the weights path, every layer on the card
    # (-ngl 99), one window per slot across the slots (-c slots x
    # ctx_per_slot) with --parallel set to the slot count, the micro-batch
    # and physical batch both at DEFAULT_UBATCH, flash attention on, the
    # scan's physical cores as threads, and the K and V cache dtypes the
    # cache was priced at.
    args: dict[str, str] = {
        "--model": str(weights),
        "-ngl": "99",
        "-c": str(ctx_per_slot * chosen.value),
        "-ub": str(DEFAULT_UBATCH),
        "-b": str(DEFAULT_UBATCH),
        "-fa": "on",
        "--parallel": str(chosen.value),
        "-t": str(_threads(scan)),
        "-ctk": cache_type_k,
        "-ctv": cache_type_v,
    }
    # The expert blocks kept off the card, when any had to be: --n-cpu-moe
    # appears only when the placement spilled, so a model that fits whole
    # is launched with no such flag rather than with a zero. A model with
    # no geometry never spills, since nothing could be said about blocks.
    if placed.n_cpu_moe > 0:
        args["--n-cpu-moe"] = str(placed.n_cpu_moe)
    # The grafted MTP head as the draft, when the model declares one: the
    # type is llama.cpp's draft-mtp and the width is the tokens per step
    # the spec states. Nothing is written for speculative: none, which is
    # the engine's own default.
    if spec.speculative == SPECULATIVE_MTP:
        args["--spec-type"] = "draft-mtp"
        args["--spec-draft-n-max"] = str(spec.spec_draft_n_max)
    # The loading mode, when _sized() chose one: --load-mode none tells
    # llama.cpp to read the blob through instead of mapping it, which is
    # what the fit's RAM figure was charged for. Unset, the engine maps
    # the file as it does by default and the host is charged disk_gb for
    # it instead.
    if sized.load_mode is not None:
        args["--load-mode"] = sized.load_mode

    return Unit(
        key=UnitKey(host=scan.machine.host, model=spec.name, engine=engine, port=port),
        host=scan.machine.host,
        model=spec.name,
        engine=engine,
        gpu=gpu.index,
        weights=weights,
        width=chosen,
        args=args,
        fit=sized,
        port=port,
        rungs=(),
        extra=spec.serve_args,
    )


def units_for(
    config: Config,
    scans: Mapping[str, Scan],
    *,
    specs: Iterable[ModelSpec],
    ctx_per_slot: int | None,
) -> tuple[Unit, ...]:
    """Build every Unit the config's ladder and its role units need, one process per
    key, from the scans and the model catalogue, refusing what cannot be sized."""
    if ctx_per_slot is not None and ctx_per_slot < 1:
        raise UnitError(
            f"the declared context window is {ctx_per_slot}, which is not a "
            f"window: a slot serves at least one token"
        )
    # The catalogue the config's models are looked up in: the shipped
    # specs a caller passes in, with the models the config declares on its
    # own units layered over them, so a unit's launch block wins.
    catalogue = {spec.name: spec for spec in specs} | declared_models(config)
    grouped: dict[UnitKey, list[str]] = {}
    hosts: dict[UnitKey, Scan] = {}
    models: dict[UnitKey, ModelSpec] = {}
    widths: dict[UnitKey, int] = {}
    images: dict[UnitKey, str | None] = {}
    # The context windows declared per process, by key: a window is
    # stated per unit, so two units behind one address that state
    # different ones are an error rather than a silent choice.
    windows: dict[UnitKey, dict[int, list[str]]] = {}
    # The launch block of any unit that splits its process across cards.
    splits: dict[UnitKey, dict[str, Any]] = {}
    # The roles declared per process, so one process stating two is caught.
    roles: dict[UnitKey, dict[str, list[str]]] = {}

    users = config.get("users", 1)
    # Whether this config provisions its own orchestrator: local-only, a
    # use case that has one, and a user count. It decides whether the
    # orchestrator's unit is served here and sized at the user count.
    provision = config.provisions_local_orchestrator

    def _local(name: str | None) -> bool:
        unit = config.units.get(name) if name else None
        return unit is not None and not unit.requires_credential

    # The rungs the ladder serves, plus the unit of a locally provisioned
    # orchestrator when the ladder does not already name it. Each name
    # must resolve to a unit with a scanned host and a known model spec,
    # or nothing is emitted at all.
    served = list(config.ladder.names)
    orchestrator_name = config.get("orchestrator.unit")
    if (
        provision
        and orchestrator_name
        and _local(orchestrator_name)
        and orchestrator_name not in served
    ):
        served.append(orchestrator_name)
    role_extra: list[str] = []
    verifier_name = (
        config.get("verifier.unit") if config.get("verifier.enabled") else None
    )
    if verifier_name and _local(verifier_name) and verifier_name not in served:
        role_extra.append(verifier_name)
    jev_name = config.get("jev.unit")
    if (
        jev_name
        and _local(jev_name)
        and jev_name not in served
        and jev_name not in role_extra
    ):
        role_extra.append(jev_name)

    orchestrator_key: UnitKey | None = None
    for name in (*served, *role_extra):
        unit = config.units.get(name)
        if unit is None:
            raise UnitError(f"{name}: no unit named {name!r}")
        host = host_of(unit.address)
        scan = scans.get(host)
        if scan is None:
            raise UnitError(
                f"{name}: host {host!r} is unscanned — "
                f"run `mcgyvr scan` on {host} before emitting a unit for it"
            )
        spec = catalogue.get(unit.model)
        if spec is None:
            raise UnitError(
                f"{name}: no model spec for {unit.model!r} — it is not in "
                f"the shipped capability table or model catalog, and nothing "
                f"declares it under `launch` in fleet.yaml. Sizing a unit "
                f"needs what the model costs, and mcgyvr will not invent "
                f"that; state it and this model is served on your numbers"
            )

        key = UnitKey(
            host=host,
            model=spec.name,
            # A unit with no engine stated is served by the default engine.
            # The key keeps the engine, so two engines on one port differ.
            engine=unit.engine or DEFAULT_ENGINE,
            port=port_of(unit.address),
        )
        if provision and name == orchestrator_name:
            orchestrator_key = key
        grouped.setdefault(key, []).append(name)
        roles.setdefault(key, {}).setdefault(unit.role, []).append(name)
        if unit.window is not None:
            windows.setdefault(key, {}).setdefault(unit.window, []).append(name)
        hosts.setdefault(key, scan)
        models.setdefault(key, spec)
        images.setdefault(key, unit.image)
        if unit.width is not None:
            # Units naming one process may each state a width: the widest
            # wins, so the process is sized for the slots they all ask for.
            widths[key] = max(widths.get(key, 0), unit.width)
        elif provision and name == orchestrator_name and _local(orchestrator_name):
            # The orchestrator's own width is the user count this
            # deployment provisions for, when its unit states none.
            widths[key] = max(widths.get(key, 0), users)
        if SHARDS_KEY in unit.launch:
            # The launch block of a unit that splits its process, kept per
            # process; a second unit stating a different one is an error.
            stated = dict(unit.launch)
            first = splits.setdefault(key, stated)
            if first != stated:
                raise UnitError(
                    f"{name}: names the process {key.slug}, which another unit "
                    f"declares with a different launch; one process is split "
                    f"one way"
                )

    def _sized(
        key: UnitKey,
        rungs: list[str],
        scan: Scan,
        reduced: Mapping[str, Scan],
    ) -> list[Unit]:
        """The Units one process becomes: a split's head and workers, or a single unit,
        carrying the rungs that need it and the image its units stated."""
        window = _window_for(key, windows.get(key, {}), ctx_per_slot)
        if key in splits:
            head, *workers = _sharded_units(
                config,
                reduced,
                models[key],
                key=key,
                launch=splits[key],
                width=widths.get(key),
                ctx_per_slot=window,
            )
            return [
                replace(head, rungs=tuple(rungs), image=images[key]),
                *(replace(worker, image=images[key]) for worker in workers),
            ]
        return [
            replace(
                _with_rungs(
                    unit_for(
                        scan,
                        models[key],
                        engine=key.engine,
                        width=widths.get(key),
                        port=key.port,
                        ctx_per_slot=window,
                    ),
                    tuple(rungs),
                ),
                image=images[key],
            )
        ]

    asleep = {
        key: _starts_asleep(key, stated, key in splits) for key, stated in roles.items()
    }

    # The orchestrator is sized first so its claim on its host's card is
    # subtracted before anything else there is sized; the rest keep the
    # order the config listed them in.
    ordered = list(grouped.items())
    ordered.sort(key=lambda pair: pair[0] != orchestrator_key)
    built: list[Unit] = []
    claimed: dict[str, float] = {}
    reduced = dict(scans)
    for key, rungs in ordered:
        scan = hosts[key]
        if key.host in claimed:
            scan = _remaining_scan(scan, claimed[key.host])
            reduced[key.host] = scan
        sized = _sized(key, rungs, scan, reduced)
        if asleep[key]:
            sized[0] = replace(sized[0], asleep=True)
        if key == orchestrator_key:
            claimed[key.host] = sized[0].fit.vram_gb
            sized[0] = replace(sized[0], resident_claim_gb=sized[0].fit.vram_gb)
        built.extend(sized)
    return tuple(built)


def _starts_asleep(key: UnitKey, stated: Mapping[str, list[str]], split: bool) -> bool:
    """Whether this process starts asleep, from the roles its units state: only a
    llama.cpp unit on one card can, since its sleep is its container stopping."""
    if len(stated) > 1:
        said = "; ".join(
            f"{role} ({', '.join(names)})" for role, names in sorted(stated.items())
        )
        raise UnitError(
            f"{key.slug} is one process and its units state two roles: {said}"
        )
    if ROLE_SLEEPER not in stated:
        return False
    names = ", ".join(stated[ROLE_SLEEPER])
    if key.engine != DEFAULT_ENGINE:
        raise UnitError(
            f"{names}: role {ROLE_SLEEPER} is for llama.cpp units, whose sleep is "
            f"a stop of their container; a {key.engine} unit is not started "
            "asleep (vLLM sleeps at level 2 with its process kept)"
        )
    if split:
        raise UnitError(
            f"{names}: role {ROLE_SLEEPER} is for a unit on one card; a unit "
            "split across cards is several processes and is not started asleep"
        )
    return True


def _sharded_units(
    config: Config,
    scans: Mapping[str, Scan],
    spec: ModelSpec,
    *,
    key: UnitKey,
    launch: Mapping[str, Any],
    width: int | None,
    ctx_per_slot: int,
) -> tuple[Unit, ...]:
    """Split one model across the cards a shard list names: size the grid, launch it
    through shardlaunch, and return one Unit per process it starts."""
    from mcgyvr.serving import sharding, shardlaunch

    engine = key.engine
    cache_type_k, cache_type_v = _require_cache_types(engine, spec)
    if spec.speculative != SPECULATIVE_NONE:
        raise UnitError(
            f"{spec.name}: declares speculative {spec.speculative!r} and a split "
            f"across cards; a split is sized with every block on its cards and "
            f"no draft head, so the two are not combined"
        )
    targets = _shard_targets(spec.name, launch.get(SHARDS_KEY), scans)
    if targets[0].host.lower() != key.host.lower():
        raise UnitError(
            f"{spec.name}: its first shard is on {targets[0].host} and its address "
            f"is on {key.host}; the first card a unit names is one of the machine "
            f"its address points at, where the serving process runs"
        )
    head_scan = scans[key.host]
    if engine == "vllm":
        if not spec.hf_cache:
            raise UnitError(
                f"{spec.name}: served by vLLM, which loads a repository id from "
                f"the rig's HuggingFace cache, and nothing says where that cache "
                f"is — set units.<unit>.hf_cache to its absolute path on the rig"
            )
        table = _tensor_table(config, spec.name, launch.get("tensor_table_json"))
        weights = Path(spec.hf_cache)
        slots = Width(value=width or VLLM_DEFAULT_SEQS, how=_how(width))
    else:
        if spec.geometry is None:
            raise UnitError(_needs_geometry(spec))
        table = spec.geometry
        weights = _weights_path(head_scan, spec)
        slots = Width(value=width or 1, how=_how(width))
    if head_scan.disk is not None and spec.disk_gb > head_scan.disk.free_gb:
        raise UnitError(
            f"{spec.name}: needs {spec.disk_gb:.1f} GB of disk, "
            f"{head_scan.disk.free_gb:.1f} GB free at {head_scan.disk.path}"
        )
    try:
        plan = sharding.choose(
            table,
            targets,
            engine=engine,
            slots=slots.value,
            ctx_per_slot=ctx_per_slot,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            n_ubatch=DEFAULT_UBATCH,
            name=spec.name,
            split=_stated_text(spec.name, launch, "split"),
            tensor=_stated_count(spec.name, launch, "tensor_parallel"),
            pipeline=_stated_count(spec.name, launch, "pipeline_parallel"),
        )
        launched = shardlaunch.processes(
            plan,
            model=spec.name,
            weights=weights,
            port=key.port,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
            threads=_threads(head_scan),
            n_ubatch=DEFAULT_UBATCH,
            rpc_port=_stated_count(spec.name, launch, "rpc_port") or RPC_DEFAULT_PORT,
            master_port=_stated_count(spec.name, launch, "master_port")
            or VLLM_MASTER_PORT,
        )
    except (sharding.ShardingError, shardlaunch.LaunchError) as exc:
        raise UnitError(str(exc)) from exc
    notes = _host_figure_notes(engine)
    allowance = plan.shards[0].allowance_bytes / _BYTES_PER_GIB
    units: list[Unit] = []
    for process in launched:
        held = process.shards
        said = f"{spec.name}: split across cards, {plan.says()}"
        units.append(
            Unit(
                key=UnitKey(
                    host=process.host, model=spec.name, engine=engine, port=process.port
                ),
                host=process.host,
                model=spec.name,
                engine=engine,
                gpu=process.gpus[0],
                weights=weights,
                width=slots,
                args=process.args,
                fit=Fit(
                    fits=True,
                    headroom_gb=allowance,
                    why=" ".join((said, *notes)),
                    vram_gb=max(s.required_bytes for s in held) / _BYTES_PER_GIB,
                    card_free_gb=min(s.target.free_bytes for s in held)
                    / _BYTES_PER_GIB,
                    notes=notes,
                ),
                port=process.port,
                rungs=(),
                extra=(
                    (*process.extra, *spec.serve_args)
                    if process.role != ROLE_RPC
                    else process.extra
                ),
                gpus=process.gpus,
                role=process.role,
                env=dict(process.env),
            )
        )
    return tuple(units)


def _how(width: int | None) -> str:
    return "written" if width is not None else "default"


def _shard_targets(name: str, declared: object, scans: Mapping[str, Scan]) -> list[Any]:
    """The scanned cards a launch.shards list names, refusing an entry that is not a
    card, a host that was never scanned, or a card the scan does not have."""
    from mcgyvr.fleet.spans import SpanError, parse_shard
    from mcgyvr.serving.sharding import Target

    if not isinstance(declared, list) or not declared:
        raise UnitError(
            f"{name}: launch.{SHARDS_KEY} is {declared!r}; it is a list of the "
            f"cards the unit is split across, each `{{rig: <host>, gpu: <index>}}`, "
            f"the first on the machine the unit's address points at"
        )
    targets = []
    for index, entry in enumerate(declared):
        where = f"{name}: launch.{SHARDS_KEY}[{index}]"
        try:
            shard = parse_shard(name, index, entry)
        except SpanError as exc:
            raise UnitError(str(exc)) from exc
        rig, gpu, bind = shard.rig, shard.gpu, shard.bind
        scan = scans.get(rig)
        if scan is None:
            raise UnitError(
                f"{where}: host {rig!r} is unscanned — run `mcgyvr scan` on "
                f"{rig} before splitting a unit across its cards"
            )
        card = next((g for g in scan.gpus if g.index == gpu), None)
        if card is None:
            found = ", ".join(str(g.index) for g in scan.gpus) or "none"
            raise UnitError(
                f"{where}: {rig} has no card {gpu} in its scan (cards: {found})"
            )
        targets.append(
            Target(host=rig, gpu=gpu, free_bytes=card.vram.free_mib << 20, bind=bind)
        )
    return targets


def _stated_count(name: str, launch: Mapping[str, Any], field_name: str) -> int | None:
    """A positive integer a unit's launch block states, or None when it states nothing,
    refusing anything that is not a count."""
    stated = launch.get(field_name)
    if stated is None:
        return None
    if isinstance(stated, bool) or not isinstance(stated, int) or stated < 1:
        raise UnitError(f"{name}: launch.{field_name} is {stated!r}, not a count")
    return stated


def _stated_text(name: str, launch: Mapping[str, Any], field_name: str) -> str | None:
    stated = launch.get(field_name)
    if stated is None or isinstance(stated, str):
        return stated
    raise UnitError(f"{name}: launch.{field_name} is {stated!r}, not a word")


def _tensor_table(config: Config, name: str, stated: object) -> Mapping[str, Any]:
    """The one safetensorscan row a vLLM split is sized from, read from
    launch.tensor_table_json and refused when the path is missing, unreadable, or
    an error row."""
    if not isinstance(stated, str) or not stated:
        raise UnitError(
            f"{name}: a vLLM unit split across cards is sized from its tensor "
            f"table, and launch.tensor_table_json names none. Run python -m "
            f"mcgyvr.serving.safetensorscan <model dir> where the weights are "
            f"and point launch.tensor_table_json at what it printed"
        )
    where = Path(stated).expanduser()
    if not where.is_absolute() and config.path is not None:
        where = config.path / where
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnitError(f"{where}: cannot read a tensor table from it: {exc}") from exc
    rows = raw if isinstance(raw, list) else [raw]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise UnitError(
            f"{where}: holds {len(rows)} rows; a vLLM unit's tensor table is one "
            f"safetensorscan row"
        )
    if "error" in rows[0]:
        raise UnitError(
            f"{where}: the scan could not read {rows[0].get('file')!r}: "
            f"{rows[0]['error']}"
        )
    table: dict[str, Any] = rows[0]
    return table


def alternate(one: Unit, other: Unit) -> bool:
    """Whether two units are alternatives on one host: the same port, or sharing a card
    whose free VRAM cannot hold them both summed."""
    if one.host != other.host:
        return False
    if one.port == other.port:
        return True
    if one.cpu_only or other.cpu_only:
        # A CPU unit holds no card on this host, so it alternates with nothing.
        return False
    shared = set(one.cards) & set(other.cards)
    if shared and (len(one.cards) > 1 or len(other.cards) > 1):
        return True
    if not shared:
        # No shared card and neither of them split: they run side by side
        # on different cards of one host, so one is no alternative to the
        # other and both stay up.
        return False
    free = _card_free_gb((one, other))
    if free <= 0:
        return False
    return one.fit.vram_gb + other.fit.vram_gb > free


def _card_free_gb(units: Iterable[Unit]) -> float:
    """The free VRAM to judge a group of units against: the smallest figure they report,
    or the largest when one of them claims its card before the others are sized."""
    figures = [unit.fit.card_free_gb for unit in units if unit.fit.card_free_gb > 0]
    if not figures:
        return 0.0
    if any(unit.resident_claim_gb > 0 for unit in units):
        return max(figures)
    return min(figures)


def _co_resident(chosen: tuple[Unit, ...], candidate: Unit) -> bool:
    """Whether a candidate unit can be up alongside those already chosen: no alternative
    to any of them, and room on its card for all of them summed."""
    if any(alternate(unit, candidate) for unit in chosen):
        return False
    sharing = tuple(unit for unit in chosen if unit.gpu == candidate.gpu)
    free = _card_free_gb((*sharing, candidate))
    if free <= 0:
        return True
    asked = candidate.fit.vram_gb + sum(unit.fit.vram_gb for unit in sharing)
    return asked <= free


@dataclass(frozen=True)
class LaunchSpec:
    """One compose file's worth of units on one host, named by its model when the host's
    units had to be cut into alternatives."""

    host: str
    units: tuple[Unit, ...]
    model: str | None = None


def launch_specs(units: Iterable[Unit]) -> tuple[LaunchSpec, ...]:
    """Split the units into one spec per compose file: on each host the units that can
    be up together, or one spec per alternative when they cannot all fit."""
    on_host: dict[str, list[Unit]] = {}
    for unit in units:
        on_host.setdefault(unit.host, []).append(unit)

    specs: list[LaunchSpec] = []
    for host in sorted(on_host):
        here = tuple(
            sorted(on_host[host], key=lambda unit: (-unit.fit.vram_gb, unit.key.slug))
        )
        awake = tuple(unit for unit in here if not unit.asleep)
        if awake and len(awake) < len(here):
            # Units that start asleep are not part of what has to fit the
            # card together, but they are written into this host's file.
            # When the awake ones fit as a set, the whole host stays one
            # spec and the sleepers keep the profile that keeps them down.
            awake_sets = _feasible(awake)
            if len(awake_sets) == 1 and len(awake_sets[0]) == len(awake):
                specs.append(
                    LaunchSpec(
                        host=host,
                        units=tuple(sorted(here, key=lambda unit: unit.key.slug)),
                    )
                )
                continue
            # The awake units do not fit as a set either, so every unit on
            # the host counts as up and the host is cut into alternatives.
            here = tuple(replace(unit, asleep=False) for unit in here)
        sets = _feasible(here)
        if len(sets) == 1 and len(sets[0]) == len(here):
            specs.append(LaunchSpec(host=host, units=sets[0]))
            continue
        for name, chosen in zip(_named(sets), sets, strict=True):
            specs.append(LaunchSpec(host=host, units=chosen, model=name))
    return tuple(specs)


def _feasible(here: tuple[Unit, ...]) -> tuple[tuple[Unit, ...], ...]:
    """Every set of units that can be up together on one host, taken by anchoring each
    unit in turn and adding each other that co-resides with what is chosen so far."""
    found: dict[tuple[str, ...], tuple[Unit, ...]] = {}
    for anchor in here:
        chosen: tuple[Unit, ...] = (anchor,)
        for other in here:
            if other.key == anchor.key:
                continue
            if _co_resident(chosen, other):
                chosen = (*chosen, other)
        settled = tuple(sorted(chosen, key=lambda unit: unit.key.slug))
        found.setdefault(tuple(unit.key.slug for unit in settled), settled)
    return tuple(found.values())


def _named(sets: tuple[tuple[Unit, ...], ...]) -> tuple[str, ...]:
    """A name per alternative spec that no other spec on the host shares: its largest
    unit's model, else every model it holds, else those plus its ports."""

    def defining(chosen: tuple[Unit, ...]) -> str:
        return max(chosen, key=lambda unit: (unit.fit.vram_gb, unit.key.slug)).model

    def every_model(chosen: tuple[Unit, ...]) -> str:
        return "_".join(sorted({unit.model for unit in chosen}))

    def with_ports(chosen: tuple[Unit, ...]) -> str:
        ports = "-".join(str(port) for port in sorted(unit.port for unit in chosen))
        return f"{every_model(chosen)}.{ports}"

    for spell in (defining, every_model, with_ports):
        names = tuple(spell(chosen) for chosen in sets)
        if len(set(names)) == len(names):
            return names
    # No spelling told the sets apart, and two specs named alike would be
    # written to one file, the later overwriting the earlier. Refused on
    # the host that has the clash, naming it, rather than emitted to
    # collide there.
    raise UnitError(
        f"{sets[0][0].host}: two launch specs cannot be told apart by the "
        f"models and ports they hold, so they would be written to one file"
    )


def hold_together(units: Iterable[Unit], scans: Mapping[str, Scan]) -> tuple[str, ...]:
    """The warnings and refusals for units sharing a host: alternatives when they
    cannot all sum onto the card, and an error when those that are up do not fit
    card or host memory together."""
    warnings: list[str] = []
    for host, cut in _cut_into_alternatives(units).items():
        listed = ", ".join(
            f"{name} ({spec_name(host, name)})" for name in sorted(cut.keys())
        )
        warnings.append(
            f"{host}: {listed} do not sum onto the card and were emitted as "
            f"{len(cut)} alternatives — one launch spec each, and only one of "
            f"them is ever up. `serve up` takes one file, and mcgyvr will not "
            f"guess which: bring the one you mean up, and delete the "
            f"{spec_name(host)} an earlier emit may have left behind"
        )
    for spec in launch_specs(units):
        if len(spec.units) < 2 or spec.host not in scans:
            continue
        scan = scans[spec.host]
        free = _free_vram_bytes(scan) / _BYTES_PER_GIB
        on_card: dict[int, list[Unit]] = {}
        # Only the units that are up hold memory: a sleeper's figures were
        # charged for the file it would occupy, not for a running server.
        up = tuple(unit for unit in spec.units if not unit.asleep)
        for unit in up:
            on_card.setdefault(unit.gpu, []).append(unit)
        for sharing in on_card.values():
            if len(sharing) < 2:
                continue
            worst = sorted(sharing, key=lambda unit: unit.key.slug)
            asked = sum(unit.fit.vram_gb for unit in worst)
            if asked > free:
                listed = ", ".join(
                    f"{unit.model} ({unit.fit.vram_gb:.2f} GB)" for unit in worst
                )
                raise UnitError(
                    f"{spec.host}: {listed} fit the card one at a time and not "
                    f"together — {asked:.2f} GB summed against {free:.2f} GB "
                    f"free. Drop a unit, or state a smaller working set you "
                    f"have measured"
                )
        memory = scan.memory
        if memory is None:
            # A scan with no host memory reading cannot say whether these
            # units fit in RAM together; the card check above still stands,
            # and nothing is guessed here about a figure nobody read.
            continue
        hungriest = sorted(up, key=lambda unit: unit.key.slug)
        wanted = sum(unit.fit.ram_gb for unit in hungriest)
        # The margin host memory is judged with: the same refusal headroom
        # _sized() holds back, because these are process engines whose
        # spilled experts are really allocated, and none at all for a set
        # of media units, whose declared figures are already the whole of
        # what they hold.
        margin = (
            REFUSAL_RAM_HEADROOM_GB
            if any(unit.engine not in MEDIA_ENGINES for unit in hungriest)
            else 0.0
        )
        if wanted and wanted + margin > memory.available_gb:
            listed = ", ".join(
                f"{unit.model} ({unit.fit.ram_gb:.2f} GB "
                f"{'unmapped' if unit.fit.load_mode == 'none' else 'mapped'})"
                for unit in hungriest
                if unit.fit.ram_gb
            )
            margin_clause = f" with {margin:.1f} GB held back" if margin else ""
            raise UnitError(
                f"{spec.host}: {listed} fit host memory one at a time and not "
                f"together — {wanted:.2f} GB summed{margin_clause}, against "
                f"{memory.available_gb:.2f} GB available. Serve one of them "
                f"from another host, drop one, or narrow a window"
            )
    return tuple(warnings)


def _cut_into_alternatives(units: Iterable[Unit]) -> dict[str, dict[str, None]]:
    """The alternative spec names per host, from the specs launch_specs() had to name
    because their units would not all fit."""
    specs = launch_specs(units)
    named: dict[str, dict[str, None]] = {}
    for spec in specs:
        if spec.model is None:
            continue
        named.setdefault(spec.host, {})[spec.model] = None
    return named


def safe_host(host: str) -> str:
    """A host name that can be used as a file name: an IPv6 address compressed and
    hyphenated, and anything else refused rather than mangled."""
    address = _ipv6(host)
    if address is not None:
        return _UNSAFE.sub("-", address)
    if not host or host != _UNSAFE.sub("-", host) or host in {".", ".."}:
        raise UnitError(f"{host!r} is not a host name a file can be named after")
    return host


def safe_model(model: str) -> str:
    """A model name reduced to what a file name can carry: unsafe runs hyphenated, and
    an empty, dot or all-hyphen result refused."""
    name = _UNSAFE.sub("-", model)
    if not name or name in {".", ".."} or set(name) <= {"-"}:
        raise UnitError(f"{model!r} is not a model name a file can be named after")
    return name


def _ipv6(host: str) -> str | None:
    """The compressed form of the host when it is an IPv6 address, and None when it is
    not."""
    try:
        return ipaddress.IPv6Address(host).compressed
    except ValueError:
        return None


def spec_name(host: str, model: str | None = None) -> str:
    """The compose file name for a host, and for one of its alternative specs when a
    model is named."""
    stem = (
        safe_host(host) if model is None else f"{safe_host(host)}.{safe_model(model)}"
    )
    return f"{COMPOSE_PREFIX}{stem}{COMPOSE_SUFFIX}"


def spec_files(root: Path, host: str) -> tuple[Path, ...]:
    """Every compose file for a host under root: its whole-host file and the per-model
    alternatives beside it."""
    try:
        whole = spec_name(host)
    except UnitError:
        # An address no file can be named after has no specs: a host a
        # caller asked about, not one this module failed on.
        return ()
    prefix = f"{whole[: -len(COMPOSE_SUFFIX)]}."
    try:
        found = [
            path
            for path in root.iterdir()
            if path.is_file()
            and path.name.endswith(COMPOSE_SUFFIX)
            and (path.name == whole or path.name.startswith(prefix))
        ]
    except OSError:
        return ()
    return tuple(sorted(found))


@dataclass(frozen=True)
class Card:
    """What the compose directory holds for one host, and the rungs served on it."""

    host: str
    # The whole-host compose file, compose.<host>.yml, built from
    # serving.compose_dir when the config states one: the file `serve up`
    # takes to bring up everything the host serves at once. It is None
    # when no directory is stated, so nothing here claims a file was
    # written. Paths are built rather than read, and whether a file of
    # that name is on disk is what the specs below report, so a caller
    # checks before taking this as the host's own launch. wake.py does
    # exactly that: it reads a file here only when it is in specs, and
    # otherwise asks which of the alternatives to use.
    compose_file: Path | None
    # The per-model alternatives found in that directory:
    # compose.<host>.<model>.yml, one per alternative launch spec, taken
    # as the file to use when the whole-host one is absent.
    specs: tuple[Path, ...] = ()
    # The ladder rungs whose unit's address points at this host, sorted:
    # several rungs can be served by one process on one machine, and they
    # are what a wake or sleep here acts on.
    rungs: tuple[str, ...] = ()
    # The same names as a set, for the callers that want the units behind
    # this host's card once each rather than in ladder order.
    sources: tuple[str, ...] = ()


def cards(config: Config) -> dict[str, Card]:
    """The Card for each rung, keyed by rung name: which compose files its host's
    directory holds and which rungs that host serves."""
    stated = config.get("serving.compose_dir")
    where = Path(str(stated)).expanduser() if stated else None

    rungs_on: dict[str, list[str]] = {}
    sources_on: dict[str, set[str]] = {}
    hosted: dict[str, str] = {}
    for name in config.ladder.names:
        unit = config.units.get(name)
        if unit is None or unit.requires_credential:
            continue
        host = host_of(unit.address)
        hosted[name] = host
        rungs_on.setdefault(host, []).append(name)
        sources_on.setdefault(host, set()).add(name)

    by_host = {
        host: Card(
            host=host,
            compose_file=where / spec_name(host) if where else None,
            specs=spec_files(where, host) if where else (),
            rungs=tuple(sorted(rungs_on[host])),
            sources=tuple(sorted(sources_on[host])),
        )
        for host in rungs_on
    }
    return {rung: by_host[host] for rung, host in hosted.items()}


def declared_models(config: Config) -> dict[str, ModelSpec]:
    """The ModelSpecs built from the units' own launch blocks, for models the shipped
    catalogue does not know; a unit that states no cost of its own declares nothing."""
    specs: dict[str, ModelSpec] = {}
    for unit in config.units.values():
        name = unit.model
        if name in specs:
            continue
        if (
            not unit.launch
            and unit.hf_cache is None
            and unit.room_mib is None
            and unit.kv_cache_memory_bytes is None
        ):
            # A unit that states no cost of its own declares no model here.
            continue
        block: dict[str, Any] = dict(unit.launch)
        if unit.hf_cache is not None:
            block.setdefault("hf_cache", unit.hf_cache)
        if unit.room_mib is not None and "vram_gb" not in block:
            block["vram_gb"] = unit.room_mib / 1024
        geometry: dict[str, Any] | None = None
        stated = block.get("geometry_json")
        if stated:
            where = Path(str(stated)).expanduser()
            if not where.is_absolute() and config.path is not None:
                where = config.path / where
            geometry = load_geometry(where, name=name)
        specs[name] = ModelSpec(
            name=name,
            vram_gb=block.get("vram_gb") or 0.0,
            ram_gb=block.get("ram_gb") or 0.0,
            disk_gb=block.get("disk_gb") or 0.0,
            vae_decode_gb=block.get("vae_decode_gb") or 0.0,
            cpu_only=bool(block.get("cpu_only")),
            moe=bool(block.get("moe")),
            geometry=geometry,
            hf_cache=str(block.get("hf_cache") or ""),
            serve_args=tuple(str(arg) for arg in (block.get("serve_args") or ())),
            kv_cache_dtype_k=block.get("kv_cache_dtype_k"),
            kv_cache_dtype_v=block.get("kv_cache_dtype_v"),
            speculative=str(block.get("speculative") or SPECULATIVE_NONE),
            spec_draft_n_max=_declared_draft_width(name, block.get("spec_draft_n_max")),
        )
    return specs


def _declared_draft_width(name: str, stated: object) -> int:
    """The --spec-draft-n-max a unit states, defaulted when it states none and refused
    when it is not a count."""
    if stated is None:
        return DEFAULT_SPEC_DRAFT_N_MAX
    if isinstance(stated, bool) or not isinstance(stated, int):
        raise UnitError(
            f"{name}: units.<unit>.launch.spec_draft_n_max is {stated!r}, and "
            f"--spec-draft-n-max is a count of tokens drafted per step"
        )
    return stated


# The keys a ggufscan row must carry to be sized from: everything vramfit
# reads to price expert blocks, the cache, the recurrent state and the head.
_GEOMETRY_KEYS = (
    "file",
    "size_bytes",
    "n_layer",
    "bytes_nonexpert",
    "bytes_experts",
    "placeable_blocks",
    "expert_bytes_by_block",
    "kv_layers",
)


def load_geometry(path: Path | str, *, name: str | None = None) -> dict[str, Any]:
    """One ggufscan row read from a JSON file: the single row it holds, or the row
    scanned from the file the named model serves, refusing an error row or one
    missing what sizing needs."""
    where = Path(path)
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnitError(f"{where}: cannot read a geometry from it: {exc}") from exc

    if isinstance(raw, dict):
        rows: list[Any] = [raw]
    elif isinstance(raw, list):
        rows = raw
    else:
        raise UnitError(
            f"{where}: a geometry is one ggufscan row or a list of them, and this "
            f"is {type(raw).__name__}; re-scan: python -m mcgyvr.serving.ggufscan "
            f"<gguf>"
        )
    if not rows:
        raise UnitError(f"{where}: holds no geometry rows at all")
    if len(rows) == 1:
        row = rows[0]
    elif name is None:
        raise UnitError(
            f"{where}: holds {len(rows)} geometry rows and nothing says which "
            f"model to choose one for"
        )
    else:
        wanted = _weights_file_name(name)
        matched = [
            r
            for r in rows
            if isinstance(r, dict) and Path(str(r.get("file") or "")).name == wanted
        ]
        if len(matched) != 1:
            raise UnitError(
                f"{where}: {len(matched)} of {len(rows)} geometry rows were "
                f"scanned from {wanted!r}, and {name} needs exactly one"
            )
        row = matched[0]

    if not isinstance(row, dict):
        raise UnitError(f"{where}: a geometry row is a mapping, found {row!r}")
    if "error" in row:
        raise UnitError(
            f"{where}: ggufscan could not read {row.get('file')!r}: "
            f"{row['error']}. Nothing is sized from an error row; fix the file "
            f"and re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
        )
    missing = [key for key in _GEOMETRY_KEYS if key not in row]
    if missing:
        raise UnitError(
            f"{where}: not a ggufscan row — it has no {', '.join(missing)}; "
            f"re-scan: python -m mcgyvr.serving.ggufscan <gguf>"
        )
    geometry: dict[str, Any] = row
    return geometry


def host_of(base_url: str) -> str:
    """The host part of a unit address, refused when the address names none."""
    host = urlparse(base_url).hostname
    if not host:
        raise UnitError(f"no host in `units.<unit>.address` {base_url!r}")
    return host


def port_of(base_url: str) -> int:
    """The port of a unit address, DEFAULT_PORT when it carries none, refused when it is
    not a usable port."""
    try:
        port = urlparse(base_url).port
    except ValueError as exc:
        raise UnitError(
            f"no usable port in `units.<unit>.address` {base_url!r}: {exc}"
        ) from exc
    return port if port is not None else DEFAULT_PORT


def _with_rungs(unit: Unit, rungs: tuple[str, ...]) -> Unit:
    """The unit, with the rungs served by its process recorded on it."""
    return replace(unit, rungs=rungs)


def _roomiest_gpu(scan: Scan) -> Gpu:
    """The scanned card with the most free VRAM, refused when the rig has no card at
    all."""
    if not scan.gpus:
        raise UnitError(
            f"{scan.machine.host}: the scan found no GPU, so there is no card "
            "to place a unit on"
        )
    return max(scan.gpus, key=lambda gpu: gpu.vram.free_mib)


def _free_vram_bytes(scan: Scan) -> int:
    """The free VRAM of the roomiest card in bytes, and 0 when the scan found no
    card."""
    if not scan.gpus:
        return 0
    return max(gpu.vram.free_mib for gpu in scan.gpus) << 20


def _remaining_scan(scan: Scan, claim_gb: float) -> Scan:
    """The scan with another unit's claim subtracted from its roomiest card, so what is
    sized against it afterwards sees what is left."""
    if claim_gb <= 0 or not scan.gpus:
        return scan
    claim_mib = int(claim_gb * 1024)
    gpus = list(scan.gpus)
    index = max(range(len(gpus)), key=lambda i: gpus[i].vram.free_mib)
    gpu = gpus[index]
    taken = min(claim_mib, gpu.vram.free_mib)
    # The claim comes off the roomiest card alone and never below zero,
    # since the figure being claimed was priced from that same card.
    gpus[index] = replace(
        gpu,
        vram=replace(
            gpu.vram,
            used_mib=gpu.vram.used_mib + taken,
            free_mib=gpu.vram.free_mib - taken,
        ),
    )
    return replace(scan, gpus=tuple(gpus))


def _allowance_gb(spec: ModelSpec) -> float:
    """The headroom a failed placement quotes: the scratch allowance when the model is
    sized from a geometry, the default headroom otherwise."""
    if spec.geometry is None:
        return DEFAULT_HEADROOM_GB
    return vramfit.SCRATCH_AND_CONTEXT_MIB / 1024


def _needs_geometry(spec: ModelSpec) -> str:
    return (
        f"{spec.name}: sizing an MoE needs its geometry: run "
        f"python -m mcgyvr.serving.ggufscan <gguf> and set "
        f"units.<unit>.launch.geometry_json, or point it at the envelope's "
        f"geometry.json. --n-cpu-moe moves whole blocks, and what each block's "
        f"experts weigh is in the tensor table and nowhere else — not in a "
        f"name, a parameter count or a file size"
    )


def _mtp_head_blocks(spec: ModelSpec) -> tuple[int, ...]:
    """The blocks of the scanned file that carry MTP tensors, from the geometry; empty
    when nothing was scanned."""
    if spec.geometry is None:
        return ()
    return tuple(int(b) for b in spec.geometry.get("nextn_blocks") or ())


def _no_mtp_head(spec: ModelSpec) -> str:
    """The reason an mtp declaration is refused: the head has to be in the scanned
    tensor table, and neither a model name nor an unscanned file can say it is."""
    if spec.geometry is None:
        seen = f"{_weights_file_name(spec.name)!r} has not been scanned, so"
    else:
        seen = (
            f"{Path(str(spec.geometry.get('file') or '')).name!r} was scanned and "
            f"its tensor table has no nextn block, so"
        )
    return (
        f"{spec.name}: declares units.<unit>.launch.speculative: mtp, and {seen} "
        f"the GGUF carries no MTP head. --spec-type draft-mtp runs the head "
        f"grafted into the file, which is read off the tensor table "
        f"(ggufscan's nextn_blocks) and never assumed from a name; every "
        f"hardware-fitting stock GGUF scans 0 MTP tensors. Serve a grafted "
        f"checkpoint and point units.<unit>.launch.geometry_json at its scan, "
        f"or set speculative: none"
    )


@dataclass(frozen=True)
class _Placement:
    """What the search settled on for one card: how many expert blocks to keep off it,
    the slot count, and the VRAM, RAM and headroom that costs."""

    n_cpu_moe: int
    width: int
    vram_gb: float
    ram_gb: float
    headroom_gb: float
    # Bytes the grafted MTP head holds on the card, 0 when there is no head.
    head_bytes: int = 0


def _placement(
    spec: ModelSpec,
    free_bytes: int,
    width: int | None = None,
    *,
    engine: str,
    host: str,
    ctx_per_slot: int,
    n_ubatch: int = DEFAULT_UBATCH,
) -> _Placement:
    """Find, for one card, the fewest expert blocks to spill and the most slots that
    fit: the width the caller states, or the widest the search reaches under
    MAX_WIDTH."""
    if spec.geometry is None:
        if spec.moe:
            raise UnitError(_needs_geometry(spec))
        return _Placement(
            n_cpu_moe=0,
            width=width if width is not None else 1,
            vram_gb=spec.vram_gb,
            ram_gb=spec.ram_gb,
            headroom_gb=DEFAULT_HEADROOM_GB,
        )

    geometry = dict(spec.geometry)
    # The cache, state and scratch are priced per slot count, so the search
    # below is over slots: constant() is everything on the card that does
    # not move with the offload, and floor() gives the lowest --n-cpu-moe
    # whose expert blocks still fit beside it, or None when no offload
    # does.
    head_bytes = (
        vramfit.mtp_head_bytes(geometry) if spec.speculative == SPECULATIVE_MTP else 0
    )

    def constant(slots: int) -> int:
        try:
            kv_total = kv_bytes_for_run(
                ctx_per_slot=ctx_per_slot,
                slots=slots,
                geometry=geometry,
                n_ubatch=n_ubatch,
                cache_type_k=spec.kv_cache_dtype_k or "f16",
                cache_type_v=spec.kv_cache_dtype_v or "f16",
            )
            rs = vramfit.rs_bytes(geometry, n_seq_max=slots)
        except ValueError as exc:
            # A geometry whose cache cannot be priced is refused here: the
            # alternative is a split nobody measured, and every figure after
            # this point would be built on it.
            raise UnitError(
                f"{spec.name}: the cache cannot be sized, so nothing is placed "
                f"from an invented split: {exc}"
            ) from exc
        return (
            int(geometry["bytes_nonexpert"])
            + head_bytes
            + kv_total
            + rs["total"]
            + (vramfit.SCRATCH_AND_CONTEXT_MIB << 20)
        )

    def floor_at(slots: int) -> int | None:
        return vramfit.floor(geometry, free_bytes, constant(slots))

    if width is not None:
        slots = width
        n_cpu_moe = floor_at(slots)
    else:
        n_cpu_moe = floor_at(1)
        slots = (
            max(w for w in range(1, MAX_WIDTH + 1) if floor_at(w) == n_cpu_moe)
            if n_cpu_moe is not None
            else 1
        )
    if n_cpu_moe is None:
        raise UnitError(
            f"{spec.name}: does not fit at any offload on a card with "
            f"{free_bytes >> 20} MiB free at {slots} slot(s): the non-expert "
            f"weights, cache, state and scratch alone want "
            f"{constant(slots) >> 20} MiB with every expert block off the card. "
            f"This is the card being too small, not the config being wrong"
        )
    card = vramfit.predict(geometry, n_cpu_moe, constant(slots))
    return _Placement(
        n_cpu_moe=n_cpu_moe,
        width=slots,
        vram_gb=card / _BYTES_PER_GIB,
        ram_gb=max(
            spec.ram_gb, _host_gb(geometry, n_cpu_moe, engine=engine, host=host)
        ),
        headroom_gb=vramfit.SCRATCH_AND_CONTEXT_MIB / 1024,
        head_bytes=head_bytes,
    )


def _host_gb(
    geometry: dict[str, Any], n_cpu_moe: int, *, engine: str, host: str
) -> float:
    """The host RAM a spill costs: the expert bytes left off the card, plus the engine's
    runtime-resident figure where that is read per host."""
    offloaded = int(geometry["bytes_experts"]) - vramfit.experts_on_card(
        geometry, n_cpu_moe
    )
    if offloaded <= 0:
        return 0.0
    if engine in derived.RUNTIME_RESIDENT_READ:
        return offloaded / _BYTES_PER_GIB
    try:
        resident = derived.runtime_resident_gb(host)
    except derived.DerivedNumbersError as exc:
        raise UnitError(str(exc)) from exc
    return offloaded / _BYTES_PER_GIB + resident


def _window_for(
    key: UnitKey, declared: Mapping[int, list[str]], ctx_per_slot: int | None
) -> int:
    """The context window one process is served at: the window its units declare or the
    one this run was told, refused when they differ or neither exists."""
    if len(declared) > 1:
        pairs = ", ".join(
            f"{window} ({', '.join(sorted(names))})"
            for window, names in sorted(declared.items())
        )
        raise UnitError(
            f"{key.slug}: one process, {len(declared)} declared context "
            f"windows — {pairs}. These units name one URL, so one window "
            f"would silently lose and the unit behind it would be served a "
            f"window its contracts were never priced against. Point them at "
            f"one window, or at two ports"
        )
    if declared:
        ((window, names),) = declared.items()
        if ctx_per_slot is not None and ctx_per_slot != window:
            raise UnitError(
                f"{names[0]}: declares window {window} and this run "
                f"was told {ctx_per_slot}. Both numbers are in hand and they "
                f"are two different launches, so neither is preferred here: "
                f"edit the unit if the rig moved, or drop the flag if it "
                f"did not"
            )
        return window
    if ctx_per_slot is None:
        raise UnitError(
            f"{key.slug}: no context window was declared for this run and its "
            f"unit declares none, so nothing can be sized: the cache, the "
            f"`-c` on the argv and the `--n-cpu-moe` floor are all priced "
            f"against it, and a window this module chose would be a number "
            f"nobody measured. Declare it — read it back off the running unit "
            f"(`max_model_len` on vLLM, `n_ctx` on llama.cpp) and state what "
            f"it said"
        )
    return ctx_per_slot


def _offload_note(spec: ModelSpec, placed: _Placement) -> str:
    """The parenthetical naming the offload a fit used: which expert blocks of a
    geometry-sized MoE the --n-cpu-moe value keeps on the card."""
    if spec.geometry is None or not spec.moe:
        return ""
    placeable = list(spec.geometry["placeable_blocks"])
    on_card = sum(1 for block in placeable if block >= placed.n_cpu_moe)
    return (
        f" (--n-cpu-moe {placed.n_cpu_moe}: {on_card} of {len(placeable)} expert "
        f"blocks on the card)"
    )


def _threads(scan: Scan) -> int:
    """The thread count to launch with: the scan's physical cores, never more than its
    threads, and one when no CPU was read."""
    if scan.cpu is None:
        return 1
    return max(1, min(scan.cpu.cores or scan.cpu.threads, scan.cpu.threads))


def _weights_file_name(name: str) -> str:
    """The GGUF file a model of this name is scanned from and served out of: its name
    with path separators written as underscores."""
    return f"{name.replace('/', '_')}.gguf"


def _weights_path(scan: Scan, spec: ModelSpec) -> Path:
    """Where the GGUF lives on the rig: beside the scan's disk path, or in the default
    weights directory when the scan read no disk."""
    root = scan.disk.path if scan.disk is not None else default_weights_dir()
    return root / _weights_file_name(spec.name)


def kv_bytes_for_run(
    *,
    ctx_per_slot: int,
    slots: int,
    geometry: Mapping[str, Any] | None = None,
    n_ubatch: int = DEFAULT_UBATCH,
    cache_type_k: str = "f16",
    cache_type_v: str = "f16",
) -> int:
    """The KV cache bytes a run holds: the context extent across slots when nothing
    is known about the model, and vramfit's figure from the geometry and dtypes
    otherwise."""
    if ctx_per_slot < 1 or slots < 1:
        raise UnitError(
            f"a cache cannot be sized at {ctx_per_slot} context across "
            f"{slots} slot(s): both are counts of something a process holds"
        )
    extent = ctx_per_slot * slots
    if geometry is None:
        return extent
    return int(
        vramfit.kv_bytes(
            dict(geometry),
            extent,
            n_seq_max=slots,
            n_ubatch=n_ubatch,
            cache_type_k=cache_type_k,
            cache_type_v=cache_type_v,
        )["total"]
    )


def served_window(reported: Mapping[str, Any]) -> int | None:
    """The window a running unit reports: max_model_len off a vLLM models answer, or
    n_ctx off a llama.cpp one, and None when it reports neither."""
    models = reported.get("data")
    if isinstance(models, list):
        for entry in models:
            if not isinstance(entry, Mapping):
                continue
            window = entry.get("max_model_len")
            if isinstance(window, int) and not isinstance(window, bool):
                return window
    window = reported.get("n_ctx")
    if isinstance(window, int) and not isinstance(window, bool):
        return window
    return None
