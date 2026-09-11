# The unified measurement campaign — KV dtype + reserve + scratch — measured 2026-09-11

The umbrella plan is `records/plans/kv-dtype-measurement-requirements-2026-09-11.md`
(tracked by PR #443). It scopes ONE combined rig run covering the KV-dtype arms
(R1–R5), the qwen35moe scratch at `-ub 512` (S1), and the two-boot
`gpu_reserve_mib` readings #438 and #439 wait on.

**Status.** S1 is measured and folded into #446. The two-boot reserve readings were
already on record (`records/measurements/fleet-identity-2026-09-11/results-reserve.json`,
folded into #438) and are folded, not re-measured. The KV-dtype arms R1–R5 are
**not yet run** — they need the srv2/srv1 window this session did not get to before
the PR-unblocking work closed; the composes and instruments to run them are the
measuring-gaps-2026-09-10 and fleet-identity-2026-09-11 scripts, unchanged.

## Rig admission (done first, owner's ruling)

srv1 read `gpu_reserve_mib` 399 MiB after the 2026-09-11 reboot against the declared
401, so the #439 stopgap re-declares srv1 at 399 (`tools/runs/hosts.json`,
`tests/onedoor.py` RIG) and gate 2 is verified open through the door — round
`r28-11-09-2026`, "srv1 matches its declaration on 11 keys" (serve up Ling, 64.4 s,
exit 0; serve down, exit 0). The real GREEN — a moving reserve is still the same rig —
is the green session's, not this run's.

## S1 — qwen35moe scratch+context at `-ub 512` — MEASURED

One cold start per `-ub`, the live srv1 Qwen3.6 placement (`--n-cpu-moe 30`,
`--parallel 2`, `-c 16384`, `llamacpp:b10644-L3`), `--verbose`. The quantity is the
one `SCRATCH_AND_CONTEXT_MIB` / `MEASURED_SCRATCH_MIB` bound:

```
scratch_context_mib = compute buffer + residue
residue_mib          = vram_net - (cuda_model + cuda_kv + cuda_rs + cuda_compute)
vram_net_mib         = steady card used - idle card used
```

(the measuring-gaps-2026-09-10 Q3 method; `s1_scratch.py`, `results-s1-scratch.json`).

| ub | compute | residue | scratch_context | door |
|---|---|---|---|---|
| 256 (control) | 208.50 | 96.07 | **304.57** | 133.3 s |
| 512 | 221.00 | 95.57 | **316.57** | 136.2 s |

The 256 control lands within 1.9 MiB (0.6%) of the pinned 302.7 reading, so the 512
figure is the same quantity at the served batch. **The #446 GREEN folds
`MEASURED_SCRATCH_MIB["qwen35moe"][512] = 316.57`.** (The 256 compute here, 208.50,
vs `srv1-buffer-probe.tsv`'s 205, is a different-placement artefact — ncmoe 30 / c
16384 here vs ncmoe 34 / c 8192 there.)

## Reserve readings — folded, not re-measured

`results-reserve.json` (fleet-identity-2026-09-11, folded into #438):

| rig | boot | reserve |
|---|---|---|
| srv1 | 2026-09-01T08:11:08Z | 401 MiB |
| srv1 | 2026-09-11T06:34:36Z | 399 MiB |
| srv2 | 2026-09-01T05:20:12Z | 377 MiB |
| srv2 | 2026-09-11T07:25:46Z | 377 MiB |

srv1 moved 2 MiB across a reboot with every other declared key identical; srv2 did not
move. These pin #439's bound width and answer #438's plan §12 "gpu_reserve_mib in the
rig's name" open item.

## Rigs as left

Both rigs: no `mcgyvr-*` container up, swap on, card idle (used 1 MiB). Nothing
declared in `hosts.json` moved beyond the #439 stopgap.
