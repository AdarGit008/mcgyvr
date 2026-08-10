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

## Amendment — 2026-08-10 (#229): the bar this was scored against is withdrawn

The measurements above stand. **The verdict does not.**

The pre-registered bar named at the top of this record — "+3pp HumanEval+ on the
served q4_K_M quant (`MIN_QUALITY_GAIN`, the table's own admission rule)" —
borrowed a constant that was never an adoption threshold. `propose.py:32` states
its actual job: the separation two **rungs** need before both are worth carrying
in the ladder. ADR-0018 Q1 withdrew the borrowing as doctrine; ADR-0019 replaces
it with a reality floor and a per-lever rule and states the provenance at the
constant itself.

Three things follow for this record:

- **"Miss" is not the outcome; UNDECIDED is.** #219 showed HumanEval+ at n = 164
  cannot resolve +3pp. Recomputed in `tools/power/mde.py` at the 10% discordance
  rate the field plans against, the instrument resolves **+6.9pp** — so +1.9pp
  and +3pp were never separable here, and the comparison decided nothing about
  the tune. Under ADR-0019 that is a failure of the instrument, not a verdict on
  the lever.
- **This record's own best finding is now doctrine.** "Backend numerics move
  deltas by more than half the admission bar" — the +1.9pp CUDA / −0.7pp CPU
  pair, a 2.6pp swing from identical weights — is one of the three reality-floor
  figures ADR-0019 binds every arm to. The caveat it asked to have "filed
  wherever `MIN_QUALITY_GAIN` is consumed" is now filed there.
- **#190's sequencing behind the "miss" loses its premise**, which ADR-0017 had
  already flagged and #234 corrected in that issue's body.

Nothing in the 2×2, the quant tax, the dataset caveat or the costs changes.

## Amendment — 2026-08-10 (#230): this adapter is unmeasurable on the floor instrument

The measurements above still stand, and this amendment does **not** say they are
contaminated. It says something narrower and worse.

`dataset-manifest.json` pins every example's provenance, and the tiers read
**622 `d1` + 116 `d2`** over 20 problems. `d1` is not a tier with its own
directory — it **is** `tools/bundle/tasks/`, byte for byte
(`tools/breadth/measure.py`, `load_tier_tasks`), which is the TypeScript half of
the only floor instrument the project has: the twenty contracts CLM-0012
measured at 45/55/50/45%. `d2` is the breadth rig's next rung, probed for
ADR-0017's floor band. Both are declared instruments as of
`tools/instruments.json`.

What follows, precisely:

- **The reported 2×2 is not contaminated.** The eval was EvalPlus HumanEval+ —
  164 Python tasks, a different set from the TypeScript material trained on.
  No arm of this pilot was ever run on `d1`, `d2` or `d3`; the graded runs on
  those tiers in `records/measurements/floor-probe-2026-08-09/` are all base
  `qwen2.5-coder:3b`.
- **The adapter can never be scored on the bench.** ADR-0018 puts every lever on
  one bench built from the floor instrument, and this adapter has trained on
  both rungs of it — including, through the paired ids and the positive
  cross-language transfer this record itself measured, the Python arm it never
  saw. A number it produced there would measure recall, not capability.
- **So the pilot's verdict is UNDECIDED on the benchmark it used (#229) and
  inadmissible on the benchmark that matters (this issue).** Neither is
  "negative". The lever — fine-tuning a small worker — has not been tested, and
  the artifact in hand cannot be the thing that tests it.

The tune is re-runnable; the finding is what it costs. What a future tune may
draw from is `docs/what-a-tune-may-train-on-2026-08-10.md`, and the guard that
makes the question unavoidable is in `tools/replies/pin.py` and
`tools/finetune/build_dataset.py`.
