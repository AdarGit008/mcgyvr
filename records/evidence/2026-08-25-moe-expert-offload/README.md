# MoE expert offload: what the serving knob is, and what it is not

Measured 2026-08-25 on srv1 and srv2. Intent header:
`records/headers/2026-08-25-moe-expert-offload.json` (retroactive — the
measurements began before the header was filed, and the header says so).

**One model throughout unless a row says otherwise:** `qwen3-coder:30b`, Q4_K_M,
**18,556,688,736 bytes**, MoE with ~3 B parameters active per token. The file was
copied from srv2's ollama blob to `srv1:~/ggufs/qwen3-coder-30b.gguf` by `rsync`,
so both rigs served **byte-identical weights** rather than two downloads.

Engines: `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481` and
`vllm/vllm-openai:v0.26.0`, the digests already pinned in
`../2026-08-24-engine-sweep/README.md`, identical on both hosts. Rates are each
engine's own timing counters (`timings.predicted_per_second` for llama.cpp,
`usage.completion_tokens` over wall for vLLM), temperature 0.

## What this record is for, and what it deliberately leaves out

This is a **serving-knob measurement**, in the line of
`../2026-08-22-coresidency-feasibility/` and `../2026-08-24-engine-sweep/`: what a
declared configuration does on a card, and which declarations are refused. It
belongs here for the same reason those do — ADR-0038 withdrew ADR-0024's roles so
a cross-rig question could be asked at all, and ADR-0039/0040 already turn
placement into a declared quantity.

**It is not a hardware recommendation.** The session that produced these numbers
also produced a ranked buy list — RAM, GPU, CPU and motherboard plays with prices.
That half is host-shopping and stays out of this repo by the standing boundary:
mcgyvr states the contract, not which host to buy. It lives with the owner, off-repo.

What survives the boundary is the part a rung has to reason about: **a MoE model's
placement is a declaration with a measurable cost curve, the curve is not
monotone, and the engine flag that fixes one rig breaks the other.**

## 1. Placement is the rate, and `--n-cpu-moe` is how it is declared

`--n-cpu-moe N` keeps attention, KV cache and embeddings on the card and puts the
expert FFN weights of `N` layers in system RAM. ollama cannot express it
(ollama/ollama#11772); it splits whole layers only.

Pre-swap, both rigs, `-ngl 99 -c 4096 -fa on`, 128 tokens after a 32-token warm-up:

| `--n-cpu-moe` | srv1 tok/s (card MiB) | srv2 tok/s (card MiB) |
|---|---|---|
| 48 | 21.60 (1,472) | 15.07 (1,519) |
| 44 | 25.37 (2,966) | — |
| 40 | 25.43 (4,410) | 17.80 (4,457) |
| 32 | — | 20.73 (7,197) |
| 24 | — | 26.32 (9,889) |
| 20 | — | **31.57 (11,283)** |
| 36 | **refuses** — 6 GB card full | — |

**An 18.56 GB model serves from 1,472 MiB of VRAM at 21.6 tok/s.** Card capacity
is not what decides whether a MoE of this class runs; it decides how fast it runs.

**Against ollama at equal card usage:** `--n-cpu-moe 20` read 31.57 tok/s at
11,283 MiB against ollama's automatic split at 28.19 tok/s and 10,787 MiB — **+12%
for a flag**, no hardware involved.

## 2. The cross-rig gap is memory channels, and two experiments say so

At matched card usage srv1 was ahead in every pair: 21.60/15.07 and 25.43/17.80
(both **1.43×**), 9.85/6.95 at a single thread (**1.42×**), and a repeat of the
first pair at 23.93/15.07 (**1.59×**). srv1's own spread on that cell is ~10%, so
the honest figure is **1.4–1.6×**, clustered at 1.43. The card is the *weaker* one
in every pair.

Two controls on srv2 alone remove the alternatives:

| srv2, `--n-cpu-moe 48` | turbo off (2.8 GHz) | turbo on (5.2 GHz) | clock worth |
|---|---|---|---|
| decode, 4 threads | 15.26 | 15.69 | +2.8% |
| decode, 10 threads | 14.63 | 15.07 | +3.0% |
| decode, at `--n-cpu-moe 20` | 31.57 | 31.67 | **+0.3%** |
| prefill, 4 threads | 25.8 | 28.7 | +11% |

srv2 boots with `no_turbo=1` and RAPL PL1 at 65 W. **Nearly doubling the clock
moved decode under 3%**, and package power peaked at 40.0 W against that 65 W
limit, so the cap was never the binding term. Prefill, which is compute-bound,
did gain.

Thread scaling says the same from the other side. srv2: 6.95 / 12.33 / 15.26 at
1, 2, 4 threads, then flat (10 → 14.63, 20 → 15.72) — **16 of 20 threads
contribute nothing**. srv1, with twice the bandwidth to feed, climbs to all six:
9.85 / 16.79 / 22.46 / 23.49 / 23.93.

**Decode under expert offload is memory-bandwidth-bound. Clock and cores are not
the lever.**

## 3. `--no-mmap` is a fix for a RAM shortage, not an optimisation

srv2's memory was later changed from 32 GB single-channel to 16 GB dual-channel
(STREAM triad 13.3 → **23.8 GB/s**, 1.79×; srv1 unchanged at 26.8 GB/s). **Every
srv2 cell got slower**, e.g. `--n-cpu-moe 20` 31.57 → 26.28.

The cause was measured, not inferred: **821 MB/s of sustained NVMe reads during
decode** (4,107 MB in 5 s) with 207 MB free and page cache pinned at maximum. An
18.56 GB mmap in 15.4 GB of RAM re-reads itself per token. llama.cpp's own load
log had said so: *"tensor overrides to CPU are used with mmap enabled — consider
using `--load-mode none`"*.

| `--n-cpu-moe` | pre-swap (mmap) | post-swap (mmap) | post-swap `--no-mmap` |
|---|---|---|---|
| 20 | 31.57 | 26.28 | **42.86** |
| 24 | 26.32 | 20.71 | 37.53 |
| 32 | 20.73 | 13.26 | 33.28 |
| 40 | 17.80 | 11.75 | 25.57 |

**On srv1 the same flag is consistently worse** — 18.89 / 20.47 / 22.19 against
23.08 / 24.66 / 25.21 at `--n-cpu-moe` 48 / 44 / 40, a 12–18% loss. srv1 has 48 GB;
the mapping never thrashes, so the flag only adds a copy.

**A serving flag that is correct on one rig and wrong on another is a property of
the declaration, not of the engine.** Anything that records a configuration has to
record the host's memory alongside it or the row does not reproduce.

### A measurement that was wrong, and why

Before the swap, a `docker --memory=15g` cell reported **no penalty**
(`--n-cpu-moe 20`: 31.55 capped against 31.43 uncapped). That test was invalid: the
GGUF was already in the **host** page cache from earlier runs and charged outside
the cgroup, so the limit never forced an eviction. It is kept in
`raw-postswap-squeeze-concurrency.txt` as a recorded wrong result. A cgroup memory
cap does not simulate a smaller machine when the file is already cached on the
larger one.

## 4. The curve is not monotone at the edge

Pushing more experts onto the card keeps paying until it abruptly does not:

| srv1, f16 KV, `-t 5` | tok/s | card MiB |
|---|---|---|
| `--n-cpu-moe 40` | 25.82 | 4,410 |
| `--n-cpu-moe 39` | 26.00 | 4,734 |
| **`--n-cpu-moe 38`** | **26.83** | 5,108 |
| `--n-cpu-moe 37` | 26.34 | 5,444 |
| `--n-cpu-moe 36` | refuses | — |

**37 is slower than 38 while still loading.** With ~700 MiB of headroom left, what
the working space costs exceeds what the extra GPU layer returns. A search that
assumes monotonicity and walks to the refusal picks the wrong cell.

Quantised KV cache does not rescue it. `q8_0` frees ~180 MiB — under half a
layer — and costs more than it frees on both rigs: srv1 26.40 against 26.83
(−1.6%), srv2 44.10 against 45.20 (−2.4%). It does let srv2 *load*
`--n-cpu-moe 18` (42.27), which f16 refuses, and that cell is still slower than 20.
srv2 refuses 16 and 14 even at `-c 2048`.

## 5. Concurrency: dense batches ~30×, expert offload batches ~2×

vLLM, historical protocol (475 tokens, `ignore_eos`, temperature 0) so the numbers
are comparable to `../2026-08-24-config-sweep/`:

| | n=1 | best | scaling |
|---|---|---|---|
| vLLM dense 1.5B AWQ | 202.2 | **6,562.0** at n=256 | 32.5× |
| vLLM dense 7B AWQ | 67.3 | **1,617.2** at n=128 | 24.0× |
| llama.cpp MoE srv2 (`--n-cpu-moe 20`) | 42.5 | 87.3 at n=16 | **2.06×** |
| llama.cpp MoE srv1 (`--n-cpu-moe 38`) | 25.2 | 36.1 at n=8 | **1.43×** |

The vLLM figures also **reproduce the prior campaign after the memory change** —
6,562.0 against 6,445.1 / 6,452.2 / 6,480.6, and 1,617.2 against 1,604.7. A model
resident on the card never touches system RAM in the decode path, so the host's
memory is invisible to it. vLLM loaded and served normally on 16 GB of host RAM.

**Mechanism.** Dense batching multiplies the *same* weight matrices for every
sequence, so one weight read serves the batch. Expert offload routes different
tokens to *different* experts, so batching multiplies the distinct expert tensors
pulled over the memory bus instead of amortising them. **Concurrency is a benefit
of residency, not of offload** — a scheduler that prices a MoE-offload rung with a
dense rung's batching curve will be wrong by an order of magnitude.

vLLM has no `--n-cpu-moe` equivalent, so a MoE larger than the card is not a vLLM
workload at all.

**Two asymmetries bound the 30&times;-against-2&times; figure, and neither is removed here.**
The dense rows are vLLM at `--max-model-len 1024`; the MoE rows are llama.cpp at
`-c 4096` across **4 slots**, so a level of n=16 is four concurrent sequences and
twelve queued rather than sixteen resident ones. Since KV cache room is what ends
a concurrency curve, both differences favour the dense side. The gap is far too
large for them to reverse it &mdash; but read the claim as *"dense batches much
better"*, not as the ratio 15.8. An equal-footing run (dense at 4096, MoE at
matched slot count) is not in this record.

## 6. Two MoE models co-reside; the constraint is threads, not VRAM

srv1, two **different** expert-offloaded MoE models at once:
`qwen3-coder:30b` (`--n-cpu-moe 48`, 1,274 MiB) and `deepseek-coder-v2:16b`
(`--n-cpu-moe 27`, 1,424 MiB) — **2,702 MiB of 6,144, both healthy**.

| threads each (6 cores, no SMT) | solo | concurrent | combined |
|---|---|---|---|
| `-t 5` (10 on 6) | 23.02 / 23.73 | 1.63 / 1.64 — **14× slower** | 3.26 |
| `-t 3` (6 on 6) | 20.53 / 20.18 | 14.14 / 14.11 — 1.44× slower | **28.25** |

**8.7× from thread count alone.** llama.cpp's threadpool spin-waits, so
oversubscribing cores collapses throughput far past the oversubscription ratio.
Sized to the core count, two models together slightly beat one (28.25 against the
best single-model 26.83) and both stay available.

This is the co-residency question of `../2026-08-22-coresidency-feasibility/` asked
of two *offloaded* models rather than two engines, and it lands in a different
place: that record found VRAM was the scarce resource and contention was a
property of the card. Here VRAM is abundant and **CPU threads are the scarce
resource**.

## 7. Refusals, recorded as results

- **ollama's `gpt-oss:20b` blob will not load in llama.cpp b10481** —
  `unknown model architecture: 'gptoss'`. ollama carries its own architecture tag.
- `--n-cpu-moe` 36 on srv1; 16 and 14 on srv2, even at `-c 2048`.
- **Two engines sharing one card is a silent failure.** With the offload server
  holding 11.3 GiB of srv2's 12 GiB, ollama placed `qwen2.5-coder:1.5b` at
  **93% CPU / 7% GPU** and returned 22.2 tok/s against 114.9 resident — HTTP 200,
  correct output, ~5× slower, and nothing in the response says so. This is the
  defect `backends/ollama.py` already documents, reproduced with a second engine.

## Bounds on all of the above

Single pass per cell unless a row says reps. **srv2 repeats within 0.2%; srv1
varies 5–10% run to run**, so an srv1 gap under ~10% is a tie — the `-t 5`/`-t 6`
pair (23.49/23.93 in one run, 21.60 in another) is exactly that. One prompt shape
for decode; the long-prompt cells use a fixed 1,694-token prompt. One model for
every cell except the leverage table and the co-residency pair. Nothing here
measures quality — every rate is tokens produced, not tokens worth keeping.

Two harness defects hit this campaign and neither changes a number above: piping
the remote driver through `sed` **block-buffers** its stdout, so cells completed on
the rig without their lines reaching the caller (affected cells were re-measured
directly against the running server); and srv1 reloads take 45–120 s per container,
which is why two of its sweeps were stopped early and their remaining cells are
absent rather than zero.

## Files

- `raw-cpu-only-and-residency.txt` — the first pass: CPU-only dense contrast and
  ollama's automatic placement across every model srv2 holds.
- `raw-n-cpu-moe-preswap.txt` — the `--n-cpu-moe` sweeps and thread scans.
- `raw-applied-c1-c2.txt` — the turbo and expert-offload changes applied to srv2,
  with before/after and the co-residency demonstration.
- `raw-postswap-squeeze-concurrency.txt` — the memory change, `--no-mmap`, the
  squeeze pass, and the concurrency and two-model results.
- `srv1-sysinfo.txt`, `srv2-sysinfo.txt` — the hosts as read.
- `drivers/` — every script that produced a number, unmodified.
