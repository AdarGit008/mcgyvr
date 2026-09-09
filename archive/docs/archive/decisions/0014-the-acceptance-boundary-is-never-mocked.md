# ADR-0014 — the acceptance boundary is never mocked, and its outcome is not a boolean

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-06

## Context

Everything mcgyvr does ends at one signal: `gate/acceptance.py` runs the
contract's declared commands in the sandbox and reports what happened. Every
other judgment in the pipeline — routing, escalation, verification, delivery —
is downstream of that signal being real. If it is fabricated or collapsed, the
system does not degrade; it inverts, promoting exactly the changes it exists to
refuse.

This is not a hypothetical failure. The #175 survey's second read found it
shipped, mature, and more than a year old. `ai-christianson/RA.Aid` at
`e71bb83dcfdf8796d41c746ad99bf4838d1d5914` (2.2k stars, actively developed
through 2026-01) gates its runs with `--test-cmd`, whose implementation calls
`run_shell_command(cmd, timeout=timeout)` on a langchain `@tool` — which raises
`TypeError: BaseTool.__call__() got an unexpected keyword argument 'timeout'`
on **every invocation since 2025-01-27**. The enclosing `except Exception` sets
`should_break=True`, the same value a passing suite sets. Verified here by
running their `execute_test_command` three ways under their own locked
dependencies: a green suite, a red suite and an exhausted retry budget all
return the identical signal.

The defect needed two conditions to survive, and each is a decision this record
makes:

1. **The mock kept it green.** All six tests of the module pass, because each
   patches `run_shell_command` with a `Mock` that accepts any kwarg. The one
   call that fails in production is the one call no test makes. A test double
   at the execution boundary does not merely weaken the test; it pins the
   test's model of the boundary at the moment the mock was written, and drifts
   in silence exactly when the real call breaks.
2. **The boolean hid it at runtime.** `should_break=True` carries *passed*,
   *failed* and *never ran* through one channel. Once the three are one value,
   no caller — human or code — can distinguish a gate that approved from a gate
   that crashed.

mcgyvr's current code already takes the right position on both points, which is
precisely why this is a decision record rather than an issue.
`gate/acceptance.py` classifies each command into a five-valued `_Outcome`
(passed, failed, did-not-run, timed-out, altered-tree — the five cases #38 made
acceptance criteria), and `AcceptanceReport` keeps *did not run* in
`environment_issues`, a separate list from `findings`, so a degraded run is
never mistaken for a passing one. `tests/test_acceptance.py` drives the whole
rung against real commands in a real git workspace via the temp-directory
sandbox, with no mock anywhere in the file. Nothing in the repository *requires*
any of that to stay true. A refactor that mocked `Sandbox.run` to make a slow
test fast, or an adapter that summarized `AcceptanceReport` to a bool for a
caller's convenience, would review as a simplification. RA.Aid is what that
simplification costs, measured at someone else's expense.

## Decision

**No test may replace the execution boundary under `Acceptance` with a test
double.** The boundary is `Sandbox.run` and everything below it as reached from
`gate/acceptance.py`: tests of the acceptance rung run real commands in a real
workspace. The temp-directory sandbox exists so this costs no Docker daemon;
"CI has none" is an argument for `TempDirSandbox`, never for a `Mock`.

**No interface may carry an acceptance outcome as a boolean.** *Passed*,
*failed* and *never ran* remain distinguishable at every point between
`_run_one` and whatever finally acts on the verdict. An adapter that collapses
`AcceptanceReport` to `bool` — or any equivalent reduction that maps an
environment issue and a pass to the same value — is a defect, whatever it
simplifies.

Two riders bound the rule:

- **The rule is about this boundary, not about mocking.** Tests elsewhere mock
  freely; workers are mocked in the bundle harness; nothing here speaks to
  that. What may not be doubled is the specific call whose honesty every other
  signal depends on.
- **Fakes that run real commands are inside the rule, not exceptions to it.**
  `TempDirSandbox` is not a mock: the command genuinely executes and the
  classification genuinely runs. The line is execution, not class name — a
  stand-in that returns a `CommandResult` without running anything is a mock
  wearing a sandbox's interface.

## Rejected: allow mocks at the boundary, backed by an integration test

The conventional answer: unit tests mock for speed and determinism, one
integration test keeps the real path honest. It fails on the drift mechanism
RA.Aid demonstrates. The mock encodes the boundary's signature as of the day it
was written; the real dependency moves; every unit test continues to pass. The
lone integration test is then the single point of honesty, and it is exactly
the test most likely to be skipped, marked slow, or quietly deleted when an
environment change breaks it — because every other green test testifies that
the module works. RA.Aid's boundary broke at a *keyword argument*, the smallest
possible drift, and stayed green for a year. The premium for running real
commands in a tempdir is seconds per suite, and it buys tests whose passing
means something.

## Rejected: a boolean verdict plus logging

The gate could return pass/fail and write the never-ran case to a log. This
loses because a log is not an interface: the caller acts on the returned value,
and the returned value is where the distinction must live. RA.Aid *logs* its
`TypeError` — the information was present, recorded, and consequence-free,
because nothing that made decisions could see it. A distinction that exists
only where nothing reads it does not exist.

## Rejected: write nothing, since the code already does this

The current shape is correct by construction, so the rule could be left
implicit. It loses on who meets the code next. The five-valued outcome and the
mock-free suite read as one author's style, not as load-bearing structure;
nothing marks them as the two conditions whose joint failure shipped a
gate that approved everything for a year. A rule that exists only as an
instance of itself is removed by the first refactor with a good reason —
and both plausible refactors (mock for CI speed, bool for caller convenience)
come with good reasons attached. This record is what makes the next reviewer's
"this simplification is a defect" citable rather than a taste argument.

## Consequences

- **Tests of the acceptance rung stay slow-ish and real.** Seconds, not
  milliseconds, per case; accepted as the price of a gate whose green means
  green. The temp-directory mode keeps the ceiling low and Docker out of CI.
- **`AcceptanceReport`'s two-list shape is now a contract**, not an
  implementation detail. Callers that want a single answer must construct it
  themselves, visibly, in their own code, where the collapse can be reviewed.
- **The verifier inherits the discipline.** ADR-0015 applies the same
  three-way honesty to the instrument that judges the work, and leans on this
  record for the channel shape.
- **What this gives up:** the freedom to stub the sandbox in future acceptance
  tests whose setup is genuinely expensive. If a case ever arrives that cannot
  be expressed as a real command in a tempdir workspace, this record is the one
  to amend, in writing, rather than the rule to route around.
- **What this bets on:** that the execution boundary is the one place where
  test realism cannot be traded away. If mocking pressure appears here, the
  correct response is a cheaper real sandbox, not a cheaper fake.
