"""What a card actually has, and what the 2026-08-30 run recorded about it.

Four findings from that day are pinned here as assertions rather than prose,
because each was reached by measurement and each was got WRONG first by
reasoning:

1. **A card has four buckets, not three.** ``total = reserved + used + free``.
   The reserve is GSP firmware -- the GPU System Processor, default on Turing
   and later, which is both rigs -- and it is held from driver load until
   reboot. Confirmed on the hardware: ``nvidia-smi -q -d MEMORY`` reports
   ``Reserved 401 MiB`` on srv1 (GSP 580.173.02) and ``380 MiB`` on srv2
   (GSP 595.84), while ``memory.used`` reads 17 MiB on both with nothing
   running. It is a fixed carveout and does not scale with capacity, so it is
   regressive: 6.5% of srv1's 6 GB card against 3.1% of srv2's 12 GB.

2. **CUDA cannot see the reserve at all.** srv2's OOM message reports "GPU 0 has
   a total capacity of 11.63 GiB" for a 12,288 MiB card -- exactly
   ``12288 - 380``. So a declaration weighed against ``memory.total`` is weighed
   against memory no process can obtain.

3. **``--cpu-offload-gb`` is not a discount on this engine.** Three launches of
   Qwen2.5-Coder-14B-Instruct-AWQ on srv2 differing only in the budget -- 0, 4
   and 6 GiB -- each reported ``Model loading took 9.38 GiB`` and each OOMed
   before startup. A gate that subtracted the declared budget from the weights
   was written and removed the same day: it converted a correct refusal into an
   admission, and the cell it admitted died at load.

4. **One predicted overhead constant cannot serve both hosts.** The residue a
   cell actually leaves -- ``footprint - weights - declared KV`` -- measured
   180-374 MiB on srv1 and 715-791 MiB on srv2. CUDA graph capture accounts for
   only 70 MiB of that gap, measured by launching one 3B on srv2 with and
   against ``--enforce-eager``; the rest is the attention backend (srv1 falls
   back to TRITON on CC 7.5, srv2 runs FLASHINFER). This is why every entry in
   that run declares a MEASURED ``_footprint_mib`` and is weighed by its reading
   instead of by the prediction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "tools" / "bench" / "serving" / "configs"
EVIDENCE = REPO / "records" / "evidence" / "serving-2026-08-30"

#: MEASURED 2026-08-30 by ``nvidia-smi --query-gpu=memory.total,memory.reserved``
#: on each rig. The reserve is what the GSP firmware holds; the ceiling is what
#: a process can actually reach, and it is the figure a declaration must clear.
CARD = {
    "srv1": {"total": 6144, "reserved": 401},
    "srv2": {"total": 12288, "reserved": 380},
}

#: The grid this run exists to measure. A cell that reports anything else did
#: not measure what was asked for.
LEVELS = [1, 2, 4, 8]


def ceiling(host: str) -> int:
    """What a process on ``host`` can actually obtain, in MiB."""
    return CARD[host]["total"] - CARD[host]["reserved"]


def _barren_levels(measured: dict[str, Any]) -> list[dict[str, Any]]:
    """`run.barren_levels`, imported by path so this test does not pin a layout.

    A level states no rate if nothing succeeded (`ok` is 0) or if replies
    arrived and none could be counted (`counted` is 0).
    """
    return [
        level
        for level in (measured.get("levels") or [])
        if isinstance(level, dict) and not (level.get("ok") and level.get("counted"))
    ]


def _run_configs() -> list[tuple[Path, dict[str, Any]]]:
    """The 2026-08-30 vLLM configs, one per host."""
    found = []
    for path in sorted(CONFIGS.glob("srv-vllm-n1248-*.json")):
        found.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return found


def _vllm_entries() -> list[tuple[Path, str, dict[str, Any], dict[str, Any]]]:
    """``(path, host, entry, serve)`` for every vLLM entry in those configs."""
    out = []
    for path, document in _run_configs():
        for entry in document.get("models") or []:
            if entry.get("backend") != "vllm":
                continue
            hosts = entry.get("hosts") or document.get("hosts") or []
            for host in hosts:
                out.append((path, host, entry, entry.get("serve") or {}))
    return out


def test_the_configs_this_pins_are_present() -> None:
    """The vacuity guard. Every assertion below reads these files, so a rename
    that emptied them would turn this module green while checking nothing."""
    configs = _run_configs()
    assert configs, f"no srv-vllm-n1248-*.json under {CONFIGS}"
    entries = _vllm_entries()
    assert entries, "configs carry no vLLM entry, so nothing below is asserted"


@pytest.mark.parametrize("host", sorted(CARD))
def test_the_reserve_is_neither_used_nor_free(host: str) -> None:
    """Finding 1, as arithmetic: the ceiling is strictly below total, and the
    gap is the reserve. If someone edits CARD to make reserved 0 -- the
    assumption that produced the wrong answer twice on 2026-08-30 -- the
    ceiling stops being a distinct figure and this fails."""
    card = CARD[host]
    assert card["reserved"] > 0, (
        f"{host}: a zero reserve is the assumption `total - used` encodes, and "
        "it was measured false on this hardware"
    )
    assert ceiling(host) == card["total"] - card["reserved"]
    assert ceiling(host) < card["total"]


def test_the_reserve_does_not_scale_with_the_card() -> None:
    """Finding 1's consequence. srv2 has twice srv1's memory and a SMALLER
    reserve, so the carveout is fixed rather than proportional -- which is what
    makes it hurt the 6 GB card twice as hard. A future rig whose reserve
    tracked capacity would break this, and should: it would mean the mechanism
    is not the one documented above."""
    assert CARD["srv2"]["total"] > CARD["srv1"]["total"]
    assert CARD["srv2"]["reserved"] < CARD["srv1"]["reserved"]
    srv1_share = CARD["srv1"]["reserved"] / CARD["srv1"]["total"]
    srv2_share = CARD["srv2"]["reserved"] / CARD["srv2"]["total"]
    assert srv1_share > 2 * srv2_share, (
        "the reserve is regressive by roughly 2x on these two cards; if it is "
        "not, the fixed-carveout reading is wrong"
    )


def test_every_declared_footprint_clears_its_host_ceiling() -> None:
    """Finding 2, against the declarations themselves. A footprint is a
    MEASURED reading, so it is exact and carries no safety margin -- which
    means it must be checked against what the card can actually give, not
    against ``total``. An entry inflated past the ceiling by a later edit fails
    here instead of at load."""
    for path, host, entry, serve in _vllm_entries():
        where = f"{path.name}:{entry.get('label')}"
        footprint = (serve.get("_footprint_mib") or {}).get(host)
        assert isinstance(footprint, int) and footprint > 0, (
            f"{where}: declares no measured footprint for {host}; the "
            "prediction path cannot stand in, because its constant was fitted "
            "on one host's residue and the two hosts differ by ~400 MiB"
        )
        assert footprint < ceiling(host), (
            f"{where}: footprint {footprint:,} MiB does not clear {host}'s "
            f"reachable ceiling of {ceiling(host):,} MiB "
            f"({CARD[host]['total']:,} total less {CARD[host]['reserved']:,} "
            "reserved). It would be admitted by any check reading `total` and "
            "would then die at load."
        )


def test_a_footprint_is_never_less_than_what_it_must_hold() -> None:
    """A transcription guard. Whatever else a process holds, it holds its
    weights and its declared KV cache, so the reading must exceed their sum.
    A footprint copied from the wrong row fails here."""
    for path, host, entry, serve in _vllm_entries():
        where = f"{path.name}:{entry.get('label')}"
        footprint = (serve.get("_footprint_mib") or {}).get(host)
        weights = serve.get("weights_bytes")
        kv = serve.get("kv_cache_memory_bytes")
        if not (footprint and weights and kv):
            continue
        floor = int(weights) // (1024 * 1024) + int(kv) // (1024 * 1024)
        assert footprint > floor, (
            f"{where}: footprint {footprint:,} MiB is below its own weights + "
            f"declared KV ({floor:,} MiB), which is impossible -- the process "
            "holds at least those two"
        )


def test_no_entry_declares_cpu_offload_as_though_it_reduced_the_card() -> None:
    """Finding 3, as a guard against reintroduction. Measured on srv2: the
    budget does not move ``Model loading took``, and the cell OOMs at 0, 4 and
    6 GiB alike. An entry carrying the flag would be declaring a discount this
    engine does not give, and the gate would weigh it at full weight anyway --
    so the flag can only mislead a reader about why the cell was refused."""
    for path, _host, entry, serve in _vllm_entries():
        flags = [str(f) for f in (serve.get("flags") or [])]
        offenders = [f for f in flags if f.startswith("--cpu-offload-gb")]
        assert not offenders, (
            f"{path.name}:{entry.get('label')} declares {offenders}. Measured "
            "inert on this engine 2026-08-30 for an AWQ checkpoint: three "
            "launches at 0/4/6 GiB each loaded 9.38 GiB and each OOMed. If a "
            "cell ever demonstrates the flag moving weights off the card, "
            "record that measurement and change this check with it."
        )


def test_a_refused_cell_is_recorded_rather_than_deleted() -> None:
    """Two cells cannot launch: srv1's 7B against a 6 GB card, and srv2's 14B
    which OOMs in every configuration tried. Both are RESULTS -- the first is
    the run's own success criterion #4 -- so neither may vanish silently. They
    are absent from `models` because the repo requires a measured footprint of
    every declared entry and a cell that never starts has none; the reason
    lives in `_refused` instead."""
    for path, document in _run_configs():
        refused = document.get("_refused") or {}
        assert refused, (
            f"{path.name}: declares no `_refused`. Both hosts had a cell that "
            "could not launch on 2026-08-30; a config recording none has lost "
            "the refusal rather than fixed it."
        )
        labels = {entry.get("label") for entry in document.get("models") or []}
        for label, reason in refused.items():
            assert label not in labels, (
                f"{path.name}: {label} is both refused and declared"
            )
            assert len(str(reason)) > 40, (
                f"{path.name}:{label}: the refusal states no reason, and a "
                "refusal without one is indistinguishable from an omission"
            )


@pytest.mark.skipif(not EVIDENCE.is_dir(), reason="the run's evidence is absent")
def test_the_recorded_run_measured_the_grid_it_was_asked_for() -> None:
    """The wiring, end to end. A cell that reported `ok` must carry a level for
    every n, and each level must carry a rate -- `tokens_per_s`, which is what
    ``run.py`` emits. The retired ``sweep.py`` named the same quantity
    `agg_tok_s`, and a
    consumer reading the wrong key sees None at every level and reads it as a
    dead run. That happened once on 2026-08-30 and cost a false alarm."""
    journals = sorted(EVIDENCE.glob("*.jsonl"))
    assert journals, f"no journal under {EVIDENCE}"
    measured = 0
    for journal in journals:
        # LAST WRITE WINS, per label -- the journal is append-only (run.py:93)
        # and every consumer reads it that way (`run.completed()` builds the
        # same dict). Judging superseded rows would make an append-only journal
        # unable to hold the record of a failure it later fixed, which is the
        # opposite of what append-only is for: on 2026-08-31 that is exactly why
        # the documented remedy was to DELETE rows, and deleting them turned the
        # tree green over outstanding cells.
        last: dict[str, dict[str, Any]] = {}
        for line in journal.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("label"):
                    last[str(row["label"])] = row
        for row in last.values():
            if row.get("outcome") != "ok":
                continue
            where = f"{journal.name}:{row.get('label')}"
            levels = (row.get("concurrency") or {}).get("levels") or []
            assert [lv.get("n") for lv in levels] == LEVELS, (
                f"{where}: measured {[lv.get('n') for lv in levels]}, not "
                f"{LEVELS}. The run exists to close n=2 and n=4."
            )
            for level in levels:
                assert level.get("tokens_per_s") is not None, (
                    f"{where}: n={level.get('n')} carries no `tokens_per_s`"
                )
                assert level.get("errors") == 0, (
                    f"{where}: n={level.get('n')} recorded "
                    f"{level.get('errors')} errors, so its rate is not a "
                    "measurement of the grid"
                )
            measured += 1
    assert measured, "no cell reported `ok`, so nothing above was asserted"


@pytest.mark.skipif(not EVIDENCE.is_dir(), reason="the run's evidence is absent")
def test_every_declared_cell_is_present_in_its_journal() -> None:
    """The other half of the assertion above, and the half that was missing.

    The test above judges the rows that ARE in a journal. It cannot see a row
    that is not there, so a cell deleted from a journal reads as green -- and
    deleting rows is exactly what the documented resume procedure does, to
    force a re-measure of a cell that was stamped `ok` before the barren-level
    downgrade landed. Between the drop and the re-measure the tree therefore
    went green while six cells were outstanding, which is the state the whole
    guard exists to refuse. An absent cell is a cell that did not run.

    A cell that could not launch belongs in the config's `_refused` with a
    reason; that is a recorded result and does not count as missing.
    """
    checked = 0
    missing: list[str] = []
    for journal in sorted(EVIDENCE.glob("*.jsonl")):
        backend, _, host = journal.stem.partition("-")
        config = CONFIGS / f"srv-{backend}-n1248-{host}.json"
        assert config.is_file(), (
            f"{journal.name}: no config at {config.name}. The journal and the "
            "config that asked for it are matched by name; a rename that broke "
            "the pairing would silently stop checking this journal."
        )
        document = json.loads(config.read_text(encoding="utf-8"))
        declared = [str(entry.get("label")) for entry in document.get("models") or []]
        assert declared, f"{config.name}: declares no models"
        refused = set(document.get("_refused") or {})
        # `outcome: ok` is not sufficient on its own -- a row written before the
        # barren-level downgrade (d75d90fb) can be `ok` while carrying a level
        # that measured nothing. Judge the curve, the same way `run.completed()`
        # and RESUME.md's status check do, so all three report one number.
        ok = {
            row.get("label")
            for line in journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for row in [json.loads(line)]
            if row.get("outcome") == "ok"
            and not _barren_levels(row.get("concurrency") or {})
        }
        for label in declared:
            if label not in ok and label not in refused:
                missing.append(f"{journal.name}:{label}")
        checked += 1
    assert checked, f"no journal under {EVIDENCE}, so nothing above was asserted"
    assert not missing, (
        f"{len(missing)} declared cells carry no `ok` row: {missing}. Either "
        "the run is not finished, or rows were dropped to force a re-measure "
        "and the re-measure has not happened yet. A journal missing a cell is "
        "not a measured grid."
    )


@pytest.mark.skipif(not EVIDENCE.is_dir(), reason="the run's evidence is absent")
def test_a_cell_that_did_not_launch_says_why_in_the_journal() -> None:
    """Fail loud, recorded. `launch_failed` with an empty refusal is the shape
    that turns a wall into a shrug."""
    for journal in sorted(EVIDENCE.glob("*.jsonl")):
        for line in journal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("outcome") in (None, "ok"):
                continue
            prose = (row.get("refusal") or {}).get("prose") or ""
            assert len(prose) > 80, (
                f"{journal.name}:{row.get('label')} did not launch and states "
                f"no reason ({prose!r})"
            )


@pytest.mark.skipif(not EVIDENCE.is_dir(), reason="the run's evidence is absent")
def test_the_run_recorded_what_produced_it() -> None:
    """Each journal closes with a provenance row -- argv, the config's digest,
    the harness's digest, whether the tree was dirty. Rows without it cannot be
    tied to the code that made them."""
    for journal in sorted(EVIDENCE.glob("*.jsonl")):
        rows = [
            json.loads(line)
            for line in journal.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert rows, f"{journal.name} is empty"
        tail = rows[-1]
        for field in ("argv", "config_sha256", "harness_sha256", "run_started_at"):
            assert field in tail, (
                f"{journal.name}: the closing row states no {field}, so these "
                "measurements name neither their config nor their harness"
            )
