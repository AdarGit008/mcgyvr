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
| North-Mini-Code-1.0-Q4_K_M.gguf | 18.7 GB | cohere2moe, 30B/3B (srv1) |
| North-Mini-Code-1.0-IQ2_M.gguf | 10.6 GB | cohere2moe, 30B/3B (srv2) |
| KAT-Coder-V2.5-Dev.Q4_K_M.gguf | 21.2 GB | qwen35moe, 35B/3B (srv1) |
| KAT-Coder-V2.5-Dev.Q2_K.gguf | 12.9 GB | qwen35moe, 35B/3B (srv2) |
| KAT-Coder-V2.5-Dev_Q3_K_M_imatrix_MTP.gguf | 18.1 GB | qwen35moe + grafted MTP head (srv1) |
| KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf | 14.1 GB | qwen35moe + grafted MTP head (srv2) |

## notes
- srv1 = 48 GB RAM / 6 GB VRAM (weak, offload-bound); srv2 = 16 GB RAM / 12 GB VRAM (fast).
- HF cache (`~/.cache/huggingface`) kept separate per box (AWQ/safetensors by repo id) — not part of this store.
- Same-vocab llama.cpp SD pairs: qwen2.5-coder 1.5b→7b (152064/151936, ≤128 diff); qwen3-coder-30b + qwen3-1.7b (151936 exact); gpt-oss 4b→20b (201088) — but gptoss arch not supported by llama.cpp build.
- North-Mini-Code uses `cohere2moe` arch — supported by stock llama.cpp ≥ b9626 (our pinned b10644 loads it; see 2026-08-28-north-mini-code).
- KAT-Coder-V2.5-Dev is a fine-tune of Qwen3.6-35B-A3B (arch `qwen35moe`). The `*_MTP` files graft the Qwen3.6 MTP head back in (blk.40); stock b10644 runs them with `--spec-type draft-mtp` (see 2026-08-28-kat-coder).
