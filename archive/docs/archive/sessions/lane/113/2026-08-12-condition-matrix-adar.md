---
record: session/1
lane: 113
agent: adar
started: 2026-08-12
---

## Did

Opened the lane and landed **the condition matrix as data** — #113's second
scope bullet and the half of its first acceptance item that was still open.
**No measurement was run.**

New: `tools/bench/matrix.json`, `tools/bench/matrix.py`,
`tests/test_bench_matrix.py`. Changed: `tools/breadth/measure.py` reads its
cells from the matrix instead of knowing them, and `tools/bench/README.md`.

### What was already done, and what was not

The first acceptance item asks for two things and one of them had already
landed. **#225/#230 declared the task set**: `tools/instruments.json` carries
`bench-ts`/`bench-py` by root, `retired: null, trainable: false`, and the
2026-08-12 null run confirmed the guard classifies a bench sweep on its own.
What was missing is the other half — *"the condition matrix is data in the
repository, not arguments a runner improvises."*

It was three string constants and a three-branch `if` inside the runner
(`measure.py:192`). The comment above them said so: *"#113 owns the general
condition matrix; this is one named knob it will subsume, not a framework."*

### The shape

A **cell** names a set of **levers**. The empty set is the baseline, and there
must be exactly one. Every effect is measured against it.

A **lever** declares two things beyond what it does:

- **`stage`** — `contract` levers change the task the worker is given;
  `message` levers change only how it is asked. Folding these together would
  make it impossible to say which of the two a cell did.
- **`slot`** — the one field it writes. `noscaffold` and `planonly` both
  rewrite `target_content`, so a cell naming both is **refused when the matrix
  loads**. Applied together the result would depend on which ran last, and an
  order-dependent cell is not a condition — it is a bug with a name, and a
  measurement taken under it would look exactly like a real one.

That rule is what makes a multi-lever cell first-class rather than a corner
case, which is #113's fourth acceptance item and what #233 consumes.

### The rule-ablation knob — #231 check 2's positive control

`norule` removes the `OUTPUT:` section from the rendered user message — the
line `render_user_message` appends from `_REPLY_INSTRUCTIONS`, which is
CLM-0017's output-shape sentence. It is a **message**-stage lever, and the
first one, because the rule lives in the render rather than the contract.

Two things it deliberately does not do:

- **It does not touch `output_schema`.** Ablating the schema would remove the
  section *and* move the parser, and the contrast would stop being about the
  sentence. The reply is parsed exactly as it is under the baseline.
- **It does not match the word loose.** `render_user_message` joins sections
  with a blank line, so the ablation matches `OUTPUT: ` at a paragraph
  boundary. A task description containing the word survives.

Removing it from a message that has no such section raises rather than
silently doing nothing: a no-op ablation contributes a concordant pair and
dilutes a paired test rather than adding to it — the same reason `noscaffold`
makes the caller select its eligible set.

**#231's check 2 now has its knob.** The eligible set and the run are that
issue's.

### The prompt is re-costed after a message lever

`norule` *removes* text, so carrying the assembled token count forward would
price the ablation as free on the cost axis #113 asks the report to carry. The
message stage recomputes with the same estimator and re-checks the same
ceiling — what `build_prompt` itself does. Measured on `b002-option-pairs`:
1015 tokens to 963, so the lever is worth **52 prompt tokens** and the report
will say so.

### The interaction term

`matrix.interaction()` returns combined-minus-the-sum-of-singles, all against
the baseline. It returns **absent rather than zero** when the matrix or the run
does not carry every part of the subtraction. A missing single-lever arm is not
evidence that two levers are additive, and 0.0 would publish it as one.

`planonly+norule` is declared as the first real multi-lever cell: whether the
output-shape rule is worth more or less when the scaffold's code is gone. Two
levers on different slots, so the cell is order-independent by the rule above.

### Nothing about the baseline moved

Pinned by test: routing `stock` through the matrix produces a dispatch
byte-identical to a plain `build_prompt` — same user message, same system, same
token count. The three cell ids every run directory on disk is recorded under
(`stock`, `planonly`, `noscaffold`) are asserted against the matrix at import,
so a rename in the data cannot silently orphan a run.

### One existing test caught a real gap

`test_every_condition_is_a_distinct_render` failed at 3 == 5. It rendered each
cell with `build_prompt(ablate(...))`, which applies the **contract** stage
only, so the two new message-lever cells collapsed onto their contract-stage
twins and the duplicate would have read as a pass.

The test's intent was right and its path was now wrong: it is rerouted through
`render_for`, which is what the runner dispatches. Worth naming because it is
the failure mode the slot rule protects against showing up at a second layer —
a cell that is distinct in the data and identical on the wire.

`make check` green.

## Left open

**Five of seven acceptance items remain**, and one of them has a consequence
worth deciding before it is built:

1. **`Gate.run` as the scorer** — the largest item. `measure.py:487` still
   calls `bundle.run_acceptance`, which shells the contract's acceptance
   command out to a temp directory. `Gate.run` adds scope, well-formedness,
   secrets, structured-output and adapter rungs, so a worker output that
   passes `accept.py` while writing outside `scope.allow` scores as a **pass**
   on the rig and a **fail** in production. The contracts already carry what
   the gate needs (`scope.allow`, `acceptance`), and E4's sandbox shipped.

   > **The consequence: this changes what `passed` means.** Every measurement
   > in `records/measurements/` — including the 2026-08-12 null on `lane/231`,
   > which reported `d` = 1 in 514 — was scored by the acceptance command
   > alone. Pass rates can only move down under the gate's extra rungs. So
   > **#231's checks must re-run after this lands, not before**, or the gate is
   > commissioned on a scorer the arms will not use. Check 1 is ~37 minutes of
   > rig time, so the cost of ordering it correctly is small; the cost of
   > getting it wrong is a commissioning that describes a different instrument.

2. **The report** — pass rate per condition carrying n, model and rig, and
   refusing to state one without them; the interaction term in the output (the
   arithmetic is done, the report is not); the cost axis beside acceptance.
3. **Single-tier mode**, and every figure declaring which it is.
4. **The keyless condition (#44)** as a first-class cell — it is a lever in
   this format, and the slot rule should make it compose.
5. **The declared reproducibility bound** — the property is #113's, the number
   is #231's and is now measured (`d` = 1 of 514, 95% CI [0.03, 1.09] pp).
   Worth wiring only after item 1, for the same reason.

**`lane/231` and PR #245 are open and held deliberately**, so #231's remaining
checks land there once this lane gives them a knob and a scorer.

next: `Gate.run` as the bench's scorer — and the re-run it obliges.
