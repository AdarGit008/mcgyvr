# Fine-tune pilot (#189): tuned on the corpus, measured through the front door

One pilot QLoRA tune of Qwen2.5-Coder-3B-Instruct on the worker-reply corpus's
verified passes (658 train / 80 val over 20 tasks — all TypeScript, see the
dataset caveat below), exported to the served form, and measured as the ladder
admits models: EvalPlus HumanEval+ greedy against llama-server, base vs tuned,
on the owner's rigs. Pre-registered success bar: **+3pp HumanEval+ on the
served q4_K_M quant** (`MIN_QUALITY_GAIN`, the table's own admission rule).

## The 2×2 (GPU backend, the primary set)

HumanEval / HumanEval+ pass@1, greedy, 164 tasks:

| | q4_K_M | f16 |
|---|---|---|
| **base** | 82.9% / 78.0% | 83.5% / 79.9% |
| **tuned** | 86.0% / 79.9% | 87.2% / 82.3% |

## Verdict against the pre-registered bar

**Miss.** Tuned-q4 over base-q4 on HumanEval+ is **+1.9pp** (79.9 − 78.0);
the bar was +3pp. The tune does not enter the routing table. (On the base
tests alone the same comparison is +3.1pp — the plus set's harder inputs eat
a third of the gain.)

## What the matrix separates

- **The tune helped, a little, everywhere.** +2.4pp at f16, +1.9pp at q4
  (HumanEval+). From 658 TypeScript whole-file examples over 20 problems to a
  Python benchmark — positive cross-language transfer, small but present in
  every cell.
- **q4_K_M costs ~2pp on this model, tuned or not.** Base loses 1.9pp to
  quantization, tuned loses 2.4pp. Most of the tune's gain survives; the
  quant tax is roughly constant, not gain-eating. (Within this pair the host
  differs with precision — f16 cannot fit rig_a — so backend and card change
  together; the pairwise tune deltas do not cross hosts.)
- **Backend numerics move deltas by more than half the admission bar.** The
  accidental CPU pass (kept under `cpu/`) scored the same artifacts at
  tuned-q4 78.0 vs base-q4 78.7: a **−0.7pp** delta where the GPU backend
  says **+1.9pp**. A single greedy run's delta near the 3pp threshold is not
  decisive; the admission rule leans on a measurement whose backend
  sensitivity is of comparable size. Filed as a caveat wherever
  `MIN_QUALITY_GAIN` is consumed; #152's re-verification instinct applies to
  this number too.

## Dataset caveat, stated up front

The corpus this trained on is measurement exhaust: 4,305 verified passes,
2,502 distinct reply texts, **20 distinct problems, 100% TypeScript**
(`dataset-manifest.json` pins every example's provenance). SWE-Gym's +12pp
came from 491 distinct problems. A small gain from a 20-problem
single-language set neither confirms nor bounds what a problem-diverse corpus
would do — that is #197's question. This pilot's job was the harness, the
bar, and the quant question, and those are answered.

## Costs

Training: 32 min on rig_b (RTX 3060). Export: ~3 min. Each GPU eval arm:
7–13 min. Total pilot cost: an afternoon on owned hardware, $0 rented.
