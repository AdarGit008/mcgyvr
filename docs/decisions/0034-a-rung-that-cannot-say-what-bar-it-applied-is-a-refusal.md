# ADR-0034 — a rung that cannot say what bar it applied is a refusal, and an absent tool is not

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0025 (its Context reads the JS adapter as recording an environment
issue on a failed invocation; it records nothing, and neither does the Python
one)
Relates: ADR-0005 (a bar that cannot run is not a bar that passed), ADR-0026
lens 3 (a check that cannot say what it applied is negative), ADR-0027 (an
unreadable field is a refusal), ADR-0014 (the acceptance boundary is never
mocked)
Date: 2026-08-16
Issue: #261

## Context

`Gate.run` accepts a change when it has no findings. Both language adapters
answer a linter they cannot read by returning **no findings**. So a linter that
crashes does not degrade the gate — it *passes* the change, and records nothing
that would let a later reader tell "clean" from "never ran".

This project has hit that shape three times, all of them listed in ADR-0025's
own Context: ruff installed with no config staged, eslint absent, eslint present
and parserless. Each looked healthy from the outside. ADR-0025 was written
believing the JavaScript adapter recorded an environment issue on a failed
invocation, and believing the Python side was the asymmetric one. Neither is
true: the two adapters implement one defect twice, and the JavaScript comment
saying it behaves "as the Python adapter does" was accurate.

## What the tools actually do, measured 2026-08-16

The issue named the `except json.JSONDecodeError` branch as the defect. Running
the four invocations the adapters make, against ruff 0.16.1, eslint 9 and
prettier 3:

| invocation | reporting | failing |
|---|---|---|
| `ruff check --output-format=json` | 0 clean, 1 diagnostics | **2, stdout empty** |
| `ruff format --diff` | 0 clean, 1 would reflow | **2, stdout empty** |
| `eslint --format json` | 0 clean, 1 problems | **2, stdout empty** |
| `prettier --list-different` | 0 clean, 1 differ | **2, stdout empty** |

All four answer a fatal config error with an **empty stdout**, not malformed
output. `json.loads(stdout or "[]")` reads that as zero diagnostics and
`if not stdout.strip()` reads it as nothing to reformat. The exception the issue
pointed at **never fires on the failure that actually happens**, and a fix that
only populated that branch would have left every measured instance of this bug
in place while appearing to close it.

The exit code is the only signal that separates the two, so it has to be the
test, and no inspection of the output can substitute for it.

## The distinction this record turns on

Two things stop a rung from running, and treating them alike loses information
in one direction or breaks a documented promise in the other.

**A tool that is absent** leaves a hole the operator can see. `README.md`
promises that mcgyvr without an API key "runs local-only ... with the gate as
the acceptance bar", and a minimal install reaching a verdict on the rungs it
has is the behaviour that promise describes. The reduction is legible, it is
already recorded in `environment_issues`, and `preflight` already refuses a
measurement sweep on it.

**A tool that is present and then fails** leaves a hole shaped exactly like a
pass. Nothing about the run looks degraded — the tool was found, it was invoked,
it exited, and the rung reported clean. This is ADR-0026 lens 3 verbatim: *a
check that cannot say what it applied is negative, because it reports health
while applying an unknown bar.* It is also ADR-0027's rule one layer down — that
record decided an unreadable **field** is a refusal, and this is an unreadable
**rung**.

The consequence is not symmetric with a missed rejection. The gate is the whole
acceptance bar for a keyless install (#44). A worker's change that trips lint is
accepted, branched and PR'd, on the strength of a linter that never looked at it.

## Decision

> **DECIDED (2026-08-16, owner).**
>
> 1. **An adapter that cannot trust a tool's run raises `ToolFailedError`**, and
>    never returns an empty finding list. Empty means *this change is clean*, and
>    it must never also mean *we could not tell*.
> 2. **The test is the exit code**, checked before the output is read, against
>    the set of codes under which the tool is reporting rather than failing.
>    Measured, not assumed: `trusted_stdout` carries the measurement above in
>    its docstring, because the fix is only correct for as long as that table is.
> 3. **An inconclusive rung is not accepted.** `GateResult.accepted` requires no
>    findings *and* no inconclusive rung. The change is not rejected — no finding
>    is invented and nothing is claimed about the worker — it simply does not
>    pass a bar that did not run.
> 4. **An absent tool keeps today's behaviour**: recorded in
>    `environment_issues`, does not reject, verdict still reached. The keyless
>    install is the case this preserves, and its hole is visible in an inventory.
> 5. **Both are recorded, and the inconclusive one is recorded structurally.**
>    `GateResult.inconclusive` carries adapter, rung, tool, exit code and the
>    tool's own first complaint; every entry is also rendered into
>    `environment_issues` so no existing reader loses sight of it. Manifest rows
>    carry an `inconclusive` field, and `as_verdict` names `inconclusive` as the
>    cause when nothing else rejected — a row saying "did not pass, rejected by
>    nothing" reads as a scoring bug rather than the environment fault it is.
> 6. **Every rung is still attempted after one faults.** An operator fixing a
>    broken environment gets both complaints from one run, not one per run.

## Consequences

- **A rate can no longer be quoted as measured under a bar that did not run.**
  Rows carry the inconclusive rungs by name, so the population is separable
  after the fact rather than silently pooled — ADR-0026 lens 1's requirement,
  applied to the scorer's own health.
- **A broken developer environment now stops the gate instead of passing it.**
  That is louder, and it is the trade ADR-0025 already made in clause 4 for the
  bench ("a declared rung must be shown able to reject, or the run is refused").
  This extends the same rule from the sweep's preflight to every single run.
- **The failing mode is recoverable and the passing one was not.** A refusal
  names the tool, the exit code and the tool's own words, and the operator fixes
  a config. A false pass produces a merged change and a corrupted rate, and
  neither announces itself.
- **This closes a round.** The gate is inside `product.py`'s surface, so
  changing it re-pins the product digest and `r1-commissioning` cannot accept
  further measurements. ADR-0018 admitted that cost; here it is not an unrelated
  edit paying it, but a change to the bar itself, which is precisely the kind of
  change a round boundary exists to separate.
- **Format rungs are covered on the same argument, not only lint.** `ruff
  format`, `prettier --list-different` and prettier's per-file print all had the
  identical shape. The issue is titled for the linter; the defect is "a rung that
  cannot say whether it ran", and fixing three of its four instances would have
  refiled the same bug.
- **`EnvironmentFault` is the new base of both faults**, so a caller that only
  wants "a check could not run" catches one class. `ToolUnavailableError` keeps
  its name, its signature and its meaning.

## What this does not decide

Whether the **semantic** and **acceptance** rungs should refuse on their own
environment issues. Both already have an `environment_issues` channel of their
own and neither was implicated in #261. They run in the sandbox, where "the tool
is missing" and "the tool crashed" have different causes and probably a
different answer, and deciding it here on no evidence would be the same error
this record was opened to fix.
