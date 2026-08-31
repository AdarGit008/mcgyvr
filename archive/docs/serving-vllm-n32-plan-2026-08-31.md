# Next run: vLLM to n=32, co-residency, and the smartest MoE each rig can hold

Planned 2026-08-31, while both rigs were unreachable. Supersedes nothing; the
2026-08-30 llama.cpp grid still has five cells outstanding and is tracked
separately in `records/evidence/serving-2026-08-30/RESUME.md`.

Four asks: **vLLM only**, **extend the ladder to n=16 and n=32**, **serve more
than one model per rig**, **find each rig's smartest MoE**.

---

## 0. The one thing that will silently ruin this run

**vLLM states `max_num_seqs` nowhere on the wire.** `backends/vllm.py` says so
in three places (lines 32, 822, 1669) and `declared_slots()` records it as
*dispatched, not observed*. llama.cpp has `/props total_slots`, so the
`--parallel 4` trap from 2026-08-30 was catchable by readback. **On vLLM it is
not.**

Every current entry declares `max_num_seqs: 8`. Left at 8, an n=16 or n=32 ramp
queues at the scheduler and produces a plateau that is indistinguishable from
saturation — the same false result as the `--parallel` default, with no
`/props` to catch it.

So: **`max_num_seqs` must equal the top of the ladder in every entry**, and the
run needs a substitute for the readback it does not have. Two candidates, both
cheap:

1. vLLM's startup log states the KV cache capacity it actually allocated, in
   blocks and in tokens. `max_num_seqs x max_model_len` must be at or below it.
   Capture that line the way `weights_bytes` already captures `Model loading
   took`, and assert it.
2. A ramp whose per-stream rate falls exactly 2x between n=16 and n=32 while
   wall clock doubles is queueing, not saturating. That shape is worth an
   explicit check rather than an eyeball.

Recommend both. Item 1 is the real guard; item 2 catches what item 1 misses.

---

## 1. What the ladder costs, per cell

KV requirement, as the gate computes it
(`max_num_seqs x max_model_len x bytes_per_token`, `_ways_out()`):

| cell | B/token | KV @ n=8 | @ n=16 | @ n=32 |
|---|---:|---:|---:|---:|
| q15 | 28,672 | 448 MiB | 896 MiB | 1,792 MiB |
| q3 | 36,864 | 576 MiB | 1,152 MiB | 2,304 MiB |
| q7 | 57,344 | 896 MiB | 1,792 MiB | 3,584 MiB |
| q34b | 147,456 | 2,304 MiB | 4,608 MiB | 9,216 MiB |

All at the declared `max_model_len: 2048`. **Keep 2048.** Shortening it is the
other way out the gate offers, and it would make the new ladder incomparable
with the committed n=1..8 rungs — which is the whole point of extending rather
than re-running.

Projected footprint is `measured footprint at n=8 - KV at n=8 + KV at n`. The
base (weights + engine residue) is what the 2026-08-30 measurements pin.

**srv1** — ceiling 5,743 MiB (6,144 less the 401 MiB GSP reserve), fp16 KV,
`--enforce-eager`, TRITON:

| cell | base | n=8 | n=16 | n=32 |
|---|---:|---:|---:|---:|
| q15 | 1,306 | 1,754 ✓ | 2,202 ✓ | 3,098 ✓ |
| q3 | 2,210 | 2,786 ✓ | 3,362 ✓ | 4,514 ✓ |
| q34b | 2,934 | 5,238 ✓ | **7,542 ✗** | **12,150 ✗** |

**srv1's q34b stops at n=8.** Record n=16 and n=32 as refusals with the
arithmetic, the way `q7-vllm-srv1` is already recorded. A refusal is the
measurement.

**srv2** — ceiling 11,908 MiB, `--kv-cache-dtype fp8`, FLASHINFER:

| cell | base | n=8 | n=16 | n=32 |
|---|---:|---:|---:|---:|
| q15 | 1,841 | 2,289 ✓ | 2,737 ✓ | 3,633 ✓ |
| q3 | 2,747 | 3,323 ✓ | 3,899 ✓ | 5,051 ✓ |
| q7 | 6,189 | 7,085 ✓ | 7,981 ✓ | 9,773 ✓ |
| q34b | 3,351 | 5,655 ✓ | 7,959 ✓ | **12,567 ✗** |

**srv2 gets every rung except q34b at n=32.**

### The fp8 question, unresolved and worth one launch

`kv_cache_memory_bytes` is a pool size in bytes. `--kv-cache-dtype fp8` should
double the tokens that pool holds, so srv2 might reach n=32 on q34b inside the
existing budget. But the gate's requirement never divides by the dtype — one
mention of fp8 in all of `vllm.py`, and it is a comment — so it will demand the
fp16-sized pool and refuse.

The residue arithmetic backs the gate: srv2's base for q15 computed against the
**full declared pool** is 1,841 - 1,126 = 715 MiB of residue, which lands exactly
on the documented 715-791 MiB window. Computed against a halved pool it gives
939 MiB, outside it. So the pool appears to be allocated as declared regardless
of dtype, and the tables above are right.

**Settle it by measurement, not by this paragraph.** One launch of q15 on srv2
at `max_num_seqs 32`, reading the engine's own KV-capacity line, says whether
the pool holds 32 x 2048 tokens or 64 x 2048. Do it in Phase A; it costs one
model load.

---

## 2. Co-residency: which pairs actually fit

The harness already supports this — `coresident` and `coresident_with` in
`run.py:310`, honoured by the vLLM backend (`vllm.py:700`), with a worked
example at `configs/d7-campaign.json:263`. No code is needed, only entries.

`coresident_with` is the field that matters. Mistyped, the entry measures
**solo** under a co-residency label and nothing looks wrong (`run.py:296`).
Assert the neighbour was actually resident, per cell.

**srv1 has exactly one viable pair.**

| pair | n=8 each | n=16 each | n=32 each |
|---|---:|---:|---:|
| q15 + q3 | 4,540 ✓ | 5,564 ✓ *(179 MiB spare)* | 7,612 ✗ |
| q15 + q34b | 6,992 ✗ | ✗ | ✗ |
| q3 + q34b | 8,024 ✗ | ✗ | ✗ |

Run **q15+q3 at n=8** as the headline srv1 co-residency cell. n=16 fits on
paper with 179 MiB of margin, which is inside the run-to-run noise of a measured
footprint — schedule it, expect it to be the cell that teaches you where the
real edge is, and let it refuse rather than tuning it until it passes.

**srv2 has room to be interesting.**

| pair | n=8 each | n=16 each | n=32 each |
|---|---:|---:|---:|
| q15 + q3 | 5,612 ✓ | 6,636 ✓ | 8,684 ✓ |
| q15 + q34b | 7,944 ✓ | 10,696 ✓ | ✗ |
| q3 + q34b | 8,978 ✓ | 11,858 ✓ *(50 MiB)* | ✗ |
| q15 + q7 | 9,374 ✓ | 10,718 ✓ | ✗ |
| q3 + q7 | 10,408 ✓ | 11,880 ✓ *(28 MiB)* | ✗ |
| q34b + q7 | 12,740 ✗ | ✗ | ✗ |
| q15 + q3 + q34b | 11,267 ✓ *(641 MiB)* | ✗ | ✗ |

Recommended srv2 set, four cells: **q15+q3 at n=8 and at n=32** (the pair that
survives the whole ladder, so co-residency cost can be read across concurrency),
**q15+q7 at n=8** (small beside large), and **q15+q3+q34b at n=8** (three-way,
641 MiB spare — the interesting one).

Drop the 28-50 MiB cells. They are not experiments, they are coin flips.

**What co-residency is measuring.** Not "does it fit" — the arithmetic above
answers that. The question is what a neighbour costs the incumbent: run each
model solo at the same n first, then beside its neighbour, and report the delta
in `tokens_per_s`. The solo halves already exist for n=8 in
`records/evidence/serving-2026-08-30/vllm-*.jsonl`, so only the paired halves
are new at that rung.

---

## 3. The smartest MoE each rig can hold

**This one is blocked on an inventory I cannot take** — both rigs were offline
when this was written, and every MoE the repo knows about is a GGUF path under
`/home/adaramir/models/moe/` (`m_dsv2`, `m_gemma4`, `m_ling`, `m_oss20`,
`m_kat`, `m_next`, `m_qc30`, `m_q36iq2/3`). Those are llama.cpp checkpoints.
vLLM needs AWQ, GPTQ, or an MXFP4/fp16 checkpoint it recognises, and none of the
committed vLLM entries is an MoE.

So Phase D starts with a question, not a config:

```bash
for h in srv1 srv2; do
  ssh $h 'ls -la /home/adaramir/models/ && du -sh /home/adaramir/models/*/* 2>/dev/null | sort -h'
done
```

**The filter is the ceiling, and it is brutal.** srv1 allows 5,743 MiB total —
weights, KV, and engine residue. srv2 allows 11,908 MiB. Against that:

- A 4-bit AWQ of a 30B-A3B class MoE is roughly 16-17 GiB of weights alone.
  Over srv2's whole card. Not a candidate on either rig.
- A 20B MXFP4 MoE is roughly 12-13 GiB. Also over srv2's ceiling.
- The 16B-class lite MoEs (A2-3B active) at 4 bit land near 9-10 GiB. **These
  are the only plausible srv2 candidates**, and they leave roughly 2 GiB for KV
  and residue — which caps the ladder well below n=32.
- **srv1 probably has no vLLM MoE at all.** 5.7 GiB does not hold a 4-bit 16B.
  If the inventory confirms that, *the refusal is the finding* — record it with
  the arithmetic and stop. srv1's MoE story is already told in llama.cpp, where
  `m_ling` scales 2.27x precisely because it is small enough to stay resident.

Note the trap this walks toward. §8 of the 2026-08-30 runbook already settled
that **`--cpu-offload-gb` is inert on vLLM for AWQ** — three launches at 0/4/6
GiB each loaded 9.38 GiB and each OOMed. There is no discount available to make
a too-large MoE fit. A gate that offered one was written and removed the same
day. Do not reopen it.

**Recommendation:** treat "smartest MoE" as one measured cell on srv2 and one
recorded refusal on srv1, and do not let it hold up Phases A-C.

---

## 4. Order of work

Phase A is not optional. Every new shape — a new `max_num_seqs`, a co-resident
pair, an MoE — has no measured `_footprint_mib`, and
`test_every_declared_footprint_fits_its_host_allocatable_ceiling` will not let
one be invented. The repo already has the two-phase pattern for exactly this:
`records/evidence/2026-08-23-phase0-footprint` then `-phase0-refit`.

| phase | what | cost |
|---|---|---|
| **A. footprint** | load each new shape once, read `Model loading took` and steady-state `nvidia-smi`, back-fill `_footprint_mib`. Settles the fp8 question. No ramp. | ~1 min/shape |
| **B. ladder** | n=1,2,4,8,16,32 solo, `max_num_seqs` at 32. 3 cells srv1, 4 cells srv2. | the bulk |
| **C. co-residency** | 1 cell srv1, 4 cells srv2, paired against the solo rungs from B. | moderate |
| **D. MoE** | inventory first, then at most one srv2 cell and one srv1 refusal. | unknown |

Phases A and B are worth committing before C starts. C's value depends
entirely on B's solo numbers being trustworthy.

## 5. Before any of it

Both rigs dropped off mid-run twice on 2026-08-31, with an idle Mac dropping in
the same window. Until that is understood, this run will lose cells the same way
the last one did. **The preflight must be a `tailscale ping`, not a
`tailscale status` read** — status reported the Mac offline while it answered
pings from the same host, so the status field is not evidence.

Nothing in this plan is worth starting on a rig that has not just answered.
