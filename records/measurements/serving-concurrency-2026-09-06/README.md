# What each rung does as its width grows — the result

Instrument: [`tools/serving/concurrency_sweep.py`](../../../tools/serving/concurrency_sweep.py).
Taken 2026-09-06, after the live e2e of the same day lost 19 of 26 contracts to
transport timeouts at the top rung.

**The two engines answer the width question in opposite directions, and the
ladder was configured as though they answered it the same way.** vLLM on a
GPU-resident model gives back nearly all of its per-stream rate up to
`--max-num-seqs` and multiplies aggregate throughput by 7.6x. llama.cpp serving
a 35B MoE with 32 of 40 expert layers on the CPU gives up 81% of its per-stream
rate to buy 50% aggregate. One of those is worth running wide. The other is
not, and it was the one running widest.

## What ran

Four sweeps. Each sends N simultaneous requests with distinct prompts and
`ignore_eos`, so every stream generates exactly the declared token count and no
stream is served from another's prefix cache. Rates are per completed stream;
aggregate is total tokens over the wall clock of the concurrent window.

| | |
|---|---|
| srv1 | GTX 1660 SUPER 6 GB, i5-9600K 6c/6t, **15.4 GB RAM** |
| srv2 | RTX 3060 12 GB, i9-10900F 10c/20t, **45 GB RAM** |
| llama.cpp | `llamacpp:b10644-L3`, `-fa on -b 512 -ub 512`, `--parallel 8`, `-c 32768` |
| vLLM | `vllm/vllm-openai:v0.26.0`, `--max-model-len 4096 --max-num-seqs 8` |
| Tokens | 192 per stream (llama.cpp), 256 (vLLM) |

## vLLM scales; the flags mean what the docs say

srv2, Qwen2.5-Coder AWQ, both units co-resident on one card.

| width | 3B per stream | 3B aggregate | 7B per stream | 7B aggregate |
|---|---|---|---|---|
| 1 | 115.85 | 115.80 | 64.64 | 64.62 |
| 2 | 113.39 | 226.29 | 64.46 | 128.70 |
| 4 | 113.38 | 452.28 | 63.51 | 253.78 |
| 8 | 109.61 | 873.59 | 61.28 | 489.18 |
| 16 | 82.59 | 900.67 | 46.34 | 499.50 |

Up to `--max-num-seqs`, per-stream cost is 5% and aggregate is near-linear.
Past it, aggregate plateaus and latency roughly doubles — 2.3s to 3.4s on the
3B, 4.2s to 6.2s on the 7B. That is queueing, and it is what the engine
documents: `--max-num-seqs` is the "maximum number of sequences to be processed
in a single iteration", and requests over it wait rather than being refused
(refusal is `--max-num-queued-reqs`, which neither unit declares).

**The two engines' context flags are not the same quantity, and mcgyvr already
models both correctly.** vLLM's `--max-model-len` is per sequence; llama.cpp's
`-c` is the total across slots, divided by `--parallel`. The emitter writes
`--max-model-len = ctx_per_slot` and `-c = ctx_per_slot * width`, and srv1's
own `/slots` confirms the division: `-c 32768` with `--parallel 8` reports
`n_ctx 4096` per slot.

## llama.cpp with CPU expert offload does not

srv1, Qwen3.6-35B-A3B-UD-IQ3_XXS, `--n-cpu-moe 32` — 32 of 40 expert layers on
the CPU.

| width | per stream | aggregate | p50 latency (192 tok) |
|---|---|---|---|
| 1 | 27.23 | 27.22 | 7.1s |
| 2 | 13.99 | 27.93 | 13.7s |
| 4 | 7.83 | 31.27 | 24.5s |
| 8 | 5.09 | 40.71 | 37.7s |

Width 2 buys 2.6% aggregate for half the per-stream rate. Width 8 buys 50% for
a fifth of it. The expert GEMM is memory-bound, and concurrent streams activate
different experts, so batching moves more weight per token rather than less.

srv2 running the *same* model CPU-only (`-ngl 0`, 10 threads) has the same
shape and a lower floor:

| width | per stream | aggregate |
|---|---|---|
| 1 | 8.97 | 8.96 |
| 8 | 2.68 | 21.36 |

Three readings follow. srv1's GPU is doing real work: its eight GPU-resident
expert layers make it 3x faster per stream than srv2 with none. srv2 scales
*better* in aggregate (2.4x against srv1's 1.5x), which is consistent with
srv1's memory pressure — `llama-server` holds 12 GB RSS on a 15.4 GB machine
with 1.9 GB already in swap. And a cold stream on srv1 measured 1.37 tok/s
against 27.2 warm, which is page cache being refilled from disk.

**srv2 with its GPU freed is the measurement this record does not have.** It
has twice the VRAM, so far more than eight expert layers would be resident, and
three times the RAM, so nothing would page. The comparison needs srv2's vLLM
units stopped, which this session was not permitted to do.

## What the numbers decide

**A reply cap, a rung's width and a request timeout are three numbers that fix
each other.** A 1024-token reply at srv1's width-1 rate takes 38s; at width 8
it takes 201s. The transport allowed 120s, as a literal in `runner.py` that no
config could reach, so the second was unreachable — and failed as a socket
error naming neither the cap nor the width behind it. That literal is now
`budgets.request_timeout_s`, defaulted to the same 120.

**srv1's `--parallel 8` came from a default, not from this curve.** The door's
`--parallel` defaults to 8 (`serving/run.py`), and that number became both
llama.cpp's `--parallel` and vLLM's `--max-num-seqs`, on every rig, whatever
each source's `max_parallel` says. On the 3B that under-declares the rig: the
config bounds dispatch at 6 while the engine was started 8 wide and scales
cleanly to 8. On srv1 it over-declares: eight slots of a rig whose aggregate
barely moves and whose latency goes up fivefold.

Widths that follow from these curves, for a ladder whose caller waits on each
reply: **8 for both vLLM rungs** (the engine's own ceiling, 5% per-stream cost)
and **1 or 2 for srv1's top rung** (width 4 already puts a 1024-token reply at
131s, past the default timeout).
