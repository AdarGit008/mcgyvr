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

Every number in it is read off a :class:`~mcgyvr.scan.Scan` rather than
declared, because the questions this module answers are the ones a nameplate
cannot. Free VRAM decides a fit today; total VRAM decides nothing. And a model
too big for the card is not automatically a model the machine cannot serve: an
MoE spills its experts to RAM, so fit is a question about a *machine* — card,
memory and disk together — not about a GPU.

The arithmetic below is anchored on the sweep in
``records/measurements/serving-sweep-2026-08-25/``, which timed 32
configurations on the two rigs this module was written for. Where a constant
here has a number in it, that record is where the number came from.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcgyvr.config import Config
from mcgyvr.detect import MIB_PER_GB
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Gpu, Scan, default_weights_dir

# The engine a unit gets when nothing says otherwise. A source's ``api`` is a
# wire protocol (:class:`mcgyvr.pool.Protocol`) and cannot answer this: vLLM
# and llama-server both speak ``openai`` and take entirely different argv.
DEFAULT_ENGINE = "llama.cpp"

# The context every sweep cell ran at. Held here so the slot arithmetic below
# and the emitted ``-c`` cannot drift apart.
DEFAULT_CONTEXT = 4096

# llama.cpp's own default port — what the engine would bind if nothing said
# otherwise. It is the fallback and never a preference: a unit built from a
# ladder takes its port from the source URL, and this number only stands in
# where nobody wrote one down, so stating it costs nothing and changes nothing.
DEFAULT_PORT = 8080

# MoE geometry. ``--n-cpu-moe N`` keeps the expert tensors of N blocks on the
# CPU, so sizing it needs two things a model knows about itself: how many
# blocks it has, and how much of its weight is experts. Both are now fields on
# :class:`ModelSpec` rather than constants here, and a spec that states neither
# is refused by :func:`fit`.
#
# There used to be an ``EXPERT_SHARE = 0.92`` and a ``MOE_BLOCKS = 48``. Read
# against the file the provenance comment cited — Qwen3.6-35B-A3B-UD-IQ3_XXS,
# byte-identical to the sweep's — both were wrong, and so was the unit they
# were applied in:
#
#   block count   48 declared, 40 actual
#   expert share  0.92 declared, 0.8416 actual
#   disk_gb       a decimal-GB numeral from the capability table, divided as
#                 though it were GiB (``detect.MIB_PER_GB = 1024.0``)
#
# The three errors multiplied to 0.978, so the per-block figure they produced
# was within 1% of the sweep's measurement and correcting any one of them
# alone made it worse. The complement did not cancel: ``1 - 0.92`` against a
# true residue fraction of 0.1475 left the resident floor at roughly half what
# the file leaves non-expert, which is the direction that OOMs a host. A
# constant that is only right because three mistakes cancel is not a constant
# to correct — it is one to delete, which is what happened here.
#
# The expert mass is per model and per quant: the same architecture at another
# quantisation has a different one, and the layers are not uniform (this file
# runs 262 MiB for 37 blocks and 300 MiB for 3). Nothing derivable from a name
# or a parameter count answers it, so the spec carries it or the fit refuses.

# What system memory holds beyond the offloaded experts themselves: context,
# compute buffers, and the copy paths that do not live on the card. Measured
# across the sweep's six ``--n-cpu-moe`` cells on srv2, where
# ``RSS - blocks * expert_per_block`` sat at 1.52-1.53 GiB at every setting
# from 4 blocks to 20 — flat, which is what makes it an intercept rather than
# a rate. It applies only where experts actually spill: a model held entirely
# on the card is not paying it, and a dense model has no spill to pay it for.
RUNTIME_RESIDENT_GB = 1.53

# What one extra slot costs on the card. The sweep bounds it from below: q8_0
# KV freed 36 MiB across 4 slots at 4096 (11,882 -> 11,846 MiB on an otherwise
# identical cell), so f16 KV is ~18 MiB per slot for that family. 64 MiB is a
# deliberate over-allowance of about 3.5x — a slot also costs compute buffers,
# and a model with wider KV heads costs more per slot than this one. It is not
# a larger margin than that, because the margin is subtracted from the slots a
# rig is allowed to serve: the previous 0.25 was 256 MiB, fourteen times the
# measurement, and it cost a 12 GB card ten slots it could measurably hold.
KV_GB_PER_SLOT = 0.0625

# The widest configuration anyone has measured on these rigs (#366, 32 slots on
# a 12 GB card). Past it this arithmetic would be extrapolating.
MAX_WIDTH = 32


class UnitError(Exception):
    """A serving unit could not be built for a host, a model or a rung."""


@dataclass(frozen=True)
class ModelSpec:
    """What a model costs, in the three places a machine can run out.

    ``vram_gb`` is the working set on the card — what it holds with nothing
    offloaded, which is not the same as the weights on disk, because a working
    set carries buffers (deepseek-coder-v2:16b's is 0.5 GB larger than its
    weights). ``disk_gb`` is those weights.

    ``ram_gb`` is what system memory may be asked to hold: zero for a dense
    model, which has nowhere to spill to, and for an MoE the experts it can
    push off the card. It is a claim about the model and not a split of it —
    how much actually spills depends on the card and is derived per machine by
    :func:`fit`, which refuses on whichever of the two numbers is larger.

    ``moe`` is not cosmetic and not inferable from the numbers: it says the
    model has a knob for *where* its weights sit, which is the difference
    between "does not fit" and "fits differently on this machine".

    ``blocks`` is what that knob counts — ``--n-cpu-moe N`` moves the experts
    of N transformer blocks — and ``expert_gb`` is how much weight those blocks
    hold between them. ``None`` on either says nobody has stated it, and an MoE
    missing either is refused rather than sized from a family default: the
    per-block cost is the expert mass over the block count, so a wrong value in
    the numerator or the denominator is not a rounding difference but gigabytes
    placed in the wrong memory.

    Both default to ``None`` on purpose. There is no honest default for either
    — the block count varies by architecture and the expert mass varies by
    quantisation of the *same* architecture — and the constants that used to
    stand in for them were wrong in both places at once. They arrive from a
    reader that has seen the file, or from an operator who states them, or the
    fit declines. Every unit in this module is in GiB, which is the convention
    :data:`mcgyvr.detect.MIB_PER_GB` sets; a caller holding decimal GB converts
    before it builds a spec.
    """

    name: str
    vram_gb: float
    ram_gb: float
    disk_gb: float
    moe: bool = False
    blocks: int | None = None
    expert_gb: float | None = None


@dataclass(frozen=True)
class Width:
    """A slot count, and whether anyone actually said it.

    A width mcgyvr derived from a card and a width an operator wrote in the
    config are different facts, and a unit that lost the difference could not
    explain itself. ``how`` is ``"written"`` only when the caller stated the
    number.
    """

    value: int
    how: str


@dataclass(frozen=True)
class Fit:
    """Whether this machine can hold this model right now, and why.

    ``headroom_gb`` is what was held back on the card rather than what was left
    over: the reserve is the claim being made, and it is absolute because what
    it protects — KV cache and compute buffers — is sized by tokens and not by
    GPU (CAV-04, and :meth:`mcgyvr.capability.CapabilityTable.fitting`).
    """

    fits: bool
    headroom_gb: float
    why: str


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

    @property
    def weights_dir(self) -> Path:
        """The directory to mount; the container sees the file inside it."""
        return self.weights.parent


def fit(scan: Scan, spec: ModelSpec) -> Fit:
    """Whether ``scan``'s machine can hold ``spec``, measured not declared.

    Four refusals, checked in the order that makes the message useful. A spec
    this module cannot size comes first, because it is a fact about the
    catalogue rather than about the machine and no amount of hardware answers
    it. Disk is next because weights that are not on the machine cannot be
    loaded however much memory there is, and a report that says "needs more
    VRAM" about a model that was never downloaded sends someone to the wrong
    shop. Memory comes before the card because an MoE that clears the card by
    spilling experts has only moved the demand, and the message an operator can
    act on names the memory it moved into.

    The RAM and VRAM refusals both read one :func:`_placement`, which is the
    same call :func:`unit_for` makes to size ``--n-cpu-moe``. That is the point
    of this function: checking a number here that the emitted argv does not
    honour is how a fit says yes to an offload the machine cannot hold, which
    is a compose file that passes review and swaps the host.

    Never raises. An unmeasurable machine is a machine nothing is claimed
    about — the same rule :mod:`mcgyvr.scan` runs on.
    """
    free_vram = _free_vram_gb(scan)
    available_ram = scan.memory.available_gb if scan.memory else 0.0

    if spec.moe and (not spec.blocks or spec.expert_gb is None):
        missing = " and ".join(
            name
            for name, absent in (
                ("a block count", not spec.blocks),
                ("an expert mass", spec.expert_gb is None),
            )
            if absent
        )
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: sizing an MoE offload needs a block count and an "
                f"expert mass, and this spec is missing {missing}. --n-cpu-moe "
                "counts blocks and the per-block cost is the expert mass over "
                "that count, so both are the model's own and neither is "
                "derivable from its name, its parameter count or its file size. "
                "Refusing rather than guessing: state them under `models:` in "
                "the config, or point this at a reader that has seen the file"
            ),
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

    placed = _placement(spec, free_vram)
    if placed.ram_gb > available_ram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {placed.ram_gb:.1f} GB of RAM"
                f"{_offload_note(spec, placed)}, "
                f"{available_ram:.1f} GB available"
            ),
        )
    if placed.vram_gb + DEFAULT_HEADROOM_GB > free_vram:
        return Fit(
            fits=False,
            headroom_gb=DEFAULT_HEADROOM_GB,
            why=(
                f"{spec.name}: needs {placed.vram_gb:.1f} GB on the card plus "
                f"{DEFAULT_HEADROOM_GB:.1f} GB headroom, "
                f"{free_vram:.1f} GB free"
            ),
        )

    spilled = (
        f", {placed.ram_gb:.1f} GB of experts in RAM{_offload_note(spec, placed)}"
        if spec.moe and placed.ram_gb
        else ""
    )
    return Fit(
        fits=True,
        headroom_gb=DEFAULT_HEADROOM_GB,
        why=(
            f"{spec.name}: {placed.vram_gb:.1f} GB on the card of "
            f"{free_vram:.1f} GB free, "
            f"{DEFAULT_HEADROOM_GB:.1f} GB headroom held back{spilled}"
        ),
    )


def unit_for(
    scan: Scan,
    spec: ModelSpec,
    *,
    engine: str = DEFAULT_ENGINE,
    width: int | None = None,
    port: int = DEFAULT_PORT,
) -> Unit:
    """The one process that would serve ``spec`` on the machine ``scan`` measured.

    A unit that cannot load is not a unit, so a spec this machine does not fit
    is refused here with the fit's own reason rather than emitted and found out
    by the loader.

    ``port`` is where this process is expected to answer. A scan and a spec do
    not know that — only a ladder does — so a unit built from those two alone
    takes :data:`DEFAULT_PORT`, which is the number the engine would have
    chosen anyway. :func:`units_for` is where the config's answer arrives.
    """
    sized = fit(scan, spec)
    if not sized.fits:
        raise UnitError(f"{scan.machine.host}: {sized.why}")

    gpu = _roomiest_gpu(scan)
    free_vram = gpu.vram.free_mib / MIB_PER_GB
    # The same derivation :func:`fit` just approved, not a second one that
    # agrees today: an argv whose offload differs from the one the fit checked
    # is a unit that was never sized for this machine.
    placed = _placement(spec, free_vram)
    chosen = (
        Width(value=width, how="written")
        if width is not None
        else Width(value=_derived_width(free_vram, placed.vram_gb), how="derived")
    )
    weights = _weights_path(scan, spec)

    # Flag → value throughout, which is the shape both renderings of a launch
    # spec need; a valueless switch would have to be a special case in each of
    # them, so anything that is one is not expressed here.
    args: dict[str, str] = {
        "--model": str(weights),
        "-ngl": "99",
        "-c": str(DEFAULT_CONTEXT),
        "-fa": "on",
        "--parallel": str(chosen.value),
        "-t": str(_threads(scan)),
    }
    # A card roomy enough for every expert derives zero blocks, and
    # ``--n-cpu-moe 0`` is a no-op printed into a file a person reads: it says
    # this rig offloads experts when it does not, and invites tuning a number
    # that was never in play.
    if spec.moe and placed.blocks > 0:
        args["--n-cpu-moe"] = str(placed.blocks)

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
    )


def units_for(
    config: Config,
    scans: Mapping[str, Scan],
    *,
    specs: Iterable[ModelSpec],
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
    """
    # The config wins over the table, and the precedence lives here rather than
    # in the caller so that every caller gets it: measured where mcgyvr can
    # measure, stated where it cannot, refused only when neither has an answer.
    catalogue = {spec.name: spec for spec in specs} | declared_models(config)
    grouped: dict[UnitKey, list[str]] = {}
    hosts: dict[UnitKey, Scan] = {}
    models: dict[UnitKey, ModelSpec] = {}
    widths: dict[UnitKey, int] = {}

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
        hosts.setdefault(key, scan)
        models.setdefault(key, spec)
        if tier.max_parallel is not None:
            # One process, one slot count. Two rungs asking for different
            # widths get the larger, because a slot the second rung never uses
            # costs KV cache and a slot it needs and does not have is a queue
            # nobody declared. The source's own ``max_parallel`` is not read
            # here: that number bounds dispatch, which is capacity.py's, and a
            # rung that states nothing has stated nothing about this process.
            widths[key] = max(widths.get(key, 0), tier.max_parallel)

    return tuple(
        _with_rungs(
            unit_for(
                hosts[key],
                models[key],
                engine=key.engine,
                width=widths.get(key),
                port=key.port,
            ),
            tuple(rungs),
        )
        for key, rungs in grouped.items()
    )


def declared_models(config: Config) -> dict[str, ModelSpec]:
    """Serving specs an operator wrote down, which override the shipped table.

    mcgyvr sizes from what it can measure, and this is the seam where somebody
    states what it cannot. Nothing here is second-guessed: a declaration that
    is wrong produces a launch spec that fails on the rig, and that is the
    operator's call to make rather than this module's to prevent. What the
    module still owes them is to say what it measured — which it does, in the
    fit's ``why`` — and then do what it was told.

    It lives here rather than in :mod:`mcgyvr.config` because a
    :class:`ModelSpec` is a serving type and config cannot import serving
    without a cycle. Already in GiB: the schema says so on every size field,
    because a unit is the one thing a reader cannot check by eye.
    """
    blocks: Mapping[str, Any] = config.data.get("models") or {}
    return {
        name: ModelSpec(
            name=name,
            vram_gb=block.get("vram_gb") or 0.0,
            ram_gb=block.get("ram_gb") or 0.0,
            disk_gb=block.get("disk_gb") or 0.0,
            moe=bool(block.get("moe")),
            blocks=block.get("blocks"),
            expert_gb=block.get("expert_gb"),
        )
        for name, block in blocks.items()
    }


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


def _free_vram_gb(scan: Scan) -> float:
    """Free VRAM on the roomiest card — free, because used memory is someone's."""
    if not scan.gpus:
        return 0.0
    return max(gpu.vram.free_mib for gpu in scan.gpus) / MIB_PER_GB


@dataclass(frozen=True)
class _Placement:
    """Where one model's weights end up on one machine, and the flag that says so.

    Private because it is an intermediate answer and not a fact about a unit:
    what survives into a :class:`Unit` is the argv and the :class:`Fit`. It
    exists so that the card figure, the memory figure and ``--n-cpu-moe`` are
    one derivation read three times rather than three derivations that have to
    be kept in step by hand.
    """

    blocks: int
    vram_gb: float
    ram_gb: float


def _placement(spec: ModelSpec, free_vram_gb: float) -> _Placement:
    """How this card splits this model, in the two places the split lands.

    Derived here and nowhere else, because the offload is three answers at once
    — what the card holds, what memory holds, and the number written into
    ``--n-cpu-moe`` — and three separate derivations of it are three chances to
    disagree. The disagreement is not academic: a fit that checks the fully
    offloaded floor while the argv offloads half of it approves a placement
    nobody sized.

    A dense model has no knob, so its working set is the demand and whatever
    the spec says about system memory stands. So does an MoE whose block count
    nobody stated — :func:`fit` refuses that one before it reaches here, and
    answering "no offload" is the honest shape for a knob this module cannot
    turn.

    The RAM figure is what this card actually spills, plus the runtime that
    spilling carries with it — not the whole model weight. It used to be
    ``max(spec.ram_gb, spilled)`` with ``spec.ram_gb`` set to the entire file
    for every MoE, which made the ``max()`` win every time and the block count
    irrelevant to the answer: four blocks offloaded and thirty-six both claimed
    13.2 GB. Against the sweep's own cells that over-claimed by 1.9x to 4.8x.
    The declaration is still honoured as a floor, so an operator who states a
    memory demand this module cannot see is not overruled by it.
    """
    if not spec.moe or not spec.blocks or spec.expert_gb is None:
        return _Placement(blocks=0, vram_gb=spec.vram_gb, ram_gb=spec.ram_gb)
    total = spec.blocks
    blocks = _offload_blocks(spec, free_vram_gb, total)
    spilled = (
        blocks * _expert_gb_per_block(spec, total) + RUNTIME_RESIDENT_GB
        if blocks
        else 0.0
    )
    return _Placement(
        blocks=blocks,
        vram_gb=_resident_gb(spec, blocks, total),
        ram_gb=max(spec.ram_gb, spilled),
    )


def _offload_note(spec: ModelSpec, placed: _Placement) -> str:
    """The offload a refusal is about, so the reader can check the arithmetic."""
    if not spec.moe or not spec.blocks:
        return ""
    return f" ({placed.blocks} of {spec.blocks} blocks of experts on the CPU)"


def _expert_gb_per_block(spec: ModelSpec, blocks: int) -> float:
    """What one block's experts weigh: the expert mass over the model's blocks.

    Both numbers are the model's own. Neither is derived from the other, and
    neither is a share of the file — the previous form divided ``disk_gb`` by a
    constant fraction and a constant block count, and was wrong in the mass,
    the count and the unit simultaneously.

    This is an average across blocks and the blocks are not equal: the file the
    sweep drove carries 262 MiB of experts in 37 of its blocks and 300 MiB in
    the other 3. ``--n-cpu-moe N`` takes the *first* N, so an offload that stays
    inside the cheap band costs less than this says and one that reaches the
    expensive blocks costs more. Averaging is the conservative direction for
    small N, which is the direction a small card offloads in.
    """
    if spec.expert_gb is None:  # pragma: no cover - fit() refuses first
        raise UnitError(f"{spec.name}: no expert mass stated")
    return spec.expert_gb / blocks


def _resident_floor_gb(spec: ModelSpec) -> float:
    """What stays on the card with every expert block offloaded.

    Attention, embeddings and the norms: ``--n-cpu-moe`` cannot move them, so
    this is the smallest a model can be made on a GPU, and the number a fit
    against a small card is really asking about.

    Now a subtraction between two figures the model states rather than a
    fraction of one of them. That matters in the direction it was wrong before:
    the old ``disk_gb * 0.08`` put this at 1082 MiB for a file that leaves 1995
    MiB non-expert, and a floor set below what the weights actually leave is a
    fit approved against room the card will not have.
    """
    if spec.expert_gb is None:  # pragma: no cover - fit() refuses first
        raise UnitError(f"{spec.name}: no expert mass stated")
    return max(0.0, spec.disk_gb - spec.expert_gb)


def _offload_blocks(spec: ModelSpec, free_vram_gb: float, blocks: int) -> int:
    """How many blocks of experts this card needs pushed onto the CPU.

    Derived, never tabulated. With ``-ngl 99`` the card holds every weight
    except the experts of the blocks named here, so the deficit is what the
    weights want minus what the card has after the headroom is held back, and
    each block moved buys back one block's worth of experts. Two rigs with
    different free VRAM therefore get different numbers from the same model,
    and the smaller card gets the larger one — which is the shape the sweep
    measured (srv1, 6 GB: 28 blocks; srv2, 12 GB: 4, on the same weights).

    Rounded up and capped at ``blocks``, the model's own count: a fractional
    block does not exist, and offloading more blocks than there are is the
    CPU-only case, not an error.
    """
    budget = free_vram_gb - DEFAULT_HEADROOM_GB
    deficit = spec.disk_gb - budget
    if deficit <= 0.0:
        return 0
    return min(blocks, math.ceil(deficit / _expert_gb_per_block(spec, blocks)))


def _resident_gb(spec: ModelSpec, blocks: int, total: int) -> float:
    """What the card ends up holding once ``blocks`` of experts are on the CPU.

    It starts from the spec's own working set rather than from the weights: the
    card holds buffers too, which is why deepseek-coder-v2:16b measures 9.4 GB
    of VRAM for 8.9 GB of weights, and a placement that quietly substituted the
    smaller number would under-state every MoE by whatever its buffers cost.
    Each offloaded block takes its experts off that, down to the floor.
    """
    if not spec.moe:
        return spec.vram_gb
    return max(
        _resident_floor_gb(spec),
        spec.vram_gb - blocks * _expert_gb_per_block(spec, total),
    )


def _derived_width(free_vram_gb: float, resident_gb: float) -> int:
    """Slots for the room the weights left, rather than the one slot nobody chose.

    A default of 1 is a claim — that this rig serves one request at a time —
    and it was never measured; #366 found 32 slots on a 12 GB card reaching
    254 tok/s against ~67 single-stream. What actually bounds the number is
    the VRAM the weights did not take, so that is what is divided here.

    Minus the headroom, because :func:`fit` already held it back and slots are
    exactly what it was held back from. A 9.9 GB model on a 12 GB card is a fit
    that reports "2.0 GB headroom held back" and a width of 8 that spends 2.0
    GB of it on KV — the module contradicting itself inside one unit, and the
    contradiction resolving on the rig as an OOM under load. The floor of one
    slot stands: a server with no slot serves nothing, and a machine that
    cannot afford the first one is a fit this module should not have approved.
    """
    spare = free_vram_gb - resident_gb - DEFAULT_HEADROOM_GB
    return max(1, min(MAX_WIDTH, int(spare / KV_GB_PER_SLOT)))


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
    return root / f"{spec.name.replace('/', '_')}.gguf"
