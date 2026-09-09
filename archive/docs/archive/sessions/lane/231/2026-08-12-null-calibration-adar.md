---
record: session/2
lane: 231
agent: adar
started: 2026-08-12
---

## Did

**#231 check 1 — the null calibration — ran and passed.** Two runs of the whole
bench half, identical in every respect, greedy, one backend session. This is the
run #189 never did.

    uv run --no-sync python tools/power/report.py --section null
    uv run --no-sync python tools/bench/null.py

New here: `tools/bench/null.py`, `tests/test_bench_null.py`, and two sections in
`tools/power/report.py` (`bench_null`, `bench_contrasts`). Measurements in
`records/measurements/bench-null-15b-{a,b}-2026-08-12/`.

The test pins the one distinction the headline number cannot make — a flip on
*identical bytes* is the harness, a flip on different bytes is the model — because
a defect that folded them together would publish the same reassuring zero either
way.

### The run

| | |
|---|---|
| subject | `qwen2.5-coder:1.5b` — ADR-0017's floor unit |
| rig | srv2, ollama **0.32.5**, one loaded model throughout (ADR-0024) |
| condition | `stock`, greedy T = 0.0, one draw, cap 2048 |
| set | `bench-py` and `bench-ts`, the full declared roots — 257 problems each |
| wall clock | 16:50 → 17:27, 1,028 dispatches, all four passes exit 0 |

The two runs went back to back with nothing else dispatched to srv2 between
them, so "one backend session" means what #231 asks it to: no unload, no build
change, no host change.

### The result

| instrument | n | pass rate | d | drift | byte-identical |
|---|---:|---:|---:|---:|---:|
| `bench-py` @ 1.5b | 257 | 70/257 | **0** | 0.00pp | 93.0% |
| `bench-ts` @ 1.5b | 257 | 60–61/257 | **1** | 0.39pp | 87.5% |
| **both arms pooled** | **514** | 130–131/514 | **1** | **0.19pp** | 90.3% |

`d` is the count of verdicts that differ — ADR-0019 D1's layer 2. **One cell in
514.** Exact McNemar p = 1.000; the single flip is a loss, so the two runs are
not distinguishable in either direction.

**The mechanism, which the headline number cannot show.** The backend is *not*
deterministic at temperature 0: **50 of 514 cells returned different code on the
two runs** (90.3% byte-identical). Of those 50, exactly **one** landed on the
other side of the acceptance boundary — `b143-drive-bridge` in the TypeScript
arm, 326 tokens against 280, both completing normally. So the wobble is real,
it is roughly 10% of cells, and at this model's pass rate it almost never
reaches the verdict.

**Acceptance drift is zero.** No cell scored differently on *identical bytes* in
either arm. That is the failure that would have mattered: a nondeterministic
grader puts a floor under every contrast the bench will ever run, and no number
of extra problems lowers it. `tools/bench/null.py` exists to separate the two
because `d` alone cannot, and only one of them is survivable.

**The replies are pinned and stamped.** All 1,028 captured replies joined the
parser's golden corpus (`tools/replies/pin.py`, 20,169 total), and #230's guard
classified all four runs as `bench-py`/`bench-ts` on its own — 257 identical
contract digests plus the declared tier, in each. Those sets are
`trainable: false`, so `build_dataset.py` refuses this material at the point of
entry without anyone remembering to exclude it. The guard did the thing it was
built for on the first run that tested it.

**Rig health.** One cell per arm truncated at the 2048 cap and was recorded as a
parse refusal — `b035-route-params` (py) and `b184-dose-totals` (ts), the same
two in both runs. Deterministic, so they contribute no drift, but they are the
same defect #212 named: a "parse refusal" is usually the output cap, not the
reply format. No dispatch losses; `completeness` is clean on all four runs.

### The stop condition, evaluated in writing

ADR-0019 D2: *the bench is fit for a bar `b` if and only if `MDE <= b` and
`d < b`.* #231's own stop condition is the second one, and #229 states it as
*"if the null drift reaches the adoption bar, the bench is unfit."*

> **`d` = 0.19pp pooled (1 of 514), 0.00pp on the Python arm, 0.39pp on the
> TypeScript arm. The lowest bar this project has named is the owner's 3pp
> floor, and the lowest achievable is class R's, which is the bench's own MDE —
> currently no better than 4.1pp at any psi. `d` is below both by more than an
> order of magnitude. The stop condition does not fire.**

Stated against the uncertainty rather than the point estimate, because one pair
of runs is one observation of a rate: 1 of 514 has a 95% interval of
**[0.03, 1.09] pp**. Even the upper end clears 3pp comfortably. Per arm the
intervals are wider — py [0.00, 1.47], ts [0.07, 2.17] — and still clear.

**This does not make the bench fit.** D2 has two conditions and this run
supplies one. `MDE <= b` needs `psi` from the commissioning contrast, which is
check 2 and has not run. **Commissioning is not complete and no arm may be
dispatched.**

**And the null does not transfer up the ladder.** `d` is low here partly because
75% of cells fail under both runs and a pinned-fail cell cannot flip. A model
with a higher pass rate has more cells near the boundary, so the 10% text wobble
has more chances to cross it. D2 already says "per target tier"; this run is why
that wording has to be obeyed rather than assumed — check 5's second tier needs
its own null, not an inherited one.

## Two findings from data already on disk

Both were found while the sweep ran and neither cost rig time.

### 1. The instrument is 514 cells, not 298 — the denominator is scoped to one band

`tools/instruments.json` declares `bench-ts`/`bench-py` by **root**, and
`measure.py --tier bench-py` accordingly serves **every** bench-half problem in
`tools/bench/tasks/py` — 257 of them, across eight steering bands:

| band | f1 | g0 | g0a | g0b | g1 | g2 | g3 | g4 | total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bench half | 149 | 23 | 22 | 18 | 13 | 14 | 12 | 6 | **257** |

`f1` is 58% of the instrument. But `tools/bench/redundancy.py --section
denominator` reports **band `f1` alone** — "280 authored, 149 bench" — and
ADR-0021's sizing table inherits that scope. The table's rows are an authoring
forecast for one band; they have been read as the bench's size.

Recomputed over what the tier actually serves, with `tools/power/mde.py`:

| authored | bench half | swept cells | psi=0.10 | psi=0.20 | psi=0.35 | psi=0.45 | `psi_draw`=0.659 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 400 (the plan) | 213 | 426 | 4.5pp | 6.3pp | 8.2pp | 9.4pp | 11.3pp |
| **498 (realized, all bands)** | **257** | **514** | **4.1pp** | **5.8pp** | **7.6pp** | **8.6pp** | **10.3pp** |

This is the same denominator defect appearing a fourth time in this chain, and
it is the first time it has run in the **optimistic** direction — the instrument
is larger than the record says, so nobody had cause to check. That is exactly
why it survived.

**It is a question, not a correction.** The g-bands are the pilot batches that
`strata.json` was measured from. Whether problems that set the stratification
may also serve as instrument material for a *lever* contrast is the owner's
call, not this session's. Two defensible readings:

- **All eight bands** — 514 cells. What the declaration says today and what
  every sweep has actually dispatched, including this null.
- **`f1` only** — 298 cells. What ADR-0021 and `redundancy.py` describe. Would
  require narrowing the declared root or the tier, neither of which exists.

The declaration and the documents disagree, and one of them has to move.

### 2. There is measured `psi` on the bench, and it is far below `psi_draw`

ADR-0021's fourth amendment leaves `psi` as the open input and its rightmost
column is `psi_draw` = 0.659 — resampling sensitivity at temperature, which is
not the discordance rate of a greedy lever contrast. The scaffold ablation of
2026-08-11 already holds paired greedy `stock` / `planonly` / `noscaffold` arms,
and nobody had added them up. `report.py --section contrasts` now does:

| model | arm | contrast | n | m | psi |
|---|---|---|---:|---:|---:|
| 3b | py | stock→planonly | 34 | 2 | 0.059 |
| 3b | py | stock→noscaffold | 34 | 2 | 0.059 |
| 3b | ts | stock→planonly | 34 | 6 | 0.176 |
| 3b | ts | stock→noscaffold | 34 | 2 | 0.059 |
| 7b | py | stock→planonly | 34 | 11 | 0.324 |
| 7b | py | stock→noscaffold | 34 | 10 | 0.294 |
| 7b | ts | stock→planonly | 34 | 7 | 0.206 |
| 7b | ts | stock→noscaffold | 34 | 5 | 0.147 |

Pooled over both arms and both levers: **3B psi = 0.088** (12 of 136), **7B psi
= 0.243** (33 of 136). Every cell sits between 0.059 and 0.324 — the whole
measured range is below the 0.45 column and nowhere near 0.659.

At 514 cells and psi ≈ 0.24 the bench resolves roughly **6.3pp**, inside ADR-0019
D5's +5 to +8pp target. #225's finding that the finished corpus *"misses D5's +5
to +8pp rather than sitting at its edge"* was computed at `psi_draw` over the f1
denominator; both inputs move the same way.

**What this is not.** It is the **scaffold** lever, at 34 tasks a cell, at the 3B
and 7B — not #231's commissioning contrast at the floor unit. Each psi carries a
wide interval at that n, and note that psi *rose* with model capability (0.088 →
0.243), which is the pinned-fail mechanism again: a floored model has fewer cells
able to move. It bounds the range. It is not D2's input and this record does not
use it as one.

## Left open

**Check 2 is next and it is the gate's remaining half.** The rule-ablation
condition #225's amendment chose needs the ablation knob, which
`docs/bench-design-2026-08-10.md` §6 defers to #113 — still open. Whether the
knob is built on this lane or #113 is dispatched first is the next decision.

**Checks 3, 4 and 5 have not started.** The round definition, the declared
reproducibility bounds, and the second-tier re-run. Check 4 is nearly free now —
the number `#113`'s fourth acceptance item wants *is* this record's `d` and its
interval — but it should be declared once, after check 2, not piecemeal.

**Authoring stays paused, and this run says nothing about whether to resume.**
That decision turns on MDE, and MDE turns on `psi`, which is check 2's.

**The band question above wants an owner answer before any sizing figure is
quoted again.** Every MDE in this record is computed at 514 cells.

next: check 2 — the rule-ablation positive control, and the knob it needs.
