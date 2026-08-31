# What a tune may train on, once the instrument is protected (#230)

**Status:** the answer to acceptance item 5 of #230. Written 2026-08-10 on
lane/230, alongside the guard that makes the question unavoidable.
**Amended the same day by #240** — the five local sets were retired and
released, which reverses source 1 below and roughly doubles the corpus. The
table and source 1 are corrected in place; the amendment at the end records
what moved and why.
**Reads:** ADR-0017 (the floor is the product), ADR-0018 (one bench, every
lever), ADR-0019 (the bar), #197 (the problem pool), #222 (the corpus the
research calls for), #225 (anchor material), #221 (whether to train at all).

#230 declares the measurement sets and refuses them at two points on the way to
a training set. That closes a hole; it also removes 9,173 of the 12,331 replies
the project has captured from the material a tune may draw on. So the guard has
to be paired with an answer to what is left, or it is just an obstacle.

## What is admissible today, measured rather than estimated

Rebuilding the training set with the guard in place
(`uv run --no-sync python tools/finetune/build_dataset.py --out …`, cap 40,
split by problem) yields:

| | examples | problems | source |
|---|---|---|---|
| TypeScript (`pool-ts`) | 506 | 147 | #197 pool sweeps |
| Python (`pool-py`) | 102 | 54 | #197 pool sweeps |
| TypeScript (`d1`, `d2`, `d3`) | 936 | 34 | retired sets, released by #240 |
| **total** | **1,544** (1,405 train / 139 val) | **184** | 63 runs |

The pool half is drawn from `qwen2.5-coder:14b` and `qwen2.5-coder:7b` — a
bigger worker's verified passes, which is the distillation shape #190 describes
rather than a model learning from itself. The released half is every model the
breadth campaigns ran, on twenty problems each.

The comparison that matters is with what #189 actually had: **738 examples over
20 problems, 100% TypeScript, every one of them from a live instrument.** The
difference is not size — it is that #189's twenty problems were the twenty it
was then scored on. This corpus is 9.2× wider in problems, and #189's own
record names problem diversity as the axis it could not speak to (SWE-Gym's
+12pp came from 491 distinct problems).

**114 released replies are drawable in principle and unresolvable in fact.**
`breadth-2026-08-06` recorded no tier and its task ids fall in five sets at
once, so the contracts behind its replies cannot be identified and the prompt
cannot be rebuilt. The builder counts them (`released-but-unresolvable`) and
names the run in the manifest rather than guessing — a training pair whose
prompt is not the prompt the reply answered is worse than a missing one.

## The four candidate sources, and what each is worth

**1. Retired instrument material (`d1`, `d2`, `d3`, both bundle arms).**
*Admissible as of #240, and it was not when this was written.* The original
reasoning stands and is worth keeping: drawing from a **live** instrument does
not corrupt a training run, it destroys the *measurement*, which is the scarcer
thing — the receipt being #189, whose adapter exists, trains fine, and can
never be scored on the bench ADR-0018 builds. What changed is that there is no
longer a measurement to destroy. #229 showed these five sets could not resolve
an effect at any size they come in, so #240 retired them, and a set nobody will
measure on again cannot be contaminated by training on it. The material was
always fine; it was the measuring that was spoiled.

**2. The problem pool (#197).** Admissible by construction, and the only source
that is admissible *today*. `tools/problems/admit.py` already holds the pool
distinct from every instrument's ids and prose, and screens it against
HumanEval entry points — and as of #230 it reads that list from the same
declaration the training guard reads, so the two properties cannot drift apart.
Its limit is shape, not hygiene: pool problems are whole-problem work, and
ADR-0017 records that the 3B reads 0% on them. That does not disqualify the
material — the examples come from models that *did* pass — but it means the
corpus teaches whole-problem solutions to a worker whose job the floor
describes differently. That gap is #222's question, not this document's.

**3. #225's reserved training split.** The named answer for material that is
*bench-shaped* without being the bench. One generation campaign, divided into a
bench half and a training half by a hash rule declared **before anything is
read**, with the near-duplicate screen run **across** the split rather than
only within each half — two halves each internally deduplicated can still be
near-translations of each other, which is exactly how the two bundle arms came
to be one instrument in two languages. #222 consumes that reserve rather than
generating its own, so there is one campaign and one screen.

**4. Decomposed sub-task material (#221's other route).** If #221 takes it, the
reserve goes unused and this question reopens under different terms, because
sub-task material is generated by the orchestrator rather than drawn from a
task set at all. Nothing here forecloses it.

## "No usable source yet" is a legitimate outcome

ADR-0019 gives three verdicts and only NULL retires a lever. The same applies
to this question: if #225's split is not built, and the pool's shape is judged
wrong for the floor by #222, then **the honest state is "no usable source yet"
and it is recorded as a finding** — not worked around by relaxing the guard,
and not by quietly reaching for `d1` again because it is the largest pile of
verified passes in the repository. It is the largest pile because it is the
instrument; that is the same fact.

## What would change this document

- #225 landing its reserved split — then item 3 becomes the primary source and
  the table above is a floor rather than the whole answer.
- #222 deciding the pool's shape is or is not floor-shaped material.
- A new measurement set being declared in `tools/instruments.json` — every
  live declaration subtracts from what a tune may draw on, and that subtraction
  is the point. Retiring one adds it back, which is #240 below.

## Amendment — 2026-08-10 (#240): the five sets are released

Written hours after the rest of this document, on the owner's direction after
reading what the guard cost.

**What moved.** All five local sets are retired as rulers and released for
training ([ADR-0020](decisions/0020-retire-the-rulers.md)). Source 1 flips from
ruled-out to admissible; the table goes from 608 examples over 150 problems to
**1,544 over 184**; `tools/instruments.json` carries `retired` and `trainable`
per set, and the builder refuses on `trainable` rather than on membership. The
build is recorded at
[`records/corpora/training-release-2026-08-10/`](../records/corpora/training-release-2026-08-10/README.md).

**Why the argument here did not survive.** This document assumed the five sets
were rulers worth protecting. #229 measured what they can decide: every arm on
the bench is a paired comparison, power is carried by the discordant pairs, and
at n = 20 no effect size reaches 80% power across the measured discordance
range. Protecting a ruler that cannot resolve anything buys nothing and costs
9,173 replies.

**What did not move.** HumanEval+ is retired *and* permanently untrainable, so
"every source is now open" would be the wrong reading — see ADR-0020 for the
exposure argument and its confound. The pool's shape question (source 2) is
untouched, #225's reserve (source 3) is still the named answer for bench-shaped
material, and **"no usable source yet" remains a legitimate outcome** for #221:
1,544 examples over 184 problems is more material, not evidence that a tune is
worth running.
