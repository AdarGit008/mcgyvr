# ADR-0035 — the bar is recorded as content, and there is one acceptance ceiling

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0025 (its Context leaves the *format* half of the JS/TS bar
undeclared — prettier ran on its release's defaults in the gate and in every
scored workspace, which the decision neither chose nor recorded)
Relates: ADR-0033 (`bar_sha256` — this is the readable block beside it),
ADR-0026 (three fields change from a name to content), ADR-0006 (the type
checker is the target repository's), ADR-0020/#240 (a retired instrument's
constants describe its recorded runs), ADR-0032 (a pin covers the bar's
configuration), #262
Date: 2026-08-17
Issue: #262

## Context

Both bench arms write the same five names into `gate_rungs` — `scope`,
`secrets`, `structured`, `adapters`, `acceptance`. ADR-0033 fixed half of what
that hides by hashing the resolved rule sets into `bar_sha256`. A hash tells a
reader that two bars differ. It cannot tell them *what* differed, and #262 asks
for exactly that, plus three specific silences behind it.

Measured on this tree, at ruff 0.16.2 / eslint 9.39.5 / prettier 3.9.6:

| | Python arm | JS/TS arm |
|---|---|---|
| lint rules, resolved | **250** (ruff) | **66** (eslint, for a `.ts` target) |
| lint config | staged, from the project's `[tool.ruff]` | staged `eslint.config.mjs` |
| format config | staged, the project's own | **none** — prettier's defaults, declared nowhere |
| type check | **none** | **none** |

Three corrections to #262 are folded in, and each changes what the fix has to be.

**The 328 figure does not reproduce; the answer is 250.** #262 derives the
Python rule count by prefix-matching `ruff rule --all` against `select` and
reports that it "reproduces exactly". It does not, because a string prefix is
not a ruff selector. `E` matches `EM`, `EXE` and `ERA`; `F` matches `FURB`,
`FAST`, `FBT`, `FIX`, `FLY` and `FA`; `I` matches `ISC`, `ICN`, `INT` and `INP`;
`N` matches `NPY`; `B` matches `BLE`. That over-counts by sixty stable rules
from ten linters this project never selected, plus six removed ones. Asked of
ruff itself — `ruff check --show-settings`, `linter.rules.enabled` — the answer
is 250 under both 0.16.1 and 0.16.2. The real ratio is **3.8:1**, not 5:1. This
is ADR-0033's own argument arriving as evidence: a re-derivation of a tool's
resolution drifts from the resolution that scores.

**The type check is symmetric, not a JS/TS asymmetry.** #262 reads it as the
TypeScript arm alone — `stage_dir` writes no `tsconfig.json`, so `tsc` never
runs. True, and incomplete. `score.lint_config` renders a `pyproject.toml`
carrying `[tool.ruff]` and nothing else, so `_declares_mypy` is false and the
**Python arm is not type-checked either**. Per ADR-0006 neither is a defect: a
repository declaring no type checker is correctly not type-checked. The defect
is that a reader of either pass rate could not tell. This is better news for
comparability than the issue assumed, and it means the fix is a record and not
a rung.

**The bar digest was resolved against a workspace of its own.**
`tools/breadth/measure.py:stage_bar` carried its own copy of `stage_dir`'s two
configuration lines. It had not drifted yet; adding `prettier.config.mjs` to the
scored workspace and not the digested one would have drifted it that day — a
`bar_sha256` describing a bar no candidate was judged by. That is #262's own
defect one level in, inside the module built to prevent it.

### The acceptance ceiling

`ACCEPTANCE_TIMEOUT_S` is **120.0** in `tools/bench/score.py` and **30.0** in
`tools/bundle/measure.py`, under a comment asserting they match.
`tools/problems/admit.py` uses 30.0 under a comment claiming "the same ceiling
as the rigs'". So pool admission rehearsed a measurement against a bar 4x
tighter than the one that would score it, and said the opposite.

Measured over the 32,601 rows in `records/measurements` carrying `acceptance_s`,
and over the 514 admitted references run against their own solutions:

| | |
|---|---|
| slowest of the 514 reference acceptance runs | **0.305 s** |
| slowest acceptance run that ever **passed** (n = 8,230) | **28.718 s** |
| second-slowest pass | 2.500 s |
| rows in [30 s, 120 s), of the 1,539 measured at the 120 s ceiling | **0** |
| timeout rows in the whole campaign | 130, none passing |

The ceiling is not a bound on what a correct solution costs — 393x headroom over
the slowest reference says nothing useful. It is a bound on a **slow but correct
candidate**, and that population has one member at 28.718 s and its next at
2.500 s.

## Decision

> **DECIDED (2026-08-17, owner).**
>
> 1. **`bar_material` is the bar, and `bar_sha256` is its hash.** One function
>    resolves the content; the digest is defined as the digest of that content,
>    so the two cannot describe different bars. It is recorded in the manifest
>    as `bar_resolved`, a sibling block beside `identity_refusals`.
> 2. **Both halves of both arms name a configuration the workspace holds.**
>    `prettier.config.mjs` is added, carrying prettier 3.9.6's own defaults
>    verbatim, and staged alongside `eslint.config.mjs`.
> 3. **`type_check` is asked of the product's own adapters** —
>    `locate_type_check_command` — and recorded as `null` on both arms, which is
>    what it resolves to. Not added as a rung.
> 4. **`score.stage_config` is the one staging seam.** `stage_bar` calls it.
> 5. **One acceptance ceiling for the live instruments: 120.0**, declared in
>    `tools/bench/score.py` and *imported* by `tools/problems/admit.py`.
>    `tools/bundle/measure.py` keeps 30.0.

### Why 120 and not 30

30 s would have made admission's existing comment true and cut runaway cost 4x,
and it is the wrong direction. A published pass sits at 28.718 s — **4.5% under
that ceiling**. A ceiling a recorded pass came within 1.3 s of is not a ceiling,
it is a coin flip on machine load, and the row it decides is already in a rate
somebody quoted. 120 s leaves that candidate 4.2x.

What the wider ceiling costs is runaway time. The whole campaign to date holds
130 timeout rows, so the difference between the two choices is about **3.25 h of
rig time spread over every run ever taken** — small against `rate-card.json`'s
per-cell prices (#289), and paid only by candidates that were going to fail.

Admission widens from 30 s to 120 s as a consequence. Nothing is admitted by
evidence that was not before: the slowest of the 514 admitted references is
0.305 s, so the ceiling is 393x the cost of the population it screens.

**The empty [30, 120) band is real and small, and is not the argument.** 31,062
of the 32,601 rows were measured under a 30 s ceiling and are censored at it —
they *could not* land in the band. 1,539 rows could have and none did. That is
enough to say the two ceilings have never disagreed about a recorded verdict; it
is not enough to say the band is empty, and the decision does not rest on it.

### Why the retired rig keeps 30.0

`tools/bundle/measure.py`'s arms were retired by #240 and `record_run` calls
`instruments.refuse_to_measure` as its first statement, so its constant sets no
ceiling for anything. It **describes** the 31,062 rows measured under it — 127
of them timeouts at exactly that value. Raising it to match would rewrite what those
rows say they were measured under, which is the one thing a retired instrument's
constants must not do. It is declared in
`tests/test_four_lenses.py::DECLARED_DUPLICATES` as a permitted disagreement,
with that as the reason rather than the old "known to disagree, and filed".

### Why the format config is the defaults, written down

Every value in `prettier.config.mjs` is prettier 3.9.6's own default, verbatim.
#262 puts changing either rule set out of scope, and this respects that: 257 of
257 `bench-ts` references format byte-identically with and without the file. The
change is not to today's bar but to tomorrow's — a default that moves in
prettier 4 would move the bar under every rate measured against it, silently,
and now it cannot.

`printWidth: 80` against `[tool.ruff] line-length = 88` is left as it is. It is
a real asymmetry; narrowing it after 32,601 scored candidates would re-base
every JS/TS format rate on disk for a cosmetic gain. It is written down, and
`bar_resolved` puts both in the manifest where a reader of a contrast meets
them.

### Why the readable block is not a keyed field

`bar_sha256` is the comparability key and `bar_resolved` is the statement of
what it hashed. Comparing both on resume would refuse a directory twice for one
change — and would refuse it for an edited comment in a config file, which the
digest also catches but which reads very differently as a diff of 250 rules. It
is adopted forward on absence and never overwritten, so a resume never rewrites
the description of rows it did not measure.

## Consequences

- **A reader of a ts/py contrast can see what differed between the bars**, which
  is #262's fourth acceptance box and the one a hash could not satisfy.
- **`gate_rungs` stays five names and is no longer the only answer.** It remains
  in `KEY`; nothing here is admitted to `KEY`, which is #276's rule to make.
- **Every JS/TS rate on disk was measured with prettier unconfigured**, and
  those manifests carry no `bar_resolved` — correctly, since they predate it.
  The block's `unconfigured` flag exists so that state is nameable rather than
  inferred from a `null`, which would read as prettier having been unreachable.
- **Pool admission runs at 120 s from here on.** Problems already admitted were
  admitted under 30 s and stay admitted; widening never un-admits.
- **`bar_material` costs one extra subprocess per run** — prettier's
  `--find-config-path` — on top of ADR-0033's pair, once in `record_run`.
- **The three figures #262 states in its own table are corrected here rather
  than in the issue alone**: 328 → 250, the type check from asymmetric to
  symmetric, and the ratio from 5:1 to 3.8:1. The issue body is amended to
  match, under the amendment convention ADR-0017 set.

## Fan-out

| what | owner |
|---|---|
| admitting `bar_sha256` to `KEY` — needs a perturbation run under #276's rule | #276, #231 |
| `rejected_by` names the first rung, not every rung that fired, so the arm read that motivated this under-counts acceptance failures | #257 |
| a `.js` target would resolve 80 eslint rules where `.ts` resolves 66; nothing admits one today and nothing refuses one either | unowned |
| re-running the concordance read of #295 now that the bar is recorded | #295, #231 |
