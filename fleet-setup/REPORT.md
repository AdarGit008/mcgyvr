# Fleet stamping — coordinator report (2026-09-13/14)

Three fleets (`a-solo`, `b-small`, `b-big`) were measured on dev by two parallel
headless runs (srv1 + srv2), the evidence was merged, the fleet/policy files were
finalized, and `mcgyvr fleet lock` wrote the lock on the first attempt.

## Deliverables (all under the measurements worktree)

- `fleet-setup/fleet.yaml` — final (7 units, 2 rigs, 3 fleets), digests + rooms
  + windows pinned.
- `fleet-setup/policy.yaml` — ladder + `fanout: idle`.
- `fleet-setup/evidence.json` — merged dev evidence (2 rigs, 6 combinations,
  4 moves).
- `records/fleet/` — **the stamp**: `a-solo.json`, `b-small.json`, `b-big.json`
  + 6 `rigs/<rig->/<cmb->.json` combination records.
- `records/measurements/fleet-setup-2026-09-13/{srv1,srv2}/` — raw run outputs +
  harnesses.
- `fleet-setup/REPORT-srv1.md`, `REPORT-srv2.md` — the two run reports.
- `fleet-setup/digests-srv1.json`, `digests-srv2.json` — exact identity-digest
  fields for reproducibility.

## Pinned results

| unit | rig | warm decode | prefill | room_mib | overhead | window | width |
|---|---|---|---|---|---|---|---|
| srv2_35b_256k | srv2 | 48.2 tok/s | 629.8 | 10597 | 490 | 262144 | 1 |
| srv1_35b_maxctx | srv1 | 33.78 | 352.71 | 5630 | 497.38 | 32768 | 1 |
| srv2_3b | srv2 | 126.7 | 11500 | 3573 | — | 4096 | 8 |
| srv2_7b | srv2 | 68.3 | 12059 | 8099 | 610.5 (pair) | 4096 | 8 |
| srv2_80b | srv2 | 28.4 | 280.9 | 11523 | 524 | 16384 | 4 |
| srv1_deepseek | srv1 | 32.56 | 307.11 | 5458 | 486.22 | 8192 | 2 |
| srv1_35b_b | srv1 | 33.28 | 342.18 | 5122 | 494.57 | 16384 | 2 |

All combinations: `restarts == 0`, `Σ room + overhead ≤ card` (see fit notes).
All 4 switch moves passed (b-small↔b-big, per rig), downtime/wake recorded in
`b-small.json`/`b-big.json`.

## Fit margins worth knowing

- **srv1_35b_maxctx is at the card ceiling**: 5630 + 497 = 6127 of 6144 MiB
  (~17 MiB slack). `-c 65536` OOMs (`cudaMalloc … out of memory`); 32768 is the
  deepest context that fits on the 6 GiB GTX 1660 SUPER. The ceiling is VRAM,
  not the 16 GB RAM (MemAvailable held ~14.8 GiB during the OOM).
- **b-small/srv2 pair margin is ~5.5 MiB**: 3573 + 8099 + 610.5 = 12282.5 of
  12288. Tight but passes.
- **No NVMe baseline** was run (`baseline_tok_s` empty), so these units lock
  without the no-NVMe slowdown tolerance check (the lock records them as such).

## Blockers for the *live* phase (not the lock — flagged by the runs)

1. **Driver drift** — `tools/runs/hosts.json` is stale against both rigs:
   - srv1 live driver `580.178.04` vs declared `580.173.02`
   - srv2 live driver `595.91.07` vs declared `595.84`
   Gate 2 compares literally, so a **door run will refuse** until `hosts.json`
   is re-declared to the live drivers. The `rig-` digests above already use the
   live drivers.
2. **Lidenburg io_uring** logs `io_uring_queue_init failed: Operation not
   permitted` under docker's default seccomp and falls back to the RAM tier —
   non-fatal, matches the plan (the expert set fits pinned RAM on srv2's 48 GB).

## Next steps (owner)

- Commit `records/fleet/` + `fleet-setup/` + the measurement records — committing
  the lock is the approval.
- Re-declare the two drivers in `tools/runs/hosts.json` before any door run.
- Proceed to a live `mcgyvr run` / door validation if you want to serve the
  stamped fleets.
