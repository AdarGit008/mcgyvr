# Shared Model Store — `~/models/{dense,moe}` (synced srv1 ↔ srv2)

## dense/  (non-MoE)
| file | size | notes |
|---|---|---|
| Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf | 4.2 GB | vocab 152064 |
| nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_M.gguf | 4.7 GB | qwen2 arch, vocab 152064 |
| nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_S.gguf | 4.5 GB | qwen2 arch, vocab 152064 |
| nemotron-4b-bf16/ (safetensors) | 7.5 GB | |
| nemotron-4b-fp8/ (safetensors) | 5.0 GB | |

## moe/  (Mixture-of-Experts)
| file | size | notes |
|---|---|---|
| Qwen3-Coder-Next-UD-Q3_K_XL.gguf | 36.3 GB | 80B/3B MoE |
| qwen3-coder-30b.gguf | 18.6 GB | vocab 151936, 30B/3B |
| nvidia_Nemotron-3-Nano-30B-A3B-IQ2_XXS.gguf | 18.0 GB | 30B-A3B |
| nemotron-30b-awq/ (safetensors) | 17.0 GB | |
| gpt-oss-20b.gguf | 13.8 GB | vocab 201088 (gptoss) |
| Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf | 13.2 GB | vocab 248320 |
| deepseek-coder-v2-16b.gguf | 8.9 GB | vocab 102400 |
| 4b-Q4_K_M.gguf (gpt-oss-4b draft) | 3.2 GB | vocab 201088 |

## notes
- srv1 = 48 GB RAM / 6 GB VRAM (weak, offload-bound); srv2 = 16 GB RAM / 12 GB VRAM (fast).
- HF cache (`~/.cache/huggingface`) kept separate per box (AWQ/safetensors by repo id) — not part of this store.
- Same-vocab llama.cpp SD pairs: qwen2.5-coder 1.5b→7b (152064/151936, ≤128 diff); qwen3-coder-30b + qwen3-1.7b (151936 exact); gpt-oss 4b→20b (201088) — but gptoss arch not supported by llama.cpp build.
