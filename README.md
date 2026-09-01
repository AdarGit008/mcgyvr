# Prompt Realism — the sweeps measured a workload we do not run (2026-08-31)

**Question.** Every serving number in `records/` was produced by sending one fixed
11-token prompt and a flat 475-token reply. Real mcgyvr traffic is the other shape.
How wrong is the measurement, and what does the honest one look like?

**Status: run 2026-09-01, both rigs.** Full n=1..32 vLLM ladders on srv1 and srv2,
a paired fp8 KV A/B, and every 2026-09-01 artifact row re-measured. Results in
`records/evidence/2026-09-01-prompt-realism/`.

**The answer: the old sweeps overstate real-traffic throughput by ~2.4x at n=8.**
New/old at that rung is 0.41-0.48 in every cell measured, across two rigs, two KV
dtypes and three model sizes. The two workloads agree at n=1 and diverge as
concurrency rises, because real prompts put prefill in contention with decode and
an 11-token prompt has none to contend.

## The finding

Prior drivers (`vllmsweep28.py`, `lcpsweep28.py`, and every ancestor back to
2026-08-24) sent:

- `PROMPT = "Write a Python function that merges two sorted lists."` — ~11 tokens,
  **byte-identical on every request of every level of every cell**
- `max_tokens/n_predict = 475` with `ignore_eos`, so every reply was exactly 475 tokens

That is **1:43 prompt:output**. Measured from `measurements/**/results.jsonl`
(n=21342 dedup'd rows, `results.jsonl` only — `gate-rescore.jsonl` and
`regrade.jsonl` are the same records rescored):

| | prior sweeps | real traffic |
|---|---|---|
| prompt tokens | ~11, one shared string | mean 719, p50 688, p95 ~1035, max 2414 |
| output tokens | 475 flat, `ignore_eos` | mean 236, p50 189, p95 ~583, max 2048 |
| prompt:output | **1 : 43** | **3 : 1** |

So `agg=` in every prior record is a **decode-throughput ceiling**, and decode is the
minority of real work. This was disclosed, not hidden — `gen_rows.py:23` and
`build.py:311` both carry `workload="475-tok, ignore_eos, temp0, fixed prompt"` —
but it was never corrected.

## What the new drivers do

`vllm_sweep_31-08-2026.py`, `lcp_sweep_31-08-2026.py` and
`vllm_cores_01-09-2026.py` share a
byte-identical workload block (deciles + `SYSTEM` + `mkprompt`), `sha256[:16] = dfb1172670619c5d`. **If that hash diverges between the files, the cross-engine
comparison is void.**

That hash is over *source text*, so a `ruff format` pass moves it even when the
workload is identical — it did exactly that in 90635351. The durable check is a
digest of the generated prompts, which no formatter can change:

```
python3 - <<'EOF'
import hashlib, itertools, threading, random
def load(p):
    src = open(p).read()
    ns = {"itertools": itertools, "threading": threading, "random": random}
    exec(src[src.index("PROMPT_DECILES"):src.index("def sh(")], ns)
    return ns["mkprompt"]
for f in ["vllm_sweep_31-08-2026.py", "lcp_sweep_31-08-2026.py",
          "vllm_cores_01-09-2026.py"]:
    mk = load(f)
    blob = "".join(f"{w}\x00{t}\x1e" for t, w in (mk() for _ in range(200)))
    print(f, hashlib.sha256(blob.encode()).hexdigest()[:24])
EOF
```

All three must print `2f2bb7932a0b660653def819`.

1. **Lengths sampled from the measured deciles**, seeded by request id — so request
   *k* always draws the same length, reproducible across levels and reruns, without
   collapsing to a constant. Verified over 512 requests: prompt mean 699 / p50 688,
   output mean 226 / p50 189, ratio 3.1:1.
2. **`ignore_eos` removed.** The sampled length is a ceiling; the model may stop
   earlier, as in production. `truncated=` therefore no longer means anything and is
   replaced by `early_stop=` (model chose to stop) and `failed=` (request errored) —
   the old single counter conflated the two and would report a failure as a short reply.
3. **A real shared prefix.** `bench-scaffold-ablation-3b-2026-08-11` measures the
   scaffold directly: stock p50 929 vs noscaffold p50 739 (py), 936 vs 729 (ts) —
   **~190–207 tokens identical on every request**. `SYSTEM` reproduces that, followed
   by a unique task body. Prefix caching then gets the hits it gets in production:
   not zero (unique-at-head is too pessimistic), not total (one fixed prompt — the old bug).
4. **`prefill=` is reported.** Prior drivers could not measure prefill at all; the
   prompt was ~11 tokens. `ptok=` and `otok=` are reported per level so every row
   self-describes its own workload.

## Two changes that move results on their own

- **`cache_prompt: False` → `True`** in the llama.cpp driver. `lcpsweep28.py:18`
  disabled prompt reuse while the vLLM driver left automatic prefix caching **on** —
  the two engines were never measured under the same caching rules. With one fixed
  prompt that was a wash; with a real shared scaffold it is not. Both now cache.
- **Context 1024 → 2048.** Worst sampled prompt (887) + worst sampled reply (460) =
  1347 > the 1024 every prior cell used. Both drivers hard-`SKIP` a cell under 1347
  with the reason printed, rather than silently truncating the tail. This doubles KV
  per sequence, which moves the memory axis the sweep measures.

## Pinned images

Both images are pinned and printed on every `CONFIG` row as `img=`, so a result
file says which binary produced it:

| engine | pin | override |
|---|---|---|
| vLLM | `vllm/vllm-openai:v0.26.0` | `VLLM_IMG=` |
| llama.cpp | `ghcr.io/ggml-org/llama.cpp:server-cuda-b10644` | `LCP_IMG=` |

`lcpsweep28.py` used the floating `:server-cuda` tag, so two runs a month apart
could not be compared — the binary could differ with nothing in the record to say
so. b10644 is the build the 2026-08-28 setup-selection sweep actually ran
(`records/evidence/2026-08-28-setup-selection/drivers/run-srv{1,2}.sh`),
which is the sweep this supersedes.
Override by environment, never by editing the line.

## Calibration

`TOK_PER_FIELD = 32` is an estimate. Run one cell at `n=1`, read `warm_ptok=`, and
tune until it lands near 688 before running anything long. Checked 2026-09-01 on
srv2: `warm_ptok=711` against the 688 target, so 32 stands and was not changed.

## Run list (ran 2026-09-01)

```
srv2 vllm:  q15 / q3 / q34b   0.9:2048:128:fp8:1,2,4,8,16,32     all 18 rungs
srv1 vllm:  q15 / q3 / q34b   0.9:2048:128:auto:1,2,4,8,16,32    15 rungs, 3 dropped
```

**srv1 runs `auto`, not `fp8`** — its 1660 SUPER is compute capability 7.5 and
vLLM's fp8 KV path needs 89, the refusal `nem4` hit on 2026-08-31. The `vllm-14b`
line this list used to carry has no checkpoint in either rig's cache; srv1's
committed cells are q15/q3/q34b, with q7 already a recorded refusal.

The three dropped rungs are srv1's q34b at n=8/16/32: its KV pool holds 12,816
tokens = 6.3 concurrent requests at `len=2048`, so those rungs would queue rather
than saturate. The driver drops only the rungs the pool cannot hold and prints a
`WIDTH` row naming them — refusing the whole cell would throw away the honest
rungs, and measuring the tail anyway would record a queue as a plateau.

Still outstanding: the llama.cpp halves of this list, and co-residency.
