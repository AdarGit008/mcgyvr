# The measuring-gaps run — measured 2026-09-10

The plan is `records/plans/measuring-gaps-2026-09-10.md`; it closed five
"needs measuring" items from the VRAM-levers reconciliation. **30 of 30 arms
landed, 0 failed.** Every arm ran cold on an empty rig through the door
(round `r27-10-09-2026`, product `3ca400675f…`), one cold start per arm, the
engine's own buffer lines captured with `--verbose` and parsed off-rig.

Results land here, not in the session. Raw rows in `results-*.json`, the
engine log behind every arm in `logs/<label>.log`, the composes in
`compose.srv?-*.yml`.

---

## The five answers

### Q1. q8_0 KV cache — the 17/32 factor holds *exactly*, and it costs nothing

deepseek-coder-v2-16b, srv1, `-c 8192 -np 2`, n=2 each side:

| arm | K | V | total | card steady | warm tok/s |
|---|---|---|---|---|---|
| f16 | 1,296.00 MiB | 864.00 MiB | 2,160.00 MiB | 5,460 MiB | 31.1–32.3 |
| q8_0 | 688.50 MiB | 459.00 MiB | 1,147.50 MiB | 4,446 MiB | 33.2–34.4 |

**K and V shrink independently by exactly 17/32** (1,296 × 17/32 = 688.5;
864 × 17/32 = 459.0), and the card drop — 5,460 → 4,446 = 1,014 MiB — is the
predicted 2,160 × 15/32 = 1,012.5 to 1.5 MiB. `CACHE_ELEM_BYTES["q8_0"] =
34/32` is now verified on-rig, not just asserted in the docstring.

**The decode delta is ~nil, sign positive.** q8_0 warm decode is *faster*
than f16 by ~2 tok/s (33.2–34.4 vs 31.1–32.3), not slower — the smaller cache
footprint wins over the dequant cost. There is no per-token q8_0 penalty to
price. (Absolute decode runs ~7% below the no-`--verbose` baseline because
`--verbose` logging is per-token; the *delta* is unaffected since both sides
pay it.)

**Two plan figures were off, the law was not.** The plan's "f16 KV 2,264.9 MiB"
is actually **2,160.00 MiB** on-rig (the 192:128 K:V split was right; the
absolute was ~105 MiB high). The 17/32 *ratio* is what matters and it is exact.

### Q2. vLLM fp8 KV — 2.000× confirmed on the refused cell, with the margin

`thewimo/Qwen3-4B-AWQ` (q34b), srv2, util 0.9, len 2048, seqs 128, n=2 each:

| arm | KV pool | maxconc | card | warm tok/s |
|---|---|---|---|---|
| fp16 (auto) | 52,192 tok | 25.48× | 10,943 MiB | 103.8 |
| fp8 | 104,400 tok | 50.98× | 11,503 MiB | 100.2 |

**104,400 / 52,192 = 2.0000**, byte-for-byte the q15 law, now on the large
model. The refused-cell margin is arithmetic and matches the plan exactly: the
n=32 cell needs 65,536 tokens, the fp16-sized gate sees 52,192 and refuses,
fp8 holds 104,400 and admits with **38,864 tokens to spare**.

**fp8 is not free.** Warm decode is ~3.5% slower (100.2 vs 103.8 tok/s) — the
FLASH_ATTN→FLASHINFER backend swap on Ampere. The card is ~flat (11.5 GiB both
sides: util backfills freed weight space with KV), so the pool gain is real and
the only cost is the ~3.5% decode.

### Q3. Compute-scratch — the 768 bound is an *under-bind* for qwen3next

Per `(arch, -ub)`, n=2, the engine's `sched_reserve: CUDA0 compute buffer size`
plus the residue (card − idle − named device buffers):

| arch | ub | compute | residue | scratch+context | vs 768 |
|---|---|---|---|---|---|
| bailingmoe3 | 256 | 31.01 | 81.63 | 112.64 | clears |
| bailingmoe3 | 512 | 62.01 | 82.63 | 144.64 | clears |
| bailingmoe3 | "1024" (ran 512) | 62.01 | 82.63 | 144.64 | clears |
| gemma4 | 256 | 176.16 | 91.65 | 267.81 | clears |
| gemma4 | "1024" (ran 512) | 211.64 | 90.17 | 301.81 | clears |
| **qwen3next** | 256 | 652.00 | 164.86 | **816.86** | **EXCEEDS** |
| **qwen3next** | "1024" (ran 512) | 664.00 | 164.86 | **828.86** | **EXCEEDS** |

**qwen3next (Qwen3-Next-80B) needs 817–829 MiB, exceeding `SCRATCH_AND_CONTEXT_MIB
= 768` by ~50–60 MiB.** This is the dangerous direction the bound exists to
prevent: a cell sized with 768 for qwen3next clears every gate and can OOM at
load. The fix is a `MEASURED_SCRATCH_MIB["qwen3next"] ≈ 829` entry, not a
global raise — the other six archs (deepseek2, gptoss, qwen35moe,
nemotron_h_moe, bailingmoe3, gemma4) all clear 768 with margin.

**The "1024" rows ran at `-ub 512`, so nothing here measures `-ub 1024`.**
Every such compose passes `-b 512 -ub 1024` (`compose.srv?-q3-*-ub1024.yml`),
and llama.cpp clamps the physical batch to the logical one: each of those arms'
engine logs prints `n_ubatch = 512`. Those logs are not committed (`*.log` is
gitignored), so the committed evidence is the composes and the rows themselves
— bailingmoe3's 512 and "1024" rows read the same to the MiB. They are one setting
read twice; the saturation this section once claimed was that clamp. What
stands: the compute buffer grows from `-ub 256` to `-ub 512` on all three
archs, and qwen3next's 829 MiB is a `-ub 512` reading. Found by
`394a48e4` (branch `red/fleet-identity-gaps`).

### Q4. `C` drift — universal, but the per-block rate is per-arch

deepseek-coder-v2-16b, srv2, ncmoe 0/13/26, n=2, `C` recomputed offline as
`headroom.py` does:

| ncmoe | C | residual vs ncmoe-0 prediction |
|---|---|---|
| 0 (probe) | 3,028.00 MiB | +0.00 |
| 13 | 3,102.00 MiB | +74.00 |
| 26 | 3,101.00 MiB | +73.00 |

**C drifts +74.00 MiB over the 26-block span (+2.85 MiB/block).** Q11's
Qwen3.6 drift (+38 MiB / 33 blocks = +1.15 MiB/block) is therefore *not* a
one-arch artefact — the drift is universal — but the rate is per-arch (deepseek
2.85 vs Qwen3.6 1.15). The `vramfit` docstring claim that `C` "does not move
with `--n-cpu-moe`" is now false on **two** architectures, in the dangerous
direction (C grows, so the card holds *more* than the law predicts).

The drift is also not linear: deepseek's whole +74 MiB appears between ncmoe 0
and 13, then holds to 26. A correction term wants a per-arch step, not a
per-block slope.

### Q5. MLA absorbed-V — the engine's own line says `V (f16): 0.00 MiB`

Ling-3.0-tiny Q4_K_M, srv1, n=2, captured verbatim:

```
llama_kv_cache: size = 54.00 MiB (4096 cells, 6 layers, 2/2 seqs), K (f16): 54.00 MiB, V (f16): 0.00 MiB
```

**V is absent, not merely small — `0.00 MiB`, exactly as `ggufscan.py`'s
`mla_absorbed_v` (`v_elems: 0`) predicts.** The card reads 4,808 MiB, which the
`v_elems = 0` prediction matches to the Q11 margin; a separately-cached V would
read ~1 GiB higher. The engine line had unit coverage only until now; it is now
on-rig.

### Q6. The `C` step is op offload — 10 arms added after the 30, same day

Q4's composes, n=2 each, with and without `--no-op-offload`, plus a
2,888-token prefill (op offload only engages at a batch of 32+) and a warm
decode. Round `r9-10-09-2026`, srv2 empty before and after.

| ncmoe | op offload | CUDA0 compute | C drift vs ncmoe 0 | prefill tok/s | decode tok/s |
|---|---|---|---|---|---|
| 0 | on | 76.13 | 0 | 440.5 | 66.4 |
| 13 | on | 151.51 | +74.00 | 327.6 | 33.9 |
| 13 | off | 76.13 | +0.00 | 168.9 | 34.3 |
| 26 | on | 151.51 | +73.00 | 252.0 | 22.2 |
| 26 | off | 76.13 | −1.00 | 96.5 | 22.5 |

**Q4's drift is the compute buffer, and op offload is all of it.** llama.cpp
copies a host-stored expert tensor into the device compute buffer for a large
batch; the buffer steps 76.13 → 151.51 MiB once any expert is on the host and
holds flat after. Turning it off takes the step away and costs 48–62% of
prefill and no decode — for 74 MiB, a quarter of one 297 MiB expert block. The
flag is banned: `okf/config/llama.cpp.md`. `--no-op-offload` flat-lines the
graph splits too (80 and 106 with no `bs=512` variant).

Runner `no_op_offload.py`, report `q6_report.py`, rows
`results-arms-q6-no-op-offload.json` and `-report.json`. Both `q6_report.py`
and `c_drift_report.py` read the deepseek geometry from
`records/measurements/ram-headroom-2026-09-09/`, relative to this tree.

---

## Records made false by this run

1. **`vramfit` module docstring** — "`C` does not move with `--n-cpu-moe`" is
   false on two archs over wide spans (Qwen3.6 +38 MiB/33, deepseek +74 MiB/26).
2. **`SCRATCH_AND_CONTEXT_MIB = 768`** — an under-bind for `qwen3next`
   (measured 817–829 MiB). Add `MEASURED_SCRATCH_MIB["qwen3next"] ≈ 829`.
3. **Plan descriptive figures** — deepseek f16 KV is 2,160 MiB (not 2,264.9),
   and its per-block expert weight is 297.0 MiB (not 311.4). Neither changes a
   law; both were off in the plan's prose.

## Harness lesson

`llama.cpp` prints the buffer lines (`load_tensors`, `llama_kv_cache`,
`sched_reserve`) only at `--verbose` (`-lv 2147483647`), not at the default
verbosity 3 — which is why the flexibility campaign's engine lines were never
captured. Every llama.cpp compose in this run carries `--verbose`, and the full
log is pulled off-rig and parsed (never `grep | tail -1`).

## Running it again

```
make_run_config.py          # emits 15 composes + 5 arms JSON + teardown index
run_all.sh                  # preflight → 5 launch runners → 2 reports → teardown
```

The rigs were verified empty at the end (srv1 17 MiB, srv2 1 MiB idle). The
flexibility campaign's live ladders were torn down for this run and their
exact pre-teardown state is in `live-state-before-teardown.md`.
