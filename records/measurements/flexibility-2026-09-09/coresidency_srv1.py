"""Q7 — two llama.cpp MoE units co-resident on srv1, where the host-RAM sum binds.

M2 ran the first two-MoE co-residency on srv2 and found ``Shmem`` additive to
4 KiB. srv2's 44.5 GiB makes that sum invisible to every gate; srv1's 14.19 GiB
does not. **Owner's pick, 2026-09-10:** gemma-4-26B at ``--n-cpu-moe 28`` and
Ling-3.0-tiny Q6_K at 21, both ``--load-mode none``, predicted at 5,635 MiB of
card and ~12.76 GiB of ``Shmem`` — **+1.43 GiB clear of what srv1 has, inside
``REFUSAL_RAM_HEADROOM_GB = 2.0``**, so a placement the rig should hold and
`emit` refuses. `emit`'s verdict is taken separately, from declared figures
(``q7/declared-pair.yaml``, ``logs/q7-emit.log``).

The runner is `coresidency.py`'s, pointed at srv1, so the figures are M2's
instrument exactly. Two things are added around it, because this is the arm
that carries srv1's hard-lock hazard and M2's did not:

* ``/proc/vmstat`` and ``SwapFree`` either side of every arm, so a placement
  that "fits" by paging is told apart from one that fits;
* the warm decode instrument beside the cold one, which §3 of the README says
  is the one to believe.

Each unit alone once, as M2 did, because additivity needs both baselines; then
the pair twice. The plan's two arms are the pair; the baselines are what make
them answer the question.
"""

from __future__ import annotations

import json

import coresidency as co
import rig

co.HOST = "srv1"
D = str(rig.SCR)
GEMMA = ("mcgyvr-srv1-gemma-4-26B-A4B-it-UD-IQ3_XXS-8080", 8080)
LING = ("mcgyvr-srv1-Ling-3.0-tiny-Q6_K-8081", 8081)
# Offloaded expert bytes from the geometry at these placements -- what an
# unmapped unit allocates as `Shmem`.
ARMS = [
    {"label": "q7-gemma-alone", "compose": f"{D}/q7/compose.srv1.q7-gemma-8080.yml",
     "units": [GEMMA], "experts_gib": 7.96},
    {"label": "q7-ling-q6k-alone", "compose": f"{D}/q7/compose.srv1.q7-ling-q6k-8081.yml",
     "units": [LING], "experts_gib": 4.80},
    {"label": "q7-both-1", "compose": f"{D}/q7/compose.srv1.q7-both.yml",
     "units": [GEMMA, LING], "experts_gib": 12.76},
    {"label": "q7-both-2", "compose": f"{D}/q7/compose.srv1.q7-both.yml",
     "units": [GEMMA, LING], "experts_gib": 12.76},
]
OUT = rig.SCR / "results-q7-coresidency.json"


def main() -> None:
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for spec in ARMS:
        before_vm, before_mem = rig.vmstat(co.HOST), rig.meminfo(co.HOST)
        try:
            row = co.arm(spec)
        except SystemExit as exc:
            print(f"    ARM FAILED: {exc}", flush=True)
            results.append({"label": spec["label"], "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
            continue
        after_vm, after_mem = rig.vmstat(co.HOST), rig.meminfo(co.HOST)
        warm = {port: rig.decode_llamacpp_warm(co.HOST, port) for _, port in spec["units"]}
        row.update({
            "pgmajfault_delta": after_vm["pgmajfault"] - before_vm["pgmajfault"],
            "pswpout_delta": after_vm["pswpout"] - before_vm["pswpout"],
            "pswpin_delta": after_vm["pswpin"] - before_vm["pswpin"],
            "swap_used_before_gib": before_mem["SwapTotal"] - before_mem["SwapFree"],
            "swap_used_after_gib": after_mem["SwapTotal"] - after_mem["SwapFree"],
            "decode_warm": warm,
        })
        warm_means = {p: round(w["mean"], 2) if w else None for p, w in warm.items()}
        print(f"    swap used {row['swap_used_before_gib']:.2f} -> {row['swap_used_after_gib']:.2f} GiB   "
              f"pswpout +{row['pswpout_delta']}   majflt +{row['pgmajfault_delta']}   "
              f"warm decode {warm_means}", flush=True)
        results.append(row)
        OUT.write_text(json.dumps(results, indent=2))
    co.teardown()
    print(f"\nwrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
