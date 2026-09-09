# 2026-08-24 — RAMP_TOKENS re-derived with CUDA graphs on (#356)

Header: `records/headers/2026-08-24-ramp-tokens.json`. Harness:
`tools/bench/serving/sweep.py` with the per-cell `tokens` field added for this
run. Data: `srv1.jsonl`, `srv2.jsonl` (one record per cell), matrices beside
them. Both rigs ran concurrently, each the sole client of its own server;
both released to 1 MiB with no container afterwards.

## The question

`RAMP_TOKENS = 475` (D3, 2026-08-19) was an interpolation between the 128- and
512-token columns of a matrix taken under `--enforce-eager`, on the argument
that at 128 tokens the per-request fixed costs are a large share of the
reply. The flag was worth 5.02x on srv2, so the rate that argument was made
against was 5x low there. With graphs on, is 475 still a throughput reading
rather than an overhead reading?

## Configuration

Container `vllm/vllm-openai:v0.26.0`, `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ`,
`--gpu-memory-utilization 0.85 --max-model-len 2048 --max-num-seqs 256`, no
`--enforce-eager`; srv2 adds `--kv-cache-dtype fp8` (its best-measured cell;
refused on srv1 by compute capability). `max-model-len` is 2048 rather than
the sweep's 512-1024 so the 1024-token column fits. Levels 1/16/64/128, one
repeat, `ignore_eos`, same short prompt as the sweep. Four cells per rig, one
per budget: 128, 256, 475, 1024 tokens. All eight launches succeeded
(136-138 s on srv1, 114-126 s on srv2 — eight more graphs-on
`START_TIMEOUT_S` points). No level errored.

## Reading

Aggregate tok/s, and each budget as a fraction of the 1024-token column at
the same level:

| rig | n | 128 | 256 | 475 | 1024 |
|---|---|---|---|---|---|
| srv1 | 1 | 34.8 (0.81) | 39.5 (0.92) | 41.8 (**0.97**) | 42.9 |
| srv1 | 16 | 166.5 (1.03) | 170.4 (1.05) | 167.6 (1.04) | 161.8 |
| srv1 | 64 | 285.0 (1.07) | 289.1 (1.08) | 283.0 (1.06) | 266.7 |
| srv1 | 128 | 296.0 (1.09) | 298.5 (1.10) | 293.6 (1.08) | 271.2 |
| srv2 | 1 | 146.4 (0.77) | 170.4 (0.89) | 180.5 (**0.95**) | 190.7 |
| srv2 | 16 | 2128.4 (0.81) | 2404.6 (0.92) | 1999.5 (0.77) | 2613.0 |
| srv2 | 64 | 3657.4 (0.77) | 4744.4 (0.99) | 5058.7 (1.06) | 4775.6 |
| srv2 | 128 | 4925.7 (0.91) | 5335.9 (0.99) | 5643.9 (1.04) | 5413.9 |

**At a single stream, where the overhead argument lives, 475 reads 97% of the
1024-token rate on srv1 and 95% on srv2; 128 reads 81% and 77%.** D3's
premise — that 128 is an overhead reading — holds with graphs on, and on the
rig the flag taxed most it holds harder.

**The fixed cost is not fixed in seconds.** Fitting n=1 latency to
`overhead + tokens / rate` across the 128 and 1024 columns: srv1 pays 0.79 s
per request at an asymptotic 44.4 tok/s, srv2 0.22 s at 198.7 tok/s. The
overhead scaled with the rig — a 3.6x smaller intercept against a 4.5x higher
rate — so its share of a 475-token reply is **6.9% on srv1 and 8.3% on
srv2**. That is why a budget chosen against a 5x-low rate survives the rate
being corrected: the argument was about a share, and the share is close to
rate-invariant on these two rigs. It is a two-rig observation, not a law.

**Past the knee, longer is slower.** At n ≥ 64 the 1024-token column reads
6-10% BELOW 475 on both rigs: a longer sequence is more KV to attend over per
decode step, and at 256 sequences that is the dominant cost. 475 is not
merely "long enough"; 1024 would be measuring a different regime. A budget
between 256 and 512 is where both effects are small, which is where D3
interpolated to.

## What this does not settle

- **Repeats.** One per level. srv2's n=16 column at 475 (1999.5, below both
  its 256 and 1024 neighbours) is the kind of single-level wobble
  `RAMP_REPEATS = 2` exists to absorb; it does not move the n=1 reading the
  constant is derived from.
- **Resolution.** Levels are 1/16/64/128, so nothing here reads a knee.
- **One model, one prompt.** A prefill-heavy shape has a different overhead
  term and this says nothing about it.

## Verdict

`RAMP_TOKENS = 475` survives re-derivation under the declared configuration.
Recorded in `contract.PROVENANCE["RAMP_TOKENS"]` as derived from this run.
