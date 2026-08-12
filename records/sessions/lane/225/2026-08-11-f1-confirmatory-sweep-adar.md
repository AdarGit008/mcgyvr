# The confirmatory sweep at 160: the brief reproduces (lane/225)

Date: 2026-08-11 (evening)
Issue: #225 (Phase 4). Run: `records/measurements/bench-calibration-15b-f1-all-2026-08-11/`

## Why it was run

160 `f1` problems were authored and only the **first 40 had ever been measured**.
Three tranches were written on the assumption that authoring to the same brief
reproduces the same difficulty, and two drift signals had appeared: spec prose
shortening (49 → 45 → 41 words) and the sibling screen's refusal rate rising
(0 → 2 → 4).

The asymmetry decided it. A sweep costs rig time and no authoring; the remaining
240 problems are the most expensive thing on the lane. Better to test the
assumption at 160 than to discover it at 400.

This is **not** the n=7 re-design error the campaign was burned by. That error was
re-aiming a design off a tiny sample. This is a confirmatory read at n=95
problems (190 cells), where the interval is real.

## Conditions

`qwen2.5-coder:1.5b` on **srv2**, greedy (T=0.0), cap 2048, condition stock, one
draw. Serving build **0.32.5** — the same build that produced the original 45.0%,
so ADR-0024's one-rig-one-build comparability holds. Both arms, fresh `--out`.
Wall clock: **4 minutes** for 190 cells.

## Result: no drift

| set | pass | rate | 95% Wilson |
|---|---:|---:|---:|
| **all f1 bench (both arms)** | **81/190** | **42.6%** | **35.8–49.7%** |
| bench-ts | 39/95 | 41.1% | 31.7–51.1% |
| bench-py | 42/95 | 44.2% | 34.6–54.2% |

By tranche — the question the sweep was run to answer:

| tranche | ids | pass | rate | 95% Wilson |
|---|---|---:|---:|---:|
| 4 | b228–b267 | 18/40 | **45.0%** | 30.7–60.2% |
| 5 | b268–b307 | 18/56 | 32.1% | 21.4–45.2% |
| 6 | b308–b347 | 24/48 | 50.0% | 36.4–63.6% |
| 7 | b348–b387 | 21/46 | 45.7% | 32.2–59.8% |

**Tranche 4 reproduces its original reading exactly: 18/40 = 45.0%.** Same
problems, same model, same rig, same build, and greedy decoding — so an exact
match is what a working instrument should give, and it is a determinism check the
sweep got for free. It also means the pooled figure and the original are on the
same footing rather than being two different measurements compared loosely.

**No trend across tranches.** The four readings are 45.0, 32.1, 50.0, 45.7 — not
monotone in either direction, with heavily overlapping intervals at n≈50. Tranche
5 is the low outlier rather than the start of a slide. **The prose shortening did
not move the dial**, which is what ADR-0023 predicts: words are an output of the
design and behaviour count is the dial.

**Hygiene: 0 parse refusals, 0 dispatch errors, 0 non-complete stop reasons**
across all 190 cells. Nothing is being lost to the cap or the harness.

## What this licenses, and one thing to keep watching

The pooled reading sits inside the 30–50% aim with an interval **much tighter
than the original** (35.8–49.7% against 30.7–60.2%). Authoring continues to this
brief unchanged; the decision needs no revisiting.

Worth watching rather than acting on: the pooled upper bound is **49.7%**, right
against the aim's ceiling, and tranche 6 read exactly 50.0%. The brief's
pre-registered rule for a read *above* 50% is to raise the behaviour budget
toward 4–5. We are not there — but the band is running at the top of its aim
rather than the middle, so the next confirmatory sweep should be read against
that ceiling as carefully as the floor.

**Suggested cadence: sweep again at 240**, not per tranche. Per-tranche reads at
n≈50 have intervals ~25pp wide, which is wide enough to invite exactly the
re-design-off-noise mistake the campaign already paid for twice.
