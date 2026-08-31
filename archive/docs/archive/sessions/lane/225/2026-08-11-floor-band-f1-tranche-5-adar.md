# Floor band `f1`, tranche 5 — the brief is spent unchanged (lane/225)

Date: 2026-08-11 (evening)
Issue: #225 (Phase 4). Brief: `2026-08-11-floor-band-f1-brief.md`, **unchanged**.
Governing records: ADR-0021 (as amended twice), ADR-0022, ADR-0023, ADR-0024.

## What the stop condition told us to do

`f1`'s first 40 problems read **45.0%** on `qwen2.5-coder:1.5b` — inside the
pre-registered 30–50% window. The brief names exactly one consequence for that
read:

> If the 1.5B reads **inside 30–50%** on the f1 bench half: the shape is right,
> and the remaining tranches toward ~400 are authored to this brief unchanged.

So this tranche changes nothing. Same behaviour budget, same shape targets, same
composition rule, same brief document. The only thing that moved is the count.

## The amendment that preceded it

The owner settled a question ADR-0021 left open, and it is recorded there rather
than here (ADR-0021, *Amendment — 2026-08-11: overlap may be total, and the aim
is met per model*):

- The **400 stays intact per model**. No relief from the count.
- Overlap between two models' sets may be **full or partial**, no upper bound.
- The binding constraint is per model: each model's 400 must meet **its own**
  30–50% aim.

The consequence recorded there and worth repeating: overlap is settled by
**measurement, never assumption**. A problem earns its second slot by reading
in-band twice. A second model's authoring bill is its *shortfall* — the problems
it ceilings on — and that bill is unknowable until it is swept against what
exists. The floor unit's 400 is still completed first (ADR-0021 clause 4).

## What was authored

**b268–b307: 40 paired problems, 40/40 ADMIT on the first pass.**

Composition, matching tranche 4's realized mix:

| | count | share |
|---|---:|---:|
| `function_implementation` | 30 | 75% |
| `bug_fix` | 10 | 25% |
| `multi_symbol` | 11 | 27.5% (#126 wants ≥ 25%) |
| carrying one error path | 7 | 18% |

Shapes: 10 numeric, 12 string, 9 iteration, 9 data_structure. No
`error_handling` primary — a band capped at one error path cannot honestly carry
it.

Realized shape against the brief's declared targets — **every median inside its
band**:

| dial | target | tranche 5 median (range) |
|---|---:|---:|
| spec prose words | 40–70 | **49** (36–70) |
| ts reference lines | 8–14 | **11** (4–24) |
| py reference lines | 6–11 | **7** (3–13) |
| asserts per arm | 5–8 | **6** (6–8) |
| problems with an error path | ~19% | **18%** |

The ranges run wider than the medians at both ends and that is expected: a
`bug_fix` states its defect in fewer words and its reference is often three
lines, while `wrapWords` and `rampPlan` are genuinely 20-line functions. The
brief targets a distribution, and the distribution landed.

## How it was written

Prose, references and assertions are hand-written, every word. `tools/bench/emit.py`
— committed in `83ad683f` precisely so this tranche would not depend on a
scratchpad — wrote the file shapes: the folded `task:` scalar, the
`demonstration`-versus-`acceptance` split a `bug_fix` turns on, and the ts arm's
`meta.json` sidecar. That division held: 40/40 admitted first pass with no gate
rejection attributable to file shape.

**One rejection, and it was arithmetic.** `b291-climb-gain` asserted
`climbGain([1, 4, 9]) === 11`; the rises are 3 and 5, so it is 8. Both arms
failed identically and the gate caught it before the manifest saw it — which is
the gate's whole job, and worth recording as evidence that the self-test arm
works rather than as an embarrassment.

## Two design traps — now screened by the emitter, not remembered

Both were first written down here as prose. Prose is a note a future session has
to remember to read, so both are now screens in `tools/bench/emit.py`, refusing
the write rather than advising against it. Neither can be waived by an argument:
a screen with an override is a screen that gets overridden at the moment it
matters.

They live in the emitter and not in the gate because the gate is *structurally
unable* to catch either. In both, the material is perfectly correct — it is
correct about the wrong thing, so executing it proves nothing.

**1. A rounding rule that is not the same rule in both languages.** The first
draft of `b298` was "the mean, with a half rounding up". Python's `round()` is
banker's rounding — `round(4.5)` is `4` — while JavaScript's `Math.round(4.5)`
is `5`. An idiomatic solution would have passed ts and failed py *on the same
problem*, which is precisely the class of defect the `ValueError`/`Error` checker
fix was about (see `2026-08-11-floor-unit-and-checker-parity-adar.md`). The
problem was replaced with `b298-price-vat`, whose `//` and `Math.floor` agree.
**Rule: before pairing a numeric problem, check that both languages' built-ins
answer the boundary the same way.**

**2. Domain collision inside the band.** Roughly a third of the first draft was
discarded against the 40 problems already in `f1` — a cyclic-next (b241), a
mask-the-tail (b237), a round-robin deal (b250), a longest-run (b251), a clamp
(b254), an interval merge (b266), a title-case (b242). **Rule: read the existing
prose before drafting.** The 0.55 prose Jaccard is the backstop, not the method,
and it cannot see this class at all: "the next fan speed, wrapping to the first"
and "who takes the next shift, wrapping to the first" share almost no vocabulary
and are one problem.

What they do share is the shape of their reference, so `siblings()` screens the
reference's **token skeleton** — identifiers, literals and types erased, kept as
3-grams. Renaming `rotaNext` to `ventCycle` and `names` to `settings` scores
**1.00** against the original.

## What the screens found in the corpus that already exists

Calibration was done against all 300 admitted problems rather than by picking a
number. Skeleton similarity runs at a median of 0.14 (py) and 0.20 (ts), p99 of
0.34 and 0.41. Refusal sits at **0.70** and a warning at **0.55**.

Run over the tree, the screens refuse **three problems, and all three are one
finding**:

> **`b080-brace-fill`, `b090-expand-markers` and `b168-badge-slots` are the same
> problem three times.** Substitute `{name}`, `%name%` and `<name>` from a
> mapping while walking the template once, rejecting a malformed name, an
> unclosed opener and a name the mapping lacks. Different delimiter, same task,
> and the prose screen never saw it because the vocabulary differs.

`b080` and `b168` are **both in the bench half**, so both are scored, and a
model that solves one has effectively seen the other. `b090` sits in **reserve**
— a twin across the split, which is precisely the recontamination
`admit.py`'s docstring says "dies here". It did not. `b080` is also the one of
the three carrying an `ablation-sets.json` and `strata.json` entry, though the
ablation used only it, so no ablation cell held two copies.

All three are in the **old 220** — the ladder's top under ADR-0021 clause 5, not
the floor band this campaign is building. `f1` itself has one milder pair,
`b259-gloss-lookup` and `b267-alias-map` at 0.59 (look one up in a mapping with
a fallback, then list the keys alphabetically) — inside the warning band, below
refusal, one in each half.

### The owner's ruling: keep one, remove the duplication

**Decided (2026-08-11, owner): keep one, and take the duplicates out of the
bench and out of the results.** `b080-brace-fill` stays — it is the copy
`ablation-sets.json` and `strata.json` already cite, so keeping either of the
others would have rewritten citations to no benefit. `b090-expand-markers` and
`b168-badge-slots` are retired.

**Retired means withdrawn, not flagged.** Both are gone from the tree and from
`admissions.jsonl`, which is the precedent b155, b176–b180 and b186 set: a
retired id holds no admission record and is never reused. What
`tools/bench/retired.json` adds over deleting them is the argument, the date,
and the id kept instead, so anything that already measured one can find out why
it went. The gate refuses to re-admit a retired id and the emitter refuses to
write one; two tests hold both.

**Bench: 300 → 298 admitted.** `f1` is untouched at 80.

### Where "remove from results" was applied, and where it was not

The run records under `records/measurements/` are **not** edited. A `run.json`
pins a `tasks_sha256` per task and a `results.jsonl` states what was dispatched;
both are evidence of what happened on the day, and a retirement afterwards does
not change that it ran. `regrade.py`'s own docstring already settles this —
*"the original rows are never rewritten … a record that changes when the tooling
changes is not a record"* — and it is the same reasoning as #230's instrument
pin, which stamps rather than excludes.

So the removal is applied **where figures are derived**: `ablation_report.py`
drops retired rows from every cell and from every declared set, `regrade.py`
marks them `retired` rather than the vaguer `not in tier`, and a set file naming
one has the drop printed rather than silently applied. Four tests pin it.

**Every figure `b168` touched, re-derived.** It was scored six times and failed
all six, so no reported rate loses a pass and every change is a denominator:

| figure | before | after |
|---|---:|---:|
| 1.5B, pooled old-shape | 12/218 = **5.5%** | 12/216 = **5.6%** |
| 1.5B old-shape, ts | 3/109 = 2.8% | 3/108 = 2.8% |
| 1.5B old-shape, py | 9/109 = 8.3% | 9/108 = 8.3% |
| 3B probe ts (as-measured / regraded) | 14/109 = 12.8% | 14/108 = 13.0% |
| 3B probe py, as-measured | 15/109 = 13.8% | 15/108 = 13.9% |
| 3B probe py, regraded | 16/109 = 14.7% | 16/108 = 14.8% |

**The 45.0% floor-band read is unchanged at 18/40** — `b168` is not in `f1`, and
the re-derivation confirms it rather than assuming it. **The ablation is
unchanged**: `b168` was never in its dispatched set, and the report still prints
+5.1pp ts / +4.6pp py on the code contrast.

The figure quoted as **5.5%** in commit `d55392ea` is now **5.6%**. That commit
message is not rewritten; it was true when written, and this record is where the
correction lives.

`b090` needed no re-derivation: it sat in reserve and appears in no file under
`records/measurements/` at all.

The audit is now **0 refusals**. `f1`'s milder pair, `b259-gloss-lookup` and
`b267-alias-map` at 0.59, is kept: case-insensitive lookup returning nothing
when absent, versus one-hop resolution returning the name itself when absent,
are different behaviours. Only their second function — list the keys
alphabetically — is shared, which is why they sit in the warning band and not
above the line.

## What the screens do not claim

Fatal means **decidable from the text**. Everything needing dataflow warns and
never refuses:

- `%` reached by a negative (`-7 % 3` is `2` in python, `-1` in JavaScript) is a
  warning, because `Math.abs` upstream, a divisibility test against zero, or an
  addend chosen to keep the numerator positive all make it safe and none is
  visible to a regex. An earlier draft refused on this and was wrong about
  `b240-hue-band`, which already writes `((degrees % 360) + 360) % 360`.
- A bare `.sort()` refuses only over a **visibly `number[]`** receiver. Over
  strings the two languages agree, and `Object.keys(m).sort()` is the commonest
  correct use in this tree — an earlier draft refused 46 problems by missing
  that, most of them sorting keys.
- Unicode-aware `str.is*()` against an ASCII `ts` regex, `Math.trunc` against
  `//`, and `localeCompare` against code-point order are all latent: the arms
  part company outside ASCII or below zero, where a checker may never go.

The audit currently stands at **3 refusals and 60 warnings** over 300 problems.
The warnings are a reading list, not a defect count.

## State after this tranche

- **Bench: 298 admitted** after the two retirements below (300 at pin time), `f1` at **80** (48 bench / 32 reserve).
- The 48/32 split is the pre-declared salted hash doing what a blind rule does
  at n=80. It is not chosen and is not corrected.
- The 1.5B's 400: **80 down, 320 to go**, at 40 a tranche.
- `admit.py --verify` clean.

## Next

The stop condition is unchanged and still governs: author the remaining tranches
to this brief **unchanged** toward ~400 for the floor unit, then relabel the 220
as the ladder's top, then Phase 5 (#224 re-read, PR). Nothing here re-opens the
band's design.

Two things deliberately **not** done, so they are not mistaken for oversights:

- **No sweep was run on this tranche.** A 40-problem read is a rate estimate the
  band does not need again; `f1`'s shape is settled and re-measuring every
  tranche would invite exactly the n=7 re-design error the brief exists to
  prevent. A sweep across the accumulated `f1` bench half is worth running when
  the count is large enough to narrow the interval meaningfully.
- **No upstream (3B) sweep.** It is now a step of the method under the
  amendment — it is the only way to learn the overlap — but ADR-0021 clause 4
  puts the floor unit's 400 first, and the owner's instruction was explicit:
  finish the 1.5B's 400 before moving on.
