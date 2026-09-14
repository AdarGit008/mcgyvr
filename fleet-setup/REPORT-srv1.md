# Fleet stamping — SRV1 half, measured 2026-09-13

Scope: srv1 (GTX 1660 SUPER 6 GiB, sm_75, 16 GB RAM) only. The srv2 half and the
fleet lock are the coordinator's. Every number below is from a run done in this
session or a cited prior-art file; raw outputs are under
`records/measurements/fleet-setup-2026-09-13/srv1/`.

## What was pinned

### 1. a-solo/srv1 = [[srv1_35b_maxctx, awake]] — the max-context sweep

llama.cpp `llamacpp:b10644-L3`, Qwen3.6-35B-A3B-UD-IQ3_XXS,
`--n-cpu-moe 28 -fa on -ctk q8_0 -ctv q8_0`, width 1 (`--parallel 1`).

| context | result |
|---|---|
| `-c 32768` | **fits** — warm decode 33.78 tok/s, prefill 352.71 tok/s, card 5630 MiB, restarts 0 |
| `-c 65536` | **does not fit** — `cudaMalloc failed: out of memory` while allocating the compute buffers (GPU/VRAM ceiling, not host RAM; `MemAvailable` held ~14.8 GiB) |

- `warm_decode_tok_s` = **33.78** (median of 5; one discarded warm-up first)
- `prefill_tok_s` = **352.71** (median of 3, long prompt ~1959 tok)
- `overhead_mib` = **497.38** (CUDA context 98.38 MiB + driver reserve 399 MiB)
- `card_peak_mib` = **5630** (peak across load + requests; steady at load 5602)
- `restarts` = **0**; `pswpout` delta = 0 (no swap)
- **Pinned window = 32768** (the deepest context that fits; 65536 OOMs).
  The ceiling is the **6 GiB card**, not the 16 GB RAM.

### 2. b-small/srv1 = [[srv1_deepseek, awake]]

deepseek-coder-v2-16b, `--n-cpu-moe 19`, width 2, `-c 8192`.

- `warm_decode_tok_s` = **32.56**
- `prefill_tok_s` = **307.11** (~2015 tok prompt)
- `overhead_mib` = **486.22** (context 87.22 + reserve 399)
- `card_peak_mib` = **5458** (steady at load 5430)
- `restarts` = **0**; `pswpout` delta = 0

### 3. b-big/srv1 = [[srv1_35b_b, awake]]

Qwen3.6-35B-A3B-UD-IQ3_XXS, `--n-cpu-moe 30`, width 2, `-c 16384`.

- `warm_decode_tok_s` = **33.28**
- `prefill_tok_s` = **342.18** (~1959 tok prompt)
- `overhead_mib` = **494.57** (context 95.57 + reserve 399)
- `card_peak_mib` = **5122** (steady at load 5094)
- `restarts` = **0**; `pswpout` delta = 0

### 4. The two srv1 switch moves (cold: page cache dropped before the target start)

| move | downtime_s | wake_s |
|---|---|---|
| b-small→b-big srv1 (deepseek → 35b_b) | **112.264** | **111.17** (35b_b) |
| b-big→b-small srv1 (35b_b → deepseek) | **78.242** | **77.118** (deepseek) |

Warm-cache reference (no `drop_caches`): deepseek→35b_b 89.8 s downtime / 89.1 s
wake; 35b_b→deepseek 73.8 s / 73.1 s. Prior-art cold wakes (through the door,
~19 s door overhead included): deepseek 86.38 s, Qwen3.6-35B 140.6 s
(`records/measurements/flexibility-2026-09-09/README.md`).

## Lock-fit arithmetic (Σ room + overhead ≤ card = 6144)

Recommended `room_mib` (set ≥ card peak; the lock also requires card_peak ≤ room):

| unit | card_peak | recommended room | + overhead | vs 6144 |
|---|---|---|---|---|
| srv1_35b_maxctx | 5630 | 5630 | 497.38 | 6127.38 ✓ (16.6 slack) |
| srv1_deepseek | 5458 | 5458 | 486.22 | 5944.22 ✓ |
| srv1_35b_b | 5122 | 5122 | 494.57 | 5616.57 ✓ |

Two draft `room_mib` values are **too low for their pinned launch** and must be
corrected by the coordinator:
- `srv1_35b_maxctx`: draft 5390 (that figure is the ncmoe-28 card at a smaller
  window); the `-c 32768` launch peaks at **5630**.
- `srv1_35b_b`: draft 4866; the `ncmoe 30 -c 16384 --parallel 2` launch peaks
  at **5122**.
- `srv1_deepseek`: draft 5446; measured peak **5458** (12 MiB short).

## Identity digests (see fleet-setup/digests-srv1.json)

- `rig-` srv1 = `rig-0f7fc6ae2bf6f8bbed8ed774507ef94a04d7f18a0f81b4d7761ce5ae81d03eeb`
- `unt-` srv1_35b_maxctx = `unt-9caefa09e43d66df76ca38411f6295383a3c1e58f6314143fa8f6e4b4b8cc399`
- `unt-` srv1_deepseek = `unt-e1f680726f3f937c8b0a22e26bb44199fc4c2c674d67e0da84ad540567672ea3`
- `unt-` srv1_35b_b = `unt-0ff8b4d1a5886ab3a77eabcb2701e02132bc521a60083d7905fa20c5c1ff77d3`

Field sets follow `records/plans/fleet-identity.md` §1 (rig = host/hardware/
system; unit = engine, image sha256 Id, weights sha256, argv, env, GPU cc). The
image Id is `sha256:d869b98f…` (the `llamacpp:b10644-L3` tag's digest, read
live). The argv is the whole resolved launch, long flag forms matching
`records/evidence/2026-09-09-live-srv1/`.

## Flags for the coordinator

1. **srv1's live driver is 580.178.04**, but `tools/runs/hosts.json` still
   declares `driver: "580.173.02"` (and the prefill README claimed it was
   re-declared). Gate 2 compares literally, so a door run would refuse until
   `hosts.json` is corrected. Out of srv1 scope — the rig_id above uses the
   **live** driver 580.178.04.
2. **`-c 32768` is at the card's limit.** It locks (room 5630 + overhead 497 =
   6127 ≤ 6144, ~17 MiB slack) but leaves only ~116 MiB card-free. It is the
   deepest context that fits; 65536 OOMs. If the owner wants more card margin,
   drop the window (the slack scales ~10.7 KiB/token with the q8_0 cache).
3. **The `-c 65536` ceiling is VRAM, not RAM** — the task text said "RAM
   ceiling", but the failure is `cudaMalloc … out of memory` on the 6 GiB card.
4. **overhead_mib is per combination** (C13/C14): context differs per model —
   Qwen3.6 98.38 MiB (np 1) / 95.57 (np 2), deepseek 87.22 — plus the 399 MiB
   driver reserve. These are fresh measurements, not the pooled 115.69 MiB
   buffer-probe figure (that was Qwen3.6 at ncmoe 34 / np 8 / f16).
5. **No NVMe baseline** was run (out of scope); `baseline_tok_s` is empty, so
   these units lock without a no-NVMe baseline comparison.

## Evidence paths

- combinations: `records/measurements/fleet-setup-2026-09-13/srv1/raw/{maxctx-32768,deepseek-bsmall,35b-bbig}.json`
- context/overhead: `.../srv1/raw/context-{maxctx,deepseek-35bb}.json`
- moves (cold): `.../srv1/raw/moves-cold.json`; (warm) `.../srv1/raw/moves.json`
- 65536 OOM log: captured in the run (see raw/maxctx-65536 log notes)
- harnesses: `.../srv1/{harness_llama.py,measure_context.py,measure_move.py}`
- digests: `fleet-setup/digests-srv1.json`
- lock evidence: `fleet-setup/evidence-srv1.json`

Rig left idle (card 1 MiB used, no `mcgyvr-*`/measurement containers, swap 0).
