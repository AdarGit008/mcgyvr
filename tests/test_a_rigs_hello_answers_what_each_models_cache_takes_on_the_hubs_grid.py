"""A rig's hello answers what each model's cache takes, on the grid a hub plans on.

The hub plans a pipeline by bytes, but a model's cache is more than one figure a
token: sliding-window layers hold only a window, recurrent blocks hold a state
per slot, and each slot's cells are padded. So the rig sizes each model by the
product's own law (``vramfit.kv_bytes`` and ``vramfit.rs_bytes``) on the grid
the wire names (``hubwire.FIT_CTX`` x ``hubwire.FIT_SLOTS``), at the cache type
and micro-batch every head is started with (``hubwire.HEAD_KV_CACHE_TYPE``,
``hubwire.HEAD_UBATCH``), and the hub picks among the answers. A model that
cannot be sized is answered nothing, and a hello the answers would make too
large goes without them, so the hub falls back to the flat figures it read
before. Every geometry here is invented.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from mcgyvr import hubwire
from mcgyvr.rig import inventory, pooled
from mcgyvr.rig import protocol as p
from mcgyvr.serving import ggufscan, vramfit
from tests import rig_schema

MIB = hubwire.BYTES_PER_MIB


def _layers(
    n: int, *, swa: set[int] | None = None, k: int = 512, v: int = 512
) -> list[dict[str, Any]]:
    return [
        {"layer": i, "is_swa": i in (swa or set()), "k_elems": k, "v_elems": v}
        for i in range(n)
    ]


DENSE: dict[str, Any] = {
    "arch": "llama",
    "n_layer": 32,
    "n_ctx_train": 40960,
    "kv_layers": _layers(32),
}
# Five of every six layers slide over a 1024-token window.
SLIDING: dict[str, Any] = {
    "arch": "gemma3",
    "n_layer": 48,
    "n_ctx_train": 131072,
    "sliding_window": 1024,
    "kv_layers": _layers(48, swa={i for i in range(48) if i % 6 != 5}),
}
# Three of every four blocks are recurrent: only the attention ones cache.
RECURRENT: dict[str, Any] = {
    "arch": "qwen3next",
    "n_layer": 48,
    "n_ctx_train": 262144,
    "kv_layers": _layers(12),
    "n_recurrent": 36,
    "ssm_inner_size": 4096,
    "ssm_state_size": 128,
    "ssm_conv_kernel": 4,
    "ssm_group_count": 16,
}


def _expected(row: dict[str, Any], ctx: int, slots: int) -> int:
    cache = vramfit.kv_bytes(
        row,
        ctx * slots,
        n_seq_max=slots,
        n_ubatch=hubwire.HEAD_UBATCH,
        cache_type_k=hubwire.HEAD_KV_CACHE_TYPE,
        cache_type_v=hubwire.HEAD_KV_CACHE_TYPE,
    )["total"]
    state = vramfit.rs_bytes(row, n_seq_max=slots)["total"]
    return math.ceil((cache + state) / MIB)


@pytest.mark.parametrize("row", [DENSE, SLIDING, RECURRENT], ids=lambda r: r["arch"])
def test_each_answer_is_the_products_own_sizing_on_the_wires_grid(
    row: dict[str, Any],
) -> None:
    fit = inventory.cache_fit(row)
    assert fit is not None
    trained = row["n_ctx_train"]
    assert fit.slots == hubwire.FIT_SLOTS
    assert fit.ctx == tuple(
        sorted({c for c in hubwire.FIT_CTX if c <= trained} | {trained})
    )
    for i, ctx in enumerate(fit.ctx):
        for j, slots in enumerate(fit.slots):
            assert fit.cache_mib[i][j] == _expected(row, ctx, slots)
    fit.validate()


def test_a_sliding_model_is_answered_below_flat_and_a_recurrent_one_above() -> None:
    """The flat figure (every caching layer at the full context, nothing else)
    is what a hub planned on before the answers: too much for a model whose
    layers slide, too little for one whose blocks keep a state."""

    def flat_mib(row: dict[str, Any], ctx: int, slots: int) -> float:
        per_token = inventory.kv_bytes_per_token(row, hubwire.HEAD_KV_CACHE_TYPE)
        assert per_token is not None
        return per_token * ctx * slots / MIB

    sliding, recurrent = inventory.cache_fit(SLIDING), inventory.cache_fit(RECURRENT)
    assert sliding is not None and recurrent is not None
    # five layers in six hold a window, so well under a quarter of the flat figure
    held = sliding.cache_bytes_at(65536, 4)
    assert held is not None and held / MIB < flat_mib(SLIDING, 65536, 4) / 4
    # the recurrent blocks' state comes on top of the attention layers' cache
    held = recurrent.cache_bytes_at(8192, 4)
    assert held is not None and held / MIB > flat_mib(RECURRENT, 8192, 4)


def test_a_model_of_no_trained_context_is_answered_up_to_the_wires_most() -> None:
    fit = inventory.cache_fit({**DENSE, "n_ctx_train": None})
    assert fit is not None and fit.ctx == hubwire.FIT_CTX
    assert fit.ctx[-1] == hubwire.MAX_CTX


def test_a_trained_context_off_the_grid_is_answered_padded_as_the_engine_pads_it() -> (
    None
):
    fit = inventory.cache_fit({**DENSE, "n_ctx_train": 40000})
    assert fit is not None
    assert fit.ctx[-1] == hubwire.context_per_sequence(40000, 1) == 40192
    assert fit.cache_bytes_at(40000, 1) == fit.cache_mib[-1][0] * MIB


@pytest.mark.parametrize(
    "row",
    [
        {**DENSE, "kv_layers": []},
        {k: v for k, v in DENSE.items() if k != "kv_layers"},
        {**SLIDING, "kv_layers": [{**r, "is_swa": None} for r in SLIDING["kv_layers"]]},
        {**RECURRENT, "ssm_state_size": None},
        {**DENSE, "kv_layers": [{"layer": 0, "k_elems": "x", "v_elems": 1}]},
    ],
    ids=["no-layers", "no-rows", "unknown-split", "no-state-size", "bad-widths"],
)
def test_a_model_that_cannot_be_sized_is_answered_nothing(row: dict[str, Any]) -> None:
    assert inventory.cache_fit(row) is None


def test_the_cheapest_answer_at_or_above_is_picked_and_none_beyond_the_last() -> None:
    fit = hubwire.CacheFit(
        slots=(1, 2, 4), ctx=(2048, 4096), cache_mib=((1, 2, 4), (2, 4, 8))
    )
    assert fit.cache_bytes_at(2048, 1) == 1 * MIB
    assert fit.cache_bytes_at(3000, 3) == 8 * MIB  # 4096 x 4, both rounded up
    assert fit.cache_bytes_at(1, 2) == 2 * MIB
    assert fit.cache_bytes_at(4097, 1) is None
    assert fit.cache_bytes_at(2048, 5) is None


@pytest.mark.parametrize(
    ("fit", "field"),
    [
        (hubwire.CacheFit(slots=(2, 1), ctx=(2048,), cache_mib=((1, 2),)), "slots"),
        (hubwire.CacheFit(slots=(1,), ctx=(4096, 2048), cache_mib=((1,), (2,))), "ctx"),
        (hubwire.CacheFit(slots=(17,), ctx=(2048,), cache_mib=((1,),)), "slots"),
        (hubwire.CacheFit(slots=(1,), ctx=(2048,), cache_mib=((1, 2),)), "cache_mib"),
        (
            hubwire.CacheFit(slots=(1,), ctx=(2048, 4096), cache_mib=((1,),)),
            "cache_mib",
        ),
        (hubwire.CacheFit(slots=(1,), ctx=(2048,), cache_mib=((-1,),)), "cache_mib"),
        (hubwire.CacheFit(slots=(), ctx=(2048,), cache_mib=((),)), "slots"),
    ],
)
def test_answers_off_their_shape_are_refused_naming_the_field(
    fit: hubwire.CacheFit, field: str
) -> None:
    with pytest.raises(ValueError, match=f"cache_fit.{field}"):
        fit.validate()
    model = p.ModelInfo(name="m.gguf", size_bytes=1, cache_fit=fit)
    with pytest.raises(ValueError, match=f"models.cache_fit.{field}"):
        _hello((model,))


def _hello(
    models: tuple[p.ModelInfo, ...], *, weight_cache: tuple[str, ...] = ()
) -> str:
    offer = p.Offer(
        roles=("head",),
        runtime=None,
        endpoints=(),
        models=models,
        sessions=(),
        weight_cache=weight_cache,
    )
    return p.hello(
        p.new_id(),
        machine_id="a" * 32,
        agent_version="1.0.0",
        ram_total_mb=1024,
        ram_free_mb=512,
        cards=(),
        offer=offer,
    )


def test_the_hello_carries_the_answers_as_the_published_schema_says() -> None:
    fit = inventory.cache_fit(SLIDING)
    model = p.ModelInfo(name="m.gguf", size_bytes=1 << 30, n_layers=48, cache_fit=fit)
    said = json.loads(_hello((model,)))["body"]["models"][0]
    assert fit is not None and said[hubwire.CACHE_FIT_FIELD] == fit.body()
    schema = rig_schema.load()
    rig_schema.validate(said, schema, "#/$defs/ModelInfo")
    shape = schema["$defs"]["CacheFit"]["properties"]
    assert shape["slots"]["maxItems"] == hubwire.MAX_FIT_SLOT_COUNTS
    assert shape["slots"]["items"]["maximum"] == hubwire.MAX_SLOTS
    assert shape["ctx"]["maxItems"] == hubwire.MAX_FIT_CONTEXTS
    assert shape["ctx"]["items"]["maximum"] == hubwire.MAX_CTX
    assert shape["cache_mib"]["items"]["items"]["maximum"] == hubwire.MAX_FIT_CACHE_MIB
    bare = json.loads(_hello((p.ModelInfo(name="m.gguf", size_bytes=1),)))
    assert hubwire.CACHE_FIT_FIELD not in bare["body"]["models"][0]


def _most_models(fit: hubwire.CacheFit) -> tuple[p.ModelInfo, ...]:
    """The most models a hello names, each with the longest name and the
    largest header figures the wire carries, and ``fit``."""
    return tuple(
        p.ModelInfo(
            name=f"{i:03d}" + "m" * 120 + ".gguf",
            size_bytes=p.MAX_MODEL_BYTES,
            digest="sha256:" + "0" * 64,
            arch="llama",
            n_layers=p.MAX_LAYERS,
            n_ctx_train=p.MAX_COUNT,
            kv_bytes_per_token=p.MAX_KV_BYTES_PER_TOKEN,
            embd_bytes=p.MAX_MODEL_BYTES,
            output_bytes=p.MAX_MODEL_BYTES,
            quant="Q4_K_M",
            cache_fit=fit,
        )
        for i in range(p.MAX_MODELS)
    )


def test_the_most_models_a_hello_names_each_carry_their_answers() -> None:
    """Every context of the grid (no trained context to stop at) and a cache
    larger than any shipped model's: the hello still fits one message."""
    fit = inventory.cache_fit({**DENSE, "n_ctx_train": None, "kv_layers": _layers(512)})
    assert fit is not None and len(fit.ctx) == len(hubwire.FIT_CTX)
    text = _hello(_most_models(fit))
    assert len(text.encode()) <= p.MAX_MESSAGE_BYTES
    said = json.loads(text)["body"]["models"]
    assert all(m[hubwire.CACHE_FIT_FIELD] == fit.body() for m in said)


def test_a_hello_the_answers_would_make_too_large_goes_without_them() -> None:
    """Answers of the widest figures beside a full weight cache would pass the
    message limit: the hello goes with every model and none of the answers."""
    widest = _layers(4096, k=8192, v=8192)
    fit = inventory.cache_fit({**DENSE, "n_ctx_train": None, "kv_layers": widest})
    assert fit is not None
    digests = tuple(f"sha256:{i:064x}" for i in range(p.MAX_MODELS))
    text = _hello(_most_models(fit), weight_cache=digests)
    assert len(text.encode()) <= p.MAX_MESSAGE_BYTES
    said = json.loads(text)["body"]["models"]
    assert len(said) == p.MAX_MODELS
    assert all(hubwire.CACHE_FIT_FIELD not in m for m in said)


def test_a_files_scanned_header_reaches_the_hello_with_its_answers(
    tmp_path: Path,
) -> None:
    from tests.test_a_rigs_hello_names_its_models_and_never_their_paths import (
        write_gguf,
    )

    folder = tmp_path / "models"
    write_gguf(folder / "m.gguf", layers=4)
    (held,) = inventory.read(str(folder)).models
    assert held.cache_fit is not None
    row = ggufscan.scan(str(folder / "m.gguf"))  # type: ignore[no-untyped-call]
    assert held.cache_fit == inventory.cache_fit(row)


def test_the_head_runs_at_the_cache_type_and_micro_batch_the_hub_plans_at() -> None:
    spec = pooled.HeadSpec(
        session_id="s1",
        name="m",
        model="m.gguf",
        models_dir=Path("/srv/models"),
        image="llama:1",
        binary="/app/llama-server",
        gpus=(0,),
        n_gpu_layers=99,
        devices=("CUDA0",),
        tensor_split=(1,),
        rpc=(),
        bind="127.0.0.1",
        memory_mb=8192,
        ctx=8192,
    )
    argv = pooled.head_server_args(spec, model="/models/m.gguf", port=8080, rpc=())
    assert argv[argv.index("-ctk") + 1] == hubwire.HEAD_KV_CACHE_TYPE
    assert argv[argv.index("-ctv") + 1] == hubwire.HEAD_KV_CACHE_TYPE
    assert argv[argv.index("-ub") + 1] == str(hubwire.HEAD_UBATCH)
    assert pooled.KV_CACHE_TYPE == hubwire.HEAD_KV_CACHE_TYPE
    # The width the hub prices an element of that cache at is the scanner's.
    assert (
        vramfit.CACHE_ELEM_BYTES[hubwire.HEAD_KV_CACHE_TYPE]
        == hubwire.HEAD_KV_BYTES_PER_ELEMENT
    )
