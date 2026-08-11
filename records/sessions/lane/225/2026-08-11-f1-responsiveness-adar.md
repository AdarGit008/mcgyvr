# `f1` responsiveness — the band is alive, and the 400 may buy less than D5 priced

Reads the run pre-registered in `2026-08-11-f1-responsiveness-prereg.md`
(committed `fd43cd0b`, before dispatch). Figures re-derive with:

```
uv run python tools/bench/responsiveness.py \
  --run records/measurements/f1-responsiveness-15b-2026-08-11 \
  --baseline records/measurements/bench-calibration-15b-f1-240-2026-08-11 --draws 8
```

Full output is kept beside the rows as `responsiveness.txt` / `.json`.

## What ran

135 `f1` bench-half problems, both arms, **9 draws per cell** — greedy draw 0
plus 8 sampled at T=0.7 — on srv2, `qwen2.5-coder:1.5b`, cap 2048, condition
`stock`, serving build **0.32.5** (the same build as both earlier reads, so
ADR-0024 comparability holds). **2,430 dispatches, 2,430 rows recorded, 0
missing cells, 0 draws lost to dispatch error.** The 105 reserve problems were
not swept. Wall clock ~65 minutes at 1.7 s per dispatch.

## Validity gate — passed, with the campaign's first greedy drift at this size

Draw 0 against the 240 sweep: **270 shared cells, greedy 105 → 104, one cell
drifted** — `ts/b387-tag-index`, which passed on the day and fails now. The
pre-registered allowance was 2, so the run is read.

That single flip is worth naming rather than rounding away, but it is **not** a
regression. ADR-0019's determinism table shows 0-task drift for this model at
**n = 20**, and 1 problem in **255** for the pool instrument at 14B. One cell in
270 is 0.37%, which is exactly the rate the larger-n instrument already showed.
Zero drift at n=20 and one at n=270 is a sample-size effect. This is now the
**fourth** free determinism check the campaign has taken and the first to have
enough cells to see a flip at all.

## Primary: the band is not arm A, and it is not close

|  cells | pinned-fail | pinned-pass | responsive |
|---:|---:|---:|---:|
| 270 | 83 (30.7%) | 9 (3.3%) | **178 (65.9%)** |

**`psi_draw` = 0.659, 95% Wilson 0.601–0.713.** The pre-registered floor was
0.10 and the "sizing holds" threshold 0.20. This clears both by a wide margin.

The failure mode that prompted the run — a band comfortably in range by level
while nearly every cell is pinned, as the bundle's Python arm A was at 65–70%
with 5% responsive — **is ruled out for `f1`.** Two thirds of its cells can move.
Whatever else is true, this material is not an instrument that returns the same
answer to every question.

## The pre-registered test: t8 vs t4–7 pooled, pinned-fail

|  | pinned-fail | of | rate |
|---|---:|---:|---:|
| t8 | 19 | 44 | 43.2% |
| t4–7 pooled | 54 | 190 | 28.4% |

**Fisher exact, two-sided: p = 0.071.** At the α = 0.05 declared in advance this
**does not reject**, and by the pre-registered rule that is outcome 1: *the
problems are reachable, merely harder.*

**It should not be reported as "t8 is fine."** The gap is 15 percentage points in
the direction predicted before the draws existed, and the test is underpowered —
44 cells against 190. A p of 0.071 is a failure to establish, not evidence of
absence. The pre-registered rule is followed because it was pre-registered, not
because the number settles the question.

## Descriptive: t8 is genuinely harder, and it is not single-draw noise

Not pre-registered, no p-values. The greedy rate of a tranche rests on **one
draw per cell**; this is the same question asked with eight times the data.

| tranche | cells | greedy | sampled (8 draws) | pinned-fail | responsive |
|---|---:|---:|---:|---:|---:|
| t4 | 40 | 45.0% | 43.8% | 15.0% | 77.5% |
| t5 | 56 | 32.1% | 26.3% | 33.9% | 66.1% |
| t6 | 48 | 50.0% | 35.7% | 29.2% | 66.7% |
| t7 | 46 | 43.5% | 31.8% | 32.6% | 58.7% |
| **t8** | 44 | **22.7%** | **19.3%** | **43.2%** | 56.8% |
| t9 | 36 | 38.9% | 26.4% | 27.8% | 72.2% |
| **ALL** | **270** | **38.5%** | **30.4%** | 30.7% | 65.9% |

t8 stays the lowest tranche under sampling — 19.3% against 33.7% for the t4–7
pool — and it carries both the highest pinned-fail share and the lowest
responsive share. **The 22.7% was not a fluke of one unlucky draw per cell.** The
thinning mechanism logged a tranche early is doing something real to difficulty.

What the numbers do *not* support is the stronger worry that motivated the run:
that t8's problems are dead cells. **56.8% of them are responsive.** They are
harder material, not absent instrument, and they earn their place in the 400.

## The knife edge — and why a greedy tranche rate is a shakier statistic than it looks

Sampled pass count per cell, over 270 cells:

| 0/8 | 1/8 | 2/8 | 3/8 | 4/8 | 5/8 | 6/8 | 7/8 | 8/8 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 89 | 45 | 26 | 19 | 26 | 22 | 22 | 12 | 9 |

**172 cells (63.7%) sit strictly between 0/8 and 8/8.** For most of the bench, a
cell's verdict is a coin weighted somewhere in the middle, and the greedy sweep
observes one arbitrary point on it.

This does **not** make the greedy instrument unreliable — greedy is
deterministic, it reproduced 269 of 270 cells, and a greedy paired contrast
therefore carries essentially no draw noise. Reproducibility is intact. What the
spread says is something different: the cells are **sensitive**, and a lever does
not need to be large to tip a lot of them.

The pooled sampled rate is **30.4% against 38.5% greedy**. Both operating points
exist in production — `runner.py` defaults to `temperature = 0.0`, which is what
the band is aimed at and what the brief pre-registered, while the breadth path
(#119, ADR-0008) dispatches draws at temperature. So the band sits mid-aim on
the default path and at the very floor of 30–50% on the breadth path. Nothing
here re-aims anything; it means the band's position is a property of the
operating point as well as the material, which no record has said before.

## The sizing consequence, and it runs the opposite way to intuition

Higher `psi` is **not** better. D5's own table makes this explicit — reaching a
3pp bar costs 920 tasks at `psi` = 0.10 and 3,113 at `psi` = 0.35 — because more
discordant pairs means more variance in the net, and the net is what the test
reads. Feeding the measured figure back through the same function:

| n | unit | MDE at `psi_draw` = 0.659 |
|---:|---|---:|
| 270 | cells today | 14.4pp |
| 400 | problems | **11.8pp** |
| 800 | cells, at 400 problems | **8.2pp** |

D5 planned n = 400 to resolve **+5 to +8pp**. On the generous reading of the
denominator it lands at 8.2pp, the pessimistic end of that range; on the strict
reading, 11.8pp — outside it.

**This is a flag, not a finding, and the reason is in the pre-registration.**
`psi_draw` is sensitivity to *resampling*, not to a *lever*, and the two are
different quantities. A greedy lever contrast has no resampling in it at all.
High draw-sensitivity makes high lever-sensitivity plausible — a knife-edge cell
is an easy cell to tip — but plausible is not measured. **The real `psi` is still
#231's to measure on the commissioning contrast, and nothing here discharges
that.** What this run does is remove the assumption that `psi` for this material
sits in the 0.10–0.35 planning prior; there is now a reason to think it may sit
above it, and above it is the expensive direction.

## The denominator, again

D5 says 400 and the campaign counts problems. The sweep dispatches cells, and a
problem carries two language arms, so the same `psi` gives 11.8pp or 8.2pp
depending on which is meant — a factor that decides whether the bench meets its
own spec. The tool reports both and picks neither.

ADR-0021 exists because D5 *"stated the number without stating its denominator"*
one level up. The same defect survives one level down and is now load-bearing.
**Owner's to settle; not settled here.**

## What this decides

1. **The catastrophic case is ruled out.** `f1` is a live instrument. Authoring
   does not stop, and no re-aim is triggered.
2. **The pre-registered rule fires outcome 1: carry on unchanged.** The owner's
   lean — accept the deviation, the 1.5B is the hard one — is the course the
   evidence supports, with the correction that t8's problems are harder in a way
   that reproduces, so the drift is material rather than noise. The band absorbs
   it; the pooled read stays in aim.
3. **160 problems remain**, and the brief stands unchanged.

## What is open, and is the owner's

- **The denominator.** 400 problems or 800 cells. It decides whether the bench
  meets D5's own resolution target.
- **Whether `psi_draw` = 0.659 changes the 400.** If the lever `psi` lands
  anywhere near it, 400 problems buys ~12pp rather than the 5–8pp planned, and
  the honest options are more material, more draws per cell (D6's replication
  route, which this run has now shown is cheap on this rig — 65 minutes for 8×),
  or accepting a coarser bar. **#231 measures the number that settles it.**
