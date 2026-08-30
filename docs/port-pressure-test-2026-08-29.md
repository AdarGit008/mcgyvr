# Pressure test of the local-ai orchestration port — 2026-08-29

**Read this before touching PR #380 or anything under the ported modules.**

> **Status, 2026-08-29 (later the same day).** This document is the record of
> what the pressure test found and is left as written. What has since been
> closed, and where:
>
> | Finding | State |
> | --- | --- |
> | B1-B9, and 11 more found reproducing them | Fixed — `16a31cbc`, PR #381 |
> | **C** · levers, not a driver | Closed — `src/mcgyvr/drive.py` and `mcgyvr run`, PR #383. §6 step 5's two pieces exist and have a production caller; a deterministic contract now runs to a commit from a command. The ladder path (`worker_attempt`) is reachable from `mcgyvr run` as of the reach work below. |
> | **E** · eight boundaries held by nothing | Closed for the five that were breached, PR #383 — #94 on the retry path *and* at the reviewer, D20 at the config and both sinks, §9's globals (now zero in `src/`), the seam's accessor hole, and the orchestrator id, which is now part of the attempt id and not only a field beside it. |
> | **A** · surrogate-escaped content | Fixed in `16a31cbc` — all four writers |
> | **D** · tests pinning states the system cannot produce | Fixed in `16a31cbc` — `cleanup` tidies a format-only rejection deliberately |
> | **B** · nothing owns the bytes | Closed, PR #383. The tree owns them and one seam commits. B6's delivery-time re-check, then phase 1 (the second delivery routed through `deliver`), phase 2 (`Judgement.value` and the three `value` fields under it deleted), phase 3 (`RepairOutcome.content` deleted, `Consensus` carries `Accepted` bindings minted per draw, `Cleanup.regate` true whenever bytes were rewritten). A guard in `tests/test_pattern_b_tree_owns_bytes.py` fails a new `content` field that carries no digest. |
> | **§4, first item** · the self-verification refusal, defeated by spelling | Fixed — `verify.model_identity`, PR #383. The comparison is on what the two names resolve to, not on the two strings. |
> | **§4** · `delivery.mode` promised three behaviours and had one | Fixed — PR #385. `branch` writes a `mcgyvr/<contract-id>` ref without moving HEAD, `none` commits to the checked-out branch, `pull_request` is retired at load. |
> | **§4** · `param-mutation` is order-blind | Fixed — PR #385. The walk is in execution order and a branch merge is a union, so a rebind defends only where no path skips it. `contract_text` is threaded from `Contract.prose` and the stand-down is reachable. |
> | **§4** · `UP035` demoted wholesale | Fixed — PR #385. The demotion is withdrawn per line, not per code. An AST family over `ImportFrom` naming `collections` rejects on `structure`, so a ruff-less install rejects too; the `typing` half stays demoted. |
> | **Reach** · three levers built against callers nobody had written | Closed — PR #385. `mcgyvr run` climbs the ladder behind one new `--config` flag (no `--rung`: `starts_on`, `ascent`, `plan` and the budgets already settle that), `best_of` draws every attempt with `breadth.draws` defaulting to 1, and `tidy` sits between the gate and `judge` behind `cleanup.enabled: false`, honouring `regate` with a full re-gate and a fresh `Accepted.read`. |
> | §4's remaining three items, and the ~48 major | Open — `max_waves`, the cooldown lever, and the task-catalog digest dependency. |
>
> **Where to start next.** §6's order of work is spent, and so are four of §4's
> seven items — the self-verification refusal (`verify.model_identity`), the
> delivery modes, `param-mutation`'s order blindness, and `UP035`'s wholesale
> demotion. Each was reproduced with running code before it was fixed, and each
> carries a control: the ordinary local install keeps its verifier, a defensive
> copy placed before every mutation still stands the rung down, and the `typing`
> half of UP035 is still a style note.
>
> What is left of §4 is three items — `max_waves` bounding total waves rather
> than re-planning, the cooldown lever inert on a single-host install, and
> contract digest identity now depending on `data/task-catalog.json` — plus the
> ~48 major.
>
> Wiring the three unreached levers is what turned up the next block of work,
> which is the point of wiring a lever built against a caller nobody had
> written:
>
> * **`consensus.best_of`'s `sample: Callable[[int], str]` cannot say a draw
>   produced nothing usable**, and an unreadable model reply — truncated, prose
>   instead of a fenced block, a refusal — is the common case rather than the
>   exceptional one. The signature offers only two answers and both are wrong:
>   fabricate a string, which is then gated and reported as a candidate the gate
>   rejected when the reply was never readable, or raise out and discard the
>   verdicts of every draw already gated. The second shipped, because it keeps
>   the single-draw behaviour exact and is honest about what happened — but at
>   `n > 1` it loses real work, since draw 0 can pass the gate and be thrown away
>   because draw 1 came back truncated. The fix is a sampler that can return "no
>   candidate", so an unusable draw scores last instead of ending the attempt.
> * **`best_of`'s `repo` and `sandbox` are mutually exclusive and the signature
>   does not say so**; a caller mid-attempt, the exact caller the docstring says
>   should pass its own sandbox, must still supply a dead `repo`.
> * **`best_of`'s `gate: Callable[[Path], GateResult]` promises the workspace is
>   enough to gate**, and in this project it is not: acceptance commands are
>   arbitrary shell that must run in a sandbox (ADR-0005), so the real caller
>   closes over the sandbox and discards the `Path` it is handed.
> * **`worker_attempt`'s `verifier` parameter still has no production caller.**
>   `mcgyvr run` passes `None`, so every ladder acceptance is labelled
>   `unverified` even on an install with `verifier.enabled: true` and a bound
>   role. `verify.reviewer_for` exists and is unwired — a fourth gap of the same
>   shape as the three just closed.
> * **`mcgyvr run` never consults `delivery.mode`**, deliberately: `--commit` is
>   a person saying commit this, in the tree they are looking at. That keeps one
>   flag meaning one thing, and it means an operator who set
>   `delivery.mode: branch` does not get a branch from `run`. Worth a deliberate
>   decision rather than leaving it implicit.
>
> Three more the earlier fixes surfaced, each load-bearing in a way it was not
> before:
>
> * `_INPLACE_WORDS` is a substring match, so a contract saying *"do not mutate
>   the caller's list"* stands the mutation rung down for the whole file. That
>   was inert while nothing could reach `contract_text`; threading the prose
>   through made it live, and reliable negation in prose is its own design
>   question.
> * `delivery.token_env` is read by nothing, because no mode talks to a forge.
>   A dead key implying a forge integration is the same species as the default
>   that was just fixed.
> * `typecheck.py`'s claim that "the verdict does not depend on which tools the
>   operator happens to have" holds for six names. `_DEPRECATED_TYPING` knows
>   `List, Dict, Set, Tuple, FrozenSet, Type` and nothing else, so on a machine
>   without ruff, `from typing import Mapping` is reported by nothing.

|                |                                                                                  |
| -------------- | -------------------------------------------------------------------------------- |
| **Subject**    | PR #380, branch `green/port-from-local-ai`, 19 levers ported from local-ai        |
| **Method**     | 11 adversarial agents, 2 independent teams — 7 per-module, 4 whole-system         |
| **Rule**       | Read-only on the repo. Every finding reproduced by running code, not by reading it |
| **Result**     | **9 critical, ~48 major.** 1,998 tests pass, ruff/mypy/docs-check clean throughout |

## 1. The one thing to know

> **The 19 levers do not compose. They are 19 modules that each pass their own test.**
> **28 of 35 public entry points have no production caller.**

Eight agents built the port on disjoint files, in parallel, without reading each other's
code. Every lever's own test passes. Nothing tested the joins, and that is where the
serious defects are.

**The headline claim in `CHANGELOG.md` and PR #380 — "mcgyvr can now run a task" — was
wrong and has been corrected.** The honest statement: a task can be driven to a commit
only by hand-writing ~160 lines of orchestration `src/` does not contain, only for the 5
of 9 task types that do not start on the deterministic floor, and only by violating the
port's own documentation at three points. There is still no `run` subcommand;
`runner.dispatch` still has no caller.

## 2. Blocking — must be fixed before this branch merges

Only **B1** has blast radius today. The rest are real defects in shipped code that
nothing currently executes; they land the day their lever is wired.

| #   | Defect                                                              | Where                                  |
| --- | ------------------------------------------------------------------- | -------------------------------------- |
| B1  | `escalate()` raises on every deterministic contract — **live regression vs `main`** | `route.py:486` → `escalate.py:600` |
| B2  | The floor plans a `ToolStep` nothing can execute                    | `deterministic.py:226`                 |
| B3  | Concurrent delivery into one repo corrupts the tree (28/40 runs dirty) | `deliver.py:225-268`                 |
| B4  | `apply_scoped` silently corrupts the file it edits                  | `worker/scoped.py:157`                 |
| B5  | `repair` writes outside `contract.scope` through a symlink          | `repair.py:153-166`                    |
| B6  | Gate-rejected bytes reach the repository                            | `repair.py:112` × `deliver.py:248`     |
| B7  | `deliver`'s documented `base` value always raises                   | `deliver.py:148` vs `sandbox/base.py:280` |
| B8  | `run_waves` reports every failure as a completion                   | `waves.py:189`                         |
| B9  | `tidy()` crashes on the repo's own byte convention                  | `cleanup.py:124`                       |

### B1 — the live one

`plan()` now returns a non-empty deterministic `Plan` holding a `ToolStep`;
`escalate()`'s skip guard is `if not each: continue` — truthiness. A family that used to
be skipped as empty is now entered, and `climb()`'s refusal fires. `RouteError` is not a
`RunnerError`, so `tools/missions/run.py:662` does not catch it: the mission loop aborts
mid-flight, *after* earlier contracts were already committed.

On `main` the same contract returned `Delivered` on `local`. The only deterministic
contracts that still work are the ones with **no** tool bound — the port made the
successful path the failing one. 94 tests pass over it, because none calls `climb()` or
`escalate()` with a tool-binding deterministic contract.

Fix: filter deterministic plans out of `ascent.runnable`, or give `Plan` an explicit
`climbable` property so the guard stops depending on truthiness. Note that fixing it
makes a latent defect live — `Plan.budget` counts the un-climbable `ToolStep`, so
`Ascent.ladder_budget` over-reports by one attempt per deterministic plan.

### B4 and B5 — the silent ones

These are worse than the crashes because they write wrong bytes and report success.

`apply_scoped` indexes `splitlines(keepends=True)` with AST line numbers.
`str.splitlines()` breaks on eight characters the tokenizer does not treat as line
terminators (`\x0b \x0c \x1c \x1d \x1e \x85 \u2028 \u2029`), all legal inside string
literals. One above the spliced node shifts every index: the requested fix is applied and
then immediately undone by resurrected old lines, the file parses, and `ruff check`
passes clean.

`repair._repairable` scope-checks the changeset path, then `.is_file()` follows a symlink
and hands it to `ruff format`, which writes through it — rewriting a file the contract
explicitly *forbids*. `test_repair_never_touches_a_file_outside_the_contracts_scope`
exists; it just does not use a symlink.

## 3. Five patterns underneath

Each produced findings from agents who never spoke to each other, which is what makes
them structural rather than local.

**A · Nobody handles the repo's own encoding convention.** All four writers in the port
crash on surrogate-escaped content — `cleanup`, `pending`, `deliver`, `consensus`. The
rest of mcgyvr uses `surrogateescape` deliberately and documents it at `pending.py:16`.
Reachable straight off the wire: `\ud800` is a legal JSON escape, so it survives
`json.loads` into `Completion.text` and passes `parse_reply` as a valid `ParsedFile`. In
`pending.stash` the encode sits *outside* the `try`, so the module whose job is catching
failures cannot report this one as its own error type.

**B · Nothing owns the bytes.** Five modules write file content and disagree about where
truth lives: `repair` and `consensus` mutate the working tree, `cleanup`/`judge`/`deliver`
pass strings by value. `judge` never checks its `value` is what the `GateResult` was
computed from, and delivery's commit-time re-check is narrowed to syntax, so it cannot see
the substitution. **This is the fix with the widest blast radius** — it dissolves B6, the
consensus sandbox defect, and part of B9.

**C · The port produced levers, not a driver.** The call graph is five disconnected
fragments, none rooted anywhere reachable. `contract.limits.max_output_tokens` is computed
at load and never applied, because nothing turns a `WorkerPrompt` into a `Request`.

**D · Some tests pin states the system cannot produce.** `cleanup.tidy` cannot fire on the
case it was written for: the gate's format rung emits `check="format"`, not `STYLE`, so it
lands in `findings` and rejects — and `tidy` refuses to touch a rejected change. Its RED
test passes only because it hand-builds
`GateResult(observations=(Finding(check="format", …),))`, a value `Gate.run` can never
return. Green, and holding nothing.

**E · Eight declared boundaries are held by nothing.** Breached: `#94` on the retry path
(`RetryNotes.of` copies `str(finding)`, and acceptance findings carry the acceptance
command in `Finding.path`, so `contract.acceptance` reaches the worker prompt on every
second attempt); `verify.py`'s documented reviewer boundary; D20 applied to the port's own
sinks (`telemetry` writes `str(failure)` unfiltered, and runner errors interpolate a
`base_url` that may carry userinfo credentials); §9's no-global-mutable-state
(`capability.py:305` `_CACHED_TABLE`, the only new `global` in `src/`); §9's orchestrator
id as *identity* rather than a field; and "nothing travels upward … never an endpoint" —
`verify.py:460` imports neither forbidden name and receives a `RoleBinding` holding a live
`credential()`. The seam guard checks imports, and is additionally bypassable by
`import mcgyvr.pool` and by relative import.

## 4. Worth knowing before editing these modules

- **The self-verification refusal is defeatable by spelling.** `verify.py:368` compares
  `strip().casefold()`. `qwen2.5-coder` vs `qwen2.5-coder:latest` (Ollama's own tag
  defaulting — same weights), a provider prefix, a zero-width space, or a Cyrillic
  homoglyph all let a model review its own output. Nothing else in the codebase
  cross-checks `verifier.model` against the ladder's tiers.
- **`UP035` should not have been demoted wholesale.** It covers both
  `typing`→`collections.abc` (genuinely style) and `collections`→`collections.abc` (a hard
  `ImportError` on 3.10+). The gate now accepts a module that cannot be imported, and tells
  the reviewer nothing is asking for it to be fixed.
- **`param-mutation` is order-blind.** A later rebind anywhere in the function — including
  dead code — erases an earlier real mutation. The canonical
  `if target is None: target = []` then `target.append(extra)` is accepted, and
  `target = list(target)` placed *after* a mutation silences the rung while reading as a
  fix. Its `contract_text` stand-down is unreachable: `LanguageAdapter.structural_checks`
  has no contract parameter, so a contract asking for in-place work is unsatisfiable.
- **The cooldown lever is inert on a single-host install.** `record_success` pops the whole
  record, so a healthy rung clears a broken rung's streak and three consecutive failures
  never accumulate. It also cannot fire inside a task: `source_map` probes once at build
  time, and `escalate` holds that map for the whole ascent.
- **`delivery.mode` defaults to `pull_request`, and all three modes commit directly** to
  the checked-out branch. Nothing pushes, nothing branches; `handoff` records an obligation
  no code can discharge.
- **Contract digest identity now depends on `data/task-catalog.json`** — the one file the
  project designates as editable without a code change. Movement is zero today only because
  the three task types in use all derive exactly 1024, the old static default. Flipping one
  boolean re-keys 11 of 20 pinned contracts.
- **`max_waves` defaults to 3 and bounds total waves, not re-planning.** A correct,
  failure-free 4-deep dependency chain is silently truncated and its tail reported as
  `blocked`.

## 5. What held under attack

Stated as plainly as the failures, and verified by execution rather than by reading.

- **Pinned digests did not move.** 2,059 contracts recomputed against a shadow tree at
  `main`: zero movement. Independently confirmed by a second agent over all 586 values
  through `tools/instruments.py`.
- **Determinism (D26).** 77 outputs across capability selection, routing, verdict parsing,
  telemetry folding and wave scheduling, hashed under five `PYTHONHASHSEED` values — one
  digest.
- **The verifier cannot be talked into approving.** 40 adversarial replies — `**APPROVE**`,
  `> APPROVE`, BOM, homoglyphs, verdict-on-second-line, "Cannot approve". Zero fail-opens.
- **Reply parsing under hostility.** 21 malformed shapes × 5 targets — unbalanced fences,
  NUL bytes, bidi overrides, 100 KB info strings — each produced a `ParsedFile` or a named
  refusal.
- **Telemetry concurrency.** 16 threads × 200 records, 8 processes × 200 KB writes, and
  `flock` monkeypatched to a no-op: all clean. `O_APPEND` carries the atomicity by itself.
- **No worker code is ever executed.** No `sys.path` mutation, no `exec`/`eval`/`compile`
  of worker output. local-ai's `run_ghostcall` hazard was not ported.
- **DAG scheduling is sound.** 4,000 randomised plans with cycles, self-edges and duplicate
  ids: zero violations of ordering, exactly-once reporting, or the failed/blocked partition.
- **Path traversal is refused.** 18 hostile task ids and every escaping target shape — none
  reached outside the store root or the repository.
- **The 18 GREEN regression guards held throughout.** Sandbox isolation, context assembly,
  availability probing, failing-test-first acceptance, secret scanning, determinism. None
  regressed.

## 6. Suggested order of work

Each step makes the next cheaper.

1. **Stop `escalate()` raising** (B1). The only live regression, and the only thing
   standing between this branch and parity with `main`.
2. **Decide who owns the bytes** (pattern B). Cheapest fix per defect removed, and doing it
   first stops the remaining repairs being written twice.
3. **Fix the four silent-corruption defects** — B4, B5, pattern A's four writers, and the
   glob target that commits a literal `**` directory.
4. **Close the boundary breaches** (pattern E), starting with `#94` on the retry path and
   the credential in `telemetry.error_detail`.
5. **Then write the driver.** A `ToolStep` executor and a dispatch binding are the two
   pieces standing between the port and a working orchestrator. Until one exists, 28 entry
   points stay untested against each other and every finding above is free to regress.

## 7. Method note

Two teams, no shared findings. Team 1 (7 agents) went deep per module; Team 2 (4 agents)
took seams, boundaries, end-to-end smoke and hostile input. Overlap between them is a
confidence signal: three agents independently found B1, and two independently confirmed
digest stability held.

The pressure test was run because the port was green — 1,998 tests, ruff, `mypy --strict`
and `docs-check` all clean — and green tests prove the stated behaviours, not the unstated
ones. Every finding above coexists with a passing suite.
