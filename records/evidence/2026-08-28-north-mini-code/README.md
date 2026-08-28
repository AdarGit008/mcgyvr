# North-Mini-Code-1.0 — a new model beats the past-week Key 1 (2026-08-28)

**Question.** Find a model we do not already have in the store that uses the two rigs'
VRAM+RAM *better*, download and run it, and try to beat the past-week numbers
(the 2026-08-28 `setup-selection` DoD table, score `tok/s × model_size × n`).

**Answer.** **Cohere `North-Mini-Code-1.0`** — a 30B-A3B MoE (3B active), Apache 2.0,
released 2026-06. It is **not** in the store, it is the newest agentic-coding model in
this size class, and on srv2 it **beats Key 1 by +36%**.

## Why this model

- **More smarts per token than the incumbent.** Key 1's holder is `gpt-oss-20b` (20.5B
  total / 3.6B active, 97.0 tok/s). North-Mini-Code is **30B total / 3B active** — a
  larger total-param count at *less* active compute, which is exactly the shape the Key 1
  metric rewards (`tok/s × total`).
- **Fast by design.** Cohere reports "up to 2.8× higher output throughput than Devstral
  Small 2" at matched concurrency (coding prompts).
- **New arch, zero build work.** `cohere2moe` landed in llama.cpp **b9626** (PR #24260,
  merged 2026-06-13). Our pinned `ghcr.io/ggml-org/llama.cpp:server-cuda` image is
  **b10644** — newer — and `strings libllama.so | grep cohere` confirms the arch is
  compiled in. No recompile: the existing `lcpsweep28.py` harness ran it unchanged.

## Protocol

Identical to `2026-08-28-setup-selection`: 475-token replies, `ignore_eos`, temperature 0,
fixed prompt ("Write a Python function that merges two sorted lists."), `-c = np × 1024`,
llama.cpp `server-cuda` b10644, driver `lcpsweep28.py`.

## Results

**srv2 (RTX 3060, 12 GB VRAM)** — `North-Mini-Code-1.0-IQ2_M.gguf` (10.55 GB), `-ngl 99`,
all experts on-GPU (`ncmoe=0`), 11,067–11,851 MiB VRAM:

| n | agg tok/s | p50 (s) |
|---|---|---|
| 1 | **90.3** | 5.26 |
| 2 | 153.0 | 6.21 |
| 4 | 180.2 | 10.54 |
| 8 | 281.1 | 13.51 |
| 16 | 518.4 | 14.66 |

`np=32` (`c=32768`) **REFUSED** — KV-cache OOM (same wall class as `gpt-oss-20b`, which
tops out at `np=8` on this card).

**srv1 (GTX 1660 SUPER, 6 GB VRAM / 48 GB RAM)** — `North-Mini-Code-1.0-Q4_K_M.gguf`
(18.74 GB), expert offload (`ncmoe=40` @ np8, `ncmoe=44` @ np16), ~4.9–5.5 GiB VRAM:

| n | agg tok/s | p50 (s) |
|---|---|---|
| 1 | 23.7 | 20.07 |
| 2 | 34.2 | 27.78 |
| 4 | 30.0 | 63.37 |
| 8 | 60.8 | 62.47 |
| 16 | 66.2 | 114.84 |

## Score vs the past week

**Key 1 — one request, one end user (`tok/s × total × 1`):**

| rank | setup | tok/s | total (B) | score |
|---|---|---|---|---|
| 🏆 **NEW** | **srv2 · llama.cpp · North-Mini-Code-1.0 IQ2_M** | **90.3** | **30.0** | **2,709** |
| (was #1) | srv2 · llama.cpp · gpt-oss-20b MXFP4 | 97.0 | 20.5 | 1,988 |
| (was #2) | srv2 · llama.cpp · Qwen3.6-35B-A3B | 44.8 | 35.0 | 1,568 |
| (was #3) | srv1 · llama.cpp · Qwen3-Coder-Next-80B-A3B | 19.0 | 80.0 | 1,520 |

→ **+36.2% over the incumbent** (2,709 vs 1,988). Same `total` convention as the DoD table
(30B-A3B counted as 30).

**Key 2 — max throughput and smarts (`tok/s × total × n*`):** **NOT beaten.**
North's best is `518.4 × 30 × 16 = 248,832`, vs `srv2 · vLLM · Qwen2.5-Coder-7B AWQ`
`1,608 × 7.6 × 128 = 1.57M`. Expected — a 30B MoE will not out-throughput a 7B dense at
128-way concurrency on a 12 GB card. Key 2 stays with the 7B.

**srv1 note:** North's srv1 single-request throughput (23.7 tok/s) ties the incumbent
`Qwen3-Coder-30B-A3B` (23.2 tok/s) at the same 30B-A3B shape — so on the weak/offload rig
North is a *different, newer* model at *equal* throughput, not a win. No Key-1 movement on
srv1 (its #3 slot, 80B at 1,520, still stands).

## Walls

| wall | rig | cause |
|---|---|---|
| `np=32` (`c=32768`) | srv2 | `llama_server: exiting due to model loading error` — 10.55 GB weights + 32-slot KV > 12 GB |
| (none) | srv1 | Q4_K_M loaded clean at `ncmoe=40/44`, ~5.5 GiB VRAM |

## Files

- `README.md` — this report
- `results-srv2.txt` — raw lcpsweep output (srv2)
- `results-srv1.txt` — raw lcpsweep output (srv1)

Rig-side (kept): `~/models/moe/North-Mini-Code-1.0-{IQ2_M,Q4_K_M}.gguf` on srv2/srv1
respectively; `~/north-bench/` holds the run scripts + raw results.

## Sources

- Cohere blog / model card: https://cohere.com/north-mini-code · https://huggingface.co/CohereLabs/North-Mini-Code-1.0
- GGUFs: https://huggingface.co/bartowski/North-Mini-Code-1.0-GGUF (IQ2_M 10.55 GB, Q4_K_M 18.74 GB)
- llama.cpp arch support: PR #24260 (merged, b9626) · https://github.com/ggml-org/llama.cpp/pull/24260
- vLLM support: https://github.com/vllm-project/vllm/pull/44707 (main branch; not the pinned v0.26.0)
