"""Sizing held against a file's own header and cells a rig actually ran.

The constants these tests replaced were wrong in three places at once and
almost right in their product, which is why a suite that checked the product
never caught them. So everything here is anchored to one of three things: a
``ggufscan`` row read off the GGUF a rig served, a placement the serving door
recorded from that row, or a launch the rig accepted or refused. Nothing is
asserted against a number this codebase chose.

THE DOOR'S OWN ENVELOPES
------------------------
``records/evidence/2026-09-05-e2e-srv2-deepseek-coder-v2-16b/``: srv2's RTX
3060 with 11 911 MiB free, ``-np 8 -c 16384 -ub 256``. The door derived
``--n-cpu-moe 7`` and predicted 11 794.8 MiB on the card. The same geometry
through :func:`mcgyvr.serving._placement` at the same ``-c``/``-np``/``-ub``
must land on the same two numbers, or the product and the door disagree
about one card.

A RIG'S REFUSALS
----------------
``records/evidence/2026-09-04-srv1-ncmoe-floor/``: srv1's GTX 1660 SUPER,
``--parallel 8 -c 8192`` on ``Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf``. ``ncmoe 32``
loaded at 4 798 MiB, ``30`` at 5 322, ``29`` at 5 584 (the retry file), and
``28`` was refused three times running. The law's floor carries one allowance
and is walked DOWN from, so what it owes the rig is direction: never admit a
cell the rig refused, never predict less than a cell the rig measured.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcgyvr.capability import GB_PER_GIB
from mcgyvr.config import Config, ConfigSchemaError, parse
from mcgyvr.scan import Scan
from mcgyvr.serving import (
    DEFAULT_CONTEXT,
    MAX_WIDTH,
    RUNTIME_RESIDENT_GB,
    ModelSpec,
    UnitError,
    _host_gb,
    _placement,
    declared_models,
    fit,
    load_geometry,
    unit_for,
    units_for,
    vramfit,
)

MIB = 1 << 20
GIB = 1 << 30

EVIDENCE = Path(__file__).resolve().parent.parent / "records" / "evidence"
SRV2_DEEPSEEK = EVIDENCE / "2026-09-05-e2e-srv2-deepseek-coder-v2-16b"
SRV1_QWEN = EVIDENCE / "2026-09-05-e2e-srv1-qwen3-6-35b-a3b-ud-iq3xxs"
SRV2_GPT_OSS = EVIDENCE / "2026-09-05-e2e-srv2-gpt-oss-20b-mxfp4"
FIXTURES = Path(__file__).parent / "fixtures" / "gguf_geometry.json"


def envelope(run: Path, name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((run / name).read_text(encoding="utf-8"))
    return document


def scanned(
    geometry: dict[str, Any], *, ram_gb: float = 0.0, disk_gb: float = 0.0
) -> ModelSpec:
    """A spec whose bytes are the scan's. The name is the file's, because a
    geometry belongs to one file and the spec is refused otherwise."""
    return ModelSpec(
        name=Path(geometry["file"]).stem,
        vram_gb=0.0,
        ram_gb=ram_gb,
        disk_gb=disk_gb,
        geometry=geometry,
    )


DEEPSEEK = envelope(SRV2_DEEPSEEK, "geometry.json")
QWEN36 = envelope(SRV1_QWEN, "geometry.json")
GPT_OSS = envelope(SRV2_GPT_OSS, "geometry.json")


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


def config_for(
    model: str, *, engine: str = "", models: str = "", path: Path | None = None
) -> Config:
    text = BASE.format(model=model, engine=f"    engine: {engine}\n" if engine else "")
    return parse(text + models, path=path)


# --------------------------------------------------------------------------
# the door's own envelope, reproduced
# --------------------------------------------------------------------------


def test_the_product_places_deepseek_on_srv2_where_the_door_did() -> None:
    """Same geometry, same ``-c``/``-np``/``-ub``, same floor and card figure.

    The door's ``data-30-placement`` and this module both compose the constant
    from :mod:`vramfit` -- non-expert weights, cache, state, one allowance --
    and walk the floor off the tensor table. If the two ever land on different
    numbers for one card, one of them has grown a constant of its own.
    """
    placement = envelope(SRV2_DEEPSEEK, "placement.json")
    slots = int(placement["parallel"])
    placed = _placement(
        scanned(DEEPSEEK),
        int(placement["card_free_mib"]) * MIB,
        slots,
        ctx_per_slot=int(placement["n_ctx_total"]) // slots,
        n_ubatch=int(placement["n_ubatch"]),
    )
    assert placed.n_cpu_moe == placement["floor_n_cpu_moe"] == 7
    predicted_mib = placement["predicted_card_mib"]
    assert placed.vram_gb * 1024 == pytest.approx(predicted_mib, abs=1.0)
    assert placement["predicted_card_mib"] == pytest.approx(11794.8, abs=0.05), (
        "the envelope this test is anchored to has changed; re-read it"
    )
    on_card = vramfit.experts_on_card(DEEPSEEK, placed.n_cpu_moe)
    constant_mib = (placed.vram_gb * GIB - on_card) / MIB
    assert constant_mib == pytest.approx(placement["constant_mib"], abs=1.0)


# --------------------------------------------------------------------------
# a rig's refusals: srv1, Qwen3.6-35B IQ3_XXS, --parallel 8 -c 8192
# --------------------------------------------------------------------------

#: ``srv1-ncmoe-floor.tsv`` and ``srv1-ncmoe-floor-retry.tsv``: ``--n-cpu-moe``
#: to the card's ``memory.used`` in MiB once the server was up.
SRV1_LOADED = {32: 4798, 30: 5322, 29: 5584}
#: Refused with ``failed to create_context`` three times running.
SRV1_REFUSED = 28
#: ``scan.json`` in the srv1 envelope: 6144 MiB total, 401 reserved, 17 idle.
SRV1_FREE_MIB = 5727


def test_the_floor_never_admits_a_refused_cell_nor_undercuts_a_loaded_one() -> None:
    """The law carries one allowance and it is walked down from, never up to.

    Over-stating the constant predicts a floor above the true one and costs
    throughput until the walk-down. Under-stating it admits a cell that
    clears every gate and then OOMs at load, which is the one outcome the
    gate exists to prevent. So the law is held to its direction on the cells
    the rig actually ran: the chosen floor is above the refused edge, the
    refused cell is predicted not to fit, and no loaded cell is predicted
    below what the driver measured for it.
    """
    free = SRV1_FREE_MIB * MIB
    placed = _placement(scanned(QWEN36), free, 8, ctx_per_slot=8192 // 8)
    constant = int(placed.vram_gb * GIB) - vramfit.experts_on_card(
        QWEN36, placed.n_cpu_moe
    )
    assert placed.n_cpu_moe > SRV1_REFUSED
    assert vramfit.predict(QWEN36, placed.n_cpu_moe, constant) <= free
    assert vramfit.predict(QWEN36, SRV1_REFUSED, constant) > free, (
        f"ncmoe {SRV1_REFUSED} was refused three times on srv1 and the law "
        f"predicts {vramfit.predict(QWEN36, SRV1_REFUSED, constant) / MIB:.0f} "
        f"MiB against {SRV1_FREE_MIB} free"
    )
    for n_cpu_moe, measured_mib in SRV1_LOADED.items():
        predicted_mib = vramfit.predict(QWEN36, n_cpu_moe, constant) / MIB
        assert predicted_mib >= measured_mib, (
            f"ncmoe {n_cpu_moe} measured {measured_mib} MiB on srv1 and the law "
            f"predicts {predicted_mib:.0f}: under-stating is the OOM direction"
        )


def test_srv1_at_the_default_context_keeps_its_experts_off_a_six_gb_card() -> None:
    """The same file at this module's own defaults still fits srv1, in RAM."""
    sized = fit(
        Scan.of(
            host="srv1",
            vram_mib=SRV1_FREE_MIB,
            ram_gb=14.1,
            disk_free_gb=900.0,
            cores=6,
            threads=6,
        ),
        scanned(QWEN36),
    )
    assert sized.fits, sized.why
    assert "experts in RAM" in sized.why


# --------------------------------------------------------------------------
# slots
# --------------------------------------------------------------------------


def test_the_width_is_the_widest_that_keeps_the_floor_at_one_slot() -> None:
    """Widening by one slot past the derived width moves the floor.

    That is the rule, stated as the two facts it is made of: every width up
    to the derived one keeps the floor the card had at one slot, and the next
    one does not (or the derived width is :data:`MAX_WIDTH`, past which nothing
    on these rigs has been measured).
    """
    free = 11_911 * MIB
    spec = scanned(DEEPSEEK)
    derived = _placement(spec, free)
    at_one = _placement(spec, free, 1)
    assert derived.n_cpu_moe == at_one.n_cpu_moe
    for width in range(1, derived.width + 1):
        assert _placement(spec, free, width).n_cpu_moe == at_one.n_cpu_moe
    if derived.width < MAX_WIDTH:
        assert _placement(spec, free, derived.width + 1).n_cpu_moe > at_one.n_cpu_moe


def test_a_slot_on_a_recurrent_model_is_priced_as_state_not_just_cache() -> None:
    """Qwen3.6 charges 30 recurrent blocks per sequence; deepseek charges none.

    So on one card the recurrent model is narrower for the same expert floor,
    and a per-slot constant fitted on either would be wrong on the other.
    """
    free = 12_288 * MIB
    recurrent = _placement(scanned(QWEN36), free)
    attention = _placement(scanned(DEEPSEEK), free)
    assert vramfit.rs_bytes(QWEN36, n_seq_max=1)["total"] > 0
    assert vramfit.rs_bytes(DEEPSEEK, n_seq_max=1)["total"] == 0
    assert recurrent.width < attention.width


def test_a_written_width_is_honoured_and_its_floor_recomputed() -> None:
    free = 11_911 * MIB
    spec = scanned(DEEPSEEK)
    written = _placement(spec, free, 8)
    derived = _placement(spec, free)
    assert written.width == 8
    assert written.n_cpu_moe > derived.n_cpu_moe
    unit = unit_for(srv2(free_mib=11_911), spec, width=8)
    assert unit.args["--n-cpu-moe"] == str(written.n_cpu_moe)
    assert unit.args["-c"] == str(DEFAULT_CONTEXT * 8)


# --------------------------------------------------------------------------
# what memory is asked to hold
# --------------------------------------------------------------------------


@pytest.mark.parametrize("n_cpu_moe", [4, 8, 12, 20])
def test_ram_tracks_the_offload_rather_than_the_whole_file(n_cpu_moe: int) -> None:
    """Measured RSS on srv2's sweep cells, against the spilled bytes plus the
    runtime intercept. The old ``max(spec.ram_gb, ...)`` claimed 12.3 GiB for
    every one of these; the rig measured 2.56 to 6.64."""
    measured = {4: 2.556, 8: 3.573, 12: 4.587, 20: 6.639}[n_cpu_moe]
    spilled = _host_gb(QWEN36, n_cpu_moe)
    assert spilled == pytest.approx(measured, rel=0.08), (
        f"--n-cpu-moe {n_cpu_moe} should cost about what the sweep recorded "
        f"({measured:.2f} GiB); the arithmetic gives {spilled:.2f}"
    )
    assert spilled > RUNTIME_RESIDENT_GB


def test_nothing_spilled_costs_no_runtime_intercept() -> None:
    assert _host_gb(QWEN36, 0) == 0.0


def test_a_roomy_card_and_a_cramped_one_do_not_claim_the_same_ram() -> None:
    cramped = _placement(scanned(QWEN36), 6 * GIB)
    roomy = _placement(scanned(QWEN36), 11_500 * MIB)
    assert cramped.n_cpu_moe > roomy.n_cpu_moe
    assert cramped.ram_gb > roomy.ram_gb, (
        "spilling more experts should ask more of memory; the old max() against "
        "the whole model weight made both cards claim the same figure"
    )


def test_a_stated_ram_floor_is_still_honoured() -> None:
    """An operator who knows something this module cannot see is not overruled."""
    assert _placement(scanned(QWEN36, ram_gb=40.0), 6 * GIB).ram_gb >= 40.0


# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------


def test_an_moe_without_its_geometry_is_refused_and_told_where_to_scan() -> None:
    sized = fit(srv2(), ModelSpec("m", 1.0, 0.0, 1.0, moe=True))
    assert not sized.fits
    assert "python -m mcgyvr.serving.ggufscan" in sized.why
    assert "models.m.geometry_json" in sized.why


def test_a_stated_size_that_disagrees_with_the_scan_is_refused_naming_both() -> None:
    """Each deviation from a scan requires a new scan.

    8.9 is the capability table's decimal-GB numeral for this file; the scan
    says 8 905 109 984 bytes, which is 8.294 GiB. Two numbers for one file is
    the situation a scan exists to end, so the spec is refused with both in
    the message and the command that produces a third that is not a guess.
    """
    with pytest.raises(UnitError) as refused:
        scanned(DEEPSEEK, disk_gb=8.9)
    message = str(refused.value)
    assert "8.9" in message
    assert "8.294" in message
    assert "re-scan: python -m mcgyvr.serving.ggufscan" in message


def test_a_stated_size_that_is_the_scan_to_two_decimals_is_the_scan() -> None:
    spec = scanned(DEEPSEEK, disk_gb=8.29)
    assert spec.disk_gb == pytest.approx(8_905_109_984 / GIB)


def test_a_geometry_scanned_from_another_file_is_refused() -> None:
    with pytest.raises(UnitError, match="re-scan"):
        ModelSpec("qwen3-coder-30b", 0.0, 0.0, 0.0, geometry=DEEPSEEK)


def test_the_scan_decides_whether_a_model_is_an_moe() -> None:
    """``moe`` is read off the placeable blocks once a geometry is present."""
    assert scanned(DEEPSEEK).moe is True
    assert ModelSpec(
        "deepseek-coder-v2-16b", 0.0, 0.0, 0.0, moe=False, geometry=DEEPSEEK
    ).moe


def test_an_undeclared_sliding_window_split_refuses_naming_the_measurement() -> None:
    """gpt-oss declares a window and no per-layer pattern, so the cache is unsized.

    The split is not derivable from the header and an alternating assumption
    is wrong for two of the three split checkpoints measured. The refusal has
    to say what would answer it -- the engine's own ``llama_kv_cache_iswa``
    lines -- and must never be caught into a default on the way up.
    """
    sized = fit(srv2(), scanned(GPT_OSS))
    assert not sized.fits
    assert "sliding_window_pattern" in sized.why
    assert "llama_kv_cache_iswa" in sized.why
    with pytest.raises(UnitError, match="llama_kv_cache_iswa"):
        unit_for(srv2(), scanned(GPT_OSS))


def test_a_card_that_cannot_hold_the_constant_is_refused_as_a_card() -> None:
    """Nemotron's 23 recurrent blocks alone overflow a 6 GB card at one slot."""
    fixture: dict[str, dict[str, Any]] = json.loads(
        FIXTURES.read_text(encoding="utf-8")
    )
    nemotron = fixture["nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf"]
    sized = fit(srv2(free_mib=6144, ram_gb=64.0), scanned(nemotron))
    assert not sized.fits
    assert "does not fit at any offload" in sized.why


# --------------------------------------------------------------------------
# a dense model with its header is sized by the same law
# --------------------------------------------------------------------------


def test_a_dense_geometry_is_placed_by_the_same_law_at_floor_zero() -> None:
    """No placeable blocks: the walk stops at zero and the width is the cache's.

    Built from deepseek's row with its experts folded into the non-expert
    mass, so every layer still caches and the constant is the whole model.
    """
    dense = {
        **DEEPSEEK,
        "placeable_blocks": [],
        "expert_bytes_by_block": {},
        "bytes_experts": 0,
        "bytes_nonexpert": DEEPSEEK["bytes_total_tensors"],
    }
    spec = scanned(dense)
    assert spec.moe is False
    placed = _placement(spec, 12_288 * MIB)
    assert placed.n_cpu_moe == 0
    assert placed.ram_gb == 0.0
    assert placed.width > 1
    assert placed.vram_gb <= 12.0
    unit = unit_for(srv2(free_mib=12_288), spec)
    assert "--n-cpu-moe" not in unit.args
    assert unit.width.how == "derived"
    assert unit.fit.headroom_gb == vramfit.SCRATCH_AND_CONTEXT_MIB / 1024


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
    assert DEEPSEEK["size_bytes"] == 8_905_109_984
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
    assert config.sources["local"].engine == "vllm"
    # A vLLM unit loads a repository id from the rig's HF cache, so the spec
    # says where that is; without it the unit is refused by name.
    spec = ModelSpec(
        "qwen2.5-coder:7b", 5.0, 0.0, 4.7, hf_cache="/home/someone/.cache/huggingface"
    )
    unit = units_for(config, {"localhost": srv2()}, specs=(spec,))[0]
    assert unit.engine == "vllm"
    assert unit.key.engine == "vllm", "the engine is part of what makes a process"


def test_an_unstated_engine_is_still_llama_cpp() -> None:
    """A config that names no engine is bound exactly as it was before."""
    config = config_for("qwen2.5-coder:7b")
    assert config.sources["local"].engine is None
    spec = ModelSpec("qwen2.5-coder:7b", 5.0, 0.0, 4.7)
    unit = units_for(config, {"localhost": srv2()}, specs=(spec,))[0]
    assert unit.engine == "llama.cpp"


@pytest.fixture
def geometry_file(tmp_path: Path) -> Path:
    where = tmp_path / "deepseek-coder-v2-16b.geometry.json"
    where.write_text(json.dumps(DEEPSEEK), encoding="utf-8")
    return where


def declared(geometry: Path, extra: str = "") -> str:
    return f"models:\n  deepseek-coder-v2-16b:\n    geometry_json: {geometry}\n{extra}"


def test_an_operator_may_serve_a_model_the_table_never_measured(
    geometry_file: Path,
) -> None:
    config = config_for("deepseek-coder-v2-16b", models=declared(geometry_file))
    spec = declared_models(config)["deepseek-coder-v2-16b"]
    assert spec.geometry is not None
    assert spec.disk_gb == pytest.approx(8_905_109_984 / GIB)
    unit = units_for(config, {"localhost": srv2(free_mib=6144)}, specs=())[0]
    assert unit.model == "deepseek-coder-v2-16b"
    assert "--n-cpu-moe" in unit.args, "a scanned geometry should drive the offload"


def test_a_declaration_overrides_the_shipped_table(geometry_file: Path) -> None:
    """Config wins. mcgyvr says what it measured, then does what it was told."""
    shipped = ModelSpec("deepseek-coder-v2-16b", 99.0, 0.0, 99.0)
    config = config_for("deepseek-coder-v2-16b", models=declared(geometry_file))
    unit = units_for(config, {"localhost": srv2()}, specs=(shipped,))[0]
    assert unit.fit.fits, "the 99 GB shipped row should not have been consulted"


def test_a_stated_disk_gb_beside_a_geometry_must_agree_with_it(
    geometry_file: Path,
) -> None:
    """A deviation from the scan is not obeyed and not corrected: it is refused."""
    config = config_for(
        "deepseek-coder-v2-16b", models=declared(geometry_file, "    disk_gb: 8.9\n")
    )
    with pytest.raises(UnitError, match="re-scan"):
        units_for(config, {"localhost": srv2()}, specs=())


def test_a_relative_geometry_json_is_read_beside_the_config(
    geometry_file: Path, tmp_path: Path
) -> None:
    config = config_for(
        "deepseek-coder-v2-16b",
        models=declared(Path(geometry_file.name)),
        path=tmp_path / "mcgyvr.yaml",
    )
    assert declared_models(config)["deepseek-coder-v2-16b"].geometry is not None


def test_a_ggufscan_list_is_read_by_the_row_scanned_from_the_models_file(
    tmp_path: Path,
) -> None:
    listing = tmp_path / "scan.json"
    listing.write_text(json.dumps([QWEN36, DEEPSEEK]), encoding="utf-8")
    assert load_geometry(listing, name="deepseek-coder-v2-16b")["arch"] == "deepseek2"
    assert load_geometry(listing, name="Qwen3.6-35B-A3B-UD-IQ3_XXS")["arch"] == (
        "qwen35moe"
    )
    with pytest.raises(UnitError, match="0 of 2"):
        load_geometry(listing, name="something-never-scanned")
    with pytest.raises(UnitError, match="which model"):
        load_geometry(listing)
    single = tmp_path / "one.json"
    single.write_text(json.dumps([DEEPSEEK]), encoding="utf-8")
    assert load_geometry(single)["arch"] == "deepseek2"


def test_an_error_row_and_a_malformed_file_are_refused_naming_the_path(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text(
        json.dumps([{"file": "/models/moe/x.gguf", "error": "not gguf"}]),
        encoding="utf-8",
    )
    with pytest.raises(UnitError, match=r"broken\.json.*not gguf"):
        load_geometry(broken)
    garbage = tmp_path / "garbage.json"
    garbage.write_text("{not json", encoding="utf-8")
    with pytest.raises(UnitError, match=r"garbage\.json"):
        load_geometry(garbage)
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps({"file": "/models/moe/x.gguf"}), encoding="utf-8")
    with pytest.raises(UnitError, match=r"partial\.json.*size_bytes"):
        load_geometry(partial)
    with pytest.raises(UnitError, match=r"missing\.json"):
        load_geometry(tmp_path / "missing.json")


def test_a_model_nobody_declared_is_refused_with_the_fix_in_the_message() -> None:
    config = config_for("nobody-measured-this")
    with pytest.raises(UnitError, match="models:"):
        units_for(config, {"localhost": srv2()}, specs=())


def test_a_size_must_be_a_number_and_not_a_flag() -> None:
    """`disk_gb: true` and `moe: true` must not pass the same rule."""
    with pytest.raises(ConfigSchemaError, match="expected a number"):
        config_for("m", models="models:\n  m:\n    disk_gb: true\n")


def test_the_retired_geometry_keys_are_unknown_keys() -> None:
    """``blocks`` and ``expert_gb`` were a block count and an averaged expert
    mass; both are read off the geometry now, and a config still stating them
    is a config that has not been re-pointed at a scan."""
    with pytest.raises(ConfigSchemaError, match="blocks"):
        config_for("m", models="models:\n  m:\n    blocks: 40\n")
    with pytest.raises(ConfigSchemaError, match="expert_gb"):
        config_for("m", models="models:\n  m:\n    expert_gb: 10.3\n")
