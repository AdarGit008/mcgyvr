# Cross-engine co-residency, and what a serving memory declaration should be

Run 2026-08-22, both rigs, by hand over ssh using `vllm._start`'s own docker
launch shape so the findings transfer to the harness. Intent header:
`records/headers/2026-08-22-coresidency-feasibility.json`. The decision this
produced is **ADR-0039**.

Rigs before and after: **1 MiB of 6,144 (srv1) and 1 MiB of 12,288 (srv2)**, no
containers, no resident models, declared ollama environment intact. Every figure
below was read off the cards; nothing is scaled or inferred.

Constants throughout: `vllm/vllm-openai:v0.26.0`,
`Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ`, `max_model_len 8192`,
`--enforce-eager`, ollama 0.32.15 serving `qwen2.5-coder:1.5b`.

## 1. It works

| rig | order | vLLM | ollama | ollama fraction |
|---|---|---|---|---|
| srv2 | vLLM then ollama, `util 0.30` | 3,636 MiB | 1,238 MiB | **1.000** |
| srv2 | ollama then vLLM, `util 0.30` | 3,636 MiB | 1,238 MiB | **1.000** |
| srv1 | vLLM then ollama, `util 0.30` | 1,720 MiB | 1,196 MiB | **1.000** |

Both engines answered a real prompt alone and **concurrently**, correct output
every time, vLLM `/health` 200 throughout, and the card total was byte-identical
before and after generating.

**Load order changed nothing at 0.30 on srv2** — the same 4,889 MiB total and
the same per-process split either way.

**`gpu_memory_utilization` is a fraction of *total* VRAM, not free VRAM.** In
the ollama-first cell, vLLM took 0.296 × 12,288 with 1,247 MiB already held by
a neighbour it did not account for. Confirmed against vLLM's own source
(`v1/worker/utils.py::request_memory`): the budget is
`ceil(total_memory × util)` with a hard `free >= requested` precondition. A
neighbour does not shrink the budget — it makes vLLM refuse to start.

## 2. The shipped 0.85 breaks co-residency silently, on both cards

| rig | vLLM held | ollama held | ollama fraction | ollama `load_http` |
|---|---|---|---|---|
| srv2 | 10,188 MiB | 684 MiB | **0.495** | **200** |
| srv1 | 4,912 MiB | 146 MiB | **0.068** | **200** |

srv1's cell reproduces, to the megabyte, the defect `backends/ollama.py`'s own
docstring records: *"a foreign 4,916 MiB allocation, the model placed at
fraction 0.08, and `ok: True`"*. Measured here: 4,912 MiB, fraction 0.068.

**The spilled model still answers correctly.** At fraction 0.068 it returned
working code in 4 seconds. Not the output, not the status, not a casual look at
the wall-clock distinguishes it. Only `size_vram / size` names it.

### Why ollama spills instead of refusing

From ollama 0.32.15's source, not from behaviour. `size_vram` is llama.cpp's
**measured** report — `total, vram := r.llama.MemorySize()` overwrites the
scheduler's estimate in `server/sched.go`, so these numbers are measurements.
The pre-flight fit check in the same file is guarded by `len(s.loaded) > 0` —
**ollama's own loaded models**. A foreign process is not in that set, so no
check runs and, as the source comment says, *"llama-server auto-detects layers
based on available VRAM"*: it fits itself into whatever is left.

Neither `OLLAMA_GPU_OVERHEAD` (default 0) nor `LLAMA_ARG_FIT` /
`LLAMA_ARG_FIT_TARGET` (auto-fit default **on**) is set on either rig. That is
the silent-spill configuration, and whether to change it is open.

## 3. What the declaration allocates

Reachable KV cache is `max_num_seqs × max_model_len × bytes_per_token`, and
`bytes_per_token` for this model is **28,672** — 28 layers × 2 KV heads × 128
head_dim × 2 (K and V) × 2 bytes (fp16). vLLM's own allocation confirms it:
3.5 GiB over 131,104 tokens is 28,665 B/token, the shortfall being block
padding.

| declaration | rig | KV tokens | vLLM's concurrency line | card |
|---|---|---|---|---|
| `util 0.85`, seqs 8 | srv1 | 131,104 | 16.00x — **cap is 8** | 4,916 MiB |
| `util 0.85`, seqs 8 | srv2 | 322,304 | 39.34x — **cap is 8** | 10,197 MiB |
| `util 0.85`, seqs 16 | srv1 | 131,088 | 16.00x | 4,956 MiB |
| `util 0.85`, seqs 16 | srv2 | 322,304 | 39.34x | 10,219 MiB |
| `kv 1,879,048,192`, seqs 8 | srv1 | 65,536 | 8.00x | **3,130 MiB** |
| `kv 1,879,048,192`, seqs 8 | srv2 | 65,536 | 8.00x | **3,183 MiB** |
| `kv 3,758,096,384`, seqs 16 | srv1 | 131,072 | 16.00x | **4,986 MiB** |
| `kv 3,758,096,384`, seqs 16 | srv2 | 131,072 | 16.00x | **5,041 MiB** |

Non-KV memory is stable across every row: 1.1 GiB weights, 0.13 GiB peak
activation, 0.04 GiB (srv1) / 0.05 GiB (srv2) non-torch, 0.0 GiB CUDAGraph.

**What 0.85 costs at `max_num_seqs 8`: 1,786 MiB on srv1 (2.0x the reachable KV
cache) and 7,014 MiB on srv2 (4.9x).**

Below one `max_model_len` sequence the engine refuses cleanly rather than
degrading — `--kv-cache-memory-bytes 200000000` raised
*"0.22 GiB KV cache is needed, which is larger than the available KV cache
memory (0.19 GiB)"*, naming the shortfall and the largest model length that
would have fitted.

**And the fix works where 0.85 failed.** With `kv 1,879,048,192` declared, srv1
holds vLLM at 3,126 MiB and `qwen2.5-coder:1.5b` at **fraction 1.000** —
4,326 MiB of 6,144 — the same cell that read 0.068 under the fraction.

### Two consequences beyond the waste

**A fraction cannot express a per-model requirement.** The same 1,792 MiB is
`util 0.565` on srv1 and `0.273` on srv2. One number cannot be right for two
cards, and a declaration restated per rig is one that drifts per rig.

**Under a fraction, `max_num_seqs` stops being a declared parameter.** The KV
budget is `total × util − non_kv`; width enters only through activation, which
moved the srv1 figure by 16 tokens out of 131,104. So `q15-vllm-s8` and
`q15-vllm-s16` — two entries whose entire difference is their width — allocated
the same KV cache. Under the byte declaration they differ by 1,856 MiB.

### This bears on #329

At the declared 0.85 with `max_num_seqs 16`, **srv1 gets 131,088 KV tokens
against the 131,072 that width 16 requires — a margin of 16 tokens, 0.012%** —
while srv2 gets 322,304, a margin of 146%. The two arms of the width-16
cross-rig contrast are **2.46x apart in KV cache** from one declared setting,
and no row records it. #329 asks whether the width-16 gap is hardware or
configuration. This does not answer that. It removes the assumption that the
configuration was equal, which "hardware, not configuration" rested on.

## 4. Contention is real, large, and a property of the card

Both engines generating simultaneously, n=3, median. The pair is fully resident
in every row — this is not spill.

| rig | ollama solo → concurrent | vLLM solo → concurrent |
|---|---|---|
| **srv1** (GTX 1660 SUPER, Turing) | 156.3 → 41.5 tok/s — **3.8x slower** | 45.1 → 33.9 — 1.33x |
| **srv2** (RTX 3060, Ampere) | 197.0 → 141.0 tok/s — **1.40x slower** | 34.4 → 33.9 — 1.01x |

**The contention cost differs 2.7x between the two rigs.** A co-residency
throughput figure is therefore per-rig and does not travel — ADR-0038 D1 and D5
confirmed by measurement rather than by argument.

**Bounds on this claim.** n=3, one prompt, one model pair, one quantization.
ollama's rate is its own `eval_duration` (generation only); vLLM's is curl
wall-clock including connection and prefill, so **solo-against-concurrent within
each engine is sound and engine-against-engine is not**. `--enforce-eager` is
declared, which disables CUDA graphs, so the vLLM figures are not that engine's
best. Nothing here is a throughput result about either engine; it is a result
about whether sharing costs anything, and it does.

## 5. Claims this run refuted

- **"vLLM subtracts memory other processes already hold."** Widely repeated;
  false for v0.26.0. It does not subtract — it refuses to start.
- **"Sharing a card costs nothing while both models fit."** Written earlier in
  this lane's session and wrong: it was measured with the neighbour idle. Under
  concurrent load it costs 3.8x on srv1.
- **"The wall-clock does not distinguish a spilled model."** Also written
  earlier in this lane and wrong: 0.67 s against 3.73 s for the same 128 tokens.
  What does not distinguish it is the HTTP status and the correctness of the
  output.
- **The withdrawn campaign header's `void_if` on ollama version skew** (srv1
  0.32.4, srv2 0.32.5). Both rigs run 0.32.15, declared and checked.

## The serving-pin re-baseline: which cells are now incomparable to which

#337 asks this to be recorded rather than assumed. **The answer is that the
population is empty, in both senses, and both are checkable.**

**Behaviourally: zero recorded cells.** The declaration changed in
`configs/srv-full.json`, and no journal row in this repository was ever produced
by that config. Every labelled row in `d7-survey.json.jsonl` (17, all ollama)
carries a `d7-campaign.json` label; every vLLM row in `d7-ramp.jsonl` (10) and
`samples.jsonl` (30) came from `calibrate.py`'s two inline serve blocks, which
still declare `gpu_memory_utilization 0.85` and are parked as a dated xfail
against #329. So nothing already measured was launched under a declaration that
moved, and no past figure changes meaning.

**By the pin: zero recorded rows too.** `harness_sha256` digests the whole of
`tools/bench/serving`, so today's edits to `backends/vllm.py` and
`configs/srv-full.json` do move it — but

    provenance keys present across ALL journals: NONE

No row in any journal carries `commit`, `tree_dirty`, `harness_sha256`,
`config_sha256`, `run_started_at` or `argv`. Those fields arrived with #325 and
no campaign has run since. There is nothing to re-baseline *against*.

**What this actually costs is forward, not backward.** The first campaign to run
after today is the first to carry a pin at all, and it will be the baseline
rather than a re-baseline. The obligation this leaves is on `calibrate.py`: its
two inline blocks are the one place where a future run would be launched under
the withdrawn fraction, and converting them is what makes every vLLM cell in the
tree comparable to every other. That is #329's arm, and it is named there.

## What this closes and what it opens

**Closes.** #337's measurement, and K10 with it — the constant is now derived
from the entry's own shape and its footprint measured on both cards, so it is
this project's choice and says so. ADR-0039 is the record; `srv-full.json`
carries the origin note; `tests/test_serving_memory_declaration.py` holds it,
mutation-swept 6 of 6.

**Opens.**

- Whether `OLLAMA_GPU_OVERHEAD` / `LLAMA_ARG_FIT` should be set so ollama
  refuses instead of spilling. That changes declared host state (#328).
- `bytes_per_token` exists for one model. ADR-0039 requires one per model, and
  the co-residency campaign's phase 0 needs the roster.
- Whether #329's width-16 arm is re-run under byte declarations.
- The two `serve` blocks built inside `calibrate.py` still carry the fraction,
  parked as a dated xfail against #329.
