# HumanEval+ Benchmark Results

Date: 2026-07-26
Hardware: GTX 1660 SUPER, 6GB VRAM
Framework: EvalPlus v0.4.0.dev44
Backend: Ollama (local)
Dataset: HumanEval+ (164 tasks, base + extra tests)
Decoding: Greedy (temperature=0, n_samples=1)

## Results

| Model | Params | Base pass@1 | HumanEval+ pass@1 | Codegen Time | Eval Time |
|---|---|---|---|---|---|
| qwen2.5-coder:1.5b | 1.5B | **70.7%** | **65.2%** | ~6 min | ~6 sec |
| qwen2.5-coder:3b | 3B | **84.1%** | **80.5%** | ~9 min | ~11 sec |
| qwen2.5-coder:7b | 7B | **87.2%** | **82.9%** | ~20 min | ~14 sec |

## Observations

- **3B → 7B gap is small**: Only +3.1pp base, +2.4pp plus. Diminishing returns on 6GB hardware.
- **1.5B → 3B jump is large**: +13.4pp base, +15.3pp plus. The 3B model is the sweet spot for quality/VRAM.
- **7B codegen time**: ~20 min for 164 tasks (~7.3s/task). 3B is ~3.3s/task. 1.5B is ~2.2s/task.
- **Parallel potential**: 3B supports 2× parallel (confirmed earlier), effectively halving wall time for batch workloads.

## Comparison (Published Baselines)

| Model | HumanEval+ pass@1 | Source |
|---|---|---|
| GPT-4 (greedy) | ~90% | EvalPlus leaderboard |
| Claude 3.5 Sonnet | ~92% | EvalPlus leaderboard |
| DeepSeek-Coder-V2 16B | ~89% | EvalPlus leaderboard |
| Qwen2.5-Coder-7B (official) | ~87% | Qwen blog |
| **Our qwen2.5-coder:7b** | **82.9%** | This run |
| **Our qwen2.5-coder:3b** | **80.5%** | This run |

Our 7B result (82.9%) is slightly below the official Qwen2.5-Coder-7B score (~87%). Likely causes:
1. Ollama q4_K_M quantization vs full precision in official eval
2. Chat template / prompt formatting differences
3. Greedy decoding vs possible sampling in official results

## Conclusion

- **Primary worker**: `qwen2.5-coder:3b` — 80.5% HumanEval+, 2× parallel capable, fast.
- **Heavy worker**: `qwen2.5-coder:7b` — 82.9% HumanEval+, single worker only, marginal gain.
- **Light worker**: `qwen2.5-coder:1.5b` — 65.2% HumanEval+, usable for trivial tasks only.
