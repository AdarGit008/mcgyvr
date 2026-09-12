"""A serving unit is one process: a host, a model, an engine and its arguments.

The ladder is a routing structure and the unit is a running process, and this
module exists because the two were being conflated. Several rungs may name one
model on one host — a cheap rung and its retry, a fast lane and a careful one —
and treating each as something to start loads one set of weights twice onto one
card. That is how a 6 GB rig runs out of memory while the config looks correct.
So a unit is keyed by what actually determines a process (host, model, engine
and the port it answers on) and the rungs that resolve to it are carried *on*
it, as names. Two rungs reaching one URL are one process; two rungs reaching
two ports on one host are two, whatever else they have in common.

What a unit deliberately does not carry is policy. There is no queue here and
no schedule: how many requests are in flight against a source is
:mod:`mcgyvr.capacity`'s, dispatch order is :mod:`mcgyvr.route`'s, and starting
anything at all is the operator's — :mod:`mcgyvr.emit` writes a file and stops.
A unit is a *launch spec*, which is why it can be built on a laptop for a rig
it has never touched.

Every number in it is read off a :class:`~mcgyvr.scan.Scan` or off the model's
own GGUF header; the one declared number is the runtime-resident intercept, a
host-side figure measured on 2026-08-25 and stated per rig in
``tools/runs/derived.json``. Free VRAM decides a fit today; total
VRAM decides nothing. And a model too big for the card is not automatically a
model the machine cannot serve: an MoE spills its experts to RAM, so fit is a
question about a *machine* — card, memory and disk together — not about a GPU.

The card arithmetic is :mod:`mcgyvr.serving.vramfit`'s, applied here and not
restated. What a placement costs is the non-expert weights, the cache and the
recurrent state the header implies for this many slots, one scratch allowance,
and the expert blocks left on the card — summed block by block from the
tensor table, never averaged. The geometry that feeds it is one ``ggufscan``
row (:attr:`ModelSpec.geometry`), and a model nobody has scanned is not sized
from anything else: an MoE without its geometry is refused and told where to
get one, and a dense model without it is served on the scalar figures its
spec states, one slot wide. Every constant this module used to carry for that
arithmetic — a cache cost per slot, an expert share, a block count, a working
set — was measured on one checkpoint and wrong on the next, and none survives.
"""

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
from mcgyvr.config import Config
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Gpu, Scan, default_weights_dir
from mcgyvr.serving import vramfit

# The engine a unit gets when nothing says otherwise. A source's ``api`` is a
# wire protocol (:class:`mcgyvr.pool.Protocol`) and cannot answer this: vLLM
# and llama-server both speak ``openai`` and take entirely different argv.
DEFAULT_ENGINE = "llama.cpp"

# There is no module-level context number, and its absence is the design.
#
# One stood here — ``DEFAULT_CONTEXT = 4096`` — and claimed "one number, two
# readers, no drift". There was a third reader and it disagreed: the door's
# ``--ctx-per-slot`` defaulted to 2048, so an ``--n-cpu-moe`` floor derived
# through ``mcgyvr.serving.run`` was computed against half the cache the
# compose file it was derived for actually launches with. The same class of
# error as ``VLLM_MAX_MODEL_LEN`` of 8192 against a llama.cpp rung serving
# 4096, which the first live day found.
#
# Owner's ruling, 2026-09-06: the window is what the run says, and it is not a
# constant. Making two literals agree would only make them agree until someone
# edits one. A default in a module is a number nobody chose for a rig nobody
# measured, so ``ctx_per_slot`` is threaded from the run's own declaration
# through every reader that prices a cache against it -- :func:`units_for`,
# :func:`unit_for`, :func:`fit`, :func:`_placement` -- and a run that declared
# none is refused rather than sized against somebody's module.
#
# llama-server's ``-c`` is the total across slots (measured 2026-09-05:
# ``-c 8192`` allocates the same cache at ``-np 8``, ``-np 4`` and ``-np 1``),
# so the argv states the declaration times the slot count and the cache law is
# fed the same product -- through :func:`kv_bytes_for_run`, which is the one
# place that multiplication happens.

# The micro-batch the cache law is sized at, and what the argv states as
# ``-ub`` and ``-b``. A sliding-window cache grows with it, so it has to be the
# number :func:`vramfit.kv_bytes` saw: stated rather than left to the engine,
# whose default the law would otherwise be guessing at.
DEFAULT_UBATCH = 512

# llama.cpp's own default port — what the engine would bind if nothing said
# otherwise. It is the fallback and never a preference: a unit built from a
# ladder takes its port from the source URL, and this number only stands in
# where nobody wrote one down, so stating it costs nothing and changes nothing.
DEFAULT_PORT = 8080

# What a launch spec's file is called. Spelled here rather than in
# :mod:`mcgyvr.emit`, which imports this module and cannot be imported back:
# :func:`cards` has to name the file a host's spec is kept in and is
# deliberately reachable without a scan, so the convention has to live on this
# side of that import. :mod:`mcgyvr.emit` re-exports both names.
COMPOSE_PREFIX = "compose."
COMPOSE_SUFFIX = ".yml"

# What a host or a model may be spelled as inside a file name. The one regex,
# used by :func:`spec_name` for the file and by :mod:`mcgyvr.emit` for the
# compose service and container names, so that a host cannot be one string in
# the name of the file and another in the name of the container inside it.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

# What system memory holds beyond the offloaded experts themselves — context,
# compute buffers, and the copy paths that do not live on the card — is a
# per-rig measured intercept, read from ``tools/runs/derived.json`` by
# :func:`mcgyvr.derived.runtime_resident_gb` inside :func:`_host_gb`. It is not
# a literal here: it applies only where experts actually spill — a model held
# entirely on the card is not paying it, and a dense model has no spill to pay
# it for — and a rig whose figure is absent is refused rather than sized from
# somebody's module.

# Held back from host RAM, on top of whatever the model needs, for the same
# reason :data:`vramfit.SCRATCH_AND_CONTEXT_MIB` is held back from the card:
# the page cache needs room to work and the host has its own processes.
#
# There are two of these, because :func:`fit` asks host RAM two questions in a
# row: they compare different figures and they fail differently. One constant
# priced both until 2026-09-09, at 2.0 GiB — what
# ``tools/bench/serving/backends/llamacpp.py`` weighed against for a campaign
# (``MMAP_HEADROOM_BYTES``), chosen against a live mmap depressing
# ``MemAvailable`` by about a gigabyte, and measured on neither gate. Both were
# then swept across three models on both rigs, mapped, with a locked balloon
# holding the clearance where it was wanted and the page cache dropped before
# every wake: ``records/measurements/ram-headroom-2026-09-09/``.

# The **mode** gate, weighed against the *blob*: what has to be clear before
# llama.cpp is left to map the weights rather than told ``--load-mode none``.
# Every page of the blob is read at load, which is why this margin predicts
# **wake** — and nothing whatever degrades between +2.0 and +0.5 GiB of it.
# srv1's Qwen3.6 wakes in 140.8 s against 139.9 s, srv2's 80B in 102.9 against
# 103.7, and across all nine arms decode throughput never moved at any
# clearance. Below zero the cost is real and reproducible and still lands only
# on wake: +19% on srv1's Qwen3.6 (n=3, alternating), +36% on deepseek, +5% on
# the 80B. Bounded, one-off, and loud enough to be noticed.
#
# Not zero, because the sweep does not vindicate a bare-blob rule. Clearance is
# measured against the blob while the process wants memory the blob does not
# account for — llama.cpp's own allocations, CUDA host-side buffers, container
# overhead — which is the likeliest reading of deepseek, the one model that paid
# above the line, costing +10.7% at exactly +0.5 GiB (n=1).
#
# What it changes on this fleet is one rung: srv1's 12.30 GiB Qwen3.6 into
# 14.19 GiB available maps at 0.5 where it went unmapped at 2.0. That is the
# answer the measurement wants — three alternating pairs at production
# ``vm.swappiness=60`` put unmapped at 132.9 s against mapped's 139.6 s, so the
# trade is 8.4 GiB of reclaimable memory for 6.7 s of one-off wake on a rung
# that stays up. The 24 s gap a single earlier sample showed was one draw.
#
# The margin is proportional rather than constant and this number cannot say so:
# one GiB of shortfall is 8% of a 12.30 GiB blob and 2.8% of a 35.67 GiB one, so
# the same figure means two different things on two rigs. The KAT-Coder wake of
# 203 s this comment used to cite is a mode datum that was read as a refusal one
# — a 16.9 GiB blob mapped into 15 GiB of RAM,
# ``records/measurements/wake-2026-09-08/``, taken before :func:`fit` had two
# arms at all.
#
# **A gap, named rather than guessed at: the loading mode has a VRAM cost and
# nothing here models it.** srv2's 80B crash-loops under ``--load-mode none`` on
# a CUDA allocation failure with 18 GiB of host RAM to spare, and loads mapped
# in 103 s (``records/measurements/ram-headroom-2026-09-09/`` § "``--load-mode
# none`` is not available to srv2's 80B at all"). The mode is decided from host
# RAM alone, so an srv2 with tighter memory would be emitted into that
# crash-loop today. Pricing it needs a measurement of what the unmapped arm
# costs the card and nobody has taken one — the crash is n=1, on one model, at
# an unknown margin — so no coefficient is asserted here.
MODE_RAM_HEADROOM_GB = 0.5

# The **refusal** gate, weighed against the *spilled experts*: what has to be
# clear before this module will admit the model to the host at all. The experts
# are the set that stays resident while the server serves, which is why this
# margin predicts **decode** — and swept against them the curve is a cliff and
# not a slope. Flat on every axis down to +0.55 GiB (131.5 s wake, 33.26 tok/s,
# zero pages swapped out); one GiB further down, a 385 s wake, 2.3 M major
# faults, 2.2 M pages swapped out and **decode at 32% of baseline**. Across
# every mode-gate arm decode never moved at all; past the experts it loses two
# thirds.
#
# So this one keeps its 2.0, for three reasons that are now measured rather than
# inherited: the cliff sits somewhere in the 1.5 GiB nobody sampled between
# +0.55 and -0.97, so its location is unknown; the failure is **silent**, which
# is what makes being wrong here different in kind from being wrong about a
# mapping — the unit comes up, gate 7 is green, ``/v1/models`` answers and every
# request is served off swap, so a run would report a disk benchmark as a decode
# rate (``okf/must-read/touching-rigs.md``); and the margin is free on this
# fleet, admitting Qwen3.6's 9.2 GiB of experts and KAT's 11.8 alike, refusing
# nothing anyone would have run.
#
# ``--load-mode none`` does not make those experts safe, either: the squeezed
# arm swapped 2.2 M pages *out* during its wake. They are allocated as shared
# anonymous memory, both rigs run 8 GiB of swap, and shared anonymous memory
# pages. The flag buys unevictability from the page cache, not from the kernel.
REFUSAL_RAM_HEADROOM_GB = 2.0

# The widest configuration anyone has measured on these rigs (#366, 32 slots on
# a 12 GB card). Past it this arithmetic would be extrapolating.
MAX_WIDTH = 32
# vLLM sizes its own cache from ``--gpu-memory-utilization`` and prices a
# request against ``--max-model-len``, so that ceiling is what a vLLM unit
# states and the cache law is not consulted. It is the run's ``ctx_per_slot``
# and not a second opinion about window size: a rung is a rung whichever
# engine serves it, and a ladder whose bottom prices a request at twice what
# its top can hold would escalate work into a window it no longer fits --
# which is what an 8192 here against llama.cpp rungs serving 4096 did. The
# utilisation itself is the operator's, in ``serve_args``: #337 measures it
# per rig and never inherits.
# The sequence cap a vLLM unit gets when no rung wrote a width. A scheduler
# cap, not an allocation — the engine's cache decides how many actually run
# — so unlike a llama.cpp slot it costs nothing to state, and 8 is what every
# driver on these rigs has started vLLM with.
VLLM_DEFAULT_SEQS = 8
# Where the rig's HuggingFace cache appears inside a vLLM container: the
# image's own default, so the model id resolves there with no further flag.
HF_CACHE_MOUNT = "/root/.cache/huggingface"

# How far a stated ``disk_gb`` may sit from the scanned ``size_bytes`` and
# still be the same figure written to two decimals. Past it they are two
# claims about one file, and the rule is that each deviation from a scan
# requires a new scan — not a tie-break in favour of whichever was typed last.
SIZE_TOLERANCE_GB = 0.005

_BYTES_PER_GIB = 1024**3


class UnitError(Exception):
    """A serving unit could not be built for a host, a model or a rung."""


@dataclass(frozen=True)
class ModelSpec:
    """What a model costs, in the three places a machine can run out.

    ``geometry`` is the model's own account of itself: one row of
    ``python -m mcgyvr.serving.ggufscan <gguf>`` (or the ``geometry.json`` a
    serving-door run leaves in its envelope), carrying the tensor table summed
    per block, the cache geometry per layer and the recurrent-state
    parameters. When it is present it is the source of truth for the model's
    bytes. ``disk_gb`` is read from its ``size_bytes``, ``moe`` from whether it
    has placeable expert blocks, and the card figure from the law in
    :mod:`mcgyvr.serving.vramfit`. A spec that states a ``disk_gb`` the
    geometry disagrees with is refused at construction rather than reconciled,
    and so is a geometry scanned from a file this spec does not name: each
    deviation from a scan requires a new scan, because the alternative is a
    number measured once on some other file that looks measured here.

    Without it the spec is scalar. ``vram_gb`` is then the working set on the
    card — what it holds with nothing offloaded, which is not the same as the
    weights on disk, because a working set carries buffers — and ``disk_gb``
    is those weights. That is enough to place a dense model on one slot and
    nothing more: an MoE has a knob for *where* its weights sit, the knob is
    priced per block from the tensor table, and no scalar stands in for a
    tensor table. :func:`fit` refuses an MoE without its geometry and says
    where to get one. ``vram_gb`` is not read when a geometry is present.

    ``ram_gb`` is a floor on what system memory may be asked to hold: zero for
    a dense model, which has nowhere to spill to, and for an MoE whatever an
    operator knows that this module cannot see. How much actually spills is
    derived per machine by :func:`fit`.

    ``moe`` is not cosmetic and not inferable from the scalar numbers: it says
    the model has a knob for *where* its weights sit, which is the difference
    between "does not fit" and "fits differently on this machine". Every unit
    in this module is in GiB, which is the convention
    :data:`mcgyvr.detect.MIB_PER_GB` sets; a caller holding decimal GB converts
    before it builds a spec.

    ``geometry`` takes no part in equality or hashing. Two specs naming one
    file at one size are one spec; the geometry is a reading of that file, not
    a further fact about it.

    ``hf_cache`` is where a vLLM model's weights are on the rig — the
    HuggingFace cache a repository id resolves in — and ``serve_args`` is what
    the server needs said that no scan can derive: the utilisation vLLM sizes
    its cache from, or the template argument that turns a thinking model's
    reasoning off. Both are the operator's, read off the config's ``models``
    block, and both ride on the spec because they are facts about serving
    this model and not about any machine.

    ``kv_cache_dtype_k`` and ``kv_cache_dtype_v`` are the KV cache dtypes the
    model launches with, read off the same ``models`` block. vLLM takes one
    value for K and V (``--kv-cache-dtype``), so only the K field is read
    there; llama.cpp takes the two independently (``-ctk``/``-ctv``). A unit
    served by either engine that omits the declaration is refused at
    :func:`unit_for` rather than defaulted: a dtype nobody wrote is a number
    nobody chose.
    """

    name: str
    vram_gb: float
    ram_gb: float
    disk_gb: float
    moe: bool = False
    geometry: Mapping[str, Any] | None = field(default=None, compare=False)
    hf_cache: str = ""
    serve_args: tuple[str, ...] = ()
    kv_cache_dtype_k: str | None = None
    kv_cache_dtype_v: str | None = None

    def __post_init__(self) -> None:
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
    """A slot count, and whether anyone actually said it.

    A width mcgyvr derived from a card and a width an operator wrote in the
    config are different facts, and a unit that lost the difference could not
    explain itself. ``how`` is ``"written"`` only when the caller stated the
    number; ``"derived"`` when the cache law sized it against the card; and
    ``"default"`` for a spec with no geometry to price a second slot from —
    one slot, because the per-slot cost is the law's and the law needs the
    header. Write ``max_parallel`` on the rung, or supply the geometry, to be
    wider than that.
    """

    value: int
    how: str


@dataclass(frozen=True)
class Fit:
    """Whether this machine can hold this model right now, and why.

    ``headroom_gb`` is what was held back on the card rather than what was
    left over: the reserve is the claim being made. For a spec with a
    geometry it is :data:`vramfit.SCRATCH_AND_CONTEXT_MIB`, the one allowance
    inside the card figure — compute scratch and the allocation the engine
    never names, everything else in that figure being read from the header.
    For a scalar spec it is :data:`mcgyvr.propose.DEFAULT_HEADROOM_GB`, held
    back on top of the stated working set.
    """

    fits: bool
    headroom_gb: float
    why: str
    #: The card figure this fit was judged on, in GiB — the predicted figure
    #: for a scanned model, the stated working set for a scalar one, zero for
    #: a refusal. Carried so that the units on one host can be summed: each
    #: fitting alone is how a 12 GB card ends up asked for 13.
    vram_gb: float = 0.0
    #: What this fit commits *host* memory to, in GiB, on the arm it took: the
    #: blob a mapped unit wants in page cache, the experts an unmapped one
    #: allocates outright, and zero for a unit with nothing to spill, whose
    #: pages are clean the moment they are uploaded to the card. Which of the
    #: three it is depends on ``load_mode``, which is why the figure is settled
    #: here and not recomputed: a sum taken before the modes are picked would
    #: be summing the wrong numbers (F2.1,
    #: ``records/plans/fleet-shape/formulas.md``). Carried for the same reason
    #: ``vram_gb`` is — every unit on a host clearing the same
    #: ``MemAvailable`` alone is how a 15 GB host is asked for 26.
    ram_gb: float = 0.0
    #: How llama.cpp must read the weights for this fit to hold, or ``None``
    #: where the engine's own default (mmap) is what was approved. A fit that
    #: admitted a model on the unmapped arm approved a different launch from
    #: the one that fits mapped, so the mode is part of what was approved and
    #: :func:`unit_for` writes it into the argv rather than deriving it again.
    load_mode: str | None = None
    #: Free VRAM on the card this fit was judged against, in GiB, as the scan
    #: read it. Carried because :func:`launch_specs` has to decide which units
    #: can be on that card *at the same time* and is handed units and nothing
    #: else — ``emit_all(units, root)`` is a function of its units, and a cut
    #: that needed a second scan would make every caller carry one, the wake
    #: path included, which is the thing D1 exists to avoid
    #: (``records/plans/sleep-wake.md`` §3).
    #:
    #: Zero means nobody measured it, which claims nothing: a unit built by
    #: hand is not evidence that two units contend, and inventing a contention
    #: there would move files for every fleet that was never sized. That is the
    #: same rule :func:`hold_together` takes for a host with no memory reading
    #: and :mod:`mcgyvr.scan` takes throughout.
    card_free_gb: float = 0.0


@dataclass(frozen=True)
class UnitKey:
    """What makes two units the same process rather than two.

    The engine is part of it because the same weights under llama.cpp and
    under vLLM are two servers, two ports and two copies of the weights in
    memory. The port is part of it for the same reason read the other way: a
    fast lane and a careful lane can name one model on one host and still be
    two ``llama-server`` processes, because their two source URLs promise two
    ports and a process listens on one. Merged into a single unit, the second
    port has nothing behind it — one container is emitted, the rung pointing at
    the other gets connection refused, and the config that says so reads as
    correct. The rung is not part of it, which is the whole point.
    """

    host: str
    model: str
    engine: str
    port: int = DEFAULT_PORT

    @property
    def slug(self) -> str:
        return f"{self.host}:{self.port}/{self.model}/{self.engine}"


@dataclass(frozen=True)
class Unit:
    """One process to start: where, what, how, and which rungs it serves.

    Everything the emit layer needs is here and nothing it would have to
    invent — the card index came from the scan, the weights path from the disk
    the scan measured, ``port`` from the URL the ladder reaches this process
    at, and ``args`` is the argv as flag → value, already sized for this
    machine.

    There is no queue and no schedule on purpose. See the module docstring.
    """

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
    #: The container image the source pinned, or ``None`` for the engine's
    #: default. A vLLM unit's ``weights`` is the HuggingFace cache directory
    #: itself, and ``extra`` is the spec's ``serve_args``, appended verbatim.
    image: str | None = None
    extra: tuple[str, ...] = ()

    @property
    def weights_dir(self) -> Path:
        """The directory to mount; the container sees the file inside it."""
        if self.engine == "vllm":
            return self.weights
        return self.weights.parent


def fit(
    scan: Scan, spec: ModelSpec, *, width: int | None = None, ctx_per_slot: int
) -> Fit:
    """Whether ``scan``'s machine can hold ``spec``, measured not declared.

    Four refusals, checked in the order that makes the message useful. A spec
    this module cannot size comes first, because it is a fact about the
    catalogue rather than about the machine and no amount of hardware answers
    it. Disk is next because weights that are not on the machine cannot be
    loaded however much memory there is, and a report that says "needs more
    VRAM" about a model that was never downloaded sends someone to the wrong
    shop. The card and memory are then one question asked of one
    :func:`_placement`: the lowest offload the card admits decides what
    memory is asked to hold, so a card that admits none is refused as a card
    and a spill the host cannot hold is refused as memory.

    ``width`` is the slot count the unit will be emitted at, when someone
    wrote one. The cache and the recurrent state are priced per slot, so the
    floor the argv carries depends on it, and a fit checked at another width
    is a fit for another process. That is the point of this function: checking
    a number here that the emitted argv does not honour is how a fit says yes
    to an offload the machine cannot hold, which is a compose file that passes
    review and swaps the host.

    ``ctx_per_slot`` is the window the run declared, and it has no default
    here for the reason stated at the top of this module: the cache is priced
    against it, so a fit checked at one window and an argv emitted at another
    is a fit for another process — the same defect ``width`` is required to
    avoid, one field over.

    Never raises. An unmeasurable machine is a machine nothing is claimed
    about — the same rule :mod:`mcgyvr.scan` runs on.
    """
    free_bytes = _free_vram_bytes(scan)
    free_vram = free_bytes / _BYTES_PER_GIB
    available_ram = scan.memory.available_gb if scan.memory else 0.0

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
            spec, free_bytes, width, host=scan.machine.host, ctx_per_slot=ctx_per_slot
        )
    except UnitError as exc:
        return Fit(fits=False, headroom_gb=_allowance_gb(spec), why=str(exc))
    # Host RAM has two arms, because how much of the model has to be resident
    # depends on how llama.cpp is told to read it. Under mmap — the engine's
    # default — every page is file-backed, the CPU-side experts included, so
    # the kernel may evict them and re-read them per token: the blob is the
    # figure that has to fit. Under `--load-mode none` only the spilled experts
    # are resident, as anonymous memory nothing can take back. Neither mode is
    # the better one in general — measured +63% on a rig too tight for its blob
    # and -12% on one with room to map it
    # (`records/evidence/2026-08-25-moe-expert-offload/`) — which is why the rig
    # decides it and not a default.
    #
    # A model with nothing to spill has no arm to take: its weights are the
    # card's, the pages it reads are clean the moment they are uploaded, and
    # host RAM is not a constraint on it at all.
    #
    # The two margins are two constants and not one, because the two arms fail
    # differently: mapping short of the blob costs a bounded, one-off wake, and
    # spilling short of the experts costs two thirds of decode with nothing
    # anywhere reporting an error. See :data:`MODE_RAM_HEADROOM_GB` and
    # :data:`REFUSAL_RAM_HEADROOM_GB`.
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
    unmapped = (
        f", read with --load-mode none because its {spec.disk_gb:.1f} GB blob "
        f"does not fit {available_ram:.1f} GB of RAM mapped"
        if load_mode
        else ""
    )
    # What the host is now committed to, on the arm just chosen: the experts
    # where they are allocated, the blob where the kernel is being asked to
    # cache it, nothing where nothing spills. One unit's figure, so that
    # :func:`hold_together` can add up a host's without deciding a mode twice.
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
            f"{free_vram:.1f} GB free, {held}{spilled}{unmapped}"
        ),
    )


def _require_cache_types(engine: str, spec: ModelSpec) -> tuple[str, str]:
    """The KV cache dtypes a unit must state, refused by name when absent.

    vLLM takes one value for K and V (``--kv-cache-dtype``), so only the K
    field is required there and the V field is not read. llama.cpp takes the
    two independently (``-ctk``/``-ctv``). Every missing knob is named in the
    one message, so a fix that binds one does not land on the next refusal for
    the other.
    """
    kv_k = spec.kv_cache_dtype_k
    kv_v = spec.kv_cache_dtype_v
    if engine == "vllm":
        if kv_k is None:
            raise UnitError(
                f"{spec.name}: served by vLLM, which sizes its KV cache from "
                f"the dtype the model declares, and nothing states one — set "
                f"models.{spec.name}.kv_cache_dtype_k (`--kv-cache-dtype`)"
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
            f"{' and '.join(missing)} — set them on models.{spec.name}"
        )
    assert kv_k is not None and kv_v is not None
    return kv_k, kv_v


def unit_for(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str = DEFAULT_ENGINE,
    width: int | None = None,
    port: int = DEFAULT_PORT,
    ctx_per_slot: int,
) -> Unit:
    """The one process that would serve ``spec`` on the machine ``scan`` measured.

    A unit that cannot load is not a unit, so a spec this machine does not fit
    is refused here with the fit's own reason rather than emitted and found out
    by the loader.

    ``port`` is where this process is expected to answer. A scan and a spec do
    not know that — only a ladder does — so a unit built from those two alone
    takes :data:`DEFAULT_PORT`, which is the number the engine would have
    chosen anyway. :func:`units_for` is where the config's answer arrives.

    ``ctx_per_slot`` is the window the run declared. It reaches the rig from
    here two ways and only two — ``-c`` times the slot count on llama.cpp,
    ``--max-model-len`` on vLLM — and the same number priced the cache the fit
    approved, which is what makes the launch and the law one number.
    """
    cache_type_k, cache_type_v = _require_cache_types(engine, spec)
    if engine == "vllm" and not spec.hf_cache:
        raise UnitError(
            f"{spec.name}: served by vLLM, which loads a repository id from the "
            f"rig's HuggingFace cache, and nothing says where that cache is — "
            f"set models.{spec.name}.hf_cache to its absolute path on the rig"
        )
    sized = fit(scan, spec, width=width, ctx_per_slot=ctx_per_slot)
    if not sized.fits:
        raise UnitError(f"{scan.machine.host}: {sized.why}")

    gpu = _roomiest_gpu(scan)
    if engine == "vllm":
        # vLLM has no offload knob this module prices and sizes its own cache
        # from the utilisation the operator states, so the argv is the engine's
        # two ceilings and nothing the cache law computed.
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
    # The same derivation :func:`fit` just approved, not a second one that
    # agrees today: an argv whose offload differs from the one the fit checked
    # is a unit that was never sized for this machine.
    placed = _placement(
        spec,
        gpu.vram.free_mib << 20,
        width,
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

    # Flag → value throughout, which is the shape both renderings of a launch
    # spec need; a valueless switch would have to be a special case in each of
    # them, so anything that is one is not expressed here. ``-c`` is the total
    # across slots and ``-ub``/``-b`` the micro-batch, stated because they are
    # exactly the numbers the cache law was fed: an argv that left either to
    # the engine would be sized for one cache and allocate another.
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
    # A card roomy enough for every expert derives zero blocks, and
    # ``--n-cpu-moe 0`` is a no-op printed into a file a person reads: it says
    # this rig offloads experts when it does not, and invites tuning a number
    # that was never in play.
    if placed.n_cpu_moe > 0:
        args["--n-cpu-moe"] = str(placed.n_cpu_moe)
    # The mode the fit approved, never a second derivation: a unit read one
    # way and sized another is exactly the drift `argv` exists to prevent, one
    # flag over. Absent where the default (mmap) is what fits, because
    # `--load-mode auto` printed into a file a person reads says a choice was
    # made where none was.
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
    """The processes a ladder implies: one per port on one host, not one per rung.

    Tiers are grouped, not iterated: every rung that resolves to the same
    process is collected onto the one :class:`Unit` that serves it, and the
    rung names ride along so a report can say what a process is for.

    A rung whose host was never scanned raises rather than being skipped. This
    module cannot size a unit for a machine nobody measured, and quietly
    dropping the rung would emit a ladder that is missing a step someone wrote
    down — a scan is the fix, and the error says so.

    Each unit's port comes from the URL its source names, because that URL is a
    promise about where the rung answers and a server that does not listen
    there makes the config a lie. Left to the engine's default, a host carrying
    two models is two processes both taking 8080 — one of which loses, silently
    and after the file was written.

    The port is therefore part of the key and not a property collected onto
    one: two sources on one host serving one model — a fast lane on 8080 and a
    careful one on 8081 — are two processes, and grouping them into a single
    unit keeps the first port and drops the second. Nothing then listens where
    the second rung is told to knock, and because the two URLs differ the
    caller's port-contention check has nothing to complain about either. That
    rung is dead in a ladder that reads as fine.

    ``ctx_per_slot`` is the window this run is bringing the ladder up with, and
    it is the *fallback*: a source that declares ``context_window`` is emitted
    at the window it declares. The declaration is a fact about the process —
    read back off the running unit and written down — while the flag is what a
    run says when nobody has written the fact down yet, and a number that
    reaches a rig only from a flag is a number ``Config.digest`` cannot see.
    One flag also cannot describe a fleet: srv1 serves 8192 per slot and srv2
    4096, so a single ``--ctx-per-slot`` makes one of the two look drifted
    under ``emit --check`` whichever value it takes.

    Where both speak and disagree, neither wins: :func:`_window_for` refuses and
    names the source and both numbers, which is the shape ``Capacity.of`` uses
    for a width disagreement. A window that nobody states at all is still
    refused, because the cache, the ``-c`` on the argv and the ``--n-cpu-moe``
    floor are all priced against it and a window this module chose would be a
    number nobody measured.
    """
    if ctx_per_slot is not None and ctx_per_slot < 1:
        raise UnitError(
            f"the declared context window is {ctx_per_slot}, which is not a "
            f"window: a slot serves at least one token"
        )
    # The config wins over the table, and the precedence lives here rather than
    # in the caller so that every caller gets it: measured where mcgyvr can
    # measure, stated where it cannot, refused only when neither has an answer.
    catalogue = {spec.name: spec for spec in specs} | declared_models(config)
    grouped: dict[UnitKey, list[str]] = {}
    hosts: dict[UnitKey, Scan] = {}
    models: dict[UnitKey, ModelSpec] = {}
    widths: dict[UnitKey, int] = {}
    images: dict[UnitKey, str | None] = {}
    #: Declared window -> the sources that declared it, per unit. A mapping and
    #: not a scalar because two sources can name one URL, and two windows on
    #: one process is a disagreement to report rather than one to resolve.
    windows: dict[UnitKey, dict[int, list[str]]] = {}

    for tier in config.ladder.tiers:
        source = config.sources.get(tier.source)
        if source is None:
            raise UnitError(f"{tier.name}: no source named {tier.source!r}")
        host = host_of(source.base_url)
        scan = scans.get(host)
        if scan is None:
            raise UnitError(
                f"{tier.name}: host {host!r} is unscanned — "
                f"run `mcgyvr scan {host}` before emitting a unit for it"
            )
        spec = catalogue.get(tier.model)
        if spec is None:
            raise UnitError(
                f"{tier.name}: no model spec for {tier.model!r} — it is not in "
                f"the shipped capability table, and nothing declares it under "
                f"`models:` in the config. Sizing a unit needs what the model "
                f"costs, and mcgyvr will not invent that; state it and this "
                f"model is served on your numbers"
            )

        key = UnitKey(
            host=host,
            model=spec.name,
            # The source's, because a URL points at one process and one process
            # runs one engine. Absent it is llama.cpp, which is what this line
            # asserted unconditionally before the field existed — so a config
            # that names no engine is bound exactly as it was.
            engine=source.engine or DEFAULT_ENGINE,
            port=port_of(source.base_url),
        )
        grouped.setdefault(key, []).append(tier.name)
        if source.context_window is not None:
            windows.setdefault(key, {}).setdefault(source.context_window, []).append(
                source.name
            )
        hosts.setdefault(key, scan)
        models.setdefault(key, spec)
        images.setdefault(key, source.image)
        if tier.max_parallel is not None:
            # One process, one slot count. Two rungs asking for different
            # widths get the larger, because a slot the second rung never uses
            # costs KV cache and a slot it needs and does not have is a queue
            # nobody declared. The source's own ``max_parallel`` is not read
            # here: that number bounds dispatch, which is capacity.py's, and a
            # rung that states nothing has stated nothing about this process.
            widths[key] = max(widths.get(key, 0), tier.max_parallel)

    units = tuple(
        replace(
            _with_rungs(
                unit_for(
                    hosts[key],
                    models[key],
                    engine=key.engine,
                    width=widths.get(key),
                    port=key.port,
                    ctx_per_slot=_window_for(key, windows.get(key, {}), ctx_per_slot),
                ),
                tuple(rungs),
            ),
            image=images[key],
        )
        for key, rungs in grouped.items()
    )
    return units


def alternate(one: Unit, other: Unit) -> bool:
    """Whether these two units can never be up at the same time.

    Two facts, and only the second was ever load-bearing.

    **The port.** A port is a thing exactly one process holds, so two units that
    name one port are two models for one server: the second cannot bind until
    the first is gone. That is srv1 as it was configured until 2026-09-09 —
    DeepSeek-Coder-V2 and Qwen3.6 both answering on ``:8080``.

    **The card.** Two units contend for a card when their card figures will not
    sum onto the free VRAM the scan read. That is srv2, and the port cannot see
    it: the vLLM pair answer on ``:8001`` and ``:8002`` and the 80B on
    ``:8003``, three ports that never collide, and all three want one RTX 3060.
    Priced as co-residents that host asks 20 GiB of a 12 GiB card, and a
    ladder either arrangement of which serves perfectly well is refused.

    **The owner ruled for port-per-model on 2026-09-09, and the port then stops
    carrying contention information at all** — no port ever collides, so this
    function's first clause never fires on the fleet it was written for. It is
    kept because it is still true, not because it still decides anything: one
    process holds a port whatever the card has room for, and a build that
    dropped the clause would call two units on one port co-residents and emit a
    file whose second service never binds. What changed is which clause is the
    *discriminator*, and the answer is the card.

    A card figure of zero means nobody measured the card — a unit built by hand
    rather than sized against a scan — and an unmeasured card claims nothing:
    the pair reads as co-resident, which is where every fleet emitted before
    this change already was. See :attr:`Fit.card_free_gb`.
    """
    if one.host != other.host:
        return False
    if one.port == other.port:
        return True
    if one.gpu != other.gpu:
        # Two cards on one host do not contend for VRAM. They still contend for
        # host RAM, and that sum is :func:`hold_together`'s — taken over what a
        # launch spec brings up together, which is what this function decides.
        return False
    free = _card_free_gb((one, other))
    if free <= 0:
        return False
    return one.fit.vram_gb + other.fit.vram_gb > free


def _card_free_gb(units: Iterable[Unit]) -> float:
    """The free VRAM these units were sized against, or zero if nobody measured.

    The minimum of what each unit recorded rather than the first, so that two
    units sized against two readings of one card are held to the tighter of
    them. That happens when a scan is retaken between two ``emit`` runs, and
    the tighter figure is the one that will still be true when both are up.
    """
    figures = [unit.fit.card_free_gb for unit in units if unit.fit.card_free_gb > 0]
    return min(figures) if figures else 0.0


def _co_resident(chosen: tuple[Unit, ...], candidate: Unit) -> bool:
    """Whether ``candidate`` can be up beside everything already in ``chosen``.

    Pairwise against the port, summed against the card: three units of 5 GiB
    each pass every pair on a 12 GiB card and fail as a set, which is exactly
    the failure :func:`hold_together` was written for and the reason a
    feasibility question cannot be answered one edge at a time.
    """
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
    """One thing an operator can bring up: units that come up *together*.

    Usually a host, and not always one. ``model`` is what distinguishes this
    spec from the other specs on the same host, or ``None`` where the spec is
    the whole host — which is every fleet emitted until 2026-09-09 and both
    live rigs today. :mod:`mcgyvr.emit` spells the two into file names; what
    they *are* is decided here, because it is a fact about units and not about
    YAML.
    """

    host: str
    units: tuple[Unit, ...]
    model: str | None = None


def launch_specs(units: Iterable[Unit]) -> tuple[LaunchSpec, ...]:
    """The ladder's units cut into the things a door can be pointed at.

    **What this function answers changed on 2026-09-09, and the change is the
    owner's.** It used to answer "which partition do this host's units fall
    into" — same port, alternatives; different port, co-residents — and a
    partition is what a port gives you, because holding a port is an
    equivalence. Card contention is not: three units may pass every pair and
    fail as a set, two of them may fit together while the third fits alone, and
    there is no single "the" grouping. So the answer is no longer a partition.
    It is a **covering by feasible combinations**: every set here is one an
    operator can actually bring up, and every unit is in at least one of them,
    because a unit no file holds is a rung mcgyvr can never start.

    **One spec per unit, grown maximal, then de-duplicated.** For each unit in
    turn, that unit plus every other unit that can be up beside it, taken
    largest-first; identical sets collapse. Three properties follow, and each
    of them is why this and not one of the two obvious alternatives:

    * **It is bounded by the number of units.** Enumerating *every* maximal
      feasible subset is exponential — N/2 conflicting pairs give 2^(N/2) of
      them — and an ``emit`` that wrote a compose file per subset would answer a
      four-unit host with sixteen files. What is given up is that some maximal
      set may have no spec: A, B and C at 5 GiB each on a 12 GiB card yield
      ``{A,B}`` and ``{A,C}`` and not ``{B,C}``. Every unit is still reachable,
      which is the property that matters, and choosing *which* feasible set to
      run is the fleet-shape controller's question and not this one's
      (``records/plans/fleet-shape/``).
    * **A host whose units all co-reside is still one spec holding all of
      them**, which falls out rather than being special-cased: every anchor
      grows to the same set and the de-duplication leaves one. That is the
      compatibility rule ``d8c5cf0a`` established — nothing on disk moves for
      such a fleet — and both live rigs are that fleet.
    * **It is deterministic.** The anchors are walked in a fixed order, each
      set is grown in a fixed order and stored sorted, and the de-duplication
      keeps first-seen. ``emit --check`` compares bytes, so a cut that iterated
      a set would report drift against a config nobody had touched.

    The rejected alternative to both is **one spec per unit, never grown**:
    always N files, trivially deterministic, and wrong twice over — it moves
    every existing fleet's files, and it throws away the ``depends_on`` that
    sequences two units onto one card, which is a measured failure and not a
    tidiness (``emit._sequence_on_one_card``, 7B on srv2 getting 0.89 GiB of KV
    cache started together against 2.77 GiB started second).

    **The refusal of a host mixing alternatives and co-residents is gone.** It
    said the third unit "belongs in neither alternative's spec", which was true
    of a partition and is not true of a covering: the mixed host is just a
    conflict graph, and its specs are the sets that fit. Owner's ruling 5,
    2026-09-09: under a fluid ladder that mix is the normal case, not an edge to
    refuse.
    """
    on_host: dict[str, list[Unit]] = {}
    for unit in units:
        on_host.setdefault(unit.host, []).append(unit)

    specs: list[LaunchSpec] = []
    for host in sorted(on_host):
        here = tuple(
            sorted(on_host[host], key=lambda unit: (-unit.fit.vram_gb, unit.key.slug))
        )
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
        sets = tuple(found.values())
        if len(sets) == 1 and len(sets[0]) == len(here):
            specs.append(LaunchSpec(host=host, units=sets[0]))
            continue
        for name, chosen in zip(_named(sets), sets, strict=True):
            specs.append(LaunchSpec(host=host, units=chosen, model=name))
    return tuple(specs)


def _named(sets: tuple[tuple[Unit, ...], ...]) -> tuple[str, ...]:
    """A distinguishing name for each of one host's launch specs.

    Three spellings, tried in order, and the first that tells every spec on the
    host apart is the one used for all of them — uniformly, because a host whose
    files were named by two different rules is a directory an operator cannot
    read.

    1. **The model of the largest unit.** What the card is doing is what its
       biggest resident is, and for a spec holding one unit this is the model
       name and nothing else, which is what ``d8c5cf0a`` wrote and what is
       already on disk for srv1's two alternatives.
    2. **Every model in the spec.** For two specs that share a defining unit.
    3. **Every model, then every port.** For two specs holding the same models
       on different ports — a fast lane and a careful one, which
       :class:`UnitKey` keeps apart and a model name cannot.

    A name is never chosen per spec, and it is never a hash: a file name is the
    thing an operator types after ``serve up --compose``, and one that changed
    when a neighbouring spec appeared would be a file they could not find twice.
    """

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
    # Two specs that agree on host, models and ports are the same spec, and
    # :func:`launch_specs` de-duplicated those before this was called. Reaching
    # here means that invariant broke, and a file quietly overwriting another
    # is exactly what :func:`mcgyvr.emit._planned`'s claim check exists to stop.
    raise UnitError(
        f"{sets[0][0].host}: two launch specs cannot be told apart by the "
        f"models and ports they hold, so they would be written to one file"
    )


def hold_together(units: Iterable[Unit], scans: Mapping[str, Scan]) -> tuple[str, ...]:
    """One launch spec's units, summed against the card and the memory they share.

    Two sums and not one, because a host has two things to run out of and they
    are counted differently: **VRAM per card, host RAM per host** (owner's
    ruling, 2026-09-09). Both are taken against the recorded scan and never a
    live read — a fit that agreed with whatever the rig happened to be doing
    when someone ran ``emit`` is a fit nobody can reproduce.

    :func:`fit` judges one unit against a free card, and every unit on a host
    passes that test on its own — which is exactly how a 12 GB card gets a
    compose file asking for 13. So the figures are added up and held to what the
    scan read, with no headroom on the card: the headroom is inside each figure
    already, and the sum is what the card will actually be asked to hold.
    Measured 2026-09-05 on srv2: 7.12 + 3.49 GiB on 11.63 free, and the card
    held it with 1.0 GiB to spare.

    **What the sum is taken over moved on 2026-09-09, and that is the whole of
    this function's change.** It used to be "the largest alternative at each
    port, added across ports" — the worst case an operator could reach when a
    port was what made two units take turns. The port is no longer the
    discriminator (:func:`alternate`), so the sum is taken over what a **launch
    spec** brings up together, which is the same sentence with the fact
    corrected: a spec is by definition the units that are on the card at once.

    **The consequence, stated because it removes a refusal.** Two units whose
    card figures do not sum are now *alternatives* rather than a refused
    ladder — :func:`launch_specs` writes each of them a file and only one is
    ever up — so the card sum below can no longer fire for a pair on a scan the
    units were sized against. It is kept, and it is not decoration: a unit
    carries the card figure it was measured against (:attr:`Fit.card_free_gb`)
    and this function is handed the scans separately, so a ladder sized against
    one reading of a rig and checked against another is caught here and nowhere
    else. What it stopped doing is refusing a fleet the owner wants emitted:
    srv2's ``:8001``/``:8002``/``:8003`` trio asks 20 GiB of a 12 GiB card as a
    sum and serves perfectly well as two launch specs.

    **The memory sum is the same shape and a different figure, and it keeps its
    teeth.** Each unit contributes what its fit committed the host to
    (:attr:`Fit.ram_gb`) — the blob a mapped unit wants cached, the experts an
    unmapped one allocates, nothing where nothing spills — and the sum runs
    *after* the loading modes are picked, because the mode is what decides which
    figure a unit brings. One host headroom is applied once to the total,
    :data:`REFUSAL_RAM_HEADROOM_GB`, and not once per unit: the margin is the
    host's own working room, and charging it per unit refuses layouts a host can
    hold. Without this, two spilling units each cleared the same
    ``MemAvailable`` alone and the file emitted asked a 15 GB host for 26. RAM
    is not what :func:`alternate` cuts on — the owner's sentence is about the
    *card* — so two units that share a card happily and cannot share the host's
    memory are still a refusal, which is what ``6a2e80d4`` landed.

    A spec holding one unit is skipped on both axes: :func:`fit` already judged
    it against the whole card and the whole of ``MemAvailable`` on its own, and
    re-asking here would refuse srv1's Qwen3.6 — 12.30 GiB of blob plus 2.0 GiB
    held back against 14.19 available — which is the unit that rig serves today.

    Two things this sum is not. It is not measured: nothing on this fleet has
    run two llama.cpp MoE units co-resident on one host, which is G2 in
    ``records/plans/fleet-shape/evidence_and_params.md``, and the arms it adds
    are F2.1's law rather than a reading of two of them together. And it is not
    symmetric in how it fails — an unmapped unit's experts are allocated and
    short of them the host swaps silently at a third of decode, while mapped
    units short of their blobs pay a bounded wake and nothing else. The sum
    treats both as a refusal, which is stricter than the mapped arm has been
    shown to need.

    A check of its own rather than a rule inside :func:`units_for`, because
    that function answers "which processes does this ladder imply" and two
    units that will not share a card are still two processes; whether the
    machine can hold them both is the question asked just before a file is
    written, and :func:`mcgyvr.cli._emit` asks it there.

    **What it returns is what the card refusal turned into.** A host whose units
    do not sum onto its card is no longer refused — it is emitted as N
    alternatives — and that is a change to what the rig does, decided by
    arithmetic the operator never sees, announced until now by nothing louder
    than the number of ``wrote ...`` lines. So the sentence that used to be the
    refusal is returned here as a warning, one per host that was cut, and
    :func:`mcgyvr.cli._emit` prints it. It is a warning and not a refusal
    because owner's ruling 5 of 2026-09-09 says the mix is the normal case under
    a fluid ladder; it is not silence because only one of those files is ever
    up, ``serve up`` takes one file, and a wake will decline to guess which
    (:func:`mcgyvr.wake.compose_for`).

    A host that comes up as one spec warns about nothing, which is most fleets
    and both live rigs: a sentence printed on every emit is a sentence nobody
    reads by the second week.
    """
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
        for unit in spec.units:
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
            # A host nobody measured the memory of is a host nothing is claimed
            # about, which is the rule :mod:`mcgyvr.scan` runs on and the one
            # :func:`fit` took when it read ``available_ram`` as zero.
            continue
        hungriest = sorted(spec.units, key=lambda unit: unit.key.slug)
        wanted = sum(unit.fit.ram_gb for unit in hungriest)
        if wanted and wanted + REFUSAL_RAM_HEADROOM_GB > memory.available_gb:
            listed = ", ".join(
                f"{unit.model} ({unit.fit.ram_gb:.2f} GB "
                f"{'unmapped' if unit.fit.load_mode == 'none' else 'mapped'})"
                for unit in hungriest
                if unit.fit.ram_gb
            )
            raise UnitError(
                f"{spec.host}: {listed} fit host memory one at a time and not "
                f"together — {wanted:.2f} GB summed with "
                f"{REFUSAL_RAM_HEADROOM_GB:.1f} GB held back, against "
                f"{memory.available_gb:.2f} GB available. Serve one of them "
                f"from another host, drop one, or narrow a window: context is "
                f"paid for in host RAM, 1.1 GB of it per slot between 2048 and "
                f"32768 on srv1's Qwen3.6"
            )
    return tuple(warnings)


def _cut_into_alternatives(units: Iterable[Unit]) -> dict[str, dict[str, None]]:
    """Each host emitted as more than one launch spec, and the names of them.

    A dict of dicts rather than a set of names, because the order has to be the
    one the file names sort in — a warning that reordered itself between two
    runs over one config is a warning an operator cannot diff.
    """
    specs = launch_specs(units)
    named: dict[str, dict[str, None]] = {}
    for spec in specs:
        if spec.model is None:
            continue
        named.setdefault(spec.host, {})[spec.model] = None
    return named


def safe_host(host: str) -> str:
    """The host as a file name component, refusing whatever it would have to tidy.

    A host is the key scans, units and files are all filed under, so a name that
    merely needs sanitising is refused rather than sanitised: rewriting it here
    would file this file under a name nothing else in the tool uses.

    An IPv6 literal is the one exception, because refusing it is refusing the
    rig. ``host_of("http://[fd00::1]:8080")`` is ``fd00::1`` — a real address of
    a real machine that a ladder can already reach — and a colon is not a
    compose name anywhere, nor a path component on every system a compose file
    gets copied to. So it is spelled out instead, and normalised first, so that
    the two ways of writing one address (``fd00::1`` and
    ``fd00:0:0:0:0:0:0:1``) cannot become two files for one rig. What comes back
    is a name, not an address; :func:`mcgyvr.emit._planned` is where two hosts
    are stopped from claiming one.

    **Lived in :mod:`mcgyvr.emit` until 2026-09-09 and moved here for one
    reason:** :func:`cards` has to name the file a host's launch spec is kept in
    and cannot import ``emit`` back. While the convention was spelled twice,
    ``cards`` spelled it wrong — ``compose.fd00::1.yml`` for a rig ``emit``
    writes as ``compose.fd00--1.yml`` — which is a card that could never be
    woken on the one address shape that has to be rewritten.
    """
    address = _ipv6(host)
    if address is not None:
        return _UNSAFE.sub("-", address)
    if not host or host != _UNSAFE.sub("-", host) or host in {".", ".."}:
        raise UnitError(f"{host!r} is not a host name a file can be named after")
    return host


def safe_model(model: str) -> str:
    """The model as a file name component, sanitised rather than refused.

    The opposite call from :func:`safe_host`, and for the opposite reason. A
    host is the key scans, units and files are filed under, so rewriting one
    would file a file under a name nothing else uses — but a model name is not a
    file-system key anywhere, and the names this fleet actually serves are
    ``Qwen/Qwen2.5-Coder-7B-Instruct-AWQ`` and ``qwen2.5-coder:3b``. Refusing a
    slash or a colon would refuse every HuggingFace id and every tagged name,
    which is refusing the ladder rather than protecting it.

    Sanitising is many-to-one, so it is :func:`mcgyvr.emit._planned` that stops
    two models from claiming one file — the same guard, and for the same reason,
    as two hosts spelling one name.
    """
    name = _UNSAFE.sub("-", model)
    if not name or name in {".", ".."} or set(name) <= {"-"}:
        raise UnitError(f"{model!r} is not a model name a file can be named after")
    return name


def _ipv6(host: str) -> str | None:
    """``host`` as one normalised IPv6 literal, or ``None`` if it is not one."""
    try:
        return ipaddress.IPv6Address(host).compressed
    except ValueError:
        return None


def spec_name(host: str, model: str | None = None) -> str:
    """The file name one launch spec is written to.

    ``compose.<host>.yml`` for a host that comes up as one — every fleet emitted
    until 2026-09-09 and both live rigs — and ``compose.<host>.<model>.yml``
    for each of a host's alternatives, where ``model`` is whatever
    :func:`launch_specs` chose to tell them apart.

    One function and not a format string in three modules. It is what
    :mod:`mcgyvr.emit` writes, what :func:`spec_files` recognises on disk and
    what an operator types after ``serve up --compose``, and a convention spelled
    once cannot be spelled two ways.
    """
    stem = (
        safe_host(host) if model is None else f"{safe_host(host)}.{safe_model(model)}"
    )
    return f"{COMPOSE_PREFIX}{stem}{COMPOSE_SUFFIX}"


def spec_files(root: Path, host: str) -> tuple[Path, ...]:
    """Every file in ``root`` that mcgyvr's own naming convention gives ``host``.

    **A directory listing and not a planner call, and the difference is the
    point.** Asking the planner what a config emits needs units, units need a
    :class:`~mcgyvr.scan.Scan`, and needing a scan is exactly what :func:`cards`
    and the wake path exist to not need (D1, ``records/plans/sleep-wake.md``
    §3). What is asked here is the other question, and it is the one a wake
    actually has: *which files are on this disk for this rig* — answerable from
    the config, the convention and the filesystem, on a laptop that never
    scanned the rig.

    It matters because the two answers can differ, and when they differ the gap
    is a **stale launch spec**. ``emit`` writes what a config plans and deletes
    nothing, so a host that used to come up as one file and is now cut into
    alternatives leaves ``compose.<host>.yml`` behind — a file holding both
    units on one card, which is the overcommit ``hold_together`` was written to
    refuse, sitting where a wake would pick it up. The planner cannot see it
    (``emit.check_all`` reads only planned paths) and a hardcoded name saw
    nothing else. A listing sees both, which is what lets a wake decline to
    guess (:func:`mcgyvr.wake.compose_for`) and lets ``emit --check`` name it
    (:func:`mcgyvr.emit.unplanned`).

    A missing or unreadable directory is no files, not an error: this is asked
    on the dispatch path, where "mcgyvr holds no launch spec for that card" is
    an honest answer and a raise is not.

    The convention is ambiguous where one host's name is a prefix of another's —
    ``compose.rig.big.yml`` is ``rig``'s alternative and could be ``rig.big``'s
    whole-host file — and this resolves it by claiming both, deliberately. Every
    caller of this uses extra candidates the same way: to decline to guess. Over-
    claiming costs a wake that says "name the file"; under-claiming costs a wake
    that starts a file this config did not write.
    """
    try:
        whole = spec_name(host)
    except UnitError:
        # A host that cannot be spelled into a file name has no file, which is
        # what an emit for it would have refused to write in the first place.
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
    """The hardware a rung's work lands on, derived and never declared.

    **A card is already modelled in this repository. It is modelled here, below
    the execution seam, and it is called a host with a GPU index.** Nothing
    above the seam learns about it: there is no ``devices:`` block, no
    ``device:`` key on a source, and no card on a :class:`~mcgyvr.config.Tier`.
    A card named up there would be a fact about a *machine* on an object whose
    whole purpose is to name no machine, and it would go stale the first time a
    source was re-pointed — which is the argument ``Source.context_window``'s
    own schema doc makes the other way round, and the same defect
    ``Capacity.of`` refuses by name when a config and a rig give two answers to
    one question.

    ``specs`` is what makes the difference a caller actually cares about
    answerable: *can mcgyvr bring this back?* is *does mcgyvr hold the launch
    spec?*, and that is answerable without touching the network. It is empty for
    a config that states no ``serving.compose_dir``, which therefore has no
    sleeping cards at all — only down ones.

    Two cards are equal when they are the same machine holding the same files,
    so the rungs on one rig compare equal through them. That is the property
    whole-card eviction is stated in: sleeping ``local_qwen2.5-coder-3b`` and
    sleeping ``local_qwen2.5-coder-7b`` are one act because they are one card.
    """

    host: str
    #: The name a host that comes up as one file is written to — ``emit``'s
    #: ``compose.<host>.yml`` under ``serving.compose_dir``, and ``None`` where
    #: the config states no such directory.
    #:
    #: **A name, and never a promise that the file is current.** It is not what
    #: a wake starts: :func:`mcgyvr.wake.compose_for` chooses out of
    #: :attr:`specs`, because a host cut into alternatives leaves this exact
    #: path on disk holding both units on one card, and starting it is the
    #: overcommit ``hold_together`` was written to refuse. Kept because it is
    #: what an operator types for the ordinary host and what every fleet emitted
    #: before 2026-09-09 is called.
    compose_file: Path | None
    #: Every launch spec on disk for this card, sorted — :func:`spec_files`.
    #: More than one means mcgyvr holds several and no way to tell which is
    #: current; that is D2's gap, and a wake declines rather than guessing.
    specs: tuple[Path, ...] = ()
    #: Every rung this card serves, sorted. Whole-card eviction takes all of
    #: them, so a caller that knew only the rung it was asked about would sleep
    #: a card another rung was serving from.
    rungs: tuple[str, ...] = ()
    #: The sources those rungs reach it through, sorted. A card is one machine
    #: and a source is one process, so this is many-to-one on purpose.
    sources: tuple[str, ...] = ()


def cards(config: Config) -> dict[str, Card]:
    """The card each rung's work lands on, keyed by rung name.

    **From the config alone, and from no scan.** :func:`units_for` needs a
    :class:`~mcgyvr.scan.Scan` per host because it has to decide a fit, and a
    card's identity needs no fit: it is the host the source's URL names and the
    file :mod:`mcgyvr.emit` wrote for it. That is what keeps the wake path
    usable on a machine that never scanned the rig — a laptop dispatching at a
    ladder it did not size can still tell a card it holds a spec for from one it
    does not.

    **The launch specs are the ones on disk, not the ones a name predicts.**
    ``d8c5cf0a`` made ``emit`` able to write more than one file for a host, and
    ``emit.planned_paths`` exists so a caller can ask the planner rather than
    spelling the convention — but the planner needs units, units need a scan,
    and needing a scan is exactly what this function is for not needing. **So
    the planner cannot be asked here, and the honest substitute is not a
    hardcoded name but a listing**: :func:`spec_files` recognises every file
    mcgyvr's own convention gives this host and hands back all of them.

    A hardcoded ``compose.<host>.yml`` was wrong in both directions and both
    were live. It **missed** a host emitted as N alternatives — the covering of
    three 5 GiB units on a 12 GiB card is ``{A,B}`` and ``{A,C}``, so that name
    is never written at all and a card ``emit`` had just written two specs for
    read as "no launch spec". And it **found** the file an earlier emit left
    behind when the same host stopped fitting together, which holds every unit
    on one card: a wake would have started the overcommit
    :func:`hold_together` used to refuse, with ``emit --check`` clean, because a
    check reads only planned paths.

    Which of several specs is the current one is still not a question the config
    answers, and D2 of ``records/plans/sleep-wake.md`` records that as a genuine
    gap: the files' existence answers "can mcgyvr bring this back?" and does not
    answer "bring back *which*", and nothing measured says how it should be
    chosen. What changed is that mcgyvr can now *see* the ambiguity instead of
    resolving it by accident.

    **A source that needs a credential has no card.** It is somebody else's
    machine reached over the internet, mcgyvr holds no launch spec for it, and
    it is never asleep — only up or down. That is the honest degradation D2
    asks for, and it falls out of the one fact the config already states.
    """
    stated = config.get("serving.compose_dir")
    where = Path(str(stated)).expanduser() if stated else None

    rungs_on: dict[str, list[str]] = {}
    sources_on: dict[str, set[str]] = {}
    hosted: dict[str, str] = {}
    for tier in config.ladder.tiers:
        source = config.sources.get(tier.source)
        if source is None or source.requires_credential:
            continue
        host = host_of(source.base_url)
        hosted[tier.name] = host
        rungs_on.setdefault(host, []).append(tier.name)
        sources_on.setdefault(host, set()).add(tier.source)

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
    """Serving specs an operator wrote down, which override the shipped table.

    mcgyvr sizes from what it can measure, and this is the seam where somebody
    states what it cannot — or points at a measurement of their own:
    ``geometry_json`` names a ``ggufscan`` row, and from there the model's
    bytes are the scan's and not the block's. A block that states a
    ``disk_gb`` beside a geometry it disagrees with is refused
    (:class:`ModelSpec`), because two numbers for one file is the situation a
    scan exists to end. Everything else an operator writes is honoured: a
    ``ram_gb`` floor this module cannot see, a ``vram_gb`` for a dense model
    nobody has scanned.

    A relative ``geometry_json`` is read against the config file's own
    directory, so a config and the scan it cites travel together.

    It lives here rather than in :mod:`mcgyvr.config` because a
    :class:`ModelSpec` is a serving type and config cannot import serving
    without a cycle. Already in GiB: the schema says so on every size field,
    because a unit is the one thing a reader cannot check by eye.
    """
    blocks: Mapping[str, Any] = config.data.get("models") or {}
    specs: dict[str, ModelSpec] = {}
    for name, block in blocks.items():
        geometry: dict[str, Any] | None = None
        stated = block.get("geometry_json")
        if stated:
            where = Path(str(stated)).expanduser()
            if not where.is_absolute() and config.path is not None:
                where = config.path.parent / where
            geometry = load_geometry(where, name=name)
        specs[name] = ModelSpec(
            name=name,
            vram_gb=block.get("vram_gb") or 0.0,
            ram_gb=block.get("ram_gb") or 0.0,
            disk_gb=block.get("disk_gb") or 0.0,
            moe=bool(block.get("moe")),
            geometry=geometry,
            hf_cache=str(block.get("hf_cache") or ""),
            serve_args=tuple(str(arg) for arg in (block.get("serve_args") or ())),
            kv_cache_dtype_k=block.get("kv_cache_dtype_k"),
            kv_cache_dtype_v=block.get("kv_cache_dtype_v"),
        )
    return specs


#: What a ``ggufscan`` row carries that this module reads. A file missing one
#: of these is not a scan, whatever else it says, and is refused by name.
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
    """One ``ggufscan`` row from ``path``, refused rather than repaired.

    Two shapes are read. A serving-door envelope's ``geometry.json`` is one
    row; ``python -m mcgyvr.serving.ggufscan <gguf>`` prints a list of them,
    one per file it was pointed at. A list of one is that one; a list of more
    needs ``name`` to choose by, and the row chosen is the one whose ``file``
    is the weights file that model serves — never the first, because the
    first row of a directory scan is whichever file sorts first.

    A row ``ggufscan`` could not read is written as ``{"file": …, "error":
    …}`` rather than dropped, so that a directory scan says which file it
    failed on. It is refused here for the same reason: a placement derived
    from an error row would be derived from nothing.
    """
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
    """The machine a source's URL names, which is what a scan is keyed by."""
    host = urlparse(base_url).hostname
    if not host:
        raise UnitError(f"no host in base_url {base_url!r}")
    return host


def port_of(base_url: str) -> int:
    """The port a source's URL reaches, or the one the engine would have picked.

    A URL that states no port is not an omission to be refused: ``http://host``
    is the ordinary way of writing "wherever llama-server lands", and the
    answer is :data:`DEFAULT_PORT`. A URL that states a *malformed* port is a
    different thing — someone wrote a number down and it is not one — and it
    surfaces here, where it is still a fixable line of config.
    """
    try:
        port = urlparse(base_url).port
    except ValueError as exc:
        raise UnitError(f"no usable port in base_url {base_url!r}: {exc}") from exc
    return port if port is not None else DEFAULT_PORT


def _with_rungs(unit: Unit, rungs: tuple[str, ...]) -> Unit:
    """The same process, told which rungs point at it."""
    return replace(unit, rungs=rungs)


def _roomiest_gpu(scan: Scan) -> Gpu:
    """The card with the most free memory. A scan with none cannot host a unit."""
    if not scan.gpus:
        raise UnitError(
            f"{scan.machine.host}: the scan found no GPU, so there is no card "
            "to place a unit on"
        )
    return max(scan.gpus, key=lambda gpu: gpu.vram.free_mib)


def _free_vram_bytes(scan: Scan) -> int:
    """Free VRAM on the roomiest card — free, because used memory is someone's.

    Read off the scan every time and cached nowhere: the number is a fact
    about the card at the moment it was scanned, and a unit is sized against
    that moment.
    """
    if not scan.gpus:
        return 0
    return max(gpu.vram.free_mib for gpu in scan.gpus) << 20


def _allowance_gb(spec: ModelSpec) -> float:
    """What a fit for ``spec`` holds back on the card, in GiB."""
    if spec.geometry is None:
        return DEFAULT_HEADROOM_GB
    return vramfit.SCRATCH_AND_CONTEXT_MIB / 1024


def _needs_geometry(spec: ModelSpec) -> str:
    return (
        f"{spec.name}: sizing an MoE needs its geometry: run "
        f"python -m mcgyvr.serving.ggufscan <gguf> and set "
        f"models.{spec.name}.geometry_json, or point it at the envelope's "
        f"geometry.json. --n-cpu-moe moves whole blocks, and what each block's "
        f"experts weigh is in the tensor table and nowhere else — not in a "
        f"name, a parameter count or a file size"
    )


@dataclass(frozen=True)
class _Placement:
    """Where one model's weights end up on one machine, and the flags that say so.

    Private because it is an intermediate answer and not a fact about a unit:
    what survives into a :class:`Unit` is the argv and the :class:`Fit`. It
    exists so that the card figure, the memory figure, the slot count and
    ``--n-cpu-moe`` are one derivation read four times rather than four
    derivations that have to be kept in step by hand.

    ``n_cpu_moe`` is a block INDEX, as the flag reads it: blocks below it go
    to the CPU whether or not they carry experts. ``vram_gb`` is the predicted
    card figure with the scratch allowance inside it (or the stated working
    set, on the scalar path), and ``headroom_gb`` is that allowance.
    """

    n_cpu_moe: int
    width: int
    vram_gb: float
    ram_gb: float
    headroom_gb: float


def _placement(
    spec: ModelSpec,
    free_bytes: int,
    width: int | None = None,
    *,
    host: str,
    ctx_per_slot: int,
    n_ubatch: int = DEFAULT_UBATCH,
) -> _Placement:
    """How this card splits this model, and how wide it can be served.

    Derived here and nowhere else, because the offload is four answers at once
    — what the card holds, what memory holds, how many slots, and the number
    written into ``--n-cpu-moe`` — and separate derivations of it are chances
    to disagree. The disagreement is not academic: a fit that checks one width
    while the argv emits another approves a placement nobody sized.

    With a geometry the card figure is :mod:`vramfit`'s law and nothing here
    is a constant of this module's: ``C(w)`` is the non-expert weights plus
    the cache and recurrent state the header implies for ``w`` slots at
    ``ctx_per_slot`` each (``-c`` being the total, ``-ub`` the micro-batch the
    cache is padded against), plus the one scratch allowance; the floor is the
    lowest ``--n-cpu-moe`` whose remaining expert blocks fit beside ``C`` on
    this card, walked block by block off the tensor table. ``None`` from that
    walk means the card cannot hold ``C`` alone — a statement about the card,
    refused as one. A dense geometry has no placeable blocks and the same walk
    stops at zero, so a dense model with its header is sized by the same law.

    The width, when nobody wrote one, is as wide as the card allows without
    moving one more expert block off it: the largest ``w`` up to
    :data:`MAX_WIDTH` whose floor is still the floor at one slot. A slot is
    cache and state on the card; the moment a further slot costs a block of
    experts it is paid for in tokens per second on every request, and that is
    a trade for an operator to write down (``max_parallel`` on the rung), not
    one to make silently. A written width is honoured and the floor recomputed
    at it, so the argv's ``--parallel`` and its ``--n-cpu-moe`` were sized
    together.

    The RAM figure is what this card actually spills, plus the runtime that
    spilling carries with it — not the whole model weight. The declaration is
    still honoured as a floor, so an operator who states a memory demand this
    module cannot see is not overruled by it.

    Without a geometry there is only the scalar path: the stated working set,
    the stated memory floor, no offload, and one slot unless one was written.
    An MoE has no scalar path; it is refused here and by :func:`fit`.
    """
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
            # Never caught into a default: an undeclared sliding-window split
            # or a recurrent model with no state size is a request for a
            # measurement, and the message says which one.
            raise UnitError(
                f"{spec.name}: the cache cannot be sized, so nothing is placed "
                f"from an invented split: {exc}"
            ) from exc
        return (
            int(geometry["bytes_nonexpert"])
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
        ram_gb=max(spec.ram_gb, _host_gb(geometry, n_cpu_moe, host=host)),
        headroom_gb=vramfit.SCRATCH_AND_CONTEXT_MIB / 1024,
    )


def _host_gb(geometry: dict[str, Any], n_cpu_moe: int, *, host: str) -> float:
    """What system memory holds at this offload: the spilled experts, plus the
    runtime that spilling carries — and nothing when nothing spills.

    The runtime intercept is per-rig and read from ``tools/runs/derived.json``;
    a rig whose figure is absent is refused by name, never defaulted.
    """
    offloaded = int(geometry["bytes_experts"]) - vramfit.experts_on_card(
        geometry, n_cpu_moe
    )
    if offloaded <= 0:
        return 0.0
    try:
        resident = derived.runtime_resident_gb(host)
    except derived.DerivedNumbersError as exc:
        raise UnitError(str(exc)) from exc
    return offloaded / _BYTES_PER_GIB + resident


def _window_for(
    key: UnitKey, declared: Mapping[int, list[str]], ctx_per_slot: int | None
) -> int:
    """The window this unit is sized and launched at, from the config or the run.

    Three ways to have one and two ways to have none. A single declared window
    is the answer, and it is the answer even when the run also stated one and
    stated the same thing — saying a number twice is not a disagreement. A run
    window is the answer where nothing was declared, which is what a fleet
    nobody has read back looks like.

    Both of the refusals name what is missing or what disagrees, because both
    are one edit away from being right and neither is this module's to guess.
    """
    if len(declared) > 1:
        pairs = ", ".join(
            f"{window} ({', '.join(sorted(names))})"
            for window, names in sorted(declared.items())
        )
        raise UnitError(
            f"{key.slug}: one process, {len(declared)} declared context "
            f"windows — {pairs}. These sources name one URL, so one window "
            f"would silently lose and the rung behind it would be served a "
            f"window its contracts were never priced against. Point them at "
            f"one window, or at two ports"
        )
    if declared:
        ((window, names),) = declared.items()
        if ctx_per_slot is not None and ctx_per_slot != window:
            raise UnitError(
                f"{names[0]}: declares context_window {window} and this run "
                f"was told {ctx_per_slot}. Both numbers are in hand and they "
                f"are two different launches, so neither is preferred here: "
                f"edit the source if the rig moved, or drop the flag if it "
                f"did not"
            )
        return window
    if ctx_per_slot is None:
        raise UnitError(
            f"{key.slug}: no context window was declared for this run and its "
            f"source declares none, so nothing can be sized: the cache, the "
            f"`-c` on the argv and the `--n-cpu-moe` floor are all priced "
            f"against it, and a window this module chose would be a number "
            f"nobody measured. Declare it — read it back off the running unit "
            f"(`max_model_len` on vLLM, `n_ctx` on llama.cpp) and state what "
            f"it said"
        )
    return ctx_per_slot


def _offload_note(spec: ModelSpec, placed: _Placement) -> str:
    """The offload a refusal is about, so the reader can check the arithmetic."""
    if spec.geometry is None or not spec.moe:
        return ""
    placeable = list(spec.geometry["placeable_blocks"])
    on_card = sum(1 for block in placeable if block >= placed.n_cpu_moe)
    return (
        f" (--n-cpu-moe {placed.n_cpu_moe}: {on_card} of {len(placeable)} expert "
        f"blocks on the card)"
    )


def _threads(scan: Scan) -> int:
    """Physical cores, not threads.

    The sweep's advice on srv2 was "take ``-t 10``" on a 10-core, 20-thread
    machine: t20, t16 and t10 were flat within noise. Expert GEMM on the CPU
    is memory-bound, and a second thread on a core adds no memory ports — it
    adds contention, and on this rig it also takes the cores the acceptance
    gate runs on. Never above what the machine has, whichever number is read.
    """
    if scan.cpu is None:
        return 1
    return max(1, min(scan.cpu.cores or scan.cpu.threads, scan.cpu.threads))


def _weights_file_name(name: str) -> str:
    """The file a model id is served from, and the name a geometry must carry.

    The separator is flattened rather than followed (see :func:`_weights_path`)
    and the extension is this module's, so a geometry scanned from
    ``Qwen_Qwen2.5-Coder-7B-Instruct-AWQ.gguf`` belongs to the id
    ``Qwen/Qwen2.5-Coder-7B-Instruct-AWQ`` and to nothing spelled differently.
    """
    return f"{name.replace('/', '_')}.gguf"


def _weights_path(scan: Scan, spec: ModelSpec) -> Path:
    """Where the weights sit, *directly* under the directory the scan measured.

    A model id can be a repository path — ``Qwen/Qwen2.5-Coder-7B-Instruct-AWQ``
    is one the shipped table carries — and spelling that into the file name
    puts the file one directory down. The unit's ``weights_dir`` is then
    ``/srv/weights/Qwen`` while the disk check was about ``/srv/weights``, so
    what gets bind-mounted is not the directory anything was measured about;
    and if it does not exist, Docker creates it, empty and root-owned, and the
    server fails at load against a mount the operator then has to go and delete
    by hand.

    So the separator is flattened rather than followed. A model id is a name
    here, not a path: the id keeps its shape in the file name, and the file
    stays in the directory the scan is a statement about.
    """
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
    """The cache a run's own declaration asks for, derived in one place.

    The multiplication ``ctx_per_slot * slots`` used to happen twice — once in
    :func:`unit_for`, writing ``-c`` onto the argv, and once in
    :func:`_placement`, feeding :func:`vramfit.kv_bytes` — and the two were fed
    by different readers. ``emit`` used the module's 4096 and the door used its
    own ``--ctx-per-slot`` default of 2048, so an ``--n-cpu-moe`` floor derived
    through the door was computed against half the cache the compose file it
    was derived for actually launches with. A floor is only correct for the
    cache the unit will actually allocate, so the law and the launch have to be
    fed one number, and this is the function that produces it.

    Two answers, and which one comes back depends on what the caller can price
    it against:

    * **With a ``geometry``** — a ``ggufscan`` header — the answer is device
      bytes, summed per layer by :func:`vramfit.kv_bytes`. That is the figure a
      placement is judged with, and it is not linear in the window: a
      sliding-window checkpoint caps its sliding half at
      ``PAD256(n_swa x seqs + n_ubatch)``, so doubling the declared window does
      not double the cache and must not be assumed to.

    * **Without one** the answer is the extent in tokens, which is exactly what
      ``-c`` states and exactly what :func:`vramfit.kv_bytes` is handed as its
      ``n_ctx``. Nothing here invents a bytes-per-token rate to convert it: a
      cache cannot be priced in bytes without a header, and a plausible
      unfalsifiable number is the failure :mod:`mcgyvr.serving.vramfit` exists
      to end.

    Both are the size of one thing asked in the two units it can be asked in,
    and the caller says which by handing over a header or not.
    """
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
    """The window a *running* unit says it serves, read from what it published.

    Declared going in and measured coming back are two different questions, and
    only this one is a fact about a process. No module knows the answer in
    advance: on 2026-09-06 srv2:8001 and srv2:8002 reported ``max_model_len``
    4096 on ``/v1/models`` and srv1:8080 reported ``n_ctx`` 4096 on ``/props``,
    each over its own API, and any of the three could have been started
    otherwise.

    Both engines are read because both serve rungs on this ladder. vLLM lists
    its models under ``data``; llama.cpp answers about the one process it is.

    ``None`` is a unit that published nothing, and it is deliberately not the
    same answer as a number: "this unit serves 4096" and "nobody can say what
    this unit serves" lead to different moves, and collapsing them into a
    window somebody assumed is how a ladder ends up priced against a rig it
    never asked.
    """
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
