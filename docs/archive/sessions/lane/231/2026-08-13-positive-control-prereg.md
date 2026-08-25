# The rule-ablation positive control — pre-registration (lane/231, #231 check 2)

**Declared 2026-08-13T12:13Z, before a single `norule` draw is dispatched.**
Every threshold, comparator and decision below is fixed here. If this document
postdates the run it is worthless — this campaign has twice paid for reading a
design off a number it had already seen.

Governing records: **#231 check 2 as amended by #225 (2026-08-10)** — the
control is a rule-ablation condition on the generated bench, not a replay of
CLM-0017; **CLM-0017** (the historical effect and its real provenance);
**ADR-0019** (the `m >= 6` wall, and MDE as a function of discordance);
**ADR-0021** (the denominator is paired cells actually swept); **ADR-0024** (one
rig, one build); **ADR-0025** (the bar both arms are scored by).

## The question

An instrument that cannot find an effect known to be there cannot be trusted to
find a new one. #133 is the cautionary case — an all-zero measurement with no
positive control cannot distinguish "no effect" from "the rig is broken".

The effect chosen is the **output-shape rule**: the `OUTPUT:` section
`render_user_message` puts in every worker message. `norule`
(`tools/bench/matrix.json`, landed with #113) removes that one paragraph and
**nothing else** — in particular it does not touch `output_schema`, because
ablating the schema would move the parser too and the contrast would stop being
about the sentence.

**The historical figure is context, not a target.** CLM-0017 measured 7/20 →
11/20 first-pass (~+20pp) with mean completion tokens falling 427.4 → 121.5 —
on local-ai's unported Python contracts, under local-ai's own harness, on a
different model. It is quoted beside the result because #231's acceptance
requires it, and for no other purpose. At n = 20 that contrast sat below the
`m >= 6` wall (best-case two-sided p = 0.125), so an exact replay could never
have passed this gate's own arithmetic.

## The measurement

| | |
|---|---|
| model | `qwen2.5-coder:1.5b` — ADR-0017's floor unit |
| rig | srv2, `http://srv2:11434`, protocol `openai` |
| serving build | **0.32.5** — same build as check 1's pair, ADR-0024 holds |
| set | `bench-py` + `bench-ts`, full declared roots — 257 each, **514 paired cells** |
| draws | greedy, draw 0 only, T = 0.0 |
| cap | 2048 output tokens |
| scored by | `Gate.run`, the ADR-0025 bar, identical on both arms |
| conditions | `stock` (comparator, already dispatched) vs `norule` |

**Eligibility, checked before dispatch and recorded here:** all **514 of 514**
cells render an `OUTPUT:` section, so the ablation is live on every cell and none
contributes a concordant pair by construction. The ablation removes a measured
mean of **52.5 prompt tokens** per dispatch.

## The comparator is fixed here, not chosen afterwards

Check 1 dispatches **two** stock runs. Having two and picking the one that reads
better after the fact is a forking path, so:

- the paired comparator is **run A**, named now;
- **run B is reported as a sensitivity check** — the same contrast recomputed
  against it, printed whatever it says;
- check 1's own `d` is the amount that choice can move, and it is measured
  rather than assumed. That is the whole reason the null runs first.

**Disclosure, load-bearing:** check 1 must pass before this is dispatched, so
the stock arm's pass rate **will be known** when the `norule` sweep starts. What
is not known is the `norule` rate, and the test below reads only the discordant
pairs. The direction was fixed by CLM-0017 years of records ago, not by this
session.

## The prediction, and what counts as recovery

Two claims, both pre-registered, and **recovery requires both**:

1. **Direction.** `stock` accepts more than `norule` — the rule helps.
2. **Mechanism signature.** `norule` mean completion tokens are **materially
   higher** than `stock`'s. This is the historical mechanism (427.4 → 121.5) and
   it is what distinguishes "the rule shapes the output" from "something moved".

A direction with no signature, or a signature with no direction, is **not**
recovery and is reported as such.

## The test

Exact two-sided **McNemar** on the discordant pairs, α = 0.05.

- **Primary:** pooled over both arms, 514 cells.
- **Secondary:** each arm separately, reported whatever it says. The arms are
  scored by the same bar (ADR-0025) precisely so this comparison is legible.
- **`m >= 6` or no p-value is quoted.** Below six discordant pairs the exact
  two-sided p cannot reach 0.05 at any split, and a number that cannot reject is
  reported as "not decidable", never as a null result.

## What each outcome decides

| outcome | reading |
|---|---|
| direction + signature + p < 0.05 | **Check 2 passes.** The bench recovers a known effect at a decidable n. The observed size is reported beside CLM-0017's, with the provenance difference stated. |
| direction + signature, p >= 0.05, m >= 6 | **Not established.** The instrument is not shown fit on this control; the effect is smaller here than history suggests, or 514 cells do not reach it. Goes to the owner with the observed MDE. |
| m < 6 | **Not decidable.** Reported as a property of the contrast, not of the rule. |
| no direction, or no signature | **Check 2 fails.** A bench that cannot see this cannot be trusted on an unknown lever. Nothing below the trunk runs. |
| `norule` accepts *more* | Reported in full and escalated. It would mean the rule is costing acceptance on this material, which is a finding about the product, not only about the instrument. |

## Reported separately, because one could masquerade as the other

**Parse refusals versus gate rejections.** Removing the output-shape sentence
may make replies the parser cannot read. That *is* the mechanism, not an
artefact — but a delta made entirely of parse refusals is a different claim from
one made of gate rejections, so the split is reported for both arms. The row
carries `rejected_by`, so this costs nothing but the discipline of printing it.

**Both cost axes.** Prompt tokens fall by construction (−52.5 mean, measured
above); completion tokens are the signature. A lever that removes text and looks
free on the prompt axis while multiplying the completion axis is exactly what
#113's cost column exists to show.

## Limitations, stated before the result

- **This is not CLM-0017's contrast.** Different material, different harness,
  different model. It is a rule ablation of the same *kind*, and the historical
  number bounds nothing here.
- **One model, one rig, greedy, one draw per cell.** The floor unit only; check
  5's second tier is a separate run.
- **A pinned-fail cell cannot flip.** Check 1 will report how much of the set
  that is; a high pinned-fail fraction lowers `m` and the contrast's power with
  it, independent of whether the rule works.
- **The 0.55-band screen finding and the reserve question are #225's** and are
  untouched by this document.
