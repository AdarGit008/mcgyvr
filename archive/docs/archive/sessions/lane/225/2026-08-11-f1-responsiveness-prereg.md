# `f1` responsiveness — pre-registration (lane/225)

**Declared 2026-08-11T19:37Z, before a single draw is dispatched.** Every
threshold, classification rule and decision below is fixed here. If this
document postdates the run it is worthless — the campaign has twice paid for
reading a design off a number it had already seen, and once for a comparison
chosen after six tranches were on the table.

Governing records: **ADR-0019** (D5 — the size is a function of `psi`, and
`psi` is measured, not assumed), **ADR-0021** (the floor unit is the
obligation), **ADR-0024** (one rig, one build). Brief this tests the material
of: `2026-08-11-floor-band-f1-brief.md` — **not re-aimed by this document.**

## The question

`f1` is 240 problems deep and reads **105/270 = 38.9%** greedy on the floor
unit, inside the brief's 30–50% aim. That figure is a statement about
**level**. ADR-0019 already priced the distance between level and resolution
and the price was severe:

> bundle Python arm A — n=20, 13 always pass, 6 always fail, **1 responsive (5%)**

Arm A sat at 65–70%, dead centre of any band one would declare, with nineteen
of twenty tasks pinned. ADR-0019's own words: *"Being in band is not the same
as having resolution, and level cannot reveal the difference."*

`tools/power/report.py` reports responsiveness for four instruments today.
**None of them is `f1`.** D5 states plainly that *"#231 measures `psi` on the
commissioning contrast and #225 is sized from that measurement"*, and #231 has
not run. So 240 problems have been authored against a number — 400 — whose only
measured input does not yet exist for this material.

This run buys that input on the material we already have, before the remaining
160 problems are authored.

**It also tests one specific worry.** Tranche 8 read 22.7% and the identified
mechanism was domain unfamiliarity (clock arithmetic, wrap windows, grid
indexing, path normalisation), not behaviour count. If the floor unit fails
those because it does not know the domain, they are plausibly **pinned-fail**:
concordant 0/0 cells that contribute zero discordant mass under any lever, and
therefore worth less toward the 400 than their nominal count. Under the m ≥ 6
wall (best-case two-sided p = 2/2^m) that is a worse defect than being a few
points under band, and the greedy sweep cannot tell the two apart.

## The measurement

| | |
|---|---|
| model | `qwen2.5-coder:1.5b` (floor unit, ADR-0021) |
| rig | srv2, `http://srv2:11434`, protocol `openai` |
| serving build | **0.32.5** — same build as both prior reads, ADR-0024 holds |
| tasks | the **135 `f1` bench-half problems**, b228–b466, both arms = **270 cells** |
| draws | **9 per cell**: greedy draw 0 at T=0.0, then **8 sampled at T=0.7** |
| cap | 2048 output tokens, unchanged |
| condition | `stock` — no lever, no scaffold (`f1` is authored `scaffold: none`) |
| reserve | **not swept.** The 105 reserve problems stay unmeasured. |

Total dispatches: 270 × 9 = **2,430**. Fresh `--out`; a directory measured at
one temperature or cap refuses another.

## Validity gate — checked first, and it can void the run

Draw 0 is greedy at the same build, rig, cap and condition as the 240 sweep. It
**must** reproduce that sweep cell for cell:

| | pooled | t4 | t5 | t6 | t7 | t8 | t9 |
|---|---:|---:|---:|---:|---:|---:|---:|
| greedy, 240 sweep | **105/270** | 18/40 | 18/56 | 24/48 | 21/46 | 10/44 | 14/36 |

Prior greedy re-runs at this model size drifted **0 tasks** (ADR-0019's
determinism table). Anything beyond **±2 cells** is rig or build drift, not
noise: the run is **VOID** and nothing below is read. This is the fourth free
determinism check the campaign has taken.

## Classification — fixed now

Per cell, over all 9 draws (greedy + 8 sampled):

- **pinned-fail** — 0 passes in 9
- **pinned-pass** — 9 passes in 9
- **responsive** — anything in between

`psi_draw` = responsive / 270.

## Primary read, with thresholds anchored in ADR-0019's measured range

ADR-0019 measured `psi` from 0.05 (arm A, the failure) to 0.45 (arm B), and
used 0.10–0.35 as the planning prior D5's sizing table spans. Thresholds are
taken from that range, not invented here:

| `psi_draw` | reading | consequence |
|---|---|---|
| **≥ 0.20** | at or above the planning prior's middle | sizing holds; n=400 buys the +5 to +8pp D5 priced |
| **0.10 – 0.20** | the prior's pessimistic end | sizing holds at the weak end; reported, authoring continues |
| **< 0.10** | arm A territory | `f1` has a resolution defect independent of any tranche; 400 problems will **not** buy what D5 priced, and this goes to the owner before more material is authored |

## Secondary read — the tranche question

**Pinned-fail fraction per tranche, reported for all six**, not only for
tranche 8 against a pool chosen to exclude it. Pre-registered comparison:
tranche 8 (44 cells) vs tranches 4–7 pooled (190 cells), two-proportion test,
two-sided, α = 0.05.

**Disclosure, load-bearing:** tranche 8's identity was selected by a post-hoc
look at six tranches. What makes this test confirmatory rather than a second
bite is that it tests a **different quantity** (pinned-fail fraction, not pass
rate) on **data that does not yet exist** (the sampled draws). It is a genuine
out-of-sample prediction. It is *not* independent evidence that tranche 8 is
unusual among tranches — the all-six table is there so a reader can judge that
for themselves, and any tranche other than 8 standing out is **observational
and gets no p-value**.

## What each outcome decides

1. **t8 pinned-fail not materially above t4–7** → its problems are reachable,
   merely harder. They are valid instrument, the pooled drift is a level
   effect and not a resolution loss, and the owner's lean is vindicated on
   evidence: **carry on unchanged**, per option 1 of the #225 comment.
2. **t8 pinned-fail materially above t4–7** → the thinning is manufacturing
   dead cells, and further authoring into unfamiliar domains buys nominal
   count without instrument. That is the case for option 2 (hold behaviour
   count at the low end of 2–4 in unfamiliar domains), and it puts the banking
   option on the table.
3. **`psi_draw` < 0.10 overall** → dominates both. The band's problem is not
   tranche 8 and re-aiming a tranche does not touch it.

Outcomes 1 and 2 are readings of the material. **Neither re-aims the brief**,
and neither is acted on beyond what is written here without the owner.

## Limitation, stated before the result

**Draw-responsiveness is a proxy for lever-responsiveness, and a permissive
one.** A cell that varies across sampled draws is demonstrably reachable by
this model, so a lever that improves its odds has something to move. The
converse does not hold cleanly: a cell pinned across 9 draws could still be
unpinned by a lever that supplies information the model lacks — a bundle
carrying a domain fact is the obvious case.

So `psi_draw` is **not** `psi`, and it is not a strict bound in either
direction. It is the cheapest available screen for dead cells, and it costs rig
time rather than authoring — the axis this project has spare. The real `psi`
for a given lever remains #231's to measure on the commissioning contrast, and
nothing here discharges that.

## Banking — named here so it cannot be invented afterwards

If outcome 2 lands, one response is to route domain-unfamiliar drafts to a
banked band for the 3B rather than force them into `f1` (ADR-0021 clause 5 did
exactly this once, re-labelling 220 problems rather than discarding them; the
overlap amendment lets one problem count toward two models' 400s).

**This is only legitimate if band assignment is declared at authoring time**
from the screen-pressure and domain signal, **before any sweep sees the
problem.** Re-banding after a read selects on the outcome and biases `f1`
upward by construction. No problem already swept is re-banded on the strength
of this run.
