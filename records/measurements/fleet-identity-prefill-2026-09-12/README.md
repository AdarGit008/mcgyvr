# The fleet-identity prefill measurements — measured 2026-09-12

The fleet-identity plan (`records/plans/fleet-identity.md` §12) owes a **prefill
tolerance**: the survey held no prefill observation, and M1 read decode only. This
run measures the prefill rate (time-to-first-token / prompt tok/s) with NVMe offload
**disabled**, per unit × rig, and derives the tolerance by the same frozen rule M1 used.

- **Protocol** mirrors M1: 3 cold starts per unit, swap **off**, `--load-mode none`
  (llama.cpp) / GPU-resident (vLLM), page cache dropped before every arm, one
  discarded warm-up then 5 prefill samples. The prompt is the ~2,315-token long
  prompt from `measuring-gaps-2026-09-10` (`cache_prompt=false`).
- **Runner** is `prefill.py`; raw rows are `raw-prefill.json`, one row per cold
  start. `derive-prefill.py` projects them into `results-prefill.json`.
- **Harness.** `prefill.py` and `derive-prefill.py` import `rig.py` / `arms.py` and
  the compose files from `records/measurements/fleet-identity-2026-09-11/` (on the
  `red/fleet-identity` branch), where this run was executed.
- **Door.** Every arm ran through the door; engine and door logs are git-ignored
  and stayed on the operator machine (as in M1).

## What was measured

| rig / unit | class | cold starts | median prefill tok/s | worst single-sample shortfall |
|---|---|---|---|---|
| srv2 Qwen2.5-Coder-3B-Instruct-AWQ (vLLM) | vLLM | 3 × 5 | 11,500 | 7.86% |
| srv2 Qwen2.5-Coder-7B-Instruct-AWQ (vLLM) | vLLM | 3 × 5 | 12,059 | **21.55%** |

**Tolerance, by the frozen M1 rule (worst single-sample shortfall from the unit
median, ceiling'd to a whole percent, floored at 1%):**

| class | worst shortfall | tolerance |
|---|---|---|
| vLLM | 21.55% | **22%** |

**The 22% rests on one 7B sample and needs an owner ruling.**

- **What set it.** `s2-pair-prefill-2`'s 7B first sample read **9,460 tok/s** against a
  unit median of 12,059; the next sample recovered to 12,174. Every other 7B sample
  is ≥ 11,056 tok/s, and all 3B samples are ≥ 10,597 tok/s.
- **Where it happens.** The 7B restarted 1× on every cold start (the known live-pair
  crash-restart), and the 3B restarted 2×. The 9,460 reading is the slowest single
  sample of the slowest-restarting unit, so it is plausibly the restart's tail, not a
  steady prefill rate.
- **What the rule does with it.** The frozen rule takes the worst single sample, so
  this one dip sets the whole vLLM class. Excluding it, the class shortfall is the
  3B's 7.86% (→ 8%), not 22%.

## Not measured — blocked

- **srv1 Qwen3.6-35B-A3B-IQ3_XXS** and **srv1 Ling-3.0-tiny-Q4_K_M** (llama.cpp,
  the `cpu_experts` and `llamacpp` classes) could not be measured: srv1's GPU is
  NVML-broken — driver 580.178.04 on disk vs the still-loaded 580.173.02 kernel
  module (`nvidia-smi`: "Driver/library version mismatch"). Awaiting an owner reboot.
