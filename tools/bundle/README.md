# The JS/TS bundle-size experiment — design, and what is not yet measured

Issue: [#144](https://github.com/AdarGit008/mcgyvr/issues/144), under
[#19](https://github.com/AdarGit008/mcgyvr/issues/19).
Instrument: `measure.py`. Conditions: `conditions/`. Task set: `tasks/`.
Prior run this repeats: [CLM-0004](../../records/claims/CLM-0004.json), designed
in [`context_size_experiment_2026-07-28.md`](../../records/evidence/local-ai-2026-08-02/research/context_size_experiment_2026-07-28.md).

**No sweep has been run. There are no results in this directory and no claim
record for JavaScript/TypeScript.** What exists is the instrument, verified as
far as it can be verified without a worker. The reason is stated under
[What blocked the run](#what-blocked-the-run) rather than left to be inferred
from an absence.

## What is under test

`src/mcgyvr/prompts/javascript.md` ships on a prediction. CLM-0004 measured a
~2 KB bundle taking `qwen2.5-coder:3b` from 45% to 70% first-pass acceptance at
~2.5× the speed, and its own confidence note bars quoting that for "other
models, task sets or languages until re-measured". The JS/TS file is an idiom
port of the Python one, so two separate things are unmeasured:

- **Whether a bundle helps at all in JS/TS.** That is `c0` against `c1` and
  `c2`.
- **Whether ≤2 KB is the right ceiling for this language.** That is `c2`
  against `c3`. `MAX_BUNDLE_BYTES = 2048` is the peak of a *Python* curve; the
  falloff arrived somewhere between 2 KB and 8 KB for Python and could sit
  elsewhere here.

## The ladder

Conditions differ **only** in the system prompt. The user message is
`render_user_message(contract.worker_view())` in every condition — the shipped
assembly from #25 — which is CLM-0004's "the contract is always the user
message, unchanged across conditions".

| Condition | System prompt | Bytes | Python counterpart |
|---|---|---:|---:|
| `c0` | none | 0 | 0 |
| `c1` | role + output rules | 369 | 440 |
| `c2` | c1 + coding standards + edge-case checklist + pitfalls | 1 877 | 1 972 |
| `c3` | c2 + engineering handbook | 8 883 | 8 342 |

The ladder is **nested** — `c1` is `c2`'s opening and `c2` is `c3`'s — so size
is the only variable. A test holds that.

`c2` is `prompts/javascript.md`, byte for byte. `measure.py` refuses to dispatch
if it is not, and a test says so without a worker. This is the property that
makes a future result quotable about the shipped file rather than about a file
resembling it, exactly as `python.md` is held equal to the measured `c2.md`.

Two deliberate divergences from the Python ladder, both because copying would
have been worse:

- **No OUT OF SCOPE rule.** The Python `c1`/`c2` end with "Everything listed
  under OUT OF SCOPE must not appear in your output", pointing at a section
  mcgyvr's `worker_view()` has no equivalent of — `scope.forbid` is deliberately
  not worker-facing under #94. lane/25 shipped that line in `python.md` anyway
  because editing a measured artifact forfeits the measurement. Nothing forces
  it into a *new* ladder, so the JS/TS conditions omit it and this ladder has no
  inert rule in it.
- **The handbook is a port, not a description of mcgyvr.** `c3`'s tail is the
  Python handbook's ten sections rewritten in JS/TS idiom. Its job is to be
  plausible, project-shaped and mostly irrelevant to an isolated task — the
  context-budget blowout — and describing this Python repository in a TypeScript
  worker's handbook would have been incoherent.

## The task set

20 tasks, CLM-0004's n, each with a contract, a reference solution and a
runnable acceptance script.

**The composition is not CLM-0004's, and could not be.** The Python set was 8
`function_impl`, 5 `bug_fix`, 3 `refactor`, 2 `type_annotation`, 2 `edge_case`.
`data/task-catalog.json` has no `refactor` and no `edge_case` — they were never
in mcgyvr's vocabulary — so those intents are carried by the catalog types that
own them, and the mapping is recorded rather than hidden in a total:

| Intent (Python set) | n | mcgyvr task type | Tasks |
|---|---:|---|---|
| function implementation | 8 | `function_implementation` | t01–t08 |
| bug fix | 5 | `bug_fix` | t09–t13 |
| refactor | 3 | `function_implementation` | t14–t16 |
| type annotation | 2 | `type_annotation` | t17, t18 |
| edge-case hardening | 2 | `bug_fix` | t19, t20 |

A slice by mcgyvr task type is therefore 11/7/2, and a slice by intent is
8/5/3/2/2. Both are true; a rate reported per type is not comparable with the
Python run's per-category rates without saying which is meant.

The tasks deliberately reproduce three failure modes CLM-0004 named as things
**no** bundle rescued in Python, so the JS/TS run can test whether that half
transfers too:

- **t02** forbids mutating the caller's arrays, including through inner-array
  aliasing — the trap both Python models fell into on `merge_intervals` under
  every condition.
- **t19** requires rejecting a boolean where a number is expected. JavaScript
  divides by `true` quite happily; the Python 3b never honoured "bool is not
  numeric".
- **t17/t18** pin the modern annotation form (`string[]`, never
  `Array<string>`), the JS/TS analogue of the `typing.List[str]` the 3b emitted
  under every condition.

### Acceptance

Every contract declares `acceptance: ["node accept.mjs"]`, and the rig executes
the contract's command rather than a command of its own. Each script imports
`./solution.ts`, asserts with `node:assert/strict`, and exits non-zero with the
failure on stderr — which is also what a remediation round is given.

**Node 24 runs TypeScript directly** by stripping types, so a task needs no
compiler, no install and no network, and acceptance stays isolated and
stdlib-only per CLM-0004's design. The rig writes the worker's file into a fresh
temp directory beside a copy of the acceptance script and runs it there.

That is a **requirement, and it is checked before anything runs.** Stripping is
unflagged from Node 23.6 and 22.18; on anything older every task fails
identically, and the failure looks exactly like a model that cannot write
TypeScript. `node_runs_typescript()` probes the capability — it runs a `.ts`
file rather than reading `--version` — and both `--selftest` and a sweep refuse
with the reason instead of producing twenty red rows. The tests that run
acceptance skip on the same predicate.

`--selftest` runs every reference against its own acceptance and is a
precondition, not a convenience: the experiment is invalid unless it is 100%
green. It needs no worker, which is why it is the part of this that has actually
been run. **20/20 green.**

## What blocked the run

The experiment is defined on `qwen2.5-coder:3b` at Q4_K_M through
`llama-server`. On the machine this was built on, `mcgyvr detect` reports:

```
GPU: none detected
Backends reachable: none
  Tried: http://localhost:11434, :8080, :8000, :1234, :3000
```

No local backend, and nothing reachable serves `qwen2.5-coder` in any size —
the configured Alibaba key is rejected, Cerebras carries only large models, and
NVIDIA NIM has small coder models but no Qwen. Substituting one of those would
change the model *and* the serving stack at once; under CAV-02 a figure from
another backend describes different weights, so it would answer a different
question while looking like an answer to this one.

So the ladder is built and the run is deferred. The command, once a worker
exists:

```
uv run --no-sync python tools/bundle/measure.py \
    --endpoint http://localhost:11434 --protocol ollama \
    --model qwen2.5-coder:3b \
    --out records/measurements/jsts-bundle-YYYY-MM-DD
```

Rows are append-only and resume-safe — an interrupted sweep skips the cells it
already recorded. `--summarise-only` prints the table from rows already
collected.

## What the rig records, and why

One row per task × condition, in CLM-0004's columns: `pass1`, `pass_final`,
`remediation_used`, `latency_s`, `prompt_tokens`, `completion_tokens`.

**Completion tokens are the load-bearing column.** They are what made the Python
latency result independent of machine-load noise: under `c0` the 3b averaged 403
completion tokens against ~124 at `c2`, and since completion tokens dominate
wall time that is *why* the bundle was faster despite a larger prompt. A latency
number alone would not survive a busy machine; the token count is the backend's
own.

Three things are recorded that the Python run did not have to record:

- **`parse_error`.** Replies go through `parse_reply` with the completion's real
  stop reason, so a reply mcgyvr would refuse is scored as a failure *here* too,
  by its refusal code — including a truncated reply, which is refused before
  parsing because a file cut off at the cap can parse cleanly and still be
  missing its tail.
- **`dispatch_error`.** A cell lost to a transport failure is its own outcome. A
  run degraded by a flaky endpoint must not read as a run where the model
  failed, and a cell that vanished would silently shrink a denominator.
- **`bundle_bytes`.** The condition's actual size, so a row is checkable against
  the ladder it claims to come from.

No VRAM column: there is no GPU here to sample, and a column of nulls reads like
a measurement that was taken.

## Threats to validity

Inherited from CLM-0004's design and still true: n=20 with a single greedy seed,
so ±1 task (5 pp) is noise and only consistent direction-agreeing deltas are
signal; acceptance scripts check behaviour and a few contract constraints, not
style; the tasks and their reference solutions were written by the same author,
which biases toward testable tasks.

New here, and none of them inherited:

- **The type-annotation tasks are not type-checked.** TypeScript erases at
  runtime, so there is no analogue of the Python set's `typing.get_type_hints`.
  t17 and t18 assert runtime behaviour and then read their own source for the
  required annotation form. That is weaker than a compiler: it proves the
  annotation is written, not that it is *correct*. A real check would need a
  staged `tsc` — the ADR-0011 arrangement `tools/reach/count3_jsts.py` uses —
  and that would cost the isolation the rest of the acceptance has.
- **Erasable syntax only.** Node's type stripping rejects `enum`, `namespace`
  and constructor parameter properties. A worker that emits legal TypeScript
  using any of them fails acceptance for a reason that is about the runner, not
  about the code. The two type tasks say so in their contracts; the other 18 do
  not, because the construct is unlikely to appear there — but a failure of this
  kind would be misattributed to the bundle.
- **The buggy code travels in the `task` field.** #25's worker prompt has no
  slot for the target file's current content — `worker_view()` exposes `task`,
  `target`, `interface`, `deps`, `stop_conditions`, `output_schema` and
  `context.max_input_tokens`, and none of them is "the file as it stands". So
  the 7 `bug_fix` tasks and the 2 `type_annotation` tasks carry their current
  content inside the task description, which is the only slot available today.
  It is legal and it is what a decomposer would have to do right now, but it
  makes those user messages longer and differently shaped than they would be
  once a content slot exists, and the bundle's effect is measured against that
  shape.
- **The composition mapping is a judgement.** Calling a refactor a
  `function_implementation` is the closest honest fit, not an equivalence. A
  per-type rate from this run and a per-category rate from the Python run are
  not the same instrument.

## What a result would license

A sweep would produce a claim record for the JS/TS result, or an explicit
finding that no bundle effect was measurable. Either way `Bundle.measured`
becomes `True` for `js/ts` **only** if the shipped file is the artifact the
measurement was taken on — which is what `check_c2_is_the_shipped_bundle` and
its test are for.

If the peak is not at `c2`, `MAX_BUNDLE_BYTES` stops being one constant and
becomes per-language. Nothing here presumes which way that goes.
