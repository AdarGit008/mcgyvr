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
own GGUF header, and none is declared. Free VRAM decides a fit today; total
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

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcgyvr.config import Config
from mcgyvr.propose import DEFAULT_HEADROOM_GB
from mcgyvr.scan import Gpu, Scan, default_weights_dir
from mcgyvr.serving import vramfit

# The engine a unit gets when nothing says otherwise. A source's ``api`` is a
# wire protocol (:class:`mcgyvr.pool.Protocol`) and cannot answer this: vLLM
# and llama-server both speak ``openai`` and take entirely different argv.
DEFAULT_ENGINE = "llama.cpp"

# Context PER SLOT. llama-server's ``-c`` is the total across slots (measured
# 2026-09-05: ``-c 8192`` allocates the same cache at ``-np 8``, ``-np 4`` and
# ``-np 1``), so the argv states this times the slot count and the cache law
# is fed the same product. One number, two readers, no drift.
DEFAULT_CONTEXT = 4096

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

# What system memory holds beyond the offloaded experts themselves: context,
# compute buffers, and the copy paths that do not live on the card. Measured
# across the sweep's six ``--n-cpu-moe`` cells on srv2
# (``records/measurements/serving-sweep-2026-08-25/``), where
# ``RSS - offloaded expert bytes`` sat at 1.52-1.53 GiB at every setting from
# 4 blocks to 20 — flat, which is what makes it an intercept rather than a
# rate. It applies only where experts actually spill: a model held entirely
# on the card is not paying it, and a dense model has no spill to pay it for.
RUNTIME_RESIDENT_GB = 1.53

# The widest configuration anyone has measured on these rigs (#366, 32 slots on
# a 12 GB card). Past it this arithmetic would be extrapolating.
MAX_WIDTH = 32

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
    """

    name: str
    vram_gb: float
    ram_gb: float
    disk_gb: float
    moe: bool = False
    geometry: Mapping[str, Any] | None = field(default=None, compare=False)

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


def fit(scan: Scan, spec: ModelSpec, *, width: int | None = None) -> Fit:
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
        placed = _placement(spec, free_bytes, width)
    except UnitError as exc:
        return Fit(fits=False, headroom_gb=_allowance_gb(spec), why=str(exc))
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
            f"{placed.width} slot(s) at {DEFAULT_CONTEXT} context each, "
            f"{placed.headroom_gb:.2f} GB of it scratch allowance"
        )
    spilled = (
        f", {placed.ram_gb:.1f} GB of experts in RAM{_offload_note(spec, placed)}"
        if spec.moe and placed.ram_gb
        else ""
    )
    return Fit(
        fits=True,
        headroom_gb=placed.headroom_gb,
        why=(
            f"{spec.name}: {placed.vram_gb:.1f} GB on the card of "
            f"{free_vram:.1f} GB free, {held}{spilled}"
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
    sized = fit(scan, spec, width=width)
    if not sized.fits:
        raise UnitError(f"{scan.machine.host}: {sized.why}")

    gpu = _roomiest_gpu(scan)
    # The same derivation :func:`fit` just approved, not a second one that
    # agrees today: an argv whose offload differs from the one the fit checked
    # is a unit that was never sized for this machine.
    placed = _placement(spec, gpu.vram.free_mib << 20, width)
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
        "-c": str(DEFAULT_CONTEXT * chosen.value),
        "-ub": str(DEFAULT_UBATCH),
        "-b": str(DEFAULT_UBATCH),
        "-fa": "on",
        "--parallel": str(chosen.value),
        "-t": str(_threads(scan)),
    }
    # A card roomy enough for every expert derives zero blocks, and
    # ``--n-cpu-moe 0`` is a no-op printed into a file a person reads: it says
    # this rig offloads experts when it does not, and invites tuning a number
    # that was never in play.
    if placed.n_cpu_moe > 0:
        args["--n-cpu-moe"] = str(placed.n_cpu_moe)

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
    ctx_per_slot: int = DEFAULT_CONTEXT,
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
            kv = vramfit.kv_bytes(
                geometry, ctx_per_slot * slots, n_seq_max=slots, n_ubatch=n_ubatch
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
            + kv["total"]
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
        ram_gb=max(spec.ram_gb, _host_gb(geometry, n_cpu_moe)),
        headroom_gb=vramfit.SCRATCH_AND_CONTEXT_MIB / 1024,
    )


def _host_gb(geometry: dict[str, Any], n_cpu_moe: int) -> float:
    """What system memory holds at this offload: the spilled experts, plus the
    runtime that spilling carries — and nothing when nothing spills."""
    offloaded = int(geometry["bytes_experts"]) - vramfit.experts_on_card(
        geometry, n_cpu_moe
    )
    if offloaded <= 0:
        return 0.0
    return offloaded / _BYTES_PER_GIB + RUNTIME_RESIDENT_GB


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
