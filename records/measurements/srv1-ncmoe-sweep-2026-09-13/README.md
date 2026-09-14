# srv1 `--n-cpu-moe` sweep (mainline llama.cpp, sm_75) — 2026-09-13

Goal: the researcher's "recommended first test" — determine whether srv1's leverage is
plain fit tuning (`--n-cpu-moe`) or expert caching, before touching any fork.

## Setup

- **srv1**: i5-9600K (6C/6T), 16 GB DDR4-3600 (40.3 GB/s), GTX 1660 SUPER 6 GB (sm_75,
  no tensor cores, 336 GB/s), driver 580.178.04, Ubuntu 26.04.
- **mainline llama.cpp** HEAD `37b3a9e`, built `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=75`
  (CUDA 12.4, cmake 4.2.3). **sm_75 compiles clean** — confirms Turing is still supported.
- **Model**: `/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` (13.2 GB) and
  `...-UD-IQ2_M.gguf` (11.5 GB).
- **Protocol**: `llama-cli -fa on -ctk q8_0 -ctv q8_0 -c 16384 --jinja -ngl 99
  --n-cpu-moe N -t 6 -n 300 -f test-prompt.txt --perf --single-turn`. Decode = `Generation` t/s.

## Results

| quant | ncmoe | peak VRAM | prefill t/s | decode t/s |
|---|---|---|---|---|
| IQ3_XXS | 28 | 5,390 MiB | 45.3 | **33.4** |
| IQ3_XXS | 30 (current) | 4,866 MiB | 47.3 | 32.4 |
| IQ3_XXS | 40 | 2,168 MiB | 43.4 | 27.4 |
| IQ2_M | 30 | 4,280 MiB | 47.8 | 32.2 |

## Finding — srv1 decode is maxed at ~33 t/s; software levers are dead ends

1. **The ncmoe dial spans only 27.4 → 33.4 t/s (6 t/s).** srv1's current `ncmoe 30` (32.4)
   is already within 1 t/s of the GPU-max `ncmoe 28` (33.4). Plain fit tuning is exhausted.
2. **Skinnier quant is neutral**: IQ2_M (0.28 B/param) gives *no* decode gain over IQ3_XXS
   (32.2 vs 32.4). Decode is **not** CPU-RAM-bandwidth-bound — so "lighter boxes" don't help here.
3. **The bottleneck is the 1660's weak GPU** (no tensor cores) at the GPU-resident split,
   and CPU RAM (40.3 GB/s) at full offload (27.4). Both are ~30 t/s class; they cross over
   near `ncmoe 30`.
4. **Implication — expert caching would *not* lift srv1.** The cache removes expert
   streaming, but srv1's ceiling is the 1660's attention/routing compute, not streaming.
   A hot/cold cache would land at ≈ `ncmoe 28` (33.4 t/s), not above it.

## Cross-check vs srv2 (same model, mainline)

srv2 RTX 3060 12 GB: `ncmoe 7` = **51.7 t/s** vs srv1's 1660 ceiling **33.4 t/s** (+55%).
The GPU is the whole difference — this independently confirms the upgrade round's
"put a 12 GB GPU in srv1" conclusion, now with a measured srv1 ceiling.

## Bottom line

srv1 is software-maxed: `ncmoe` tuning, skinnier quant, and (by extension) expert caching
are all dead ends at ~33 t/s. The only lever that moves srv1 is a faster GPU.
