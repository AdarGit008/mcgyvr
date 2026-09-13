# Lidenburg MoE expert-cache fork — measured on srv2, 2026-09-13

Goal: verify whether the `Lidenburg/llama.cpp` three-tier expert cache (the "offload
smarter" prior art from RFC `ggml-org/llama.cpp#20757`) delivers its claimed **+60%
decode** on our actual rig — **RTX 3060 12 GB + 48 GB DDR4-2933** — with our exact model
`Qwen3.6-35B-A3B-UD-IQ3_XXS`.

## Setup

- **Rig**: srv2 — i9-10900F (10C/20T), 48 GB DDR4-2933 (16 GB Kingston + 32 GB Transcend),
  RTX 3060 12 GB, driver 595.91.07, Ubuntu 26.04.
- **Fork**: `https://github.com/Lidenburg/llama.cpp`, HEAD `e85e4d9` ("Track time spent
  waiting for disk reads…").
- **Build**: `cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86
  -DCMAKE_BUILD_TYPE=Release`, cmake 4.2.3, gcc 15.2.0, CUDA 12.4. Required
  `liburing-dev` (not present by default — the fork's io_uring disk tier).
- **Model**: `/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` (13.2 GB).
- **Prompt**: the fork's own `test-prompt.txt` ("Create a python script that prints the
  size in bytes of all the expert weights in a gguf file").
- **Protocol**: `llama-cli -fa on -ctk q8_0 -ctv q8_0 -m <model> -c <ctx> --jinja -ngl 99
  -t 11 -n 1000 -f test-prompt.txt --perf --single-turn`. Stock arms add `--no-mmap
  --n-cpu-moe N`; cache arms add `--mmap --cpu-moe` plus `GGML_EXPERT_CACHE_MAX`,
  `GGML_EXPERT_RAM_CACHE_MAX`, `GGML_OP_OFFLOAD_MIN_BATCH=1`. Decode is the
  `Generation` t/s from the final `[ Prompt … | Generation … ]` line.

## Results

| # | arm | ctx | decode t/s | prompt t/s | peak VRAM MiB | expert hit (GPU/RAM/disk) |
|---|---|---|---|---|---|---|
| 1 | stock `--n-cpu-moe 30` (no cache) | 256k | 30.4 | 41.5 | — | — |
| 2 | cache `70/186` | 256k | 40.1 | 64.6 | 8,445 | 80.8 / 19.2 / 0.0 |
| 3 | stock `--n-cpu-moe 7` (best short-ctx) | 16k | 51.7 | 100.3 | ~11,000¹ | — |
| 4 | cache `120/256` | 256k | **49.0** | 73.4 | 10,475 | 92.1 / 7.9 / 0.0 |

¹ `ncmoe 7` VRAM from the Q13 record (`fleet-identity-2026-09-11`); not re-measured here.

## Findings

1. **The README's +60% does *not* reproduce at its default `70/186` config** on the 3060:
   arm 1 → arm 2 is **+32%** (30.4 → 40.1 t/s). The README's 66-vs-40 was measured on an
   RTX 5080 (PCIe 4.0) with Q4_K_M; the 3060's lower GPU-compute ceiling caps the gain.

2. **But at a cache sized for the 3060 (`120/256`), the +60% *does* hold**: arm 1 → arm 4
   is **+61%** (30.4 → 49.0 t/s). 120 experts cached in VRAM lifts the hit rate from
   80.8% → 92.1% and peak VRAM stays under the 12 GB ceiling (10.5 GiB).

3. **The real value is context, not raw speed.** `ncmoe 7` (51.7 t/s) physically cannot
   load at 256k (needs ~15.6 GiB VRAM). The tuned cache delivers **49.0 t/s at 256k
   context** — ~95% of the best short-context speed, at **16× the context**, for ~10.5 GiB
   VRAM. It decouples decode speed from expert residency by caching only the hot experts.

4. **Disk tier idle.** `disk=0 / disk_wait=0.000s` on every arm — with 48 GB RAM the full
   expert set fits the pinned RAM tier, so no io_uring path was exercised. The 3-tier
   design's disk leg is untested here (and likely irrelevant for us).

## Verdict

The expert cache is real and transfers to the 3060, but **only if the VRAM cache is sized
up** from the fork's default (`70` → `120`). Tuned, it is the only way we have to hold
**~49 t/s on the 35B at 256k context** in a 12 GB card — a regime `--n-cpu-moe 7` cannot
reach. Untuned (`70/186`), it is a modest +32%.

Raw logs: `/tmp/arm1.log` … `/tmp/arm4.log` on srv2 (operator machine, git-ignored).
