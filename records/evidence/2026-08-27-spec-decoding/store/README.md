# Model Store — srv1 (`~/model-store`)

Organised by family. Symlinks (→) point to the canonical files elsewhere; real files were
downloaded into the store. Reuse this as the single source of truth for llama.cpp runs.

## Index

| family | file | size | vocab | kind | source |
|---|---|---|---|---|---|
| gpt-oss | `gpt-oss/20b.gguf` | 13.8 GB | 201088 | target (MoE 20B) | → `~/ggufs/gpt-oss-20b.gguf` |
| gpt-oss | `gpt-oss/4b-Q4_K_M.gguf` | 3.23 GB | 201088 | draft (MoE 4B) | mradermacher/gpt-oss-4B-GGUF |
| qwen2.5-coder | `qwen2.5-coder/7b-iq4_xs.gguf` | 4.2 GB | 152064 | target | → `~/ggufs/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf` |
| qwen2.5-coder | `qwen2.5-coder/1.5b-q6_k.gguf` | 1.46 GB | 151936 | draft | → `~/specdecode/llama_sd/qwen2.5-coder-1.5b-instruct-q6_k.gguf` |
| qwen3 | `qwen3/coder-30b.gguf` | 18.6 GB | 151936 | target (MoE 30B/3B) | → `~/ggufs/qwen3-coder-30b.gguf` |
| qwen3 | `qwen3/35b-iq3_xxs.gguf` | 13.2 GB | 248320 | target (MoE 35B/3B) | → `~/ggufs/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` |
| deepseek | `deepseek-coder-v2-16b.gguf` | 8.9 GB | 102400 | target (MoE 16B) | → `~/ggufs/deepseek-coder-v2-16b.gguf` |

## SD pairing notes
- Same-vocab pairs (valid for llama.cpp `--model-draft`): gpt-oss 4b→20b (201088);
  qwen2.5-coder 1.5b→7b (151936 vs 152064, ≤128 diff); qwen3 coder-30b + qwen3-1.7b (151936 exact).
- **qwen3-1.7b draft** lives in `~/specdecode/llama_sd/qwen3-1.7b-IQ4_XS.gguf` (vocab 151936).

## Notes
- Boxes: srv1 48 GB RAM / 6 GB VRAM (weak, offload-bound); srv2 16 GB RAM / 12 GB VRAM (fast).
- Big MoE targets (gpt-oss-20b, qwen3-coder-30b) only fit srv1 → offload-bound → SD gain ~3% (measured).
- 7B on srv2 remains the best real SD win (+11%).
