---
record: session/3
lane: 231
agent: adar
started: 2026-08-13
---

## Did

**Checks 1 and 2 ran under #113's gate scorer. Check 1 passes. Check 2 recovers
the effect decidably and does *not* satisfy the signature it was pre-registered
against — that is the owner's call, and it is not being counted as a pass here.**

Re-derive: `uv run --no-sync python tools/bench/null.py` and
`uv run --no-sync python tools/bench/control.py`. Both exit non-zero when their
own criteria fail, so neither verdict can drift from the number it describes.

### Why check 1 was re-run rather than recomputed

#245 measured the null under the acceptance command alone. #113 moved scoring to
`Gate.run`, which is a **different bar and therefore a different null**, and the
old figure cannot be converted into the new one — `Gate.run` short-circuits, so
a lint-rejected candidate never ran its test.

Four passes back to back on srv2, nothing else dispatched between them:
**1,028 greedy dispatches, 12:10 → 13:05 UTC, all exit 0, none lost to
transport.** Both arms, full declared roots, cap 2048, `stock`, build 0.32.5.

| arm | pass | d | byte-identical |
|---|---:|---:|---:|
| `bench-py` | 23/257 both runs | **0** | 232/257 |
| `bench-ts` | 33/257 both runs | **0** | 225/257 |
| pooled | 56/514 | **0 of 514**, 95% CI [0.00, 0.74] pp | 457/514 |

The stop condition does not fire. **57 of 514 candidates differed in bytes and
none crossed the boundary**, and acceptance drift — identical bytes scoring
differently — is **zero**, as it was under the old bar. That is the failure that
would have been unfixable.

Read honestly, `d = 0` is partly a property of where the boundary now sits: at
8.9% and 12.8%, most cells are pinned-fail, and a pinned-fail cell cannot flip.

### Check 4, which check 1 is what fills

`tools/bench/reproducibility.json` now carries a bound per arm: **±1.47pp**, the
upper limit of the 95% Wilson interval on 0/257. Declaring **0.0pp** would claim
the instrument is exact, which 257 cells cannot establish. Per tier, not pooled
(0.74pp): ADR-0019 D2 measures the null per target tier and the report keys a
bound to one. #113 declared the property this morning and left it empty by
design; it was empty for about four hours.

### Check 2 — pre-registered before dispatch, and read to that document

Pre-registration `f73f47bf`, committed before a single `norule` draw. It fixed
three things that would otherwise have been chosen afterwards: the comparator is
run **A** (two stock runs exist; picking the flattering one is a forking path),
recovery requires **direction and the mechanism's signature**, and `m >= 6` or
no p is quoted.

| | stock | norule | delta | m | exact p |
|---|---:|---:|---:|---:|---:|
| `bench-py` | 23/257 | 15/257 | −3.1pp | 14 (3 gained, 11 lost) | 0.057 |
| `bench-ts` | 33/257 | 11/257 | −8.6pp | 26 (2 gained, 24 lost) | 1.05e−5 |
| pooled | 56/514 | 26/514 | **−5.8pp** | **40** (5, 35) | **1.4e−6** |

**Direction recovered, decidably, and far outside the bound declared an hour
earlier** — the first real use of that bound, and it did its job. The
sensitivity check against run B is identical to the point estimate, which
follows from `d = 0` rather than from luck.

**The Python arm alone would not have passed.** p = 0.057 at m = 14. It is
reported because the pre-registration said both arms are reported whatever they
say, and because a single-arm bench would have returned "not established" here.

### The signature was absent, and the pre-registration is being honoured

CLM-0017's mechanism was **length**: 121.5 completion tokens with the rule,
427.4 without — 3.5×. On this material it does not appear at all.

| arm | stock mean/median | norule mean/median | ratio |
|---|---|---|---:|
| `bench-py` | 161 / 135 | 166 / 120 | **1.03×** |
| `bench-ts` | 188 / 135 | 192 / 135 | **1.02×** |

Per the pre-registered rule — *"a direction with no signature is not recovery,
and is reported as such"* — **check 2 is not being marked passed.** The
limitations section of that same document anticipated why: *"this is not
CLM-0017's contrast… the historical number bounds nothing here."* I pre-registered
a signature borrowed from other material, a different harness and a different
model, and it did not transfer.

### Where the mechanism actually shows

Not in length — in **form**. Counted over every rung that fired, recomputed from
`fail_output` rather than `rejected_by` (which is `findings[0]`, an ordering
artefact that would show rungs merely trading places):

| rung | py stock → norule | ts stock → norule |
|---|---|---|
| lint | 154 → 197 (**+43**) | 32 → 156 (**+124**) |
| structure | 1 → 26 (**+25**) | — |
| format | 155 → 162 (+7) | 148 → 149 (+1) |
| any adapter finding | 178 → 212 (**+34**) | 157 → 199 (**+42**) |
| reached the acceptance rung | 79 → 45 (**−34**) | 100 → 58 (**−42**) |

**`acceptance` falling is not the ablation doing better.** The gate
short-circuits, so that row counts candidates that *got as far as* the test.
Proven rather than assumed: **no row in either run carries both an adapter
finding and an acceptance finding**, in any of the four run-arms. The adapters
rung always runs, so its row is the uncontaminated comparison — and it says the
ablation produces 34 and 42 more ill-formed candidates, which never reach the
correctness test at all.

So the rule is load-bearing on this material, and what it buys is **well-formed
output**, not short output. That is a finding about the product as much as about
the instrument.

### One defect in my own first read

The rung profile was initially parsed by splitting `fail_output` on `;` and `:`.
Acceptance findings carry whole Python tracebacks, so that invented rungs out of
stack frames (`ValueError`, `Traceback (most recent call last)`). Fixed with a
fixed label vocabulary anchored at a finding boundary, plus `check_vocabulary`,
which refuses to print a profile unless every row's own `rejected_by` appears in
the set parsed from its text — an under-reported profile fails in the direction
that makes an ablation look tidier than it is.

## Left open

- **Check 2's verdict is the owner's.** The effect is recovered and decidable at
  p = 1.4e−6; the pre-registered signature is absent; the mechanism is visible in
  the rung profile instead. Marking it passed means accepting a signature the
  pre-registration did not name, and that is a decision, not a reading.
- **Checks 3 and 5 have not run.** Check 3 is the pinned round (one product
  revision per round, recorded in run metadata); check 5 re-runs the battery
  against a second tier, the 7B being the natural subject.
- **The Python arm's p = 0.057** is a live datum for #225's sizing question, not
  just a footnote here: at this bar the arms differ in what they can resolve.
- **#245 is superseded by this run** and should close or be re-pointed; its null
  describes the old grader.
- **`make check` has not run since the sweeps** — deliberately, to keep local CPU
  off the rig while it measured. It runs before this branch is pushed.

next: run `make check`, push, and take check 2's verdict to the owner before
checks 3 and 5 — a commissioning gate that grades its own borrowed criterion is
the failure this issue exists to prevent.
