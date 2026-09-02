---
record: session/2
lane: 113
agent: adar
started: 2026-08-12
---

## Did

**The bench scores through `Gate.run`.** #113's scope bullet — *"the outcome of
a run is the gate's own verdict, never a bespoke scorer"* — and its sixth
acceptance item. **No rig time was spent:** every number below is re-scored from
candidates already on disk.

New: `tools/bench/score.py`. Changed: `tools/breadth/measure.py`.

    uv run --no-sync python tools/breadth/measure.py --tier bench-ts ...   # refuses, see 3

### What changed

`measure.py` called `bundle.run_acceptance`, which shells the contract's
acceptance command out to a temp directory. `Gate.run` runs that command
**last**, behind scope, secrets, structured-data and per-adapter rungs. The tree
the command runs in is built exactly as before — target file, accept file,
nothing else — deliberately, so any movement in a rate is attributable to the
added rungs and not to a different working directory.

The row now carries `rejected_by` and `rejected_before_acceptance`, and
`run.json` carries `gate_rungs` — a rate is never quoted against an unstated bar.
The semantic rung is off by decision (ADR-0011) and the manifest says so.

**A correction made mid-session, by this lane's own test.** The row first
carried `passed_acceptance_only`, on the claim that the acceptance-only rate
every earlier figure was measured at would stay recoverable. It does not.
`Gate.run` short-circuits — acceptance runs only `if not findings` — so a
candidate rejected at lint **never executed its own test** and no field on the
row can say what it would have done. The field now states the fact
(`rejected_before_acceptance`) rather than inferring the counterfactual.

The consequence points the same way the sequencing already did, harder: the old
rate is not derivable from a gate run, so #231's checks must be **re-run** under
this scorer rather than recomputed from the rows they already produced.

## Four defects, in ascending order of importance

The first two were mine, found by scoring the corpus's own reference solutions —
which is the cheapest possible smoke test and should have existed already.

### 1. The checker failed itself

`python accept.py` writes `__pycache__/`, and the gate rejects an acceptance
command that alters the working tree. **Every Python candidate** was rejected by
its own test runner.

The gate had already designed for this: `_worktree_tree` hashes through a
throwaway index whose docstring says ignored paths *"are excluded, so a run that
only writes those is correctly not counted as altering the tree."* What the
staged workspace lacked was the `.gitignore` any real repository carries.

### 2. The bench was about to apply a *stricter* bar than the product

The adapter runs `ruff check` with the workspace as its working directory. A
workspace holding one solution and one checker has no `pyproject.toml`, so ruff
found no configuration and enabled a rule set far wider than this project
selects.

Measured: **`TRY004` alone rejected 75 of 257 checked-in references** for raising
`ValueError` where the contract asked only for "an error". A perfect worker
copying the reference verbatim would have failed 30% of Python problems, on a
rule nobody chose.

Fixed by staging the project's own ruff settings, derived from `pyproject.toml`
at call time so the two cannot drift. References went **70.0% → 87.9%** (py) and
**100%** (ts).

> **Still open, and it is #225's:** 31 Python references fail the project's own
> bar — 19 format reflows, 12 `E701`, 10 `UP031`, 3 over-length. The cause is
> visible in `pyproject.toml`: `extend-exclude` lists `tools/bench/tasks`, so
> `make check` has never linted the corpus. They are digest-pinned in
> `admissions.jsonl` and changing them needs a dated `amended` block — the
> manifest already carries one of exactly this shape (ADR-0023 arm parity). A
> sub-100% ceiling is not cosmetic: those 31 become pinned-fail cells that
> contribute nothing to discordance while still counting in `n`.

### 3. The two arms were about to be scored by different bars

**This is the one that would have done real damage, and it is silent.**

`eslint` and `prettier` are not installed. The adapter raises
`ToolUnavailableError`, which the gate records as an **environment issue and not
a finding** — so the candidate passes. Under the full gate the Python arm is
judged by five rungs and the TypeScript arm by three, and `passed` says nothing
about the difference.

    bench-py  environment_issues = ()
    bench-ts  environment_issues = ('js/ts: eslint not installed - lint skipped',
                                    'js/ts: prettier not installed - format skipped')

Every paired `ts`/`py` contrast would have carried a scoring-bar difference
inside it, and ADR-0021's denominator is *both arms together*. That is the same
shape as #189's backend confound and the serving-build confound ADR-0024 exists
to close: a real difference folded into a contrast with nothing on disk
revealing it.

**A sweep now refuses to start** when it would not measure what it claims to
(`score.require_rungs`, called before the first dispatch).

**The first version of that probe asked the wrong question**, and installing the
missing tools proved it. `eslint` and `prettier` were installed at the owner's
direction; the tool-inventory check went green on both arms; and the TypeScript
lint rung was **still inert**. Without a TypeScript parser eslint emits only
severity-1 warnings, the adapter counts severity-2, and the adapter's own comment
names the case — a fatal eslint error *"writes no JSON to stdout ... we score it
as inconclusive rather than inventing findings"*. Inconclusive is scored as no
findings, which is a pass. There is also **no eslint configuration anywhere in
this repository** — no `eslint.config.*`, no `.eslintrc*` — so unlike ruff there
is no project standard to inherit.

*Installed* is not the property that matters. **Able to reject** is. The probe is
now a positive control, the same logic as #231 check 2: two candidates per
language through the real scoring path — the corpus's **reference**, which must
pass, and a **canary** violating rules the configured tools carry, which must
fail. A rung that runs and never rejects is reported as inert rather than
healthy.

What it says today, and this is the honest state of the two arms:

    python  canary rejected by: ['format', 'lint']
    jsts    canary rejected by: ['format']

    ISSUE: the arms of this sweep are scored by different rungs — jsts rejects
    by format; python rejects by format+lint. A paired ts/py contrast would
    carry that difference inside it.

The comparison is over the **set** of rungs that fired, not `rejected_by`, which
is `findings[0]` and therefore an ordering artefact — comparing that would refuse
runs whose bars match and accept runs whose bars differ past the first finding.

Behaviour is right for production and wrong for an instrument: a developer's
missing linter must not block their work, but it must not quietly shrink a
bench's bar. #113 already says it — *"a condition matrix whose cells cannot fail
visibly has not been shown to measure anything."*

### 4. The product rejects two thirds of correct worker output on whitespace

Re-scored over the 514 real greedy candidates from the 2026-08-12 null run:

| arm | old scorer | full gate | flipped to fail |
|---|---:|---:|---:|
| `bench-py` | 70/257 (27.2%) | **23/257 (8.9%)** | 47 — all lint/format |
| `bench-ts` | 61/257 (23.7%) | 61/257 (23.7%) | 0 — *because lint never ran* |

What rejects a candidate the old scorer passed, on the Python arm:

| count | rule |
|---:|---|
| 61 | blank line contains whitespace |
| 40 | formatter would reflow a worker-added line |
| 27 | `List` vs `list` annotation |
| 9 | import block un-sorted |
| ~10 | line too long |

**Not one is a correctness defect.** No scope violation, no secret, no syntax
error, no failed test. Every one is auto-fixable, and **production has no format
step before the gate** — so this is what mcgyvr does today.

## The finding that outgrew the task

A deterministic `ruff check --fix && ruff format` on the worker's output, before
the gate, on the same 256 parseable candidates:

| | pass |
|---|---:|
| full gate, raw worker output | 23 (9.0%) |
| full gate, after the deterministic step | **58 (22.7%)** |
| recovered | **35, with 0 lost** |

**+13.7pp at zero tokens.** 35 gains against 0 losses is far past ADR-0019's
`m >= 6` wall; the exact two-sided p is `2^-35`.

**This is not #81, and saying so was imprecise.** #81 routes tasks whose *type*
is `format`/`import_sort`/`lint_fix`/`rename_symbol` to a program instead of a
model. It does not touch the output of a `function_implementation` task, which
is what was measured here. What ADR-0019 **D3** actually says of #81 — **"C —
cost-only ... does not move pass rate. Not a bench lever at all."** — is a claim
about that rung, and the measurement above is about a *different, unplanned*
one: deterministic normalisation of worker output before the gate.

Searched the open and closed issue list for it (2026-08-12); the nearest are #71
(grammar-enforced output), #94 and #95, and none covers it. **We did not find a
planned pre-gate normalisation step.** What production has instead is the retry
path: `RetryNotes` feeds gate findings back as *"fix exactly these"*, so today's
answer to trailing whitespace is another model call. That is the lever this
competes with, and it costs tokens where a formatter costs none.

**Two limits, stated.** It is the Python arm alone, because the TypeScript
arm's lint rungs do not run (defect 3), so nothing corroborates it. And it is
measured under a scorer that is not itself commissioned — #231 is what would
license it as a claim rather than an observation.

### The rig tests, and a stub that had to move with it

Five tests in `tests/test_breadth_rig.py` stubbed `bundle.run_acceptance` — the
seam this change replaces. They exercise the draw plan, the resume and the
dispatch-error path, so they now stub `score.score` instead.

Three of them then failed a second time, and the reason is worth keeping: the
preflight proves a rung can *reject* by scoring a malformed canary **through the
same `score.score` the tests hold at "passed"**. With the scorer stubbed the
canary passes by construction, the preflight correctly reports an instrument
that cannot fail, and `main` refuses before dispatching. Stubbing one without
the other tests neither, so `_always_passes` now stubs both and says why.

That is the positive control working on the first day it existed — against a
test suite rather than a rig, but working.

## The report (items 2-7)

`tools/bench/report.py` lays a set of run directories beside each other — one
directory is one cell — and `summarise()` gained the same discipline for a
single run.

    uv run --no-sync python tools/bench/report.py <cell-dir> <cell-dir> ...

What one output now carries, which is five acceptance items at once: the subject
(**model, rig, build, tier, condition, and the rungs that scored it**), the
**single-tier declaration**, n and pass rate per cell, the contrast against the
baseline, **both outcome axes** (acceptance and prompt/completion tokens), the
**interaction term** for any multi-lever cell, and a per-rung breakdown of what
did the rejecting.

**Two refusals carry the weight.** A cell whose manifest cannot name a model, a
rig and a bar gets no rate at all — the refusal is the report. And cells that
differ in model, endpoint, build, tier or scoring rungs are not laid beside each
other: that is the confound #189 shipped and ADR-0024 closes, and it now
includes a pre-#113 run placed next to a gate-scored one, because they measure
different things.

### Two corrections the tests forced

**`serving_build` is not required provenance.** The first version refused a rate
when the build was unknown. `serving_build()`'s own docstring had already
decided otherwise — *"an endpoint that does not answer `/api/version` is **not**
one this project refuses to measure ... `None` says exactly that rather than
inventing a value."* A recorded "unknown" is a statement. The header prints it
and flags the limit; the risk ADR-0024 actually guards — two builds inside one
contrast — is caught in `require_comparable`, where it belongs.

**Completeness still leads.** The provenance header initially displaced #217's
first line, which exists because *"a run missing an observation says so in its
first line, before any rate it might be quoted for"* — the warning is what gets
scrolled past. Order is now completeness, then subject, then any figure. Both
requirements hold rather than one winning.

## Left open

- ~~**Install `eslint` and `prettier`.**~~ **DONE** (owner direction,
  2026-08-12) — both on PATH. It was necessary and **not sufficient**: the JS
  lint rung is still inert, see defect 3. A two-arm sweep is still refused, now
  for the true reason rather than the tool inventory.
- **Author a JS/TS lint standard, or decide there is none.** Making that rung
  real needs `typescript-eslint` plus a chosen rule set, and there is no
  existing config in the repository to inherit — so it defines the *product's*
  bar for JS, not merely the bench's. Not this lane's to pick. Until it is
  decided, `--tier bench-py` runs and a paired run does not.
- **#81's classification is an ADR-0019 amendment**, not this lane's to make.
  The measurement is here; the reclassification is the owner's.
- **The 31 non-conforming references are #225's**, pinned material needing an
  amendment block.
- **#231's checks re-run after this**, and the null in PR #245 is now known to
  describe the *old* scorer. It stays open and unmerged for exactly that reason.
- **#113 stands at 7 of 8.** Only the declared reproducibility bound is open,
  and the issue itself splits it: *"the report declares the property here; the
  **number** that fills it comes from #231's null calibration"* — and that
  number must now be re-measured under this scorer.
- **The keyless condition (#44)** is a lever in the matrix format and unbuilt.

next: install the JS toolchain, then the report — and decide whether #81's
reclassification is filed here or as its own issue.
