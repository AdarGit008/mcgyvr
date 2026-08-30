"""Sizing held against numbers read from a file rather than declared.

The constants these tests replaced were wrong in three places at once and
almost right in their product, which is why a suite that checked the product
never caught them. So everything here is anchored to one of two things: a
figure read out of the GGUF the sweep actually drove, or a cell the sweep
actually recorded. Nothing is asserted against a number this codebase chose.

READ FROM THE FILE
------------------
``unsloth/Qwen3.6-35B-A3B-GGUF -> UD-IQ3_XXS``, byte-identical to the file in
``records/measurements/serving-sweep-2026-08-25/`` (13_211_155_424 bytes)::

    <arch>.block_count   40
    expert tensors       11_108_614_144 B  (10.345 GiB)
    non-expert           2_091_551_232 B   (1.948 GiB)
    per block            262 MiB x 37, 300 MiB x 3   -- not uniform

The old arithmetic put the block count at 48, the expert share at 0.92 and read
a decimal-GB numeral as GiB. Those three errors multiplied to 0.978, so the
per-block figure landed within 1% of the sweep's measurement; the complement
did not cancel and the resident floor came out at roughly half what the file
leaves. Correcting any one error alone made the per-block figure worse, which
is the trap: there is no single constant here that can be right.

MEASURED BY THE SWEEP
---------------------
srv2, RTX 3060 (12288 MiB), ``-c 4096 --no-mmap -t 20``, 4 slots. VRAM falls
262.0 MiB per block offloaded across ncmoe 4..20, and RSS tracks
``blocks * 262 MiB + 1.53 GiB``. The KV control: ncmoe 4 with f16 KV used
11_882 MiB and the same cell with ``-ctk q8_0 -ctv q8_0`` used 11_846, freeing
36 MiB across 4 slots -- so f16 KV costs about 18 MiB per slot.
"""

from __future__ import annotations

import pytest

from mcgyvr.capability import GB_PER_GIB
from mcgyvr.config import ConfigSchemaError, parse
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    KV_GB_PER_SLOT,
    ModelSpec,
    UnitError,
    _expert_gb_per_block,
    _placement,
    _resident_floor_gb,
    declared_models,
    fit,
    units_for,
)

MIB = 1024.0

# The file, in the unit this module works in.
BLOCKS = 40
EXPERT_GIB = 11_108_614_144 / 1024**3
NONEXPERT_MIB = 2_091_551_232 / 1024**2
FILE_GIB = 13_211_155_424 / 1024**3

# What the sweep measured f16 KV to cost, from the q8_0 control.
MEASURED_KV_MIB_PER_SLOT = 18.0

SWEPT = ModelSpec(
    name="Qwen3.6-35B-A3B-UD-IQ3_XXS",
    vram_gb=FILE_GIB,
    ram_gb=0.0,
    disk_gb=FILE_GIB,
    moe=True,
    blocks=BLOCKS,
    expert_gb=EXPERT_GIB,
)


def srv2(*, free_mib: int = 12_000, ram_gb: float = 14.3) -> Scan:
    """srv2 as the sweep found it. ``Scan.of`` reports the card wholly free, so
    ``free_mib`` is passed as the total: what this module reads is free VRAM."""
    return Scan.of(
        host="localhost",
        vram_mib=free_mib,
        ram_gb=ram_gb,
        disk_free_gb=900.0,
        cores=10,
        threads=20,
    )


BASE = """\
version: 1
sources:
  local:
    base_url: http://localhost:8080
    api: openai
{engine}\
ladder:
  tiers:
    - name: local_rung
      source: local
      model: {model}
"""


def config_for(model: str, *, engine: str = "", models: str = "") -> object:
    text = BASE.format(model=model, engine=f"    engine: {engine}\n" if engine else "")
    return parse(text + models)


# --------------------------------------------------------------------------
# the file's own geometry
# --------------------------------------------------------------------------


def test_expert_cost_per_block_is_the_mass_over_the_count() -> None:
    """Both numbers the model's own, neither a share of the other."""
    per_block_mib = _expert_gb_per_block(SWEPT, BLOCKS) * MIB
    # 37 blocks at 262 MiB and 3 at 300 average to 264.9. The sweep only ever
    # offloaded into the cheap band, which is why its delta read flat at 262.
    assert per_block_mib == pytest.approx(264.9, abs=1.0), (
        f"one block's experts should be the file's expert mass over its own "
        f"block count; got {per_block_mib:.1f} MiB"
    )


def test_resident_floor_is_what_the_file_leaves_non_expert() -> None:
    """A subtraction between two stated figures, not a fraction of one.

    ``disk_gb`` is the file and the file is 10.5 MB larger than its tensor data
    (13_211_155_424 against 13_200_165_376 — GGUF metadata and padding), so the
    floor comes out about 10 MiB above the tensor-only non-expert mass. That is
    the harmless direction for a floor and not worth a second field to remove.
    """
    floor_mib = _resident_floor_gb(SWEPT) * MIB
    overhead_mib = (13_211_155_424 - 13_200_165_376) / 1024**2
    assert floor_mib == pytest.approx(NONEXPERT_MIB + overhead_mib, abs=1.0), (
        f"the floor should be disk minus experts (~{NONEXPERT_MIB:.0f} MiB of "
        f"tensors plus {overhead_mib:.0f} MiB of file overhead); got "
        f"{floor_mib:.0f}"
    )
    assert floor_mib > 1082, (
        "the old `disk_gb * (1 - 0.92)` gave 1082 MiB, which is under what the "
        "weights actually leave on the card -- the OOM direction"
    )


def test_an_moe_missing_either_figure_is_refused_and_named() -> None:
    """Refusal is honest where a guess would be gigabytes wrong."""
    for missing, spec in (
        ("a block count", ModelSpec("m", 1.0, 0.0, 1.0, moe=True, expert_gb=0.8)),
        ("an expert mass", ModelSpec("m", 1.0, 0.0, 1.0, moe=True, blocks=40)),
    ):
        sized = fit(srv2(), spec)
        assert not sized.fits
        assert missing in sized.why, (
            f"the refusal should name what is missing; got {sized.why!r}"
        )


# --------------------------------------------------------------------------
# what memory is asked to hold
# --------------------------------------------------------------------------


@pytest.mark.parametrize("blocks", [4, 8, 12, 20])
def test_ram_tracks_the_offload_rather_than_the_whole_file(blocks: int) -> None:
    """``max(spec.ram_gb, ...)`` used to make the block count irrelevant here.

    Measured RSS at these cells ran from 2.56 to 6.64 GiB while the old code
    claimed 12.3 for every one of them.
    """
    placed = _placement(SWEPT, free_vram_gb=12_000 / MIB)
    del placed  # the derivation under test is the one below, at a fixed offload
    spilled = blocks * _expert_gb_per_block(SWEPT, BLOCKS) + 1.53
    measured = {4: 2.556, 8: 3.573, 12: 4.587, 20: 6.639}[blocks]
    assert spilled == pytest.approx(measured, rel=0.08), (
        f"{blocks} blocks offloaded should cost about what the sweep recorded "
        f"({measured:.2f} GiB); the arithmetic gives {spilled:.2f}"
    )


def test_a_roomy_card_and_a_cramped_one_do_not_claim_the_same_ram() -> None:
    cramped = _placement(SWEPT, free_vram_gb=6.0)
    roomy = _placement(SWEPT, free_vram_gb=11.5)
    assert cramped.blocks > roomy.blocks
    assert cramped.ram_gb > roomy.ram_gb, (
        "spilling more experts should ask more of memory; the old max() against "
        "the whole model weight made both cards claim the same figure"
    )


def test_a_stated_ram_floor_is_still_honoured() -> None:
    """An operator who knows something this module cannot see is not overruled."""
    claimed = ModelSpec(
        name="m",
        vram_gb=FILE_GIB,
        ram_gb=40.0,
        disk_gb=FILE_GIB,
        moe=True,
        blocks=BLOCKS,
        expert_gb=EXPERT_GIB,
    )
    assert _placement(claimed, free_vram_gb=6.0).ram_gb >= 40.0


# --------------------------------------------------------------------------
# slots
# --------------------------------------------------------------------------


def test_a_slot_is_not_allowed_many_times_what_one_costs() -> None:
    """The margin is subtracted from the slots a rig may serve."""
    allowed = KV_GB_PER_SLOT * MIB
    assert allowed >= MEASURED_KV_MIB_PER_SLOT, "a slot must not be under-priced"
    assert allowed <= 4 * MEASURED_KV_MIB_PER_SLOT, (
        f"{allowed:.0f} MiB per slot against a measured "
        f"{MEASURED_KV_MIB_PER_SLOT:.0f}. The old 0.25 GiB was 256 MiB -- "
        f"fourteen times -- and cost a 12 GB card ten slots it measurably held"
    )


# --------------------------------------------------------------------------
# the table's unit
# --------------------------------------------------------------------------


def test_the_table_is_decimal_and_the_conversion_is_explicit() -> None:
    """Tied to a real file: deepseek-coder-v2-16b.gguf is 8_905_109_984 bytes.

    Its row says ``weights_gb: 8.9``, which is decimal (GiB would read 8.3).
    """
    row_says = 8.9
    as_decimal = 8_905_109_984 / 1e9
    as_gib = 8_905_109_984 / 1024**3
    assert as_decimal == pytest.approx(row_says, abs=0.05), (
        "the row matches the file read as decimal GB"
    )
    assert as_gib == pytest.approx(8.294, abs=0.01), (
        "and does not match it read as GiB, which is how the code used it"
    )
    assert row_says / GB_PER_GIB == pytest.approx(as_gib, abs=0.01), (
        "GB_PER_GIB is the conversion that reconciles them"
    )


# --------------------------------------------------------------------------
# what the operator may say
# --------------------------------------------------------------------------


def test_a_source_names_the_engine_and_it_reaches_the_unit() -> None:
    config = config_for("qwen2.5-coder:7b", engine="vllm")
    assert config.sources["local"].engine == "vllm"  # type: ignore[attr-defined]
    spec = ModelSpec("qwen2.5-coder:7b", 5.0, 0.0, 4.7)
    unit = units_for(config, {"localhost": srv2()}, specs=(spec,))[0]  # type: ignore[arg-type]
    assert unit.engine == "vllm"
    assert unit.key.engine == "vllm", "the engine is part of what makes a process"


def test_an_unstated_engine_is_still_llama_cpp() -> None:
    """A config that names no engine is bound exactly as it was before."""
    config = config_for("qwen2.5-coder:7b")
    assert config.sources["local"].engine is None  # type: ignore[attr-defined]
    spec = ModelSpec("qwen2.5-coder:7b", 5.0, 0.0, 4.7)
    unit = units_for(config, {"localhost": srv2()}, specs=(spec,))[0]  # type: ignore[arg-type]
    assert unit.engine == "llama.cpp"


DECLARED = """\
models:
  my-own-moe:
    vram_gb: 12.3
    disk_gb: 12.3
    moe: true
    blocks: 40
    expert_gb: 10.35
"""


def test_an_operator_may_serve_a_model_the_table_never_measured() -> None:
    config = config_for("my-own-moe", models=DECLARED)
    assert "my-own-moe" in declared_models(config)  # type: ignore[arg-type]
    unit = units_for(config, {"localhost": srv2()}, specs=())[0]  # type: ignore[arg-type]
    assert unit.model == "my-own-moe"
    assert "--n-cpu-moe" in unit.args, "a stated block count should drive the offload"


def test_a_declaration_overrides_the_shipped_table() -> None:
    """Config wins. mcgyvr says what it measured, then does what it was told."""
    shipped = ModelSpec("my-own-moe", 99.0, 0.0, 99.0)
    config = config_for("my-own-moe", models=DECLARED)
    unit = units_for(config, {"localhost": srv2()}, specs=(shipped,))[0]  # type: ignore[arg-type]
    assert unit.fit.fits, "the 99 GB shipped row should not have been consulted"


def test_a_wrong_declaration_is_obeyed_not_corrected() -> None:
    """The operator is allowed to break it; that is what owning the rig means."""
    wrong = DECLARED.replace("blocks: 40", "blocks: 4")
    config = config_for("my-own-moe", models=wrong)
    unit = units_for(config, {"localhost": srv2()}, specs=())[0]  # type: ignore[arg-type]
    assert declared_models(config)["my-own-moe"].blocks == 4  # type: ignore[arg-type]
    assert int(unit.args["--n-cpu-moe"]) <= 4, (
        "an offload sized from a wrong block count should reflect the wrong "
        "count, not a corrected one"
    )


def test_a_model_nobody_declared_is_refused_with_the_fix_in_the_message() -> None:
    config = config_for("nobody-measured-this")
    with pytest.raises(UnitError, match="models:"):
        units_for(config, {"localhost": srv2()}, specs=())  # type: ignore[arg-type]


def test_a_size_must_be_a_number_and_not_a_flag() -> None:
    """`expert_gb: true` and `moe: true` must not pass the same rule."""
    with pytest.raises(ConfigSchemaError, match="expected a number"):
        config_for("m", models="models:\n  m:\n    expert_gb: true\n")
