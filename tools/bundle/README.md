# The JS/TS bundle-size experiment — design, and what is not yet measured

Issue: [#144](https://github.com/AdarGit008/mcgyvr/issues/144), under
[#19](https://github.com/AdarGit008/mcgyvr/issues/19).
Instrument: `measure.py`. Conditions: `conditions/`. Task set: `tasks/`.
Prior run this repeats: [CLM-0004](../../records/claims/CLM-0004.json), designed
in [`context_size_experiment_2026-07-28.md`](../../records/evidence/local-ai-2026-08-02/research/context_size_experiment_2026-07-28.md).

**The sweep has run, twice, and it found nothing.** `c0`/`c1`/`c2`/`c3` measured
45/55/50/45% first-pass acceptance on `qwen2.5-coder:3b` — no rung separates
from having no bundle at all. The result, both runs and the limits are in
[`records/measurements/jsts-bundle-2026-08-04/`](../../records/measurements/jsts-bundle-2026-08-04/README.md);
the claim is [CLM-0012](../../records/claims/CLM-0012.json). This document is
the instrument and its design — read the measurement record for what came out.

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
green. It needs no worker, so it was verifiable long before one was reachable.
**20/20 green.**

## What blocked the run, and what unblocked it

For three sessions the answer was: nothing reachable served the model. The
experiment is defined on `qwen2.5-coder:3b` at Q4_K_M, and `mcgyvr detect`
reported `GPU: none detected` / `Backends reachable: none` on the machine the
rig was built on. Substituting a hosted model would have changed the model *and*
the serving stack at once — under CAV-02 a figure from another backend describes
different weights — so it would have answered a different question while looking
like an answer to this one.

Two things landed on 2026-08-04 and between them the block was gone:

- **#161** made the host an input rather than a hardcoded `localhost`, so rigs
  reachable over a tailnet are addressable at all.
- **#164** separated *asking* a backend what it serves from *dispatching* to it.
  Ollama is probed natively and bound on the OpenAI-compatible shape. Before it,
  every rung an init-written config produced was `quality_safe=False`, and this
  rig marks every request `quality_sensitive=True` — so the sweep would have
  been refused outright, one dispatch at a time, under CAV-01.

Both rigs turned out to hold `qwen2.5-coder:3b` at the exact quant the
experiment is defined on, so no substitution was needed.

## Running it against a worker you can reach

The rig needs one thing from you: an HTTP endpoint serving a model. It does not
care where that is. The acceptance side needs nothing but Node — no GPU, no
network — so the ordinary arrangement is **the rig here, the model elsewhere**.

Everything machine-specific goes in `worker.local.json`, which is git-ignored.
Copy the committed shape and fill it in:

```
cp tools/bundle/worker.example.json tools/bundle/worker.local.json
```

```json
{
  "endpoint": "http://localhost:11434",
  "protocol": "openai",
  "model": "qwen2.5-coder:3b"
}
```

**`openai` even against Ollama, and this is not a preference.** Every request a
sweep sends is `quality_sensitive`, and `runner.generate` refuses those on
Ollama's native `/api/generate` under CAV-01 — which measured that path scoring
a model at 32.3% against a true 84.1%. Choosing `ollama` here does not degrade
the run; it produces eighty dispatch errors and no measurement. The rig now
refuses it up front rather than one request at a time, an hour in. Ollama serves
`/v1/chat/completions` on the same port.

Then the sweep is just:

```
uv run --no-sync python tools/bundle/measure.py \
    --out records/measurements/jsts-bundle-YYYY-MM-DD
```

Flags beat the file, so a one-off against a second worker needs no edit:
`--model qwen2.5-coder:7b --out .../7b-YYYY-MM-DD`.

**A machine you reach over SSH is a local endpoint.** Forward the port and the
rest is unchanged — this is the arrangement to prefer, because it leaves the
model's serving stack exactly as its owner configured it:

```
ssh -N -L 11434:localhost:11434 gpubox     # in another shell, or -f to background
```

**A keyed endpoint** — a hosted provider, or your own box behind a gateway —
sets `protocol` to `openai` and names the *variable* holding the key, never the
key:

```json
{
  "endpoint": "https://api.example.com/v1",
  "protocol": "openai",
  "model": "qwen2.5-coder-3b-instruct",
  "api_key_env": "MEASURE_API_KEY"
}
```

`export MEASURE_API_KEY=…` in your shell, or put it in the git-ignored `.env` at
the repo root and source it (`set -a; . .env; set +a`). The rig refuses to start
if the named variable is unset, rather than sending twenty unauthenticated
requests. A key value written into `worker.local.json` under any of the obvious
names is refused too: git-ignored is not encrypted.

Before a real sweep, one dispatch is worth more than any amount of config
reading:

```
uv run --no-sync python tools/bundle/measure.py \
    --tasks t01 --conditions c2 --out /tmp/smoke
```

Rows are append-only and resume-safe — an interrupted sweep skips the cells it
already recorded. `--summarise-only` prints the table from rows already
collected. Resuming into a directory measured on a *different* worker is
refused; see `run.json` below.

**What a remote worker does not change.** #144 is defined on `qwen2.5-coder:3b`,
and CAV-02 says a figure from another backend describes different weights. A
sweep against a different model, or the same model on a different serving stack,
is a valid measurement of *that* — it just does not settle #144 as written, and
the claim record has to say which one it is. `run.json` records what was
actually reached so that this cannot be lost.

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

**`run.json` carries what the rows cannot.** A rate is not quotable without the
worker that produced it, and now that the worker can be anything anyone can
reach, the rows no longer imply one. The manifest records the endpoint (with any
embedded credentials stripped), the protocol, the model, a SHA-256 per condition
and the rig's own revision, plus one entry per invocation — so a table assembled
over three sittings still says what it measured. It is also what makes resume
safe: a sweep resumed into a directory whose manifest names a different worker or
a different ladder is refused, because blending two backends into one denominator
produces a table that looks like one measurement and is not.

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
- **The starting code travels in `target_content`, and that is the shape
  CLM-0012 measured.** Authoring this task set is what raised #150: the
  worker prompt had no slot for the target file's current content, so the 12
  tasks that start from existing code carried it inside the task description,
  fenced. That was legal and it was the only slot available, but it made those
  user messages longer and differently shaped than the ones production will
  send. #150 has since landed: `target_content` is a worker-facing field of its
  own, rendered as its own section, and the 12 contracts state their code there
  instead. Nothing was measured under the old shape, so no comparison is
  stranded — but this is the shape any figure quoted from here will describe,
  and a re-run against a contract set edited after the fact would not be
  comparing like with like. `run.json` now records a digest per task alongside
  the per-condition ones, so resuming into a directory measured against a
  different task set is refused rather than averaged.
- **The composition mapping is a judgement.** Calling a refactor a
  `function_implementation` is the closest honest fit, not an equivalence. A
  per-type rate from this run and a per-category rate from the Python run are
  not the same instrument.

## What the result licensed

The second arm: an explicit finding that no bundle effect was measurable
(CLM-0012). What followed from it:

- **`Bundle.measured` is `True` for `js/ts`** — the sweep was taken on the
  shipped file, which is what `check_c2_is_the_shipped_bundle` exists to
  guarantee. Because the marker is stripped before that comparison, rewriting it
  to state the null result did not forfeit the equality.
- **A boolean stopped being enough.** Both bundles are now measured and only one
  of them helped, so `measured` was demoted to derived provenance and
  `BundleStanding` carries the outcome: `MEASURED_BENEFIT` for Python,
  `MEASURED_NO_EFFECT` for JS/TS. "Measured" is a word readers take as
  endorsement; the type no longer lets them.
- **`MAX_BUNDLE_BYTES` stays one constant**, and now for a stated reason rather
  than for want of evidence. A per-language ceiling needs a language whose curve
  has a peak. JS/TS measured flat, so there is no JS/TS peak to place one at —
  which is not the same as JS/TS agreeing that 2 KB is right.
- **`prompts/javascript.md` still ships.** No benefit measured is not harm
  measured, and the same run cannot separate `c2` from `c0` in either direction.
  What it lost is the reason it shipped on in #25 — "probably better than
  nothing" is no longer available.
