# The measuring-gaps run — planned 2026-09-10

**PLAN-ONLY. Nothing has been launched and nothing here authorises a launch.**
This document is the measurement-run plan for human approval. It names arms and
runner scripts; none of the runners exist yet and none will be written or run
until the plan is approved.

**The question this round exists to answer.** Five "needs measuring" items from
the reconciliation of the local-AI **VRAM levers** research into mcgyvr, ranked
by rig-time. Each is a lever the code already *models* but has never closed the
loop on with an on-rig reading, or has closed on too few archs to be a law. The
rigs are idle now; this run spends them before any of the levers is trusted.

The five, in the reconciliation's order:

1. **q8_0 KV cache on-rig (llama.cpp)** — `CACHE_ELEM_BYTES["q8_0"] = 34/32` is
   asserted "verified exactly" in `vramfit.py`, but no on-rig run has ever passed
   `-ctk q8_0 -ctv q8_0`. Measure the allocation against the 17/32 factor and the
   wake + decode cost.
2. **vLLM fp8 KV** — the pool is exactly 2.000x under fp8, measured once on a
   small model, but the gate still sizes fp16 and refuses cells that fit. Measure
   the actual fp8 pool on the refused cell and the margin.
3. **Compute-scratch / activation curve** — `SCRATCH_AND_CONTEXT_MIB = 768` is a
   bound over four archs, and the scratch-vs-`-ub` dependence is one point.
   Measure more archs and more `-ub` values.
4. **`C` drift at wide placement** — flexibility Q11 found `C` drifts +38 MiB
   over 33 blocks on Qwen3.6/srv2, contradicting the `vramfit` docstring. Extend
   to a second arch to test universal vs per-arch.
5. **MLA absorbed-V on-rig** — `v_elems = 0` for the MLA checkpoints has unit
   coverage but the engine's own `V (f16): 0.00 MiB` line has never been captured
   on a rig.

**Explicitly excluded from this run** — each needs code or the web before rig
time, and is recorded as blocked rather than measured:

* **The embed/lm_head sensitivity ablation** — needs a tensor-role split in
  `ggufscan.py` first; the parser today sums the table and cannot separate
  `token_embd`/`output` from the rest. A runner would measure a number the code
  cannot yet state.
* **Per-expert on-demand paging status** — llama.cpp #11532; a doc/web check, not
  a rig measurement.

---

## Before any arm runs

**No `src/` change is required for this run.** Every arm is a hand-written
compose or a runner patch of an existing flag; nothing in `mcgyvr/src` moves.
That is the opposite of the flexibility freeze, and it removes the freeze's
largest hazard. The two trees carry `vramfit.py` and `ggufscan.py` byte-identical
(verified 2026-09-10), so the levers the door executes are the same levers this
run measures.

### Verify rigs empty — preflight, before the first arm

The flexibility campaign ended with both rigs torn down; **re-verify, do not
assume**:

1. **No containers up.** `docker ps -a` on srv1 and srv2 shows no `mcgyvr-*`
   container. The door's gate 2 refuses `serve up` onto a busy rig, and a stale
   leftover makes every later arm a teardown casualty (the Q9 three-arm loss).
2. **Cards idle.** `nvidia-smi` reads the rig's idle baseline — 17 MiB used on
   srv1, 1 MiB on srv2. Any number above baseline is a leftover process.
3. **No balloon resident, page cache cold.** `sudo pkill -f /tmp/balloon.py` on
   both rigs; `sync; echo 3 > /proc/sys/vm/drop_caches` before every arm so each
   wake is genuinely cold and each mapped-blob card figure is a cold page-cache
   measurement.
4. **Teardown markers current.** `teardown-index.json` and `last-up-{srv1,srv2}.txt`
   in the measurement directory name the composes actually in use (the "write the
   teardown marker on every path that starts a unit" lesson).

### Order of execution

Ordered to minimise model swaps and put the expensive srv2 loads in one block.

1. **Preflight** — both rigs verified empty, caches dropped.
2. **srv1, deepseek block** — Q1 (4 arms), one model resident throughout.
3. **srv1, Ling block** — Q3's Ling `-ub` sweep (6) and Q5's Ling arms (2) share
   the resident model; Q3's gemma cells (4) follow on one swap.
4. **srv2, vLLM block** — Q2 (4 arms), one model resident throughout.
5. **srv2, llama.cpp block** — Q4's deepseek placements (6) and Q3's 80B `-ub`
   cells (4); two models, two swaps.
6. **Teardown and report** — both rigs empty again; results land in the run's own
   records directory, not in the session.

---

# srv1 — 6 arms (Q1, Q5)

(Q3's srv1 cells — Ling 6, gemma 4 — are in the scratch section below; they run
in the srv1 blocks of the order-of-execution.)

## Q1. q8_0 KV cache on-rig: does the 17/32 factor hold, and what does it cost? *(4 arms)*

**Claim under test.** `CACHE_ELEM_BYTES["q8_0"] = 34/32` bytes per element, i.e.
a q8_0 cache is `17/32` of its f16 twin. The module docstring asserts this was
"verified exactly" (192.00 MiB f16 → 102.00 MiB), but `okf/config/llama.cpp.md`
carries `-ctk`/`-ctv` only as a parenthetical and its neighbour (`-nkvo`) is
"Untested here" — no on-rig run has ever passed `-ctk q8_0 -ctv q8_0`. Two
unknowns: (a) does the allocation really land on 17/32, and (b) what does the
q8_0 dequant cost in wake and decode.

**Why deepseek.** Its cache is the largest single card term on srv1 — f16 KV is
**2,264.9 MiB** at `-c 8192 -np 2` (a 192-wide key), so the 17/32 shrink is a
**1,061.7 MiB** signal, cleanly readable off both the engine line and the card.
It is also the architecture the code's own "192.00 MiB" figure is about.

| arm | checkpoint × placement × flags | what |
|---|---|---|
| 1–2 | deepseek-coder-v2-16b, `ncmoe 19`, `-c 8192 -np 2`, KV f16 (default) | same-day control |
| 3–4 | deepseek-coder-v2-16b, `ncmoe 19`, `-c 8192 -np 2`, `-ctk q8_0 -ctv q8_0` | the new side |

n=2 each. Every arm reads the engine's `llama_kv_cache` line (`K (…): X MiB, V
(…): Y MiB`), the 1 Hz card sampler, and decode cold + warm (the flexibility
README's two instruments, so the q8_0 decode delta is read on the warm mean, not
a single cold sample).

**Expected answer.** The engine line reports `K (q8_0)` and `V (q8_0)`; total
**1,203.2 MiB = 2,264.9 × 17/32**, and the card steady figure drops by ~1,062 MiB
net of the idle baseline. Wake is ~unchanged (the cache is ~1 GiB of an 8.29 GiB
load). Warm decode moves by the q8_0 per-token dequant cost — the number this arm
exists to record, expected small, sign and magnitude unrecorded today.

**Cross-reference.** flexibility README Q1 already has deepseek f16 at n=2
(86.3/86.4 s, card 5,460 MiB, warm 34.84 tok/s); arms 1–2 re-establish that
baseline same-day so the q8_0 delta is never a cross-day subtraction.

**Runner.** `kv_q8_ab.py` — A/B cold starts of one llama.cpp unit with and
without `-ctk/-ctv`, reading the engine KV line + card + wake + decode. Emits the
compose by patching the existing srv1 deepseek compose (the runner writes the
flag; `make_config.py`/`emit` do not).

## Q5. MLA absorbed-V: the engine's own `V (f16): 0.00 MiB` line *(2 arms)*

**Claim under test.** `ggufscan.py` marks `bailingmoe3` `mla_absorbed_v` and
writes `v_elems: 0` for every KV layer (Ling: `k_elems 576, v_elems 0`,
`key_length_mla 192`), and the docstring says the engine prints `V (f16): 0.00 MiB`.
That line has unit coverage only — the flexibility Q2 arms ran all five Ling
quants and their card figures are *consistent* with `v_elems = 0`, but no arm
ever captured the engine's own KV-cache decomposition to confirm it.

| arm | checkpoint × placement × flags | what |
|---|---|---|
| 1–2 | Ling-3.0-tiny Q4_K_M, `-c 8192 -np 2 -ub 512`, mapped | capture the full KV line |

n=2. Each arm writes the engine's `llama_kv_cache` line verbatim and the card
figure, and cross-checks the card against `vramfit.predict` (which already uses
`v_elems = 0`).

**Expected answer.** The line reads `K (f16): ~56.6 MiB, V (f16): 0.00 MiB` —
V absent, not merely small. The card matches the `v_elems = 0` prediction to the
Q11 margin. If V were cached separately the card would read ~1 GiB higher and
the line would name a non-zero V.

**Cross-reference.** `ggufscan.py` (the `mla_absorbed_v` split and the
`V (f16): 0.00 MiB` quote); flexibility README Q2 (Ling card figures already
consistent with `v_elems = 0`; the engine line was simply never collected).

**Runner.** `mla_absorbed_v.py` — Ling cold start that writes the engine KV-cache
line and the card; the same capture is folded into Q3's Ling arms below, so these
two arms are the belt-and-braces pin at the serving-standard `-ub 512`.

---

# srv2 — 10 arms (Q2, Q4)

(Q3's srv2 cells — the 80B 4 — are in the scratch section below.)

## Q2. vLLM fp8 KV: the actual pool on the refused cell, and the margin *(4 arms)*

**Claim under test.** `--kv-cache-dtype fp8` gives exactly **2.000×** the KV pool
vs fp16, measured once on srv2 q15 (`okf/config/vllm.md:79-93`). But the gate
sizes KV at the fp16 `bytes_per_token` and never reads the flag, so it **refuses
cells that fit** — the 2026-08-31 plan predicted exactly one such refusal
("srv2 q34b at n=32") and the cell ran to n=32 without trouble. What is missing
is the **fp16 control on that same refused cell on srv2** and the **quantified
margin** between the gate's fp16 demand and the fp8 pool that actually exists.

The refused cell is `thewimo/Qwen3-4B-AWQ` (the "q34b" of the vLLM records), the
only one the gate's fp16 sizing pushes over the edge.

| arm | checkpoint × flags | what |
|---|---|---|
| 1–2 | q34b (`thewimo/Qwen3-4B-AWQ`), `util 0.9`, `--max-model-len 2048 --max-num-seqs 128`, kv=auto (fp16) | the missing srv2 control |
| 3–4 | q34b, same, `--kv-cache-dtype fp8` | the pool the gate refuses on |

n=2 each (cold-start flake near the memory edge is a coin flip — retry before
believing a refusal). Every arm reads the engine's own `GPU KV cache size: N
tokens` / `Maximum concurrency …: Xx` lines, the card figure, and one warm decode.

**Expected answer.** fp16 pool **~52,200 tok** (maxconc ~25.5) against fp8
**104,400 tok** (maxconc 51.0) — 2.000× confirmed on the large model, not just
q15. The refused-cell margin is then arithmetic: the n=32 cell needs 65,536
tokens, the fp16-sized gate sees 52,200 and refuses, fp8 actually holds 104,400
and admits it with **38,864 tokens to spare**. The card figure is ~flat
(~11.5 GiB both sides — util backfills freed weight space with KV). The warm
decode is recorded because fp8 KV is **not free**: on Ampere it swaps FLASH_ATTN
for FLASHINFER (`okf/must-read/touching-engine.md`), and the result must not be
attributed to the pool alone.

**Cross-reference.** `okf/config/vllm.md:79-93` (the 2.000× A/B and the gate
refusal); `okf/must-read/touching-engine.md` (fp8 is srv2-only — srv1's cc 7.5
refuses `Minimum capability: 89` — and the backend change);
`records/evidence/serving-2026-08-30/vllm-srv2.json` (q34b = `thewimo/Qwen3-4B-AWQ`);
`records/evidence/2026-09-01-prompt-realism/srv2-ladder-n32.tsv` (fp8 q34b
already 104,400 tok, but with no srv2 fp16 control).

**Runner.** `vllm_fp8_kv.py` — A/B vLLM cold starts of one model with the
`--kv-cache-dtype` toggled, reading the engine pool line + card + decode.

## Q4. Does `C` drift with `--n-cpu-moe`, or was Q11's +38 MiB one arch? *(6 arms)*

**Claim under test.** The `vramfit` module docstring says `C` "does not move with
`--n-cpu-moe`", verified at five placements of one checkpoint. Flexibility Q11
measured the opposite on a *wide* span: `C` drifts **+38 MiB over 33 blocks** on
Qwen3.6/srv2 (ncmoe 7 → 40), while the two narrow groups (4 and 6 blocks) show
exactly 0.00. The open question is whether that drift is **universal** (per
block) or **per-arch** (Qwen3.6's `C` composition). The direction matters: the
drift is positive, so the card holds *more* than the law predicts — the dangerous
direction for a headroom term.

**Why deepseek on srv2.** It is a different arch (`deepseek2` vs Qwen3.6's
`qwen35moe`), has 26 placeable blocks at a **uniform 311.4 MiB each** (no bimodal
confound, unlike Qwen3.6), and spans the card from ~11.6 GiB at ncmoe 0 to
~3.8 GiB at ncmoe 26 — a **26-block** span, the only other checkpoint that can
open one as wide as Q11's 33.

| arm | checkpoint × placement | what |
|---|---|---|
| 1–2 | deepseek-coder-v2-16b, srv2, mapped, `ncmoe 0` | near-full (~0.3 GiB free) |
| 3–4 | deepseek-coder-v2-16b, srv2, mapped, `ncmoe 13` | mid |
| 5–6 | deepseek-coder-v2-16b, srv2, mapped, `ncmoe 26` | all experts off |

n=2 each. Each arm records `vramfit.predict` against the sampler's steady-state
card (net of idle), and `C` is recomputed offline per arm exactly as `headroom.py`
does — the probe is the lowest placement (ncmoe 0), every other arm is predicted
from it, and the spread of `C` is the answer.

**Expected answer.** If universal, deepseek reproduces the per-block drift —
Q11's +38 MiB / 33 blocks ≈ +1.15 MiB/block, so ~**+30 MiB over 26 blocks**. If
per-arch, deepseek's `C` (which is KV-dominated — 2,265 MiB of KV in a ~3.5 GiB
`C`, against Qwen3.6's 168 MiB) holds at 0.00. Either is a result; both settle
the docstring.

**Contingency.** ncmoe 0 is the tightest mapped placement (~0.3 GiB free). If it
flakes at load, ncmoe 1 is card-identical (deepseek's block 0 is dense, so
`--n-cpu-moe 1` moves nothing) and ncmoe 2 buys one 311-MiB block of safety while
keeping the span ≥ 24 blocks.

**Cross-reference.** flexibility README §4 (Q11, the +38 MiB drift and the two
zero-drift narrow groups, all n=2); `headroom.py` (the offline prediction
recompute this runner reuses); `vramfit.py` module docstring (the claim under
test, flagged false-by-33-blocks in the flexibility README's "records made
false").

**Runner.** `c_drift_deepseek.py` — launches the three placements n=2 and records
prediction vs card; `c_drift_report.py` — offline, recomputes `C` per arm and
prints the spread, mirroring `headroom.py`.

---

# Both rigs — 14 arms (the scratch sweep)

## Q3. Compute-scratch / activation curve: three new archs, and the `-ub` law *(14 arms)*

**Claim under test.** `SCRATCH_AND_CONTEXT_MIB = 768` bounds the compute buffer
plus the unnamed device allocation, but only over **four archs** —
`{deepseek2, gptoss, qwen35moe, nemotron_h_moe}` — all at `-ub 256`. The
scratch-vs-`-ub` dependence is **one point** (nemotron 521.2 MiB at `-ub 256`,
652 at `-ub 1024`). Two sub-gaps: (a) three archs on the rigs today have **no**
scratch entry — `bailingmoe3`, `gemma4`, `qwen3next` — and any one of them
exceeding 768 would be the dangerous under-bind; (b) the serving cells run
`-ub 512`, which the bound was never calibrated against.

The measurement is the engine's own `sched_reserve: CUDA0 compute buffer size`
line plus the residue (card − idle − named buffers), per `(arch, -ub)` — the
`records/evidence/2026-09-05-context-decomposition` methodology, through the
door this time.

| arm | checkpoint × arch × `-ub` | what |
|---|---|---|
| 1–2 | Ling-3.0-tiny Q4_K_M (`bailingmoe3`), `-ub 256` | new-arch baseline |
| 3–4 | Ling-3.0-tiny Q4_K_M, `-ub 512` | the serving standard |
| 5–6 | Ling-3.0-tiny Q4_K_M, `-ub 1024` | growth point |
| 7–8 | gemma-4-26B (`gemma4`), `-ub 256` | new-arch baseline |
| 9–10 | gemma-4-26B, `-ub 1024` | growth point |
| 11–12 | Qwen3-Next-80B (`qwen3next`), `-ub 256` | new-arch baseline |
| 13–14 | Qwen3-Next-80B, `-ub 1024` | growth point |

n=2 each. Ling carries the `-ub` curve (three points, the cheap arch); gemma and
the 80B carry a baseline plus one growth point each. Every arm writes the
compute-buffer line verbatim and the steady-state card, net of idle.

**Expected answer.** The compute buffer grows with `-ub` on `bailingmoe3`,
reproducing the law the single nemotron point asserts; each new arch's
scratch+context total lands **under 768** (the bound holds and gains three more
provenances) — or one of them exceeds it, which is the finding that forces a
`MEASURED_SCRATCH_MIB` entry rather than the conservative default.

**Cross-reference.** `vramfit.py:56-93` (the bound, the four-arch provenance, and
the one-point `-ub` claim); `records/evidence/2026-09-05-context-decomposition`
(the `ctx-probe.sh` / `parse-logs.py` methodology this runner reuses); flexibility
README §3 (the card law is exact, but scratch lives inside `C` and has never been
separated on-rig).

**Runner.** `scratch_curve.py` — one cold start per `(arch, -ub)`, capturing the
engine compute-buffer line and the card; `scratch_report.py` — offline, sums
compute + residue per cell against the 768 bound.

---

## Totals

| question | rig | arms |
|---|---|---|
| Q1 — q8_0 KV | srv1 | 4 |
| Q2 — vLLM fp8 KV | srv2 | 4 |
| Q3 — compute-scratch | both | 14 |
| Q4 — `C` drift | srv2 | 6 |
| Q5 — MLA absorbed-V | srv1 | 2 |
| **total** | | **30** |

At the flexibility campaign's observed 4–5 minutes an arm, and the 80B/gemma/
deepseek loads at 100–125 s, that is **roughly three hours of rig time**, run as
one block with the order-of-execution above. The single largest lever on the
budget is Q3; if the owner wants fewer arms, the trim that costs the least
coverage is to drop the 80B `-ub 1024` cell (arms 13–14) or the gemma pair
(arms 7–10) — the bound check on the three new archs is the part that must not go.

**Report when every arm is done and both rigs are idle, not before.** Arm results
land in the run's own `records/measurements/measuring-gaps-2026-09-10/`, not in
the session.
