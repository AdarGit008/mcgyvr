---
record: session/5
lane: 113
agent: adar
started: 2026-08-13
---

## Did

**The eighth acceptance item's own half.** #113 splits it: *"the report declares
the property here; the number that fills it comes from #231's null
calibration."* Four sessions carried it as open on both halves. This closes the
half this issue owns — the report now states the deviation two identical runs may
differ by, on every table, or states that none is declared.

Changed: `tools/bench/reproducibility.json` (new), `tools/bench/report.py`,
`tests/test_bench_report.py`. No rig time, no dispatch.

### Not declared is a state, and it is printed like one

`bounds` ships **empty**, and that is the honest state of the world rather than
an omission: no null has been measured under the gate scorer, and #231's is
under the old grader (`Gate.run` short-circuits, so its figures cannot be
recomputed into this one — the memo on that stands). So today every table says:

    - reproducibility: **not declared** — no null has been measured for
      qwen2.5-coder:1.5b at tier bench-py (#231). Every `vs baseline` figure
      below is unqualified: nothing here states how much of one is the
      instrument's own drift

The wording is the point. An absent bound is not a zero bound, and a delta
smaller than an undeclared drift is not a small effect — it is an unknown one.
This is the same rule the interaction term already follows in this file, applied
one level up: **absent rather than zero**.

When a bound *is* declared the header states it with the two runs it came from,
and every `vs baseline` figure at or inside it is marked `†` with a footnote
saying the contrast is the instrument and not the lever.

### A bound is matched on four fields, and it is meant to be brittle

`model`, `tier`, `gate_rungs`, `serving_build`. A mismatch in any one means *not
declared*, and the message names the field that differed.

- **tier** — ADR-0019 D2 says the null is measured per target tier. #231 already
  found why: `d` is low partly because 75% of cells fail under both runs and a
  pinned-fail cell cannot flip, so a higher-pass-rate model has more cells near
  the boundary.
- **gate_rungs** — a bar that scores differently produces a different null. This
  lane moved bench-py from 27.2% to 8.9% by changing the bar alone; a bound
  measured on one side of that describes nothing on the other.
- **serving_build** — ADR-0024. Two runs differing by an ollama patch release
  that nothing on disk recorded is the failure that already happened twice.

Brittle on purpose. A null costs roughly 40 minutes to re-measure. A borrowed one
costs a published effect that isn't there.

### The interaction term is not qualified by this bound

An interaction term is a difference of differences and carries the drift of every
arm inside it, so a single-contrast bound is a **floor** on its noise rather than
a bound on it. The report says so under `## Interaction` and marks no term. The
alternative — reusing the number because it is the one to hand — is the
arithmetic #233 exists to stop anyone assuming away.

### An input for #231, deliberately not declared here

The two gate-scored runs session/2 left on disk are the same model, tier, bar and
build, and `score.py` has not moved for the Python arm since (`f9aac21e` stages
the JS toolchain only). Compared today:

    cells 257   flips 0   byte-identical 233/257   acceptance drift 0

Zero flips, and zero on identical bytes — the failure that would be unfixable is
absent again. It is **not entered as a bound**, for three reasons: it is
bench-py only where the protocol is both arms (514 cells), it was run to hunt
scorer defects rather than under a pre-registered null, and commissioning is
#231's verdict to give, not this lane's. It is recorded here so #231 starts from
a number instead of from cold.

### Verified

- `make check`: **1356 passed** (1346 + the ten added here).
- The renderer against a real run directory, not a fixture: the *not declared*
  line prints as quoted above.

## Left open

- **#113 is 8 of 8 and closes with this.** The number that fills the declared
  property is #231's and is tracked there, which is what the issue's own split
  says.
- **#231's checks re-run under the gate scorer**, both arms; the input above is
  bench-py only.
- **The pre-gate normalisation lever** (+13.7pp at zero tokens, session/2) still
  needs an issue of its own.
- **`make lint` still runs ruff only** — this repository's own JavaScript is not
  held to ADR-0025's bar. Named in that ADR's consequences.
- **#81's classification is an ADR-0019 amendment**, and the 31 non-conforming
  references are #225's.

next: #231's commissioning checks under the gate scorer — a null over both arms,
then CLM-0017's known output-shape effect recovered through the `norule` lever.
