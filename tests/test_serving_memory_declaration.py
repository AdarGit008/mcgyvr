"""A serving memory declaration is bytes, and the bytes match the declaration.

ADR-0039. ``gpu_memory_utilization = 0.85`` was never decided in this project —
it is local-ai's OOM fix for a 12 GB card, applied unchanged to a 6 GB one — and
the reason it survived is that nothing could see it was wrong. A fraction reads
as a tuning knob. What it actually is, in vLLM's own arithmetic
(``vllm/v1/worker/utils.py::request_memory``), is ``total_memory * util`` with a
hard ``free >= requested`` precondition, so it is a statement about a *card*.
Measured on the rigs 2026-08-22, at ``max_num_seqs 8``, ``max_model_len 8192``:

    srv1  0.85 -> 131,104 KV tokens, 4,916 MiB   reachable: 65,536 tokens
    srv2  0.85 -> 322,304 KV tokens, 10,197 MiB  reachable: 65,536 tokens

2.0x and 4.9x over, and the two entries that differ *only* in ``max_num_seqs``
allocated the same KV cache, because ``max_num_seqs`` does not enter the budget.
The instrument could not distinguish the two instruments it was built to be.

These checks hold the configs to bytes and hold ``_start`` to refusing an entry
that declares neither or both. They are static and cost no rig time: the
measurement is in ADR-0039 and in each entry's own ``_footprint_mib``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
SERVING = REPO / "tools" / "bench" / "serving"
CONFIGS = SERVING / "configs"


def _by_path(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vllm() -> Any:
    return _by_path("serving_vllm_memory", SERVING / "backends" / "vllm.py")


def _vllm_entries() -> list[tuple[Path, dict[str, Any]]]:
    """Every vLLM entry in every serving config, discovered rather than listed.

    A config added tomorrow is covered without editing this file, which is the
    property a hand-written list cannot have.
    """
    found: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(CONFIGS.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for entry in document.get("models") or []:
            if isinstance(entry, dict) and entry.get("backend") == "vllm":
                found.append((path, entry))
    return found


def test_a_vllm_entry_declares_bytes_and_the_bytes_match_its_own_shape() -> None:
    """ADR-0039 rules 1 and 2, over every vLLM entry in the tree."""
    entries = _vllm_entries()
    assert entries, "no vLLM entry was discovered; the sweep found nothing to hold"
    for path, entry in entries:
        where = f"{path.name}:{entry.get('label')}"
        serve = entry.get("serve") or {}
        assert "gpu_memory_utilization" not in serve, (
            f"{where} declares a fraction. A fraction is a statement about one "
            "card: the same 1,792 MiB of KV cache is 0.565 on srv1 and 0.273 on "
            "srv2 (ADR-0039)"
        )
        assert "kv_cache_memory_bytes" in serve, f"{where} declares no KV cache size"
        expected = (
            serve["max_num_seqs"] * serve["max_model_len"] * serve["bytes_per_token"]
        )
        assert serve["kv_cache_memory_bytes"] == expected, (
            f"{where} declares {serve['kv_cache_memory_bytes']} bytes, but its own "
            f"shape ({serve['max_num_seqs']} seqs x {serve['max_model_len']} tokens "
            f"x {serve['bytes_per_token']} B/token) is {expected}. A declared size "
            "that does not follow from the declaration is the config lying about "
            "itself"
        )


def test_every_declared_model_records_how_its_bytes_per_token_was_derived() -> None:
    """ADR-0039 rule 2: the constant carries its derivation, or it is a magic
    number with a longer name. The note must show the arithmetic AND name a
    measurement, because either alone is how 0.85 travelled."""
    for path, entry in _vllm_entries():
        where = f"{path.name}:{entry.get('label')}"
        serve = entry["serve"]
        note = serve.get("_bytes_per_token_note", "")
        assert "head_dim" in note and "layers" in note, (
            f"{where}: the note does not show where bytes_per_token comes from"
        )
        assert "2026-" in note, f"{where}: the note names no measurement date"
        footprint = serve.get("_footprint_mib")
        assert isinstance(footprint, dict) and footprint, (
            f"{where}: no measured footprint. ADR-0039 rule 4 -- the arithmetic "
            "predicts the KV cache and only the card says what the process took"
        )
        assert all(isinstance(v, int) and v > 0 for v in footprint.values()), where


def test_there_is_no_silent_default_and_both_fields_together_are_a_refusal(
    vllm: Any,
) -> None:
    """ADR-0039 rules 1 and 3, against the argument builder itself.

    Both directions, so the check can be shown to reject: a bare shape must
    raise rather than fall back, and the two fields together must raise rather
    than pick a winner. vLLM's own precedence silently discards the fraction,
    so honouring it here would record a fraction that never applied.
    """
    shape = {"max_model_len": 8192, "max_num_seqs": 8}

    with pytest.raises(vllm.contract.NotCleanError) as bare:
        vllm._memory_args(dict(shape))
    assert "neither" in str(bare.value) and "0.85" not in str(bare.value)

    with pytest.raises(vllm.contract.NotCleanError) as both:
        vllm._memory_args(
            {
                **shape,
                "kv_cache_memory_bytes": 1879048192,
                "gpu_memory_utilization": 0.85,
            }
        )
    assert "exclusive" in str(both.value)

    assert vllm._memory_args({**shape, "kv_cache_memory_bytes": 1879048192}) == [
        "--kv-cache-memory-bytes",
        "1879048192",
    ]
    # Rule 5: a fraction is un-defaulted, not banned.
    assert vllm._memory_args({**shape, "gpu_memory_utilization": 0.5}) == [
        "--gpu-memory-utilization",
        "0.5",
    ]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "2026-08-22: decided — ADR-0039 rule 1 reaches calibrate.py's two inline "
        "serve blocks (the width sweep and the sleep arm), and converting them "
        "re-baselines every vLLM cell they produced. That is #329's arm, which "
        "already owes a width-16 measurement, and it lands there rather than "
        "here: at 0.85 srv1 gets 131,088 KV tokens against the 131,072 width 16 "
        "needs (a 16-token margin) while srv2 gets 322,304, so the two arms of "
        "that contrast are 2.46x apart in KV cache from one declared setting"
    ),
)
def test_the_calibration_probes_declare_bytes_too() -> None:
    """The two `serve` blocks built inside `calibrate.py` rather than in a config.

    A config-only sweep would report green while the code that actually launches
    the campaign's vLLM cells still carries the withdrawn fraction — the same
    where-it-is-run defect this lane has now hit four times.
    """
    source = (SERVING / "calibrate.py").read_text(encoding="utf-8")
    assert "gpu_memory_utilization" not in source, (
        "calibrate.py still builds a serve block around a fraction"
    )


# --- #354: a declaration the card cannot hold -------------------------------
#
# ADR-0039's rule is `max_num_seqs x max_model_len x bytes_per_token`, and the
# three cells that refused on 2026-08-23 each computed it EXACTLY right. What
# was missing is that a byte declaration travels across cards and travelling is
# not the same as fitting: every vLLM figure this project held came from the
# 1.5B, 28 layers x 2 KV heads, and Qwen3-4B is 36 x 8 -- four times wider per
# layer. Nothing refused the configuration until vLLM did, three minutes and one
# cell later. These checks are static and cost no rig time; their content is
# phase 0's own 25-cell campaign, which produced both the failures and the
# footprints that let a pre-check exist at all.

PHASE0 = REPO / "records" / "evidence" / "2026-08-23-phase0-footprint"
REFIT = REPO / "records" / "evidence" / "2026-08-23-phase0-refit"

#: Free on an EMPTY card: nameplate minus the 1 MiB both rigs read at rest, as
#: `footprints.csv`'s `card_mib_before` column records for all 25 cells.
PHASE0_FREE_MIB = {"srv1": 6144 - 1, "srv2": 12288 - 1}

#: Each rig's driver/firmware reserve, MEASURED 2026-08-30 via
#: `nvidia-smi --query-gpu=memory.reserved`: the GSP firmware carveout, which
#: belongs to no process and so appears in neither `memory.used` nor
#: `memory.free`. `free_mib` returns `total - used` and therefore overstates
#: what a process can allocate by exactly this much.
RESERVED_MIB = {"srv1": 401, "srv2": 380}

#: What each card can actually hand a process at rest: nameplate, less the
#: 17 MiB both rigs read as `used` with nothing running, less the reserve.
ALLOCATABLE_MIB = {
    "srv1": 6144 - 17 - RESERVED_MIB["srv1"],
    "srv2": 12288 - 17 - RESERVED_MIB["srv2"],
}

#: The weights, in bytes, for the three cells that never reached a footprint --
#: from the engine's OWN words in `engine-refusals/`, the `Model loading took
#: X GiB` line it prints before it touches the KV cache. Qwen3-4B reported 2.5
#: GiB on both rigs independently, which is why one figure serves two cells.
PHASE0_WEIGHTS_BYTES = {
    "thewimo/Qwen3-4B-AWQ": int(2.5 * 1024**3),
    "Qwen/Qwen2.5-Coder-14B-Instruct-AWQ": int(9.38 * 1024**3),
}

#: The 1.5B's weights, measured, from ADR-0039's table -- stable across all
#: eight of its rows on both rigs. Used only to solve for the two rigs' non-KV,
#: non-weights residue below.
WEIGHTS_1_5B_MIB = 1126

#: Each rig's non-weights, non-KV residue as phase 0's 1.5B rows give it:
#: `footprint - kv - weights`. Used only to DERIVE the weights of the 3B and 7B
#: cells, whose own weights line was never captured -- those two set the
#: phase-0 half of the ceiling and nothing else. The refit measures the residue
#: directly and does not need this.
PHASE0_RESIDUE_MIB = {"srv1": 3130 - 1792 - 1126, "srv2": 3183 - 1792 - 1126}


def _phase0_cells() -> list[dict[str, Any]]:
    """Phase 0's seven vLLM cells: the declaration it ran, and what the card did.

    Read from the campaign's own config and its parsed CSV rather than typed
    here, so a check about a measurement cannot drift from the measurement.
    """
    config = json.loads((PHASE0 / "config.json").read_text(encoding="utf-8"))
    serves = {
        (entry["hosts"][0], entry["id"]): entry["serve"]
        for entry in config["models"]
        if entry.get("backend") == "vllm"
    }
    cells: list[dict[str, Any]] = []
    for line in (
        (PHASE0 / "footprints.csv").read_text(encoding="utf-8").splitlines()[1:]
    ):
        # `csv` rather than split(","): the refusal column contains commas.
        import csv as _csv

        row = next(_csv.reader([line]))
        if row[1] != "vllm":
            continue
        host, model = row[0], row[2]
        cells.append(
            {
                "host": host,
                "model": model,
                "serve": serves[(host, model)],
                "loaded": row[10] == "ok",
                "footprint_mib": int(row[4]) if row[4] else None,
            }
        )
    return cells


def test_the_phase0_cells_are_all_seven_and_three_of_them_refused() -> None:
    """The fixture above is the campaign, not a sample of it.

    Without this, a parse that silently dropped rows would make every check
    below pass over whatever survived -- the shape session 22's own mutation
    sweep caught twice, a check asserting a property it never exercised.
    """
    cells = _phase0_cells()
    assert len(cells) == 7, f"phase 0 ran 7 vLLM cells, parsed {len(cells)}"
    refused = [c for c in cells if not c["loaded"]]
    assert len(refused) == 3, f"3 cells refused, parsed {len(refused)}"
    assert {(c["host"], c["model"].split("/")[-1]) for c in refused} == {
        ("srv1", "Qwen3-4B-AWQ"),
        ("srv2", "Qwen3-4B-AWQ"),
        ("srv2", "Qwen2.5-Coder-14B-Instruct-AWQ"),
    }


def test_the_pre_check_agrees_with_the_card_on_every_phase_0_cell(
    vllm: Any, monkeypatch: Any
) -> None:
    """Seven cells, seven verdicts, and the rule must match the card on all of them.

    This is the check with the content. A pre-check that refused everything
    would be safe and useless; one that refused nothing is what shipped. The
    campaign is both controls at once -- four cells that loaded and must be
    admitted, three that died in `_allocate_kv_cache` and must be refused --
    and it is the only evidence in the tree that can separate them.

    A cell that loaded is judged on its MEASURED footprint, because a footprint
    the card produced needs no model of why it fits. A cell that never loaded
    has no footprint by definition, so it is judged on the predicted path: its
    weights, from the engine's own log, plus its declared KV, plus the residue.
    """
    # The measured branch reads the card's reserve, and this check is static by
    # construction -- its content is a campaign already on disk. Left unstubbed
    # it would ssh to a live rig, which passes on a machine that has one and
    # hangs on a machine that does not.
    monkeypatch.setattr(vllm, "reserved_mib", lambda host: RESERVED_MIB[host])
    for cell in _phase0_cells():
        serve = dict(cell["serve"])
        if cell["loaded"]:
            serve["_footprint_mib"] = {cell["host"]: cell["footprint_mib"]}
        else:
            serve["weights_bytes"] = PHASE0_WEIGHTS_BYTES[cell["model"]]
        where = f"{cell['host']} / {cell['model']}"
        try:
            vllm.declaration_fits(
                cell["host"], cell["model"], serve, PHASE0_FREE_MIB[cell["host"]]
            )
            refused = None
        except Exception as error:  # NotCleanError, by path-import
            refused = str(error)
        if cell["loaded"]:
            assert refused is None, (
                f"{where} loaded on the card, and the rule refused it: {refused}"
            )
        else:
            assert refused is not None, (
                f"{where} died in _allocate_kv_cache on an empty card, and the "
                "rule admitted it -- which is the defect #354 exists to close"
            )
            assert "Nothing was measured" in refused


def _refit_cells() -> list[dict[str, Any]]:
    """The three cells phase 0 could not measure, re-declared so they fit.

    Same models, same cards, a shorter `max_model_len` — the owner's choice of
    2026-08-23 between the two ways out. They are the only cells in the tree
    that show what a vLLM process holds BESIDES weights and KV at more than one
    model size, which is what makes the residue below a measurement.
    """
    import csv as _csv

    config = json.loads((REFIT / "config.json").read_text(encoding="utf-8"))
    serves = {
        (entry["hosts"][0], entry["id"]): entry["serve"] for entry in config["models"]
    }
    rows = _csv.DictReader(
        (REFIT / "footprints.csv").read_text(encoding="utf-8").splitlines()
    )
    return [
        {
            "host": row["host"],
            "model": row["model"],
            "serve": serves[(row["host"], row["model"])],
            "footprint_mib": int(row["card_mib_after_load"]),
        }
        for row in rows
        if row["engine"] == "vllm" and row["outcome"] == "ok"
    ]


def test_the_refit_measured_all_three_cells_phase_0_could_not() -> None:
    """#354's last box: the footprint table is complete rather than 22 of 25.

    Three cells, all `ok`. If this shrinks, every figure derived from the
    residue below is derived from fewer cells than it claims.
    """
    cells = _refit_cells()
    assert len(cells) == 3, f"the refit measured 3 cells, parsed {len(cells)}"
    assert {(c["host"], c["model"].split("/")[-1]) for c in cells} == {
        ("srv1", "Qwen3-4B-AWQ"),
        ("srv2", "Qwen3-4B-AWQ"),
        ("srv2", "Qwen2.5-Coder-14B-Instruct-AWQ"),
    }


def test_the_overhead_constant_is_derived_from_the_residue_and_not_chosen(
    vllm: Any,
) -> None:
    """733 MiB is a reading plus a block, and the check re-derives both.

    The first version of this constant was 910, assembled from ADR-0039's terms
    — driver context, activation, non-torch, one allocator block. That sum
    double-counts: `nvidia-smi`'s card figure already contains the driver's
    reserve and the process's own context, so two of the four terms were being
    charged twice, and it over-predicted every one of the three refit
    footprints by 433 to 573 MiB. Assembling a constant from parts is what let
    that go unnoticed; measuring the whole residue is what caught it.

    The residue is `card_mib_after_load - weights - declared_kv`, and the
    constant is the largest one seen plus the block a launch must still be able
    to take. Both halves are re-read here, so a cell with a larger residue
    fails this rather than silently making the constant wrong.
    """
    residues = {}
    for cell in _refit_cells():
        serve = cell["serve"]
        weights = vllm._mib(serve["weights_bytes"])
        kv = vllm._mib(serve["kv_cache_memory_bytes"])
        residues[f"{cell['host']}/{cell['model']}"] = (
            cell["footprint_mib"] - weights - kv
        )

    assert min(residues.values()) >= 300, residues
    assert (
        max(residues.values()) + vllm.ALLOCATOR_BLOCK_MIB == vllm.NON_KV_OVERHEAD_MIB
    ), (
        f"the residues are {residues}; the constant is derived as the largest "
        f"of them plus one {vllm.ALLOCATOR_BLOCK_MIB} MiB block, and "
        f"{vllm.NON_KV_OVERHEAD_MIB} is not that"
    )


def test_the_constant_lands_inside_the_window_every_measured_cell_allows(
    vllm: Any,
) -> None:
    """Ten cells, one interval, and the derived value has to land in it.

    * The **floor** is set by the cells that must be REFUSED: the residue has to
      be large enough that srv2's Qwen3-4B at the campaign's original
      declaration — which missed by exactly one allocator block — does not
      launch. `free - weights - kv` there is 511 MiB.
    * The **ceiling** is set by every cell that must be ADMITTED, and the
      tightest is the refit's 14B at 1,145 MiB. Phase 0 alone allowed up to
      1,793; measuring three more cells narrowed it, which is the direction
      evidence is supposed to move a bound.

    The window is a consequence of the verdicts, not a target: nothing here
    tunes the constant to sit inside it. If a future cell narrows the window
    past the derived value, this fails and the two have to be reconciled
    against the cards rather than against each other.
    """
    free = PHASE0_FREE_MIB
    floor, ceiling = [], []
    for cell in _phase0_cells():
        kv = vllm._mib(cell["serve"]["kv_cache_memory_bytes"])
        if cell["loaded"]:
            residue = cell["footprint_mib"] - kv - PHASE0_RESIDUE_MIB[cell["host"]]
            ceiling.append(free[cell["host"]] - residue - kv)
        else:
            weights = vllm._mib(PHASE0_WEIGHTS_BYTES[cell["model"]])
            floor.append(free[cell["host"]] - weights - kv)
    for cell in _refit_cells():
        serve = cell["serve"]
        ceiling.append(
            free[cell["host"]]
            - vllm._mib(serve["weights_bytes"])
            - vllm._mib(serve["kv_cache_memory_bytes"])
        )

    assert (max(floor), min(ceiling)) == (511, 1145), (
        f"the window moved to ({max(floor)}, {min(ceiling)}); the constant's "
        "docstring and ADR-0039's amendment both quote it and must be re-read"
    )
    assert max(floor) < vllm.NON_KV_OVERHEAD_MIB < min(ceiling)


def test_the_refusal_names_both_ways_out_and_takes_neither(vllm: Any) -> None:
    """It prints the two figures that would fit and applies neither of them.

    Naming one is how a run comes to measure a configuration nobody chose --
    the same failure `_memory_args` already refuses when an entry declares both
    memory fields and vLLM silently keeps one. The entry is not mutated either:
    a launcher that repaired the config in place would leave the record saying
    one thing and the run doing another.
    """
    serve = {
        "max_model_len": 8192,
        "max_num_seqs": 8,
        "kv_cache_memory_bytes": 9663676416,
        "bytes_per_token": 147456,
        "weights_bytes": int(2.5 * 1024**3),
    }
    before = json.dumps(serve, sort_keys=True)
    with pytest.raises(Exception) as raised:
        vllm.declaration_fits("srv1", "thewimo/Qwen3-4B-AWQ", serve, 6143)
    message = str(raised.value)
    assert json.dumps(serve, sort_keys=True) == before, "the refusal edited the entry"

    for term in ("weights 2,560 MiB", "declared KV 9,216 MiB", "733 MiB", "6,143 MiB"):
        assert term in message, f"the arithmetic does not name {term!r}"
    assert "Short by 6,366 MiB" in message
    # Both ways out, with a figure each, and no instruction to take either.
    assert "max_num_seqs 2 at the declared max_model_len 8,192" in message
    assert "max_model_len 2,533 at the declared max_num_seqs 8" in message
    assert "picks neither" in message


def test_a_declaration_is_checked_after_the_release_and_before_the_launch(
    vllm: Any,
) -> None:
    """Order, not existence: both neighbours of the call site are the point.

    AFTER `release`, because the free memory a declaration is measured against
    is the memory it will get, and the previous engine has not let go until
    then -- checking first would refuse a fitting cell whose card was still
    held. BEFORE the argument list, because the whole value of the check is not
    spending the launch. A check that ran at either edge would pass a test that
    only asserted it was called.
    """
    source = (SERVING / "backends" / "vllm.py").read_text(encoding="utf-8")
    body = source[source.index("def _start(") :]
    body = body[: body.index("\n    args = [")]
    assert "release(host)" in body, "the fit check is no longer inside _start"
    assert body.index("release(host)") < body.index("declaration_fits("), (
        "declaration_fits runs before release(host): it would read the free "
        "memory of a card the previous engine is still holding"
    )
    # And the two commands that actually start a server both come after it.
    start = source[source.index("def _start(") :]
    start = start[: start.index("\ndef ", 1)]
    at = start.index("declaration_fits(host")
    for launch in ("nohup vllm serve", "docker run -d --name mcgyvr-vllm"):
        assert at < start.index(launch), (
            f"{launch!r} is built before the declaration is checked, so the "
            "refusal would come after the rig time it exists to save"
        )


def test_every_vllm_entry_can_be_checked_against_a_card() -> None:
    """An entry that declares bytes must give the pre-check something to work with.

    Either a measured `_footprint_mib` for the host it targets, or
    `weights_bytes` with a note showing where the figure came from -- ADR-0039
    rule 2's idiom, which makes a model whose constant is unrecorded a refusal
    rather than a guess. Without one of the two, `declaration_fits` refuses and
    the entry is undispatchable, so this fails at check time instead of on a rig.
    """
    for path, entry in _vllm_entries():
        serve = entry["serve"]
        if serve.get("kv_cache_memory_bytes") is None:
            continue
        where = f"{path.name}:{entry.get('label', entry.get('id'))}"
        assert serve.get("weights_bytes") or serve.get("_footprint_mib"), (
            f"{where} declares KV bytes and gives the pre-check nothing to "
            "weigh them against (#354)"
        )
        if serve.get("weights_bytes"):
            note = serve.get("_weights_bytes_note", "")
            assert "MEASURED" in note and "Model loading took" in note, (
                f"{where}: the note does not show where weights_bytes came from"
            )


# --- the reserve: the measured branch's own ceiling -------------------------
#
# `free_mib` returns `total - used`. That is not what a process can allocate:
# the card also carries a driver/firmware reserve belonging to no process, so
# the identity is `total = reserved + used + free`. Measured 2026-08-30 --
# 401 MiB on srv1, 380 on srv2 -- and confirmed from the other side by PyTorch,
# which called srv2's 12,288 MiB card a `total capacity of 11.63 GiB` in the
# OOM that prompted this: 12,288 less 380, exactly.
#
# The predicted branch is already right against `total - used`, because
# NON_KV_OVERHEAD_MIB was FITTED as a residue against that figure and carries
# the reserve inside itself. The measured branch has no such constant. These
# checks pin both halves: that the measured ceiling drops by the reserve, and
# that the predicted one does not -- so the double-count cannot be reintroduced
# by a later reader who notices the two branches disagree and "fixes" it.


def test_the_measured_branch_refuses_a_footprint_inside_the_reserve_window(
    vllm: Any, monkeypatch: Any
) -> None:
    """srv1's window is 5,726..6,127 MiB, and every cell in it must be refused.

    Both edges, because a check that only proved the refusal would pass on a
    branch that refused everything. The admitted case sits one MiB under the
    real ceiling and the refused case one MiB over it, so the boundary itself
    is asserted rather than a value comfortably either side of it.
    """
    monkeypatch.setattr(vllm, "reserved_mib", lambda host: RESERVED_MIB[host])
    free = 6144 - 17  # what `free_mib` reports: total - used
    ceiling = ALLOCATABLE_MIB["srv1"]  # 5,726 -- what the card can actually give
    assert free - ceiling == RESERVED_MIB["srv1"]

    def verdict(footprint: int) -> str | None:
        serve = {
            "kv_cache_memory_bytes": 1879048192,
            "_footprint_mib": {"srv1": footprint},
        }
        try:
            vllm.declaration_fits("srv1", "model", serve, free)
            return None
        except Exception as error:
            return str(error)

    assert verdict(ceiling) is None, "a footprint at the real ceiling was refused"
    assert verdict(ceiling - 1) is None

    for inside in (ceiling + 1, (ceiling + free) // 2, free):
        refused = verdict(inside)
        assert refused is not None, (
            f"footprint {inside:,} MiB sits in the reserve window and was "
            "admitted -- it would die in torch.OutOfMemoryError at load"
        )
        # The refusal states the term it subtracted, not just the shortfall.
        assert f"{RESERVED_MIB['srv1']:,} MiB this card reserves" in refused
        assert "GSP firmware" in refused
        assert "Nothing was measured" in refused


def test_the_predicted_branch_does_not_subtract_the_reserve(
    vllm: Any, monkeypatch: Any
) -> None:
    """The double-count, pinned shut from both directions.

    NON_KV_OVERHEAD_MIB is a residue fitted against `total - used`, so it
    already carries the reserve. Subtracting the reserve again would refuse
    cells that fit. Two assertions: the predicted path never asks for the
    reserve at all, and a declaration sitting between the two ceilings is
    ADMITTED there -- the opposite verdict to the measured branch above, on the
    same numbers, which is the whole reason the branches are kept apart.
    """
    asked: list[str] = []
    monkeypatch.setattr(
        vllm, "reserved_mib", lambda host: asked.append(host) or RESERVED_MIB[host]
    )
    free = 6144 - 17
    # Weights + KV + 733 lands at 5,898: inside srv1's reserve window (5,726
    # ..6,127), the exact band the measured branch refuses.
    serve = {
        "max_model_len": 11264,
        "max_num_seqs": 8,
        "kv_cache_memory_bytes": 8 * 11264 * 36864,
        "bytes_per_token": 36864,
        "weights_bytes": int(1.95 * 1024**3),
    }
    predicted = (
        vllm._mib(serve["weights_bytes"])
        + vllm._mib(serve["kv_cache_memory_bytes"])
        + vllm.NON_KV_OVERHEAD_MIB
    )
    assert ALLOCATABLE_MIB["srv1"] < predicted <= free, (
        "this fixture no longer sits between the two ceilings, so it cannot "
        "tell the branches apart"
    )
    vllm.declaration_fits("srv1", "model", serve, free)
    assert asked == [], (
        "the predicted branch read the card's reserve. NON_KV_OVERHEAD_MIB is "
        "fitted against `total - used` and already contains it; subtracting it "
        "here too charges it twice and refuses cells that fit"
    )


def test_the_predicted_verdicts_are_unchanged_across_the_fitted_window(
    vllm: Any, monkeypatch: Any
) -> None:
    """733 is derived, not chosen -- and the window admits no verdict change.

    The floor is EXCLUSIVE. `test_the_constant_lands_inside_the_window...`
    derives it as `free - weights - kv` = 511 for srv2's Qwen3-4B, the value at
    which that cell's requirement equals free exactly and so is admitted; the
    smallest constant that still refuses it is 512. The window this sweeps is
    therefore (511, 1,145].

    If an edit to the predicted branch ever made a verdict depend on where
    inside that window the constant sits, the constant would have stopped being
    a residue and become a tuning knob.
    """
    monkeypatch.setattr(vllm, "reserved_mib", lambda host: RESERVED_MIB[host])
    baseline: dict[tuple[str, str], bool] = {}
    for overhead in (512, 733, 1145):
        monkeypatch.setattr(vllm, "NON_KV_OVERHEAD_MIB", overhead)
        for cell in _phase0_cells():
            serve = dict(cell["serve"])
            if cell["loaded"]:
                serve["_footprint_mib"] = {cell["host"]: cell["footprint_mib"]}
            else:
                serve["weights_bytes"] = PHASE0_WEIGHTS_BYTES[cell["model"]]
            key = (cell["host"], cell["model"])
            try:
                vllm.declaration_fits(
                    cell["host"], cell["model"], serve, PHASE0_FREE_MIB[cell["host"]]
                )
                admitted = True
            except Exception:
                admitted = False
            assert admitted is cell["loaded"], (
                f"{key} disagrees with the card at overhead {overhead}"
            )
            baseline.setdefault(key, admitted)
            assert baseline[key] is admitted, (
                f"{key} changed verdict at overhead {overhead}: the constant's "
                "stated 511..1,145 window no longer holds"
            )


def test_an_unreported_reserve_refuses_rather_than_assuming_zero(
    vllm: Any, monkeypatch: Any
) -> None:
    """A driver that withholds the field must stop the run, not be read as zero.

    Assuming zero is precisely the optimism this whole fix removes: it restores
    `total - used` as the measured branch's ceiling and re-opens the window.
    """
    monkeypatch.setattr(vllm, "reserved_mib", lambda host: None)
    serve = {
        "kv_cache_memory_bytes": 1879048192,
        "_footprint_mib": {"srv1": 3130},  # comfortably fitting, if it were checked
    }
    with pytest.raises(vllm.contract.NotCleanError) as raised:
        vllm.declaration_fits("srv1", "model", serve, 6144 - 17)
    message = str(raised.value)
    assert "did not report" in message
    assert "NOT assumed to be zero" in message
    assert "memory.reserved" in message
    assert "Nothing was measured" in message


def test_every_declared_footprint_fits_its_host_allocatable_ceiling() -> None:
    """The configs' own numbers, against what the card can actually hand over.

    A footprint is only evidence that a cell fits if it fits the ceiling the
    card enforces, not the one `total - used` advertises. This fails on an edit
    that inflates a declared footprint past that line, which is the shape of
    mistake a hand-copied reading makes.
    """
    seen = 0
    for path in sorted(CONFIGS.glob("srv-vllm-n1248-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for entry in document.get("models") or []:
            footprints = (entry.get("serve") or {}).get("_footprint_mib") or {}
            assert footprints, f"{path.name}:{entry.get('label')} declares none"
            for host, mib in footprints.items():
                ceiling = ALLOCATABLE_MIB[host]
                assert 0 < mib <= ceiling, (
                    f"{path.name}:{entry.get('label')} declares {mib:,} MiB on "
                    f"{host}, whose card can allocate {ceiling:,} MiB "
                    f"({RESERVED_MIB[host]:,} of the nameplate is driver and "
                    "GSP firmware reserve). A footprint above that line was "
                    "never observed on this card"
                )
                seen += 1
    assert seen >= 7, f"only {seen} declared footprints checked"
