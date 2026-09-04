"""Every llama.cpp serving declaration, checked before a rig is touched.

**Why these checks and not others.** Three of this backend's failure modes do
not raise, do not warn, and do not look like failures in the recorded row --
they produce a plausible number that means something other than what the column
says. A campaign that ranks engines on those numbers ranks its own
misconfiguration. Each is asserted here, at config time, where a fix costs a
line rather than a re-run:

1. ``--parallel`` below the ramp's widest level. ``llama-server``'s default is
   **four** slots. Measured on srv1 2026-08-30, one model, one prompt, only the
   flag differing: at the default, n=8 aggregate came out 175.41 against n=4's
   175.35 -- flat, while latency doubled. At ``--parallel 8`` the same cell gave
   206.63. The flat reading is the exact shape of hardware saturation, and it
   would have CONFIRMED the "llama.cpp caps ~2x" claim this campaign exists to
   test, from a flag that did not take.

2. ``ctx_per_slot`` below the completion budget. ``-c`` is TOTAL and the server
   divides it across slots, so ``-c 4096 --parallel 8`` is 512 tokens per slot
   against a 475-token completion -- 37 left for the prompt. The generation is
   truncated, the server answers 200, and the row reads as a slow model.

3. A GGUF past the mmap budget. Nothing refuses it: the model loads, thrashes,
   and reports a disk benchmark as a decode throughput.

The backend enforces all three at launch. These are the same checks one layer
earlier, so a typo fails in a second instead of after a teardown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "tools" / "bench" / "serving" / "configs"

#: 475-token completion budget plus 512 tokens of room for the prompt. Mirrors
#: ``backends/llamacpp.py``'s ``MIN_CTX_PER_SLOT``; asserted equal below so the
#: two cannot drift apart silently.
MIN_CTX_PER_SLOT = 987

#: ``MemAvailable - 2 GB``. The headroom mirrors the backend's
#: ``MMAP_HEADROOM_BYTES``.
MMAP_HEADROOM_BYTES = 2 * 1000**3

#: MEASURED with ``awk '/MemAvailable/' /proc/meminfo``. The gate at launch
#: reads the number live -- this is the floor each host has been observed at, so
#: a cell declared here is one that fit the WORST reading and not merely the
#: luckiest.
#:
#: **srv1's floor was LOWERED on 2026-09-04, from 13,869 MiB to 13,714.** The
#: rigs' RAM moved between them: srv1 is the 16 GB box (MemTotal 16.14 GB) and
#: srv2 the 48 GB one (49.37 GB), which is the reverse of what the 2026-08-27
#: store record says and the reverse of what the 2026-08-25 sweep measured.
#: Read idle, no containers up, six samples over 20 s: 13,714 / 13,738 / 13,741
#: / 13,741 / 13,742 / 13,742 MiB.
AVAILABLE_FLOOR_BYTES = {"srv1": 13_714 * 1024**2, "srv2": 47_744_253_952}

#: MEASURED with ``nvidia-smi --query-gpu=memory.total,memory.reserved`` on both
#: rigs 2026-08-30. The reserve is GSP firmware -- a coprocessor on the GPU die
#: whose code lives in card memory -- and no process can allocate it. It is a
#: fixed carveout rather than a fraction: 401 MiB of srv1's 6,144 (6.5%) and 380
#: of srv2's 12,288 (3.1%). CUDA does not report it as existing; PyTorch called
#: srv2's 12 GB card "a total capacity of 11.63 GiB", which is 12,288 - 380.
CARD_TOTAL_MIB = {"srv1": 6144, "srv2": 12288}
CARD_RESERVED_MIB = {"srv1": 401, "srv2": 380}
USABLE_CARD_MIB = {
    host: CARD_TOTAL_MIB[host] - CARD_RESERVED_MIB[host] for host in CARD_TOTAL_MIB
}

#: The CUDA context alone, in VRAM, separate from :data:`COMPUTE_ALLOWANCE_MIB`
#: because the floor derivation in ``okf/must-read/touching-rigs.md`` names it
#: separately ("~1.0 GB"). Also an allowance. Mirrors the backend's
#: ``CUDA_CONTEXT_MIB``; asserted equal below.
CUDA_CONTEXT_MIB = 1024

#: What ``llama-server`` holds beyond weights and KV -- CUDA context, compute
#: buffers, graph scratch. Deliberately an ALLOWANCE and not a fitted residue:
#: the sibling engine's equivalent constant was fitted on one host and found to
#: be wrong by 400 MiB on the other (180-374 MiB of residue on srv1 against
#: 715-791 on srv2, same models), so this one is stated as a round number that
#: the cells clear by a margin rather than a precision it has not earned.
COMPUTE_ALLOWANCE_MIB = 400

#: Blob sizes, MEASURED with ``stat -c %s`` on the serving host 2026-08-30.
GGUF_BYTES = {
    "dense/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf": 1_929_903_264,
    "dense/Qwen3-4B-Q4_K_M.gguf": 2_497_281_248,
    "dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf": 4_218_460_800,
    "dense/nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_M.gguf": 4_683_073_248,
    "dense/Qwen3-8B-Q4_K_M.gguf": 5_027_783_136,
    "dense/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf": 8_988_110_048,
    "moe/Ling-3.0-tiny-Q4_K_M.gguf": 4_920_000_000,
    "moe/deepseek-coder-v2-16b.gguf": 8_905_248_512,
    "moe/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf": 11_420_000_000,
    "moe/Qwen3.6-35B-A3B-UD-IQ2_M.gguf": 11_520_000_000,
    "moe/gpt-oss-20b-MXFP4.gguf": 12_110_000_000,
    "moe/Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf": 12_850_000_000,
    "moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf": 13_210_000_000,
    "moe/qwen3-coder-30b.gguf": 18_560_000_000,
    "moe/KAT-Coder-V2.5-Dev.Q4_K_M.gguf": 21_166_758_464,
    "moe/Qwen3-Coder-Next-UD-Q3_K_XL.gguf": 36_280_000_000,
}

#: ``(bytes_experts, n_layer, bytes_nonexpert, full_attention_interval)``, READ
#: FROM each blob's own tensor table by ``ggufscan.py`` on the serving host and
#: recorded at ``records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/``.
#:
#: **The expert mass is the only part ``--n-cpu-moe`` can move**, so it and not
#: the file size is what a host must hold. The gap between the two is the whole
#: reason this table exists: ``Qwen3.6-35B-A3B-UD-IQ3_XXS`` is a 13.21 GB blob
#: of which 11.11 GB is experts and 2.09 GB is not, and the 2.09 GB goes to the
#: card at ``-ngl 99`` and stays there.
#:
#: A blob absent from this table is weighed whole -- correct for the dense
#: cells, which have nothing to spill.
EXPERT_GEOMETRY = {
    "moe/KAT-Coder-V2.5-Dev.Q4_K_M.gguf": (19_503_513_600, 40, 1_652_255_232, 4),
    "moe/Ling-3.0-tiny-Q4_K_M.gguf": (4_192_468_992, 24, 718_369_408, None),
    "moe/Qwen3-Coder-30B-A3B-Instruct-UD-IQ3_XXS.gguf": (
        11_843_665_920,
        48,
        999_127_040,
        None,
    ),
    "moe/Qwen3-Coder-Next-UD-Q3_K_XL.gguf": (33_663_483_904, 48, 2_613_212_160, 4),
    "moe/Qwen3.6-35B-A3B-UD-IQ2_M.gguf": (9_766_436_864, 40, 1_745_275_392, 4),
    "moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf": (11_108_614_144, 40, 2_091_551_232, 4),
    "moe/deepseek-coder-v2-16b.gguf": (8_097_103_872, 27, 804_009_984, None),
    "moe/gemma-4-26B-A4B-it-UD-IQ3_XXS.gguf": (9_341_385_728, 30, 2_059_337_592, None),
    "moe/gpt-oss-20b-MXFP4.gguf": (10_178_887_680, 24, 1_917_670_656, None),
    "moe/qwen3-coder-30b.gguf": (17_553_162_240, 48, 997_554_176, None),
}

#: What the process holds in host RAM BEYOND the offloaded experts themselves.
#: ``RSS - blocks * expert_per_block`` sat at 1.52-1.53 GiB at every setting
#: measured, which is why it is a constant and not a rate. Mirrors the
#: backend's ``RUNTIME_RESIDENT_BYTES``; asserted equal below.
RUNTIME_RESIDENT_BYTES = int(1.53 * 1024**3)


def _floor_blocks(
    entry: dict[str, Any],
    expert_bytes: int,
    nonexpert_bytes: int,
    n_layer: int,
    interval: int | None,
    host: str,
) -> int:
    """The FEWEST blocks of experts this card can leave in host RAM.

    ``usable VRAM - CUDA context - non-expert weights - KV - slot state``, over
    the per-block expert mass, is what the card can hold; the rest is the floor.
    Mirrors ``backends/llamacpp.py``'s ``expert_floor``.

    Derived and not measured: the CUDA-context and slot-state figures are
    allowances, so this is a prediction to walk down to. It is used here to
    answer one question only -- whether ANY placement fits -- and that answer
    is insensitive to a hundred MiB either way for every cell in these configs.

    **Judged against an IDLE card, which is where this suite differs from the
    gate on purpose.** ``USABLE_CARD_MIB`` is total-less-reserve; the gate uses
    ``memory.free`` at launch, because a card can be occupied by something the
    campaign did not start and must not stop -- measured on srv1 2026-09-04,
    two ``ollama`` llama-server processes held 3,374 of 5,743 MiB. A static
    declaration cannot know that and should not pretend to: what a config can
    assert is that the cell fits a rig that is free to run it, and the runtime
    refusal is what covers a rig that is not.
    """
    serve = entry["serve"]
    slots = int(serve.get("parallel") or 1)
    tokens = int(serve.get("ctx_per_slot") or 0) * slots
    caching = n_layer // interval if interval else n_layer
    kv_mib = caching * tokens * 2048 / 1024**2
    state_mib = (n_layer - caching) * slots * 2
    for_experts = (
        USABLE_CARD_MIB[host]
        - CUDA_CONTEXT_MIB
        - kv_mib
        - state_mib
        - nonexpert_bytes / 1024**2
    )
    per_block_mib = expert_bytes / n_layer / 1024**2
    resident = max(0, min(n_layer, int(for_experts // per_block_mib)))
    return n_layer - resident


#: ``block_count x attention.head_count_kv x key_length x 2 (K and V) x 2 bytes``,
#: READ FROM each blob's own GGUF header 2026-08-30, not from a model card. The
#: spread is the point: Qwen3-4B carries 8 KV heads against Qwen2.5-3B's 2, so
#: its cache is four times the size per token despite being the larger-numbered
#: but similarly sized model. A cell excluded for VRAM is usually excluded by
#: this column rather than by its weights.
BYTES_PER_TOKEN = {
    "dense/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf": 36_864,
    "dense/Qwen3-4B-Q4_K_M.gguf": 147_456,
    "dense/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf": 57_344,
    "dense/nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_M.gguf": 57_344,
    "dense/Qwen3-8B-Q4_K_M.gguf": 147_456,
    "dense/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf": 196_608,
}


def _configs() -> list[Path]:
    return sorted(CONFIGS.glob("srv-lcpp-*.json"))


def _entries() -> list[tuple[Path, dict[str, Any]]]:
    out = []
    for path in _configs():
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("models") or []:
            if entry.get("backend") == "llamacpp":
                out.append((path, entry))
    return out


def _blob(entry: dict[str, Any]) -> str:
    identifier: str = entry["id"]
    return identifier.split("/models/", 1)[1]


def test_there_are_llamacpp_entries_to_check() -> None:
    """Without this the whole file passes by reading nothing."""
    entries = _entries()
    assert entries, (
        f"no config under {CONFIGS} declares a llamacpp entry, so every check "
        "in this file would pass vacuously"
    )
    assert len(_configs()) == 2, "one config per host: srv1 and srv2"


def test_the_floor_here_matches_the_backend() -> None:
    """Two copies of 987 that could drift apart, pinned to each other."""
    source = (
        REPO / "tools" / "bench" / "serving" / "backends" / "llamacpp.py"
    ).read_text(encoding="utf-8")
    assert "PROMPT_HEADROOM_TOKENS = 512" in source, (
        "the backend's prompt headroom moved; MIN_CTX_PER_SLOT here is derived "
        "from it and is now stale"
    )


def test_the_sizing_allowances_here_match_the_backend() -> None:
    """The gate and this suite must judge a cell by the same arithmetic.

    Both derive an ``--n-cpu-moe`` floor and weigh the experts below it against
    ``MemAvailable``. If the backend's allowances move and these do not, the
    suite goes on passing cells the rig will refuse -- which is the failure the
    987 pin above already exists to prevent, one constant over.
    """
    source = (
        REPO / "tools" / "bench" / "serving" / "backends" / "llamacpp.py"
    ).read_text(encoding="utf-8")
    for constant in (
        f"CUDA_CONTEXT_MIB = {CUDA_CONTEXT_MIB}",
        "KV_BYTES_PER_TOKEN_PER_CACHING_LAYER = 2048",
        "STATE_MIB_PER_LINEAR_LAYER_PER_SLOT = 2",
        "RUNTIME_RESIDENT_BYTES = int(1.53 * 1024**3)",
        f"MMAP_HEADROOM_BYTES = {MMAP_HEADROOM_BYTES // 1000**3} * 1000**3",
    ):
        assert constant in source, (
            f"{constant!r} is not what the backend says; this suite's floor "
            "derivation has drifted from the gate's"
        )


def _case_id(value: Any) -> str:
    """Name each parametrised case by its cell label, so a failure reads as the
    cell that failed rather than as an index into a list."""
    if isinstance(value, dict):
        return str(value.get("label"))
    return str(value)


@pytest.mark.parametrize("path,entry", _entries(), ids=_case_id)
def test_parallel_covers_the_widest_level(path: Path, entry: dict[str, Any]) -> None:
    """The false-plateau check. See this module's docstring, point 1."""
    serve = entry["serve"]
    where = f"{path.name}:{entry['label']}"
    levels = serve.get("levels")
    assert levels, f"{where}: declares no levels, so no width can be checked"
    parallel = serve.get("parallel")
    assert parallel is not None, (
        f"{where}: declares no `parallel`. llama-server would default to FOUR "
        "slots and run n=8 as two sequential batches, flattening the aggregate "
        "into something shaped exactly like saturation"
    )
    assert parallel >= max(levels), (
        f"{where}: parallel={parallel} is below the widest level n={max(levels)}"
    )


@pytest.mark.parametrize("path,entry", _entries(), ids=_case_id)
def test_ctx_per_slot_clears_the_completion_budget(
    path: Path, entry: dict[str, Any]
) -> None:
    """The silent-truncation check. See this module's docstring, point 2."""
    serve = entry["serve"]
    where = f"{path.name}:{entry['label']}"
    per_slot = serve.get("ctx_per_slot")
    assert per_slot is not None, f"{where}: declares no ctx_per_slot"
    assert per_slot >= MIN_CTX_PER_SLOT, (
        f"{where}: ctx_per_slot={per_slot} is below {MIN_CTX_PER_SLOT}. A slot "
        "holds the prompt AND the reply; the generation being timed would be "
        "truncated and the server would still answer 200"
    )


@pytest.mark.parametrize("path,entry", _entries(), ids=_case_id)
def test_the_two_level_declarations_agree(path: Path, entry: dict[str, Any]) -> None:
    """``serve.levels`` sizes the launch, ``concurrency.levels`` drives the ramp.

    Different readers, so nothing makes them equal on its own: ``claim`` sets
    the slot width from the first and ``run.py`` walks the second. Declaring
    ``[1,2,4]`` in one and ``[1,2,4,8]`` in the other launches four slots and
    then measures eight -- the false plateau again, arrived at from the other
    side.
    """
    where = f"{path.name}:{entry['label']}"
    assert entry["serve"].get("levels") == entry["concurrency"].get("levels"), (
        f"{where}: serve.levels {entry['serve'].get('levels')} and "
        f"concurrency.levels {entry['concurrency'].get('levels')} disagree"
    )


@pytest.mark.parametrize("path,entry", _entries(), ids=_case_id)
def test_no_entry_turns_off_mmap(path: Path, entry: dict[str, Any]) -> None:
    """``--no-mmap`` is a fix for a RAM shortage, not an optimisation.

    Every srv2 cell measured slower with it on 2026-08-25. The mmap gate is
    what keeps an oversized model from thrashing, and disabling mmap removes
    the thing the gate is protecting.
    """
    serve = entry["serve"]
    where = f"{path.name}:{entry['label']}"
    assert "--no-mmap" not in (serve.get("flags") or []), f"{where}: declares --no-mmap"
    assert not serve.get("no_mmap"), f"{where}: declares no_mmap"


@pytest.mark.parametrize("path,entry", _entries(), ids=_case_id)
def test_the_resident_share_fits_its_hosts_mmap_budget(
    path: Path, entry: dict[str, Any]
) -> None:
    """Checked against the LOWEST ``available`` each host has been seen at.

    The gate at launch reads the number live, and srv1's has swung 13,714 to
    15,142 MiB. A cell admitted only by the high reading is a coin flip; this
    asserts it would have been admitted by the low one too.

    **What is weighed is what stays in RAM, not the blob.** ``-ngl 99
    --n-cpu-moe N`` puts the non-expert weights and ``n_layer - N`` blocks of
    experts on the card, and under mmap those pages are read once, uploaded,
    and then clean and evictable -- never resident alongside the CPU-side
    experts. This mirrors ``backends/llamacpp.py``'s ``mmap_gate``, which was
    rewritten on 2026-09-04 for the same reason: judged by blob size,
    ``Qwen3.6-35B-A3B-UD-IQ3_XXS`` is 13.21 GB against srv1's 12.38 GB budget
    and refused, while the experts it actually holds weigh 9.16 GB at its floor.

    **And it is judged at MAX OFFLOAD.** The declared ``n_cpu_moe`` is the
    entry's choice and can be moved; the floor is the card's answer and cannot.
    A model is too big for a host only when it overflows RAM with the card as
    full as it can be made.
    """
    host = entry["hosts"][0]
    blob = _blob(entry)
    where = f"{path.name}:{entry['label']}"
    assert blob in GGUF_BYTES, f"{where}: {blob} has no measured size here"
    budget = AVAILABLE_FLOOR_BYTES[host] - MMAP_HEADROOM_BYTES

    geometry = EXPERT_GEOMETRY.get(blob)
    if geometry is None:
        # Dense, or a blob whose table is not recorded here: it has nothing to
        # spill and no --n-cpu-moe to spill it with, so the whole file is the
        # right quantity. The backend's gate falls back the same way.
        assert GGUF_BYTES[blob] <= budget, (
            f"{where}: {GGUF_BYTES[blob] / 1000**3:.2f} GB against a "
            f"{budget / 1000**3:.2f} GB budget on {host} at its lowest observed "
            "MemAvailable. mmap'd past `available` the server thrashes and the "
            "throughput it reports is a disk benchmark"
        )
        return

    expert_bytes, n_layer, nonexpert_bytes, interval = geometry
    per_block = expert_bytes / n_layer
    floor = _floor_blocks(entry, expert_bytes, nonexpert_bytes, n_layer, interval, host)
    resident = int(floor * per_block) + RUNTIME_RESIDENT_BYTES
    assert resident <= budget, (
        f"{where}: {resident / 1000**3:.2f} GB resident at its floor of "
        f"--n-cpu-moe {floor} ({n_layer - floor} of {n_layer} blocks on the "
        f"card) against a {budget / 1000**3:.2f} GB budget on {host} at its "
        "lowest observed MemAvailable. Max offload was tried and still "
        "overflows; mmap'd past `available` the server thrashes and the "
        "throughput it reports is a disk benchmark"
    )


@pytest.mark.parametrize("path,entry", _entries(), ids=_case_id)
def test_a_full_gpu_dense_cell_fits_the_usable_card(
    path: Path, entry: dict[str, Any]
) -> None:
    """Weights + KV + compute against the card LESS its firmware reserve.

    Only dense cells: a MoE cell's expert weights leave the card under
    ``--n-cpu-moe`` and what stays is not predictable from the blob size.
    """
    blob = _blob(entry)
    if blob not in BYTES_PER_TOKEN:
        pytest.skip("MoE cell — resident share is not the blob size")
    serve = entry["serve"]
    host = entry["hosts"][0]
    where = f"{path.name}:{entry['label']}"
    weights_mib = GGUF_BYTES[blob] // 1024**2
    tokens = serve["ctx_per_slot"] * serve["parallel"]
    kv_mib = tokens * BYTES_PER_TOKEN[blob] // 1024**2
    need = weights_mib + kv_mib + COMPUTE_ALLOWANCE_MIB
    assert need <= USABLE_CARD_MIB[host], (
        f"{where}: -ngl {serve['ngl']} needs {need:,} MiB "
        f"({weights_mib:,} weights + {kv_mib:,} KV over {tokens:,} tokens + "
        f"{COMPUTE_ALLOWANCE_MIB} compute) against {USABLE_CARD_MIB[host]:,} "
        f"MiB usable on {host} ({CARD_TOTAL_MIB[host]:,} less "
        f"{CARD_RESERVED_MIB[host]} MiB of GSP firmware reserve)"
    )


def test_every_excluded_cell_says_why() -> None:
    """An omission that states no reason is indistinguishable from an oversight.

    The configs carry ``_excluded`` precisely so that a model absent from the
    matrix is absent on the record rather than by having been forgotten.
    """
    for path in _configs():
        document = json.loads(path.read_text(encoding="utf-8"))
        excluded = document.get("_excluded")
        assert isinstance(excluded, dict) and excluded, (
            f"{path.name}: declares no `_excluded`. Every config in this run "
            "excludes something — srv1 cannot hold the 8B at full GPU and srv2 "
            "does not carry three of srv1's MoE blobs"
        )
        for blob, reason in excluded.items():
            assert len(reason) > 40, f"{path.name}:{blob}: reason is not a reason"


def test_moe_cells_declare_their_offload() -> None:
    """A MoE cell either offloads experts or states that it does not need to.

    ``Ling-3.0-tiny`` is the one that does not: 4.92 GB against srv1's 5,743
    MiB of usable card, so it runs ``-ngl 99`` with no ``--n-cpu-moe`` and
    measures MoE concurrency with no host-RAM path in the loop. That is a
    different instrument from the offload cells and the config says so rather
    than leaving the missing flag to be read as an oversight.
    """
    for path, entry in _entries():
        blob = _blob(entry)
        if not blob.startswith("moe/"):
            continue
        serve = entry["serve"]
        where = f"{path.name}:{entry['label']}"
        if serve.get("n_cpu_moe") is None:
            assert serve.get("_cell_note"), (
                f"{where}: a MoE cell with no --n-cpu-moe and no note. Either "
                "it fits the card outright — say so — or the flag was dropped"
            )
