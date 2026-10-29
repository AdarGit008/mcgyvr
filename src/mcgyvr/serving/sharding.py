"""Size a model across several GPUs.

A scan of the model (llama.cpp or safetensors) yields a tensor table of per-block
byte counts. From that table, the free memory each named card reports, and the
requested slots and context, this module builds shard plans for llama.cpp's
layer/tensor split and for vLLM's tensor x pipeline grids. Each plan sums the
weights, KV cache and recurrent state one card would hold, adds an allowance for
what the scan cannot see, and estimates the time per token spent on the links
the split crosses. `choose` enumerates the grids, plans each, and keeps the one
that fits best.
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

#: The two --split-mode values llama.cpp offers for a server; llama.cpp's "row"
#: mode is handled below as a refusal rather than a split.
SPLIT_LAYER = "layer"
SPLIT_TENSOR = "tensor"
SPLITS = (SPLIT_LAYER, SPLIT_TENSOR)
#: Split modes the planner rejects before planning, with the reason it reports.
REFUSED_SPLITS = {
    "row": (
        "llama.cpp's --split-mode row needs the backend's split buffers, which "
        "the CUDA backend no longer has, so the server throws at load"
    ),
}
#: Architectures whose llama.cpp graph cannot run a tensor split
#: (llm_arch_supports_sm_tensor is false for them), as spelled by the scan's
#: `arch` field. On one of these, split: tensor is refused and split: layer used.
LLAMA_TENSOR_REFUSED_ARCHS = frozenset(
    {
        "grok",
        "mpt",
        "plamo2",
        "minicpm3",
        "gemma3n",
        "mamba",
        "mamba2",
        "jamba",
        "falcon-h1",
        "olmo2",
        "olmoe",
        "deepseek2",
        "deepseek32",
        "hy_v4",
        "dots3note",
        "glm-dsa",
        "bitnet",
        "t5",
        "nemotron_h",
        "nemotron_h_moe",
        "granitehybrid",
        "minimax-01",
        "minimax-m2",
        "minimax-m3",
        "mistral4",
        "kimi-linear",
        "bailingmoe3",
        "kimi-k3",
        "glm5-next",
        "qwen3tts",
    }
)
#: The extra tensor-table keys a llama.cpp tensor split reads: the bytes each
#: block's weights lose when divided, the same for the output projection, and the
#: tensors the scan refused to place on llama.cpp's partial axis.
LLAMA_TENSOR_KEYS = (
    "bytes_tensor_split_by_block",
    "bytes_output_tensor_split",
    "tensor_split_refused",
)

#: Width in bytes of one activation element per engine, i.e. its compute dtype;
#: the payload a link carries per token is n_embd times this.
ACTIVATION_BYTES = {LLAMACPP_ENGINE: 4, VLLM_ENGINE: 2}

#: All-reduces a tensor-parallel block performs per token: one over the attention
#: output projection and one over the MLP down projection.
ALL_REDUCES_PER_BLOCK = 2

#: Bytes per KV cache element for each --kv-cache-dtype spelling that vLLM sizing
#: accepts; a dtype outside this table is refused rather than guessed at.
VLLM_CACHE_ELEM_BYTES = {
    "float16": 2.0,
    "bfloat16": 2.0,
    "fp8": 1.0,
    "fp8_e4m3": 1.0,
    "fp8_e5m2": 1.0,
}

#: The tensor-table keys every scan must carry for a split to be summed per card:
#: block counts, hidden width, weight bytes per block and for the matrices, the
#: embedding/output bytes, and the per-layer KV rows.
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
    """A split cannot be planned: the table, the cards or the request disagree."""


@dataclass(frozen=True)
class Target:
    """One card a unit names: the machine it sits on, its GPU index, the free
    bytes it reported, and the address the launch binds."""

    host: str
    gpu: int
    free_bytes: int
    bind: str | None = None
    #: The card's backend as its scan read it: a scratch reading taken under
    #: one backend is never given to a card of another (`vramfit.allowance_mib`).
    backend: str = vramfit.MEASURED_SCRATCH_BACKEND


@dataclass(frozen=True)
class Grid:
    """The shape of a split: `tensor` ranks per pipeline stage times `pipeline`
    stages, and for llama.cpp the --split-mode that shape is expressed as."""

    tensor: int
    pipeline: int
    split: str | None = None

    @property
    def cards(self) -> int:
        return self.tensor * self.pipeline


@dataclass(frozen=True)
class Shard:
    """What one card holds in a plan: its stage and rank, the blocks assigned to
    it, the bytes of weights, KV cache and recurrent state, and the allowance."""

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
        """Required bytes as a fraction of the card's free bytes, infinite when
        the card reports no free memory, so it can never be the fullest that
        fits."""
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
    """A planned split: the engine it is for, the grid, one shard per card, the
    block count each stage holds, the estimated cost per token of the links
    crossed, and the slots and context the plan was sized at."""

    engine: str
    grid: Grid
    shards: tuple[Shard, ...]
    layer_counts: tuple[int, ...]
    comm_s_per_token: float
    links: tuple[Link, ...]
    slots: int
    ctx_per_slot: int
    #: The machine the launch is driven from, taken from the first target; link
    #: crossings per token are counted against it.
    head: str

    @property
    def fits(self) -> bool:
        return all(shard.fits for shard in self.shards)

    @property
    def fullest(self) -> Shard:
        return max(self.shards, key=lambda shard: shard.fullness)

    def says(self) -> str:
        """One line naming the split shape, what each card holds, and the cost
        per token of crossing links, with the links it was estimated from."""
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
    """Require the table keys every split reads, and on a miss name the scan
    command that would produce a fresh table."""
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
    """Plan one named grid: check the table, the engine, the slot counts, the
    grid and that no card is named twice, supply the allowance when not given,
    then hand to the engine's own planner."""
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
        else _allowance_bytes(
            table,
            engine=engine,
            n_ubatch=n_ubatch,
            name=name,
            split=grid.split,
            backend=_one_backend(targets),
        )
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
    """Plan every grid the hints allow, keep the plans that fit, and return the
    preferred one; when none fits, report each grid's reason in the error."""
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


def _preference(made: Plan) -> tuple[int, int]:
    """Sort key for plans that fit: prefer a plan with no stage whose cards
    spread over more than one machine, then the widest tensor split."""
    hosts: dict[int, set[str]] = {}
    for shard in made.shards:
        hosts.setdefault(shard.stage, set()).add(shard.target.host.lower())
    crosses = any(len(stage) > 1 for stage in hosts.values())
    return (int(crosses), -made.grid.tensor)


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
    """The grids to consider, from the request's hints and the card count: the
    named one when a hint is given, else every divisor of the card count, and
    for llama.cpp the layer split plus the tensor split when it is allowed."""
    cards = len(targets)
    if cards < 1:
        raise ShardingError(f"{name}: a split names no card")
    if engine == LLAMACPP_ENGINE:
        if tensor is not None or pipeline is not None:
            raise ShardingError(
                f"{name}: tensor_parallel and pipeline_parallel are vLLM's; "
                f"llama.cpp is told `split: layer` or `split: tensor`"
            )
        if split in REFUSED_SPLITS:
            raise ShardingError(
                f"{name}: split {split!r} is refused: {REFUSED_SPLITS[split]}; "
                f"use split: layer, or split: tensor on one machine"
            )
        if split is not None and split not in SPLITS:
            raise ShardingError(
                f"{name}: split {split!r} is not one llama.cpp offers "
                f"({', '.join(SPLITS)})"
            )
        layer = Grid(tensor=1, pipeline=cards, split=SPLIT_LAYER)
        whole = Grid(tensor=cards, pipeline=1, split=SPLIT_TENSOR)
        if split == SPLIT_LAYER:
            return [layer]
        why_not = _llama_tensor_refusal(table, targets)
        if split == SPLIT_TENSOR:
            if why_not is not None:
                raise ShardingError(f"{name}: split 'tensor' is refused: {why_not}")
            return [whole]
        # No split stated: the layer split is always on offer, and the tensor
        # split joins it only when it is not refused for these cards.
        return [layer] if why_not is not None else [layer, whole]
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


def _llama_tensor_refusal(
    table: Mapping[str, Any], targets: Sequence[Target]
) -> str | None:
    """Why llama.cpp's tensor split is refused these cards, or None when it is
    allowed: too few cards, cards on more than one machine, an architecture
    without the split, a scan lacking the tensor-split keys, tensors the scan
    could not place on the partial axis, or heads that do not divide."""
    cards = len(targets)
    if cards < 2:
        return "a tensor split shares every block between two cards or more"
    if len({target.host.lower() for target in targets}) > 1:
        return (
            "its cards are on more than one machine; llama.cpp runs one split "
            "mode for the whole process, and a tensor split meets twice in "
            "every block, so across machines it is split: layer"
        )
    arch = str(table.get("arch") or "")
    if arch in LLAMA_TENSOR_REFUSED_ARCHS:
        return (
            f"llama.cpp does not implement it for architecture {arch!r} "
            "(llm_arch_supports_sm_tensor); use split: layer"
        )
    missing = [key for key in LLAMA_TENSOR_KEYS if key not in table]
    if missing:
        return (
            f"its scan has no {', '.join(missing)}; re-scan it: python -m "
            "mcgyvr.serving.ggufscan <gguf>"
        )
    refused = list(table["tensor_split_refused"])
    if refused:
        return (
            f"{', '.join(refused[:3])} must be F32 to be split on llama.cpp's "
            "partial axis, and is not"
        )
    try:
        _check_heads(table, cards, name="", replicate=False)
    except ShardingError as exc:
        return str(exc).removeprefix(": ")
    return None


def _heads_divide(table: Mapping[str, Any], tensor: int) -> bool:
    try:
        _check_heads(table, tensor, name="")
    except ShardingError:
        return False
    return True


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


def _one_backend(targets: Sequence[Target]) -> str:
    """The backend a split's scratch is priced under: the measured one when every
    card runs it, else the first card's that does not."""
    other = [
        t.backend for t in targets if t.backend != vramfit.MEASURED_SCRATCH_BACKEND
    ]
    return other[0] if other else vramfit.MEASURED_SCRATCH_BACKEND


def _allowance_bytes(
    table: Mapping[str, Any],
    *,
    engine: str,
    n_ubatch: int,
    name: str,
    split: str | None = None,
    backend: str = vramfit.MEASURED_SCRATCH_BACKEND,
) -> int:
    """Headroom to reserve on every card: vramfit's u-batch allowance for a
    llama.cpp layer split (a reading only for cards of the backend it was taken
    under), else the derived per-shard allowance."""
    if engine == LLAMACPP_ENGINE and split != SPLIT_TENSOR:
        return int(
            vramfit.allowance_mib(dict(table), n_ubatch=n_ubatch, backend=backend)
            * _MIB
        )
    try:
        return int(derived.shard_allowance_gib(engine, sizing=name) * _GIB)
    except derived.DerivedNumbersError as exc:
        raise ShardingError(str(exc)) from exc


@dataclass(frozen=True)
class _Sizing:
    """The tensor table together with the request it is sized at (engine, slots,
    context, cache dtypes), and the per-card allowance to add to every shard."""

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

    @property
    def tied(self) -> bool:
        """Whether the model ties input and output embeddings, so one copy of
        those weights serves both ends."""
        return self.table.get("tied_embeddings") is True

    def block(self, b: int) -> int:
        return int(self.table["bytes_by_block"].get(str(b), 0))

    def matrix(self, b: int) -> int:
        return int(self.table["bytes_matrix_by_block"].get(str(b), 0))

    def rows(self, blocks: Sequence[int]) -> list[dict[str, Any]]:
        held = set(blocks)
        return [dict(row) for row in self.table["kv_layers"] if row["layer"] in held]

    def kv(self, blocks: Sequence[int], *, tensor: int = 1) -> int:
        """KV cache bytes for `blocks` at this context and slot count, divided
        over `tensor` cards by slicing each layer's heads; vLLM is summed in
        closed form, llama.cpp through vramfit."""
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
        """Recurrent (state-space) buffers for the recurrent blocks among
        `blocks`, zero when none of them is recurrent."""
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
    """vLLM's cache, closed form: per-layer key and value elements times the
    dtype width, the context length and the slot count, rounded up."""
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


def _check_heads(
    table: Mapping[str, Any], tensor: int, *, name: str, replicate: bool = True
) -> None:
    """Require that a tensor split over `tensor` cards can divide the attention
    and KV heads the scan states: the scan must give a head count per cached
    layer, n_head must divide, and each layer's KV heads must divide or be
    fewer than the cards (in which case they are replicated unless `replicate`
    is off)."""
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
        if h < 1 or (h % tensor and (tensor % h or not replicate)):
            raise ShardingError(
                f"{name}: {h} KV heads cannot be split over {tensor} cards"
            )


def _slice_heads(row: Mapping[str, Any], tensor: int) -> dict[str, Any]:
    """One card's share of a layer's cache: its key and value elements divided
    by the whole head count and multiplied by the heads it holds, which is one
    per card when the heads are replicated."""
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
    """Split `count` consecutive items into `stages` non-empty runs, minimising
    the fullest run under `fullness(stage, lo, hi)`; returns the run lengths in
    order."""
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
    """Order llama.cpp's cards so the head machine's cards come last, by GPU
    index, and the other machines' cards come first; the order fixes which stage
    boundaries cross the network."""
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
    """Plan llama.cpp's layer split: give each card a contiguous run of the n
    layer blocks plus the trailing output item, partitioning so the fullest card
    is as empty as possible; a tensor split is delegated."""
    if grid.split == SPLIT_TENSOR:
        return _llama_tensor_plan(sizing, targets, grid, links)
    if grid.split != SPLIT_LAYER:
        raise ShardingError(
            f"{sizing.name}: llama.cpp is split by layer or tensor here, not "
            f"{grid.split!r}"
        )
    ordered = _llama_order(targets)
    n = sizing.n_layer
    items = n + 1  # layer blocks then the output item, so the last stage can hold it
    output = int(sizing.table["bytes_output"])
    if sizing.tied:
        output += int(sizing.table["bytes_input"])
    devices = len(ordered)

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
    for index, (target, held) in enumerate(zip(ordered, counts, strict=True)):
        blocks = tuple(b for b in range(start, start + held) if b < n)
        has_output = start + held > n
        weights = sum(sizing.block(b) for b in blocks) + (output if has_output else 0)
        shards.append(
            Shard(
                target=target,
                stage=index,
                rank=0,
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


def _llama_tensor_plan(
    sizing: _Sizing, targets: Sequence[Target], grid: Grid, links: Links
) -> Plan:
    """Plan llama.cpp's tensor split: every card holds every block, keeping the
    part of each weight that is not divided, plus one card's share of the cache;
    the bytes are therefore identical on all cards."""
    why_not = _llama_tensor_refusal(sizing.table, targets)
    if why_not is not None:
        raise ShardingError(f"{sizing.name}: split 'tensor' is refused: {why_not}")
    ordered = sorted(targets, key=lambda target: target.gpu)
    cards = len(ordered)
    if grid.tensor != cards or grid.pipeline != 1:
        raise ShardingError(
            f"{sizing.name}: a llama.cpp tensor split shares every block between "
            f"all {cards} cards, not {grid.tensor} x {grid.pipeline}"
        )
    n = sizing.n_layer
    split_by_block = sizing.table["bytes_tensor_split_by_block"]

    def divided(whole: int, split: int) -> int:
        return whole - split + math.ceil(split / cards)

    blocks = tuple(range(n))
    weights = sum(
        divided(sizing.block(b), int(split_by_block.get(str(b), 0))) for b in blocks
    )
    weights += divided(
        int(sizing.table["bytes_output"]),
        int(sizing.table["bytes_output_tensor_split"]),
    )
    if sizing.tied:
        weights += int(sizing.table["bytes_input"])
    kv = sizing.kv(blocks, tensor=cards)
    state = sizing.state(blocks)
    shards = tuple(
        Shard(
            target=target,
            stage=0,
            rank=rank,
            blocks=blocks,
            weights_bytes=weights,
            kv_bytes=kv,
            state_bytes=state,
            allowance_bytes=sizing.allowance,
        )
        for rank, target in enumerate(ordered)
    )
    comm, used = _llama_comm(sizing, ordered, grid, links, head=targets[0].host)
    return Plan(
        engine=LLAMACPP_ENGINE,
        grid=grid,
        shards=shards,
        layer_counts=tuple([1] * cards),
        comm_s_per_token=comm,
        links=used,
        slots=sizing.slots,
        ctx_per_slot=sizing.ctx_per_slot,
        head=targets[0].host,
    )


def _prefix(values: Sequence[int]) -> list[int]:
    out = [0]
    for value in values:
        out.append(out[-1] + value)
    return out


def _hop_s(link: Link, payload: int) -> float:
    """Time for one hop: the link's latency plus the payload at its bandwidth."""
    return link.latency_us * _US + payload / (link.gib_s * _GIB)


def _all_reduce_s(link: Link, payload: int, cards: int) -> float:
    """Time for one all-reduce over `cards` cards on `link`, as a ring of
    2 * (cards - 1) messages, each paying the latency and carrying payload /
    cards."""
    if cards < 2:
        return 0.0
    steps = 2 * (cards - 1)
    return steps * link.latency_us * _US + steps / cards * payload / (link.gib_s * _GIB)


class _LinkBook:
    """Links looked up by class, each class resolved through the injected
    callable once, so a plan can report the links it priced in."""

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
    """Cost per token of what llama.cpp exchanges: for a tensor split one
    all-reduce per block on each card's PCIe link, for a layer split one
    activation hop per stage boundary, priced on the network when a boundary has
    a remote end and on PCIe when it has none."""
    book = _LinkBook(links)
    payload = int(sizing.table["n_embd"]) * ACTIVATION_BYTES[LLAMACPP_ENGINE]
    if len(ordered) < 2:
        return 0.0, ()
    if grid.split == SPLIT_TENSOR:
        # Every block is shared, so every block all-reduces inside one machine.
        each = _all_reduce_s(book.of_class(PCIE), payload, len(ordered))
        return sizing.n_layer * ALL_REDUCES_PER_BLOCK * each, book.used

    def remote(target: Target) -> bool:
        return target.host.lower() != head.lower()

    total = 0.0
    if remote(ordered[0]):
        total += _hop_s(book.of_class(NETWORK), payload)
    for here, there in itertools.pairwise(ordered):
        # A boundary travels the network once for each remote end it has: none
        # for two cards in the head machine, two when both ends are elsewhere.
        crossings = int(remote(here)) + int(remote(there))
        if crossings:
            total += crossings * _hop_s(book.of_class(NETWORK), payload)
        else:
            total += _hop_s(book.of_class(PCIE), payload)
    return total, book.used


def _vllm_order(targets: Sequence[Target], *, name: str) -> list[Target]:
    """Order vLLM's cards machine by machine, each machine's cards by GPU index,
    stages taking consecutive runs of the result; a multi-node launch needs the
    same card count on every machine, so uneven counts are refused."""
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
    """Plan vLLM's tensor x pipeline split: a pipeline stage holds one contiguous
    run of blocks, replicated across its tensor ranks, and each rank holds its
    shard of every matrix plus its share of the embeddings and output head at the
    two ends of the pipeline."""
    ordered = _vllm_order(targets, name=sizing.name)
    t, p = grid.tensor, grid.pipeline
    _check_heads(sizing.table, t, name=sizing.name)
    n = sizing.n_layer
    output = int(sizing.table["bytes_output"])
    output_matrix = int(sizing.table["bytes_output_matrix"])
    inp = int(sizing.table["bytes_input"])
    tower = int(sizing.table.get("bytes_tower") or 0)

    def block_on_rank(b: int) -> int:
        return math.ceil(sizing.matrix(b) / t) + sizing.block(b) - sizing.matrix(b)

    def ends(stage: int) -> int:
        held = tower
        if stage == 0:
            held += math.ceil(inp / t)
        if stage == p - 1:
            held += output - output_matrix
            if not sizing.tied:
                held += math.ceil(output_matrix / t)
            elif stage != 0:
                held += math.ceil(inp / t)
        return held

    def rank_weights(stage: int, blocks: Sequence[int]) -> int:
        return sum(block_on_rank(b) for b in blocks) + ends(stage)

    def stage_targets(stage: int) -> Sequence[Target]:
        return ordered[stage * t : (stage + 1) * t]

    # Cumulative cost of the blocks on one rank, so a stage's run can be summed
    # by subtracting two prefix entries; the end weights are added per stage.
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
    """Cost per token of what vLLM exchanges: per stage, the all-reduces of its
    blocks over its tensor ranks, priced on the network when the stage spans
    machines and on PCIe when it does not; plus one activation hop from each
    stage to the first card of the next."""
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
