"""What each card holds when one model is split across several, and what it costs.

A model too large for one card is not a model the fleet cannot serve: it can be
split across the cards of one machine, or across machines. There are two ways
to split it, and both engines offer both.

``pipeline`` (llama.cpp's ``--split-mode layer``, vLLM's
``--pipeline-parallel-size``)
    Each card holds a contiguous run of blocks, whole: their weights, their
    cache and their state. A token visits the cards in turn, and what crosses
    between two of them is one hidden state per token.

``tensor`` (llama.cpp's ``--split-mode row``, vLLM's
``--tensor-parallel-size``)
    Every card holds a slice of every block's matrices. A token is computed on
    all of them at once, and they meet twice in every block to add their
    partial results up (an all-reduce).

vLLM can do both at once: ``pipeline`` stages of ``tensor`` cards each.

**Every byte here is read off the tensor table, never off a bits-per-weight
figure**: a bits-per-weight figure is a guess. A shard is charged the blocks
it actually holds, summed block by block from the scan; the cache of the layers
it holds, by :func:`mcgyvr.serving.vramfit.kv_bytes`; the recurrent state of
those layers, by :func:`mcgyvr.serving.vramfit.rs_bytes`; and one allowance for
its compute scratch and context, because every card runs its own. A split never
moves part of a block off a card into host memory: a sharded unit keeps every
block it was given on its cards, so no ``--n-cpu-moe`` is derived here.

**What crosses between cards is an estimate, and says so.** The cost of a token
crossing a link is priced from the link's bandwidth and latency
(:mod:`mcgyvr.serving.interconnect`): a shipped estimate by link class until
the user's own reading or setting replaces it. It decides between splits that
fit -- never whether one fits, which is the card's memory alone.

Two terms are this module's choices and are stated where they are used: blocks
are given to cards so that the fullest card is as empty as it can be, and among
the splits that fit, the one that adds the least time crossing links per token
is chosen. What a tensor split buys in compute is not priced here, because no
card's memory bandwidth is read; a unit that wants it states its split.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mcgyvr import derived
from mcgyvr.fleet.links import NETWORK, PCIE, link_class
from mcgyvr.serving import vramfit
from mcgyvr.serving.interconnect import Link
from mcgyvr.serving.interconnect import link as shipped_link

LLAMACPP_ENGINE = "llama.cpp"
VLLM_ENGINE = "vllm"
ENGINES = (LLAMACPP_ENGINE, VLLM_ENGINE)

#: llama.cpp's two ways of splitting across several cards.
SPLIT_LAYER = "layer"
SPLIT_ROW = "row"
SPLITS = (SPLIT_LAYER, SPLIT_ROW)

#: What one element of a hidden state weighs as it crosses from card to card.
#: llama.cpp computes its graph's activations in 32-bit floats and copies them
#: between backends as they are; vLLM serves in a 16-bit dtype.
ACTIVATION_BYTES = {LLAMACPP_ENGINE: 4, VLLM_ENGINE: 2}

#: The all-reduces one block costs per token under a tensor split: one after
#: the attention, one after the feed-forward. The layout every tensor-parallel
#: transformer implementation uses, both engines' included.
ALL_REDUCES_PER_BLOCK = 2

#: Bytes per cache element under each ``--kv-cache-dtype`` vLLM takes that
#: names a width. ``auto`` follows the model's dtype and is refused: a cache is
#: sized at the dtype it launches with, spelled.
VLLM_CACHE_ELEM_BYTES = {
    "float16": 2.0,
    "fp16": 2.0,
    "bfloat16": 2.0,
    "bf16": 2.0,
    "fp8": 1.0,
    "fp8_e4m3": 1.0,
    "fp8_e5m2": 1.0,
}

#: What a tensor table must carry for a shard to be sized from it. A scan from
#: before these keys existed is refused with the command that re-reads it.
TABLE_KEYS = (
    "n_layer",
    "n_embd",
    "bytes_by_block",
    "bytes_matrix_by_block",
    "bytes_input",
    "bytes_output",
    "bytes_output_matrix",
    "kv_layers",
)

_GIB = 1 << 30
_MIB = 1 << 20
_US = 1e-6


class ShardingError(Exception):
    """A split cannot be sized or does not fit, and the message says which."""


@dataclass(frozen=True)
class Target:
    """One card a shard may land on: the machine, the card, and what it has free.

    ``host`` is the machine as a scan and an address name it; ``gpu`` the card's
    index there; ``free_bytes`` what the scan read free on it. ``bind`` is the
    IPv4 address a worker process on that machine listens on, where one is
    needed and the host is not one already.
    """

    host: str
    gpu: int
    free_bytes: int
    bind: str | None = None


@dataclass(frozen=True)
class Grid:
    """How many cards hold a slice of each block, and how many runs of blocks.

    ``tensor`` cards share every block of a stage; ``pipeline`` stages each hold
    a run of blocks. ``split`` is llama.cpp's ``--split-mode`` and ``None`` for
    vLLM, which takes the two numbers instead.
    """

    tensor: int
    pipeline: int
    split: str | None = None

    @property
    def cards(self) -> int:
        return self.tensor * self.pipeline


@dataclass(frozen=True)
class Shard:
    """What one card holds, and whether it fits there.

    ``stage`` and ``rank`` place it in the grid; ``blocks`` are the blocks it
    runs (a slice of each under a tensor split). The four byte figures are the
    claim; ``required_bytes`` is their sum and is held to the card's free
    memory.
    """

    target: Target
    stage: int
    rank: int
    blocks: tuple[int, ...]
    weights_bytes: int
    kv_bytes: int
    state_bytes: int
    allowance_bytes: int

    @property
    def required_bytes(self) -> int:
        held = self.weights_bytes + self.kv_bytes + self.state_bytes
        return held + self.allowance_bytes

    @property
    def fits(self) -> bool:
        return self.required_bytes <= self.target.free_bytes

    @property
    def fullness(self) -> float:
        """What this shard asks of its card, as a share of the card's free memory."""
        if self.target.free_bytes <= 0:
            return math.inf
        return self.required_bytes / self.target.free_bytes

    def says(self) -> str:
        return (
            f"{self.target.host} card {self.target.gpu}: "
            f"{self.required_bytes / _GIB:.2f} GiB of "
            f"{self.target.free_bytes / _GIB:.2f} GiB free (weights "
            f"{self.weights_bytes / _GIB:.2f}, cache {self.kv_bytes / _GIB:.2f}, "
            f"state {self.state_bytes / _GIB:.2f}, allowance "
            f"{self.allowance_bytes / _GIB:.2f}; blocks "
            f"{_span(self.blocks)})"
        )


@dataclass(frozen=True)
class Plan:
    """One split of one model over named cards: what each holds and what it costs.

    ``shards`` are in the order the engine numbers its devices: llama.cpp puts
    the cards it reaches over RPC first and its own after them, and vLLM
    numbers ranks machine by machine. ``layer_counts`` is the split as the
    engine is told it: per card for llama.cpp (``--tensor-split``, the last
    card's count including the output layer), per stage for vLLM
    (``VLLM_PP_LAYER_PARTITION``). ``comm_s_per_token`` is the estimated time
    one token spends crossing links, and ``links`` the links it was priced
    over, each saying where its figures came from.
    """

    engine: str
    grid: Grid
    shards: tuple[Shard, ...]
    layer_counts: tuple[int, ...]
    comm_s_per_token: float
    links: tuple[Link, ...]
    slots: int
    ctx_per_slot: int
    #: The machine the serving process runs on: the one of the first card the
    #: unit names, which is where its address points.
    head: str

    @property
    def fits(self) -> bool:
        return all(shard.fits for shard in self.shards)

    @property
    def fullest(self) -> Shard:
        return max(self.shards, key=lambda shard: shard.fullness)

    def says(self) -> str:
        """The split, card by card, and the crossing cost with its sources."""
        shape = (
            f"--split-mode {self.grid.split} over {self.grid.cards} cards"
            if self.engine == LLAMACPP_ENGINE
            else f"tensor {self.grid.tensor} x pipeline {self.grid.pipeline}"
        )
        cards = "; ".join(shard.says() for shard in self.shards)
        crossing = (
            f"about {self.comm_s_per_token * 1e3:.2f} ms per token crossing "
            f"links, estimated from: " + "; ".join(link.says() for link in self.links)
            if self.links
            else "no link crossed"
        )
        width = f"{self.slots} slot(s) of {self.ctx_per_slot}"
        return f"{shape} at {width}: {cards}. {crossing}"


Links = Callable[[str], Link]


def check_table(table: Mapping[str, Any], *, name: str) -> None:
    """Refuse, by name, a tensor table a shard cannot be sized from."""
    missing = [key for key in TABLE_KEYS if key not in table]
    if missing:
        raise ShardingError(
            f"{name}: its scan has no {', '.join(missing)}, so what each card "
            f"would hold cannot be summed from the tensor table. Re-scan it: "
            f"python -m mcgyvr.serving.ggufscan <gguf> (llama.cpp) or python -m "
            f"mcgyvr.serving.safetensorscan <model dir> (vLLM)"
        )


def plan(
    table: Mapping[str, Any],
    targets: Sequence[Target],
    grid: Grid,
    *,
    engine: str,
    slots: int,
    ctx_per_slot: int,
    cache_type_k: str,
    cache_type_v: str,
    n_ubatch: int,
    name: str,
    links: Links | None = None,
    allowance_bytes: int | None = None,
) -> Plan:
    """One split of ``table`` over ``targets`` in ``grid``, sized shard by shard.

    ``targets`` are in the order the unit declared them, the first being a
    card of the machine the serving process runs on. The plan reorders them
    into the engine's device order and says so in :attr:`Plan.shards`.

    Never decides whether to split: a plan is returned whether or not it fits,
    and :attr:`Plan.fits` says. What cannot be sized at all -- a table without
    the keys, a cache dtype nobody spelled, a head count the split does not
    divide, a grid that does not match the cards -- is refused.
    """
    check_table(table, name=name)
    if engine not in ENGINES:
        raise ShardingError(f"{name}: no split is known for engine {engine!r}")
    if slots < 1 or ctx_per_slot < 1:
        raise ShardingError(
            f"{name}: a split is sized at {slots} slot(s) of {ctx_per_slot} "
            f"tokens, and both are counts of something a process holds"
        )
    if grid.tensor < 1 or grid.pipeline < 1:
        raise ShardingError(f"{name}: a grid of {grid.tensor} x {grid.pipeline}")
    if grid.cards != len(targets):
        raise ShardingError(
            f"{name}: the split asks for {grid.tensor} x {grid.pipeline} = "
            f"{grid.cards} cards and the unit names {len(targets)}"
        )
    _no_card_twice(targets, name=name)
    resolve = links if links is not None else shipped_link
    allowance = (
        allowance_bytes
        if allowance_bytes is not None
        else _allowance_bytes(table, engine=engine, n_ubatch=n_ubatch, name=name)
    )
    sizing = _Sizing(
        table=table,
        engine=engine,
        slots=slots,
        ctx_per_slot=ctx_per_slot,
        cache_type_k=cache_type_k,
        cache_type_v=cache_type_v,
        n_ubatch=n_ubatch,
        name=name,
        allowance=allowance,
    )
    if engine == LLAMACPP_ENGINE:
        return _llama_plan(sizing, targets, grid, resolve)
    return _vllm_plan(sizing, targets, grid, resolve)


def choose(
    table: Mapping[str, Any],
    targets: Sequence[Target],
    *,
    engine: str,
    slots: int,
    ctx_per_slot: int,
    cache_type_k: str,
    cache_type_v: str,
    n_ubatch: int,
    name: str,
    split: str | None = None,
    tensor: int | None = None,
    pipeline: int | None = None,
    links: Links | None = None,
    allowance_bytes: int | None = None,
) -> Plan:
    """The split of ``table`` over every one of ``targets`` that fits and crosses least.

    What the unit stated is honoured and only the rest is chosen: a llama.cpp
    unit's ``split``, a vLLM unit's ``tensor`` and ``pipeline`` (one of the two
    is enough; the other is the card count over it). Every card the unit names
    is used: the unit named them.

    Among the splits that fit, the one whose tokens spend the least estimated
    time crossing links wins; a tie goes to llama.cpp's own default, the layer
    split, and for vLLM to the wider tensor split. Refused, naming every
    candidate's fullest card, when none fits.
    """
    grids = _grids(
        table,
        targets,
        engine=engine,
        split=split,
        tensor=tensor,
        pipeline=pipeline,
        name=name,
    )
    candidates: list[Plan] = []
    reasons: list[str] = []
    for grid in grids:
        try:
            made = plan(
                table,
                targets,
                grid,
                engine=engine,
                slots=slots,
                ctx_per_slot=ctx_per_slot,
                cache_type_k=cache_type_k,
                cache_type_v=cache_type_v,
                n_ubatch=n_ubatch,
                name=name,
                links=links,
                allowance_bytes=allowance_bytes,
            )
        except ShardingError as exc:
            if len(grids) == 1:
                raise
            reasons.append(f"{_grid_words(grid, engine)}: {exc}")
            continue
        if made.fits:
            candidates.append(made)
        else:
            fullest = made.fullest
            reasons.append(
                f"{_grid_words(grid, engine)}: {fullest.says()} does not fit"
            )
    if not candidates:
        raise ShardingError(
            f"{name}: no split over the {len(targets)} card(s) it names fits. "
            + " | ".join(reasons)
        )
    return min(candidates, key=_preference)


def _preference(made: Plan) -> tuple[float, int, int]:
    layer_first = 0 if made.grid.split in (None, SPLIT_LAYER) else 1
    return (made.comm_s_per_token, layer_first, -made.grid.tensor)


def _grid_words(grid: Grid, engine: str) -> str:
    if engine == LLAMACPP_ENGINE:
        return f"--split-mode {grid.split}"
    return f"tensor {grid.tensor} x pipeline {grid.pipeline}"


def _grids(
    table: Mapping[str, Any],
    targets: Sequence[Target],
    *,
    engine: str,
    split: str | None,
    tensor: int | None,
    pipeline: int | None,
    name: str,
) -> list[Grid]:
    """Every grid the engine can run over these cards, narrowed by what was stated."""
    cards = len(targets)
    if cards < 1:
        raise ShardingError(f"{name}: a split names no card")
    if engine == LLAMACPP_ENGINE:
        if tensor is not None or pipeline is not None:
            raise ShardingError(
                f"{name}: tensor_parallel and pipeline_parallel are vLLM's; "
                f"llama.cpp is told `split: layer` or `split: row`"
            )
        if split is not None and split not in SPLITS:
            raise ShardingError(
                f"{name}: split {split!r} is not one llama.cpp offers "
                f"({', '.join(SPLITS)})"
            )
        wanted = (split,) if split is not None else SPLITS
        grids = []
        for mode in wanted:
            if mode == SPLIT_ROW:
                if split is None and cards == 1:
                    continue
                grids.append(Grid(tensor=cards, pipeline=1, split=SPLIT_ROW))
            else:
                grids.append(Grid(tensor=1, pipeline=cards, split=SPLIT_LAYER))
        if split is None and _spans_machines(targets):
            # A row split needs every card's split buffer in one process, so
            # it never crosses to a card reached over RPC (see _llama_plan).
            grids = [grid for grid in grids if grid.split != SPLIT_ROW]
        return grids
    if split is not None:
        raise ShardingError(
            f"{name}: `split` is llama.cpp's; vLLM is told tensor_parallel and "
            f"pipeline_parallel"
        )
    for stated, what in ((tensor, "tensor_parallel"), (pipeline, "pipeline_parallel")):
        if stated is not None and (stated < 1 or cards % stated):
            raise ShardingError(
                f"{name}: {what} {stated} does not divide the {cards} card(s) "
                f"the unit names"
            )
    if tensor is not None and pipeline is not None:
        return [Grid(tensor=tensor, pipeline=pipeline)]
    if tensor is not None:
        return [Grid(tensor=tensor, pipeline=cards // tensor)]
    if pipeline is not None:
        return [Grid(tensor=cards // pipeline, pipeline=pipeline)]
    return [
        Grid(tensor=t, pipeline=cards // t)
        for t in range(cards, 0, -1)
        if cards % t == 0 and _heads_divide(table, t)
    ]


def _heads_divide(table: Mapping[str, Any], tensor: int) -> bool:
    try:
        _check_heads(table, tensor, name="")
    except ShardingError:
        return False
    return True


def _spans_machines(targets: Sequence[Target]) -> bool:
    return len({target.host.lower() for target in targets}) > 1


def _no_card_twice(targets: Sequence[Target], *, name: str) -> None:
    seen: set[tuple[str, int]] = set()
    for target in targets:
        card = (target.host.lower(), target.gpu)
        if card in seen:
            raise ShardingError(
                f"{name}: names card {target.gpu} of {target.host} twice, and a "
                f"card holds one shard"
            )
        seen.add(card)


def _allowance_bytes(
    table: Mapping[str, Any], *, engine: str, n_ubatch: int, name: str
) -> int:
    """The room each card needs past what it holds: scratch, context, buffers.

    llama.cpp's is :func:`mcgyvr.serving.vramfit.allowance_mib`, the one
    allowance a single-card fit already charges, once per card because every
    card runs its own compute buffer and context. vLLM's is the shipped
    estimate per rank (:func:`mcgyvr.derived.shard_allowance_gib`), which the
    user's own value replaces.
    """
    if engine == LLAMACPP_ENGINE:
        return int(vramfit.allowance_mib(dict(table), n_ubatch=n_ubatch) * _MIB)
    try:
        return int(derived.shard_allowance_gib(engine, sizing=name) * _GIB)
    except derived.DerivedNumbersError as exc:
        raise ShardingError(str(exc)) from exc


@dataclass(frozen=True)
class _Sizing:
    """Everything a shard's bytes depend on besides which blocks it holds."""

    table: Mapping[str, Any]
    engine: str
    slots: int
    ctx_per_slot: int
    cache_type_k: str
    cache_type_v: str
    n_ubatch: int
    name: str
    allowance: int

    @property
    def n_layer(self) -> int:
        return int(self.table["n_layer"])

    def block(self, b: int) -> int:
        return int(self.table["bytes_by_block"].get(str(b), 0))

    def matrix(self, b: int) -> int:
        return int(self.table["bytes_matrix_by_block"].get(str(b), 0))

    def rows(self, blocks: Sequence[int]) -> list[dict[str, Any]]:
        held = set(blocks)
        return [dict(row) for row in self.table["kv_layers"] if row["layer"] in held]

    def kv(self, blocks: Sequence[int], *, tensor: int = 1) -> int:
        """The cache of the layers in ``blocks``, as one card of ``tensor`` holds it."""
        rows = self.rows(blocks)
        if not rows:
            return 0
        if tensor > 1:
            _check_heads(self.table, tensor, name=self.name)
            rows = [_slice_heads(row, tensor) for row in rows]
        if self.engine == VLLM_ENGINE:
            return _vllm_kv(self, rows)
        try:
            return int(
                vramfit.kv_bytes(
                    dict(self.table),
                    self.ctx_per_slot * self.slots,
                    n_seq_max=self.slots,
                    n_ubatch=self.n_ubatch,
                    cache_type_k=self.cache_type_k,
                    cache_type_v=self.cache_type_v,
                    layers=rows,
                )["total"]
            )
        except (ValueError, KeyError) as exc:
            raise ShardingError(
                f"{self.name}: the cache of blocks {_span(blocks)} cannot be "
                f"sized: {exc}"
            ) from exc

    def state(self, blocks: Sequence[int]) -> int:
        """The recurrent state of the recurrent blocks among ``blocks``."""
        recurrent = set(self.table.get("recurrent_blocks") or ())
        held = sum(1 for b in blocks if b in recurrent)
        if not held:
            return 0
        try:
            return int(
                vramfit.rs_bytes(
                    dict(self.table),
                    n_seq_max=self.slots,
                    recurrent_layers_on_device=held,
                )["total"]
            )
        except ValueError as exc:
            raise ShardingError(f"{self.name}: {exc}") from exc


def _vllm_kv(sizing: _Sizing, rows: Sequence[Mapping[str, Any]]) -> int:
    """vLLM's cache requirement for these layers: window x width x bytes per token.

    Sized at every layer's full window, a sliding one included: vLLM's pool is
    a declaration the engine fills per token, and the requirement it is held
    to is the worst case: every slot at its whole window. A layer whose
    sliding is unknown is refused, as :func:`vramfit.kv_bytes` refuses it.
    """
    width = VLLM_CACHE_ELEM_BYTES.get(sizing.cache_type_k)
    if width is None:
        raise ShardingError(
            f"{sizing.name}: --kv-cache-dtype {sizing.cache_type_k!r} names no "
            f"width this sizing knows ({', '.join(VLLM_CACHE_ELEM_BYTES)}); "
            f"spell the dtype the unit launches with"
        )
    unknown = [row["layer"] for row in rows if row.get("is_swa", False) is None]
    if unknown:
        raise ShardingError(
            f"{sizing.name}: which of layers {unknown[0]}...{unknown[-1]} slide "
            f"is not stated by the checkpoint, so their cache is not sized"
        )
    per_token = sum(float(row["k_elems"]) + float(row["v_elems"]) for row in rows)
    return math.ceil(per_token * width * sizing.ctx_per_slot * sizing.slots)


def _check_heads(table: Mapping[str, Any], tensor: int, *, name: str) -> None:
    """Refuse a ``tensor``-wide split the model's heads cannot be divided over.

    Heads are divided whole: ``h / tensor`` each when ``tensor`` divides them,
    and one each -- a head held twice -- when the heads divide ``tensor``
    instead, which is what vLLM does with fewer KV heads than cards. Any other
    pair cannot be split. The attention heads must divide too, where the scan
    states them.
    """
    if tensor == 1:
        return
    rows = list(table["kv_layers"])
    if any("heads" not in row for row in rows):
        raise ShardingError(
            f"{name}: its scan states no head count per cached layer, and a "
            f"tensor split divides the cache by head; re-scan it"
        )
    n_head = table.get("n_head")
    if isinstance(n_head, int) and not isinstance(n_head, bool) and n_head % tensor:
        raise ShardingError(
            f"{name}: {n_head} attention heads do not divide over {tensor} cards"
        )
    for h in sorted({int(row["heads"]) for row in rows}):
        if h < 1 or (h % tensor and tensor % h):
            raise ShardingError(
                f"{name}: {h} KV heads cannot be split over {tensor} cards"
            )


def _slice_heads(row: Mapping[str, Any], tensor: int) -> dict[str, Any]:
    """One cached layer as one card of a ``tensor``-wide split holds it."""
    heads = int(row["heads"])
    held = heads // tensor if heads % tensor == 0 else 1
    out = dict(row)
    out["k_elems"] = int(row["k_elems"]) // heads * held
    out["v_elems"] = int(row["v_elems"]) // heads * held
    out["heads"] = held
    return out


def _span(blocks: Sequence[int]) -> str:
    if not blocks:
        return "none"
    if list(blocks) == list(range(blocks[0], blocks[-1] + 1)):
        return f"{blocks[0]}-{blocks[-1]}"
    return ",".join(str(b) for b in blocks)


def _partition(
    count: int,
    stages: int,
    fullness: Callable[[int, int, int], float],
    *,
    name: str,
) -> tuple[int, ...]:
    """Contiguous runs of ``count`` items over ``stages``, the fullest least full.

    ``fullness(stage, lo, hi)`` is what stage ``stage`` would ask of its
    card(s) holding items ``lo`` to ``hi - 1``, as a share of free memory. Every
    stage holds at least one item. Exact (a minimax over contiguous splits by
    dynamic programming), so the answer does not depend on where a heuristic
    started; ties go to the earlier boundary, so it is deterministic.
    """
    if stages > count:
        raise ShardingError(
            f"{name}: {stages} cards cannot each hold a run of its {count} block(s)"
        )
    inf = math.inf
    best = [[inf] * (count + 1) for _ in range(stages + 1)]
    cut = [[0] * (count + 1) for _ in range(stages + 1)]
    best[0][0] = 0.0
    for s in range(1, stages + 1):
        for hi in range(s, count - (stages - s) + 1):
            for lo in range(s - 1, hi):
                if best[s - 1][lo] == inf:
                    continue
                worst = max(best[s - 1][lo], fullness(s - 1, lo, hi))
                if worst < best[s][hi]:
                    best[s][hi] = worst
                    cut[s][hi] = lo
    counts: list[int] = []
    hi = count
    for s in range(stages, 0, -1):
        lo = cut[s][hi]
        counts.append(hi - lo)
        hi = lo
    return tuple(reversed(counts))


def _llama_order(targets: Sequence[Target]) -> list[Target]:
    """llama.cpp's device order: the cards it reaches over RPC, then its own.

    Its device list puts RPC servers first "to minimize network transfers" and
    its own cards after them in the order the driver numbers them, which the
    launch pins to the bus order. The head is the machine of the first card
    the unit names.
    """
    head = targets[0].host.lower()
    remote = [target for target in targets if target.host.lower() != head]
    local = sorted(
        (target for target in targets if target.host.lower() == head),
        key=lambda target: target.gpu,
    )
    return [*remote, *local]


def _llama_plan(
    sizing: _Sizing, targets: Sequence[Target], grid: Grid, links: Links
) -> Plan:
    """llama.cpp over several cards: a layer split or a row split.

    The engine assigns layer ``il`` (and the output layer, as index
    ``n_layer``) to the first device whose cumulative ``--tensor-split`` share
    exceeds ``il / (n_layer + 1)``, so stating the split as whole layer counts
    that sum to ``n_layer + 1`` lands every block exactly where this plan puts
    it. The input embedding stays in host memory on every split and is charged
    to no card.

    Under ``row`` the same counts also set each card's share of every matrix,
    the output head's included; the norms, the cache and the state of a layer
    stay with the card its count gives it. A row split needs the backend's
    split buffers in one process, so a card reached over RPC refuses it.
    """
    ordered = _llama_order(targets)
    head = targets[0].host.lower()
    if grid.split == SPLIT_ROW and any(t.host.lower() != head for t in ordered):
        raise ShardingError(
            f"{sizing.name}: --split-mode row splits every matrix with the "
            f"backend's split buffers, which a card reached over RPC does not "
            f"have; use split: layer to span machines"
        )
    n = sizing.n_layer
    items = n + 1  # the blocks, then the output layer
    output = int(sizing.table["bytes_output"])
    output_matrix = int(sizing.table["bytes_output_matrix"])
    matrices = sum(sizing.matrix(b) for b in range(n)) + output_matrix
    devices = len(ordered)

    if grid.split == SPLIT_ROW:
        counts = _by_free_share(items, ordered, name=sizing.name)
    else:
        prefix_weights = _prefix([sizing.block(b) for b in range(n)] + [output])
        kv_each = [sizing.kv([b]) for b in range(n)] + [0]
        state_each = [sizing.state([b]) for b in range(n)] + [0]
        prefix_kv = _prefix(kv_each)
        prefix_state = _prefix(state_each)

        def fullness(stage: int, lo: int, hi: int) -> float:
            asked = (
                prefix_weights[hi]
                - prefix_weights[lo]
                + prefix_kv[hi]
                - prefix_kv[lo]
                + prefix_state[hi]
                - prefix_state[lo]
                + sizing.allowance
            )
            free = ordered[stage].free_bytes
            return asked / free if free > 0 else math.inf

        counts = _partition(items, devices, fullness, name=sizing.name)

    shards: list[Shard] = []
    start = 0
    total = sum(counts)
    for index, (target, held) in enumerate(zip(ordered, counts, strict=True)):
        blocks = tuple(b for b in range(start, start + held) if b < n)
        has_output = start + held > n
        if grid.split == SPLIT_ROW:
            share = held / total
            weights = (
                sum(sizing.block(b) - sizing.matrix(b) for b in blocks)
                + math.ceil(matrices * share)
                + ((output - output_matrix) if has_output else 0)
            )
        else:
            weights = sum(sizing.block(b) for b in blocks) + (
                output if has_output else 0
            )
        shards.append(
            Shard(
                target=target,
                stage=index if grid.split == SPLIT_LAYER else 0,
                rank=0 if grid.split == SPLIT_LAYER else index,
                blocks=blocks,
                weights_bytes=weights,
                kv_bytes=sizing.kv(blocks),
                state_bytes=sizing.state(blocks),
                allowance_bytes=sizing.allowance,
            )
        )
        start += held
    comm, used = _llama_comm(sizing, ordered, grid, links, head=targets[0].host)
    return Plan(
        engine=LLAMACPP_ENGINE,
        grid=grid,
        shards=tuple(shards),
        layer_counts=tuple(counts),
        comm_s_per_token=comm,
        links=used,
        slots=sizing.slots,
        ctx_per_slot=sizing.ctx_per_slot,
        head=targets[0].host,
    )


def _by_free_share(
    items: int, ordered: Sequence[Target], *, name: str
) -> tuple[int, ...]:
    """``items`` shared out in proportion to free memory, each card at least one.

    llama.cpp's own default split, by free memory, stated as whole counts by
    the largest remainder so the argv says it and the engine does not decide
    it again at load against memory that may have moved.
    """
    if len(ordered) > items:
        raise ShardingError(
            f"{name}: {len(ordered)} cards cannot share {items} layer(s)"
        )
    free = [max(target.free_bytes, 0) for target in ordered]
    whole = sum(free)
    if whole <= 0:
        return tuple([1] * (len(ordered) - 1) + [items - len(ordered) + 1])
    spare = items - len(ordered)
    raw = [spare * f / whole for f in free]
    counts = [1 + int(r) for r in raw]
    left = items - sum(counts)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - int(raw[i])), i))
    for i in order[:left]:
        counts[i] += 1
    return tuple(counts)


def _prefix(values: Sequence[int]) -> list[int]:
    out = [0]
    for value in values:
        out.append(out[-1] + value)
    return out


def _hop_s(link: Link, payload: int) -> float:
    """One message of ``payload`` bytes over ``link``: latency plus transfer."""
    return link.latency_us * _US + payload / (link.gib_s * _GIB)


def _all_reduce_s(link: Link, payload: int, cards: int) -> float:
    """A ring all-reduce of ``payload`` bytes over ``cards`` cards on ``link``.

    ``2 (n - 1)`` steps, each a latency and ``1 / n`` of the payload: the
    textbook cost of the ring both engines' collectives fall back to.
    """
    if cards < 2:
        return 0.0
    steps = 2 * (cards - 1)
    return steps * link.latency_us * _US + steps / cards * payload / (link.gib_s * _GIB)


class _LinkBook:
    """Each link class priced once, and the ones a plan used, in first-use order."""

    def __init__(self, links: Links) -> None:
        self._links = links
        self._seen: dict[str, Link] = {}

    def between(self, host_a: str, host_b: str) -> Link:
        cls = link_class(host_a, host_b)
        if cls not in self._seen:
            self._seen[cls] = self._links(cls)
        return self._seen[cls]

    def of_class(self, cls: str) -> Link:
        if cls not in self._seen:
            self._seen[cls] = self._links(cls)
        return self._seen[cls]

    @property
    def used(self) -> tuple[Link, ...]:
        return tuple(self._seen.values())


def _llama_comm(
    sizing: _Sizing,
    ordered: Sequence[Target],
    grid: Grid,
    links: Links,
    *,
    head: str,
) -> tuple[float, tuple[Link, ...]]:
    """What one token spends crossing links under llama.cpp's split.

    Layer split: the hidden state passes from each card to the next. Every
    byte to or from a card reached over RPC goes through the head, so a step
    between two such cards on other machines is two network crossings, and
    the first card, when remote, is reached from the head where the input
    embedding is computed. Row split: every block's matrix products meet
    across the cards twice per token, priced as all-reduces on the bus.
    """
    book = _LinkBook(links)
    payload = int(sizing.table["n_embd"]) * ACTIVATION_BYTES[LLAMACPP_ENGINE]
    if len(ordered) < 2:
        return 0.0, ()
    if grid.split == SPLIT_ROW:
        link = book.of_class(PCIE)
        total = (
            sizing.n_layer
            * ALL_REDUCES_PER_BLOCK
            * _all_reduce_s(link, payload, len(ordered))
        )
        return total, book.used

    def remote(target: Target) -> bool:
        return target.host.lower() != head.lower()

    total = 0.0
    if remote(ordered[0]):
        total += _hop_s(book.of_class(NETWORK), payload)
    for here, there in itertools.pairwise(ordered):
        # One rpc-server per card, so even two cards of one other machine
        # meet through the head: each remote end is a network crossing.
        crossings = int(remote(here)) + int(remote(there))
        if crossings:
            total += crossings * _hop_s(book.of_class(NETWORK), payload)
        else:
            total += _hop_s(book.of_class(PCIE), payload)
    return total, book.used


def _vllm_order(targets: Sequence[Target], *, name: str) -> list[Target]:
    """vLLM's rank order: machine by machine, head first, cards in bus order.

    Its multi-node launch numbers ranks node by node, ``node_rank x
    local_size + local_rank``, and gives every node the same number of
    cards; a stage is ``tensor`` consecutive ranks. A unit whose machines hold
    different numbers of its cards is refused.
    """
    hosts: list[str] = []
    for target in targets:
        if target.host.lower() not in (h.lower() for h in hosts):
            hosts.append(target.host)
    by_host = {
        host: sorted(
            (t for t in targets if t.host.lower() == host.lower()),
            key=lambda t: t.gpu,
        )
        for host in hosts
    }
    sizes = {len(cards) for cards in by_host.values()}
    if len(sizes) > 1:
        spelled = ", ".join(f"{host} {len(by_host[host])}" for host in hosts)
        raise ShardingError(
            f"{name}: vLLM's multi-node launch runs the same number of cards on "
            f"every machine, and the unit names {spelled}"
        )
    return [target for host in hosts for target in by_host[host]]


def _vllm_plan(
    sizing: _Sizing, targets: Sequence[Target], grid: Grid, links: Links
) -> Plan:
    """vLLM over a ``tensor`` x ``pipeline`` grid of cards.

    Stage ``s`` holds a contiguous run of blocks, stated to the engine as
    ``VLLM_PP_LAYER_PARTITION`` so its own default does not move the boundary.
    Each of a stage's ``tensor`` cards holds ``1 / tensor`` of every matrix of
    its blocks and the whole of every norm, ``1 / tensor`` of the KV heads,
    and the first stage holds its share of the input embedding, the last its
    share of the output head plus the final norm.
    """
    ordered = _vllm_order(targets, name=sizing.name)
    t, p = grid.tensor, grid.pipeline
    _check_heads(sizing.table, t, name=sizing.name)
    n = sizing.n_layer
    output = int(sizing.table["bytes_output"])
    output_matrix = int(sizing.table["bytes_output_matrix"])
    inp = int(sizing.table["bytes_input"])

    def block_on_rank(b: int) -> int:
        return math.ceil(sizing.matrix(b) / t) + sizing.block(b) - sizing.matrix(b)

    def ends(stage: int) -> int:
        held = 0
        if stage == 0:
            held += math.ceil(inp / t)
        if stage == p - 1:
            held += math.ceil(output_matrix / t) + output - output_matrix
        return held

    def rank_weights(stage: int, blocks: Sequence[int]) -> int:
        return sum(block_on_rank(b) for b in blocks) + ends(stage)

    def stage_targets(stage: int) -> Sequence[Target]:
        return ordered[stage * t : (stage + 1) * t]

    # Per block, the three terms are additive, so the partition is searched
    # over prefix sums; the shards are then sized exactly from their blocks.
    prefix = _prefix(
        [
            block_on_rank(b) + sizing.kv([b], tensor=t) + sizing.state([b])
            for b in range(n)
        ]
    )

    def fullness(stage: int, lo: int, hi: int) -> float:
        asked = prefix[hi] - prefix[lo] + ends(stage) + sizing.allowance
        free = min(target.free_bytes for target in stage_targets(stage))
        return asked / free if free > 0 else math.inf

    counts = _partition(n, p, fullness, name=sizing.name) if p > 1 else (n,)
    shards: list[Shard] = []
    start = 0
    for stage, held in enumerate(counts):
        blocks = tuple(range(start, start + held))
        for rank, target in enumerate(stage_targets(stage)):
            shards.append(
                Shard(
                    target=target,
                    stage=stage,
                    rank=rank,
                    blocks=blocks,
                    weights_bytes=rank_weights(stage, blocks),
                    kv_bytes=sizing.kv(blocks, tensor=t),
                    state_bytes=sizing.state(blocks),
                    allowance_bytes=sizing.allowance,
                )
            )
        start += held
    comm, used = _vllm_comm(sizing, ordered, grid, counts, links)
    return Plan(
        engine=VLLM_ENGINE,
        grid=grid,
        shards=tuple(shards),
        layer_counts=tuple(counts),
        comm_s_per_token=comm,
        links=used,
        slots=sizing.slots,
        ctx_per_slot=sizing.ctx_per_slot,
        head=targets[0].host,
    )


def _vllm_comm(
    sizing: _Sizing,
    ordered: Sequence[Target],
    grid: Grid,
    counts: Sequence[int],
    links: Links,
) -> tuple[float, tuple[Link, ...]]:
    """What one token spends crossing links under vLLM's grid.

    Each stage's blocks all-reduce twice per token over the slowest link its
    cards share; each stage boundary passes one hidden state on.
    """
    book = _LinkBook(links)
    payload = int(sizing.table["n_embd"]) * ACTIVATION_BYTES[VLLM_ENGINE]
    t = grid.tensor
    total = 0.0
    for stage, held in enumerate(counts):
        cards = ordered[stage * t : (stage + 1) * t]
        if t > 1:
            hosts = {card.host.lower() for card in cards}
            link = book.of_class(NETWORK if len(hosts) > 1 else PCIE)
            total += held * ALL_REDUCES_PER_BLOCK * _all_reduce_s(link, payload, t)
        if stage + 1 < len(counts):
            nxt = ordered[(stage + 1) * t]
            total += _hop_s(book.between(cards[0].host, nxt.host), payload)
    return total, book.used
