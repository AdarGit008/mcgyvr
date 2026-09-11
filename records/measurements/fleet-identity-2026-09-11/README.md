# The fleet identity measurements — measured 2026-09-11

The plan is `records/plans/fleet-identity-measurements-2026-09-11.md`. The criteria are
`tests/test_the_numbers_the_fleet_identity_design_waits_on_are_measured.py`, and **all 12
now pass**.

- **Door.** Every arm ran through the door: round `r27-10-09-2026`, product
  `3ca400675f…`, `profile=live`.
- **Cold starts.** Each arm was one cold start. The page cache was dropped first, and
  gate 2 required the rig to be idle.
- **Records.** The raw rows are `raw-*.json`, one row per cold start. `derive.py`
  projects them into the `results-*.json` records the test reads.
- **Logs.** Engine and door logs are git-ignored (`*.log`) and stayed on the operator
  machine. Every figure parsed from them is in the rows.

**Rigs as left:**

- both rigs: no `mcgyvr-*` container, swap on, and both rebooted once (M8);
- srv1: its reserve now reads 399 MiB against the 401 in `tools/runs/hosts.json`, so gate
  2 refuses srv1 on this branch (see M8).

---

## M1. Warm decode: no-NVMe baseline vs as-run

All samples are 256 tokens: 5 per cold start after one discarded warm-up, 3 cold starts
per arm.

| rig / unit | class | baseline tok/s | as-run tok/s | gap | NVMe |
|---|---|---|---|---|---|
| srv1 Qwen3.6-35B-A3B IQ3_XXS, `--n-cpu-moe 30` | CPU experts | 33.13 (unmapped, swap off) | 31.76 (mapped, swap on) | **4.15%** | allowed |
| srv1 Ling-3.0-tiny Q4_K_M, all on card | llama.cpp | 116.65 | 116.64 | 0.01% | allowed |
| srv2 Qwen2.5-Coder-3B AWQ, live pair | vLLM | 127.85 | 127.86 | −0.01% | allowed |
| srv2 Qwen2.5-Coder-7B AWQ, live pair | vLLM | 68.86 | 68.87 | −0.01% | allowed |

**Tolerances, by the rule the plan fixed before any arm:**

| class | worst single-sample shortfall | tolerance | provisional survey value |
|---|---|---|---|
| vLLM | 0.58% | **1%** | 3% |
| llama.cpp | 0.52% | **1%** | 5% |
| CPU experts | 47.84% | **48%** | 15% |

**The 48% comes from one sample and needs an owner ruling.**

- **What set it.** In `s1-qwen36-baseline-1` the 5th sample read 17.28 tok/s against a
  median of 33.13. Both unmapped `--n-cpu-moe 32` starts dipped on the same sample
  (22.4, 23.7).
- **Where it happens.** Every dip is on the 5th sample of an unmapped, swap-off start, so
  it is not a warm-up effect. The cause is UNVERIFIED.
- **What the rule does with it.** The frozen rule takes the worst single sample, so this
  one dip sets the class. Without the baseline arm, the as-run shortfall is 1.44%.
- **A second effect.** The as-run cold starts themselves differ by 5.4% (33.2, 31.8,
  31.4), which the per-sample rule does not see.

**`no baseline: NVMe required`: none.** Every unit fit in RAM and VRAM.

**The survey's figures do not hold as written.**

- **vLLM and llama.cpp.** Their spread on this instrument is under 1%. The survey's 3%
  and 5% were loose.
- **CPU experts.** The 15% is too tight for single samples and too loose for start-to-start
  medians.

## M2. Cold wake per unit × rig

Each unit was measured alone, n=3, with 0 restarts. Medians, with the largest deviation
from the median:

| rig / unit | Waker clock (door process) | door unit clock | StartedAt → first 200 | Waker − door |
|---|---|---|---|---|
| srv1 Qwen3.6 | **154.2 s** (1.4%) | 132.9 s | 130.5 s | 20.8 s |
| srv1 Ling | **83.4 s** (0.6%) | 63.8 s | 63.5 s | 19.4 s |
| srv2 3B | **115.9 s** (0.6%) | 96.0 s | 93.4 s | 19.6 s |
| srv2 7B | **115.3 s** (2.0%) | 96.4 s | 95.7 s | 19.0 s |

- **Which clock.** `wake.json` names `door_process_s` as the clock the design reads, the
  span `src/mcgyvr/wake.py` `_run_door` times.
- **The Waker's offset.** It reads 19.0–20.8 s over the door's clock on all four units,
  so the 19 s seen on one srv1 unit (`flexibility-2026-09-09`) holds for every unit here.
- **Against the proposed tolerance.** Every spread is well inside `max(10%, 5 s)`.

**The live srv2 pair still crash-restarts on every cold start.** It is ordered
`service_started` and its KV is not pinned.

- **Restarts.** In all 6 pair starts (3 as-run, 3 baseline), the 3B restarted 2× and the
  7B 1×.
- **Wake.** 190.5–195.3 s on the Waker's clock.
- **KV.** The 7B's first logged KV size moved between 8,592 and 51,920 tokens.

## M3. vLLM host RAM per rig

The cost is `MemAvailable` idle less `MemAvailable` with the unit up, with the page cache
dropped before both reads.

| rig | unit | n | cost GiB | Σ RssAnon+RssShmem GiB |
|---|---|---|---|---|
| srv1 | 3B (util 0.60) | 3 | 2.48–**2.51** | 2.38–2.40 |
| srv2 | 3B | 3 | 2.70–2.74 | 2.60–2.61 |
| srv2 | 7B | 3 | 2.71–**2.77** | 2.60 |

**Per rig: srv1 2.51 GiB, srv2 2.77 GiB.** Both are below the survey bounds of 2.60 and
2.96. The pair costs 5.24–5.30 GiB, which is two units' worth.

## M4. Unmapped Shmem as a per-model residual

`residual = (Shmem up − Shmem idle) − spilled experts (tensor table)`, with swap off.

| model | placements (starts) | residual | spread |
|---|---|---|---|
| Qwen3.6-35B-A3B IQ3_XXS | `--n-cpu-moe` 30 (×3), 32 (×2) | **428.0 MiB** | 0.01 MiB |
| Ling-3.0-tiny Q4_K_M | `--n-cpu-moe` 0 (×3), 4 (×2) | **153.6 MiB** | 0.01 MiB |

**The residual is one constant per model, independent of placement.** Both fall inside the
survey's +0.60 GiB for unmeasured models.

## M5. fp8 KV cache on the RTX 3060 (sm_86)

The live 7B alone on srv2, 3 cold starts per dtype.

| | `auto` | `fp8` |
|---|---|---|
| attention backend (vLLM's own log line) | FLASH_ATTN | **FLASHINFER** |
| KV tokens | 37,248 | 74,512 (2.000×) |
| card used | 7,795 MiB | 8,245 MiB (+450) |
| warm decode | 68.84 tok/s | 67.43 tok/s (−2.0%) |
| bench-py greedy passes | 68 / 257, both runs | **6 / 257**, both runs |

**Quality: outside the null.**

- **The contrast.** 62 cells flip between `auto-a` and `fp8-a` (24.1 pp).
- **The bound.** Each dtype's own a/b null has 0 flips, so the 95% Wilson bound is
  1.47 pp.
- **What the failures are.**
  - fp8 replies fail syntax in 185 cells; auto fails syntax in 2.
  - 25 fp8 replies leave a code fence open, and 15 are truncated.
  - The replies drop tokens mid-line, for example
    `def parse_option(segment:    key, eq,    raw = …`.

**fp8 KV is not usable for this unit on this card.**

- **Cause, UNVERIFIED.** No calibrated KV scales (the default is 1.0) combined with the
  FlashInfer path.
- **What this changes.** The design's "fp8 KV approved as a validated unit" would fail its
  own validation here.

## M6. `--kv-cache-memory-bytes` on srv2

| case | outcome |
|---|---|
| first start (card empty) | 3B 32,768 tokens, 7B 32,768 tokens, 0 restarts |
| started beside a neighbour serving a saturating load (~3,500–4,100 requests sent in the window) | **same**: 32,768 each |
| restart: `kill -9` of the engine, docker restarts it, writable layer kept | **same**: 32,768 each, `RestartCount` 1 |
| pinned size that takes the 7B past its room (share 0.68 = 8,099 MiB) but inside free memory | **served**, no warning. Peak 8,768 MiB, 669 MiB past its room; KV 53,712 tokens, exactly as pinned |
| pinned size above free memory (11.63 GiB) | **failed at start**: `torch.OutOfMemoryError … Tried to allocate 426.00 MiB`. It does not shrink |
| 7B at util 0.90 with the 3B up | **refused by the start gate**: `ValueError: Free memory on device cuda:0 (8.15/11.63 GiB) on startup is less than desired GPU memory utilization` |

**Pinned KV is identical across start order, restart and neighbour.** That supports the
design's premise.

**The fixed-room rule cannot rely on the engine to stay in its room.** A pinned size
silently runs a unit past its share. Only the card's free memory stops it, by OOM, and the
start gate checks the share, not the pinned size. So the lock must check
`non-KV peak + pinned KV ≤ room` itself.

## M7. Headroom per rig, and resized srv2 shares

| rig | reserve | contexts | headroom |
|---|---|---|---|
| srv1 | 401 MiB | Qwen3.6 95.6 MiB | **496.6 MiB** |
| srv2 | 377 MiB | 3B 116.8, 7B 116.8 MiB | **610.5 MiB** |

**How the contexts were read.**

- **vLLM.** `cuda_memory` at the init snapshot, less idle use. vLLM logs it to 2 dp of
  GiB, so the upper edge of the rounding (+0.005 GiB) is taken.
- **llama.cpp.** Card net of idle, less the named device buffers from two `--verbose`
  starts: model 4,330.81, KV 320.00, compute 221.00, RS 125.62 MiB.

**Proposed srv2 shares.** `proposal.json` applies the plan's sizing rule to the solo
readings (non-KV peak 3B 2,319 MiB, 7B 6,185 MiB under 8 × ~4,000-token streams):

| unit | share | room | pinned KV |
|---|---|---|---|
| 3B | **0.30** (today 0.26) | 3,573 MiB | 32,768 tokens = 1,152 MiB |
| 7B | **0.68** (today 0.72) | 8,099 MiB | 32,768 tokens = 1,792 MiB |

`Σ rooms 11,672.8 + Σ contexts 233.5 = 11,906.3 ≤ T 11,911 MiB`, which is
`Σ rooms + headroom 12,283.3 ≤ card 12,288 MiB`.

**Both start orders pass.** 3B-first ×2 and 7B-first ×2:

- both units healthy, 0 restarts;
- 32,768 KV tokens each;
- peaks under a combined saturating load: 3B 3,446 MiB (room + context 3,690), 7B
  7,522 MiB (8,216).

**Correction to the ruled design.** The report says "0.26 + 0.72 leave only 0.23 GiB, too
thin; both shares must shrink".

- **What was measured.** The contexts are 117 MiB each, so a 0.98 total fits, with
  **4.7 MiB** to spare.
- **What changes.** The shares are redistributed, not shrunk, and each unit's KV is pinned.
- **Why it still matters.** The margin is at the resolution of the context reading, so a
  0.97 total is the safer lock.

## M8. `gpu_reserve_mib` across boots

Each reading was taken idle, with the same card and driver; the boot is `/proc/stat`
btime.

| rig | boot 2026-09-01 | boot 2026-09-11 |
|---|---|---|
| srv1 | 401 MiB (08:11:08Z) | **399 MiB** (06:34:36Z) |
| srv2 | 377 MiB (05:20:12Z) | 377 MiB (07:25:46Z) |

- **srv1.** Its reserve moved 2 MiB and nothing else did (`rig-snapshot.sh` against
  `hosts.json`, every other key equal).
- **Consequence.** Gate 2 compares the value literally, so it now refuses srv1:
  `gpu_reserve_mib: declared '401', reads '399'`.
- **What was done.** The owner asked for the fix as a RED test against `main`, together
  with the stopgap re-declaration: branch `red/card-reserve-bound`.

---

## Harness lessons

- **The door's gate scripts are `#!/usr/bin/env python3`.**
  - Spawning `.venv/bin/python -m mcgyvr.serving.run` without the venv on PATH fails at
    gate 6 with `No module named 'mcgyvr'`. `uv run` puts it there.
  - The Waker spawns `sys.executable` the same way. Whether an installed Waker hits this
    is UNVERIFIED.
- **Gate 5 never reuses a RUN_ID, including after a refused attempt.** The suffix now
  carries a clock reading.
- **The bench's card sampler opens ssh to a non-local endpoint's host, which only the door
  may do.** The bench ran through a localhost port-forward, as `srv1-correct-2026-09-03`
  did.
- **`pkill -f <script>` matched and killed the invoking shell.** This is the lesson
  `rig.py` already carried.
- **srv1 keeps an old exited container named `mcgyvr-lcpp`** (not the door's naming).
  Teardown matches `mcgyvr-<host>-`, and that container was left alone.
- **vLLM's DEBUG init snapshot is printed in GiB to 2 dp, not in bytes.** The 1 Hz sampler
  sees weights before a context-only reading.
- **This machine's low-memory watchdog killed background shells twice.** The runners ran
  under `setsid nohup`.

## Running it again

```
make_composes.py               # the fixed composes (the live ones copied byte for byte)
reserve.py srv1 srv2           # M8, once per boot, idle
srv1.py                        # M1, M2, M4 on srv1; M3 srv1 3B; M7 llama.cpp context
srv2_a.py                      # M1 pair, M2/M3 each unit alone, M5 fp8 and bench quality
srv2_pinned.py                 # M7 solo -> proposal.json -> both orders; M6
derive.py                      # the records the test reads
```
