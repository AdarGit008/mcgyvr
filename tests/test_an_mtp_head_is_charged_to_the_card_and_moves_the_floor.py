"""An MTP head is charged to the card, and the ``--n-cpu-moe`` floor moves.

srv2, RTX 3060 12 GB, ``Ornith-1.0-35B_Q2_K-AllGPU`` single slot: the baseline
loads at ``ncmoe=4`` and ``--spec-type draft-mtp`` at ``ncmoe=4`` is refused
(``cudaMalloc failed``); the MTP floor is 8
(``records/evidence/2026-08-28-mtp-ornith/README.md`` §1). The grafted head is
``blk.40``, which ``ggufscan`` already keeps out of ``placeable_blocks`` because
``--n-cpu-moe`` never places it — its expert set weighs 816 MiB in the tensor
table (``expert_bytes_by_block["40"]``), against 278 for each neighbour.

Under ``speculative: mtp`` those bytes are on the card, so:

* :func:`vramfit.mtp_head_bytes` is the head's expert bytes off the table, and
  zero for a checkpoint with no nextn block;
* :func:`vramfit.explain` moves by exactly that many bytes;
* :func:`vramfit.floor` walks past exactly as many blocks as the head displaces
  — on a synthetic geometry, three blocks of 100 MiB for a 300 MiB head;
* KAT's own probe (``test_serving_vramfit``: C 2127 MiB at full offload, 11911
  MiB free) derives the plain floor 5 and the MTP floor **8**, the number the
  rig measured;
* a unit built for the 12 GB card carries the higher floor and a card figure
  that differs from the plain unit's by the head less the blocks it displaced.

The head's own KV is **not** charged: the header's ``kv_layers`` follow
``full_attention_interval`` and stop at block 39, and no measurement separates
the head's state from the main cache. The README's "~1 GB" against the table's
816 MiB bounds what is uncharged; the fit is optimistic by that much and the
docstring says so.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.scan import Scan
from mcgyvr.serving import ModelSpec, fit, unit_for, vramfit

MIB = 1024**2
WINDOW = 4096
GEOMETRY: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "gguf_geometry.json").read_text(
        encoding="utf-8"
    )
)
KAT = "KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf"
STOCK = "Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf"
HEAD_MIB = 816.0


def synthetic(*, blocks: int, block_mib: int, head_mib: int) -> dict[str, Any]:
    """A geometry of ``blocks`` placeable blocks and one nextn block after them."""
    by_block = {str(b): block_mib * MIB for b in range(blocks)}
    by_block[str(blocks)] = head_mib * MIB
    return {
        "file": "/models/synthetic.gguf",
        "size_bytes": 1,
        "arch": "synthetic",
        "n_layer": blocks + 1,
        "bytes_nonexpert": 1000 * MIB,
        "bytes_experts": sum(by_block.values()),
        "expert_blocks": list(range(blocks + 1)),
        "nextn_blocks": [blocks],
        "placeable_blocks": list(range(blocks)),
        "expert_bytes_by_block": by_block,
        "kv_layers": [],
        "n_recurrent": 0,
    }


def test_the_head_is_its_nextn_blocks_expert_bytes_off_the_table() -> None:
    assert vramfit.mtp_head_bytes(GEOMETRY[KAT]) / MIB == HEAD_MIB
    assert vramfit.mtp_head_bytes(GEOMETRY[STOCK]) == 0


def test_explain_moves_by_exactly_the_head() -> None:
    plain = vramfit.explain(GEOMETRY[KAT], n_cpu_moe=8, slots=1, ctx_per_slot=WINDOW)
    mtp = vramfit.explain(
        GEOMETRY[KAT], n_cpu_moe=8, slots=1, ctx_per_slot=WINDOW, speculative="mtp"
    )
    assert mtp.predicted_mib - plain.predicted_mib == pytest.approx(HEAD_MIB)
    assert mtp.allowance_mib == plain.allowance_mib


def test_the_floor_walks_past_exactly_the_blocks_the_head_displaces() -> None:
    geometry = synthetic(blocks=10, block_mib=100, head_mib=300)
    constant = 1000 * MIB
    free = constant + 8 * 100 * MIB
    assert vramfit.floor(geometry, free, constant) == 2
    assert (
        vramfit.floor(geometry, free, constant + vramfit.mtp_head_bytes(geometry)) == 5
    )


def test_kats_probe_derives_the_floor_the_rig_measured_with_mtp() -> None:
    """Plain 5, MTP 8 — the README's ``ncmoe=4 REFUSED`` / ``8`` row."""
    geometry = GEOMETRY[KAT]
    constant = vramfit.constant_from_probe(geometry, 41, (2127 - 1) * MIB)
    free = 11911 * MIB
    assert vramfit.floor(geometry, free, constant) == 5
    assert (
        vramfit.floor(geometry, free, constant + vramfit.mtp_head_bytes(geometry)) == 8
    )


def card() -> Scan:
    return Scan.of(
        host="srv2",
        vram_mib=12288,
        ram_gb=48.0,
        disk_free_gb=120.0,
        cores=10,
        threads=20,
        bandwidth_gbps=41.2,
    )


def scanned(speculative: str) -> ModelSpec:
    return ModelSpec(
        name=KAT[: -len(".gguf")],
        vram_gb=0.0,
        ram_gb=0.0,
        disk_gb=0.0,
        geometry=GEOMETRY[KAT],
        kv_cache_dtype_k="f16",
        kv_cache_dtype_v="f16",
        speculative=speculative,
    )


def test_a_unit_carries_the_higher_floor_and_the_head_in_its_card_figure() -> None:
    plain = unit_for(card(), scanned("none"), width=1, ctx_per_slot=WINDOW)
    mtp = unit_for(card(), scanned("mtp"), width=1, ctx_per_slot=WINDOW)
    n_plain = int(plain.args["--n-cpu-moe"])
    n_mtp = int(mtp.args["--n-cpu-moe"])
    assert n_mtp > n_plain
    displaced = vramfit.experts_on_card(
        GEOMETRY[KAT], n_plain
    ) - vramfit.experts_on_card(GEOMETRY[KAT], n_mtp)
    moved = (mtp.fit.vram_gb - plain.fit.vram_gb) * 1024**3
    assert moved == pytest.approx(HEAD_MIB * MIB - displaced, abs=1.0)


def test_the_fit_says_the_head_is_on_the_card() -> None:
    sized = fit(card(), scanned("mtp"), width=1, ctx_per_slot=WINDOW)
    assert sized.fits, sized.why
    assert "MTP head" in sized.why
    assert "816" in sized.why
    plain = fit(card(), scanned("none"), width=1, ctx_per_slot=WINDOW)
    assert "MTP head" not in plain.why
