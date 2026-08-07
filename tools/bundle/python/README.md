# The Python arm — the control CLM-0012 could not run

Issue: [#167](https://github.com/AdarGit008/mcgyvr/issues/167).
Claim: [CLM-0017](../../../records/claims/CLM-0017.json).
Result: [`records/measurements/python-bundle-2026-08-07/`](../../../records/measurements/python-bundle-2026-08-07/README.md).
Instrument: `../measure.py --language python`. Comparison: `compare.py`.
Positive control: `output_rule_probe.py`.

## Why there is a second arm

CLM-0012 measured the JS/TS bundle flat and had to scope the finding, because
two readings fitted the data and had opposite consequences. Under **language**,
`prompts/python.md` keeps its evidence and only the JS/TS port is unsupported.
Under **serving stack**, CLM-0004 does not describe the stack mcgyvr dispatches
on — it drove the Q4_K_M blob through bare `llama-server` where mcgyvr drives it
through Ollama — and the Python bundle's standing is no better than the JS/TS
one.

Separating them needs CLM-0004's own Python ladder on a reachable rig. The
conditions were vendored; the task set was not. It was still in
`AdarGit008/local-ai`, and is now vendored too — see
[`records/evidence/local-ai-2026-08-02/instrument/`](../../../records/evidence/local-ai-2026-08-02/instrument/README.md),
pinned to the commit the run was made at with the check that it has not drifted.

**Both readings were wrong.** The variable is the harness. The whole result is
in the measurement record; this file is the instrument.

## What is here

| | |
|---|---|
| `tasks/` | The twenty tasks as mcgyvr contracts |
| `compare.py` | Recomputes every table in the measurement record from rows |
| `output_rule_probe.py` | The positive control — one sentence, nothing else |

Conditions are **not** here. The arm reads
`records/evidence/local-ai-2026-08-02/data/context_exp/bundles/` directly, so
there is no copy to drift from what was measured, and `c2.md` is
`src/mcgyvr/prompts/python.md` byte for byte — the same equality the JS/TS arm
holds, reached from the opposite direction, since `python.md` was derived *from*
the measured file rather than the file from it.

## What travelled, and what could not

The acceptance scripts and reference solutions are **copies, byte for byte**, and
`tests/test_python_arm.py` holds them to the vendored originals by digest. Those
are what decide whether a cell passes; re-authoring them would have made this a
new instrument wearing CLM-0004's task ids.

The contracts could not travel. local-ai stores a *pre-rendered* user message —
`CONTRACT ctx-t01 · project:local-ai`, then `FILE(S)`, `INTERFACE`,
`CONSTRAINTS`, `ACCEPTANCE`, `OUT OF SCOPE` — and mcgyvr does not accept a
rendered prompt. It renders its own from structured fields, which is the whole
point of running this arm through this rig. So each contract was decomposed into
`task` / `target` / `target_content` / `interface` / `stop_conditions` /
`acceptance` / `scope`, with:

- **`CODE:` becoming `target_content`**, its own worker-facing field since #150,
  rather than being fenced inside the task description.
- **`OUT OF SCOPE` dropped.** `scope.forbid` is deliberately not worker-facing
  under #94, and the JS/TS ladder omitted it for the same reason.
- **Types mapped by the same rule the JS/TS arm used**, because `refactor` and
  `edge_case` are local-ai vocabulary and not in `data/task-catalog.json`:

| Intent | n | mcgyvr task type |
|---|---:|---|
| function implementation | 8 | `function_implementation` |
| bug fix | 5 | `bug_fix` |
| refactor | 3 | `function_implementation` |
| type annotation | 2 | `type_annotation` |
| edge-case hardening | 2 | `bug_fix` |

That gives 11/7/2 by type — **identical to the JS/TS arm**, which is what makes a
rate from one comparable with a rate from the other. A test pins it.

Bug-fix tasks carry their command in `demonstration` rather than `acceptance`,
since it fails on the task's base by design (#183).

## The authorship risk, stated plainly

The contracts above were written by hand. A rewrite can make tasks easier without
anyone meaning it to, and this arm's headline number is a *baseline* — `c0` at
13/20 where the original harness scores 7/20.

The within-arm comparison is immune: `c0` and `c2` use the same contracts, so
what the ladder measures is unaffected. The cross-arm baseline comparison is not,
which is why `output_rule_probe.py` exists — it runs the **unported** contracts
under the **unported** harness and changes exactly one thing. Read its docstring
before quoting the baseline.

The residue is visible and runs both ways: this arm's never-passing set differs
from the other two by one swap in each direction. `t17` becomes reliably passable
(its `interface` field renders the fully annotated signature, which states the
annotation form its acceptance checks) and `t20` stops passing.

## Running it

Same worker configuration as the JS/TS arm — see [`../README.md`](../README.md).

```
# verify the task set (no worker needed) — 20/20 is a precondition
uv run --no-sync python tools/bundle/measure.py --language python --selftest

# the sweep
uv run --no-sync python tools/bundle/measure.py --language python \
    --endpoint http://srv1:11434 --protocol openai --model qwen2.5-coder:3b \
    --out records/measurements/python-bundle-YYYY-MM-DD

# the comparison, from rows already collected
uv run --no-sync python tools/bundle/python/compare.py \
    --out records/measurements/python-bundle-YYYY-MM-DD
```

`run.json` records `language`, so resuming one arm into the other's directory is
refused rather than averaged.

**Acceptance runs `python accept.py` on the host**, exactly as the JS/TS arm runs
`node accept.mjs`: a fresh temp directory per cell, stdlib-only, no network. This
is a measurement rig and not the gate — ADR-0005 governs the gate, which never
runs target code on the host.

The arm's files are excluded from ruff (`pyproject.toml` says why): formatting a
copy held to a digest would change the instrument rather than tidy it.
