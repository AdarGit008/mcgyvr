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
> | §4's remaining three items | Closed — the wrap branch (`green/port-dod-wrap`). `max_waves` now bounds re-planning, not plan depth; `record_success` resets the failure count without cancelling an armed cooldown, and the cooldown is wired into `worker_attempt` so it fires inside a task; and the emitted contract form carries the *declared* output cap (null when derived), so `sha256(dumps(contract))` no longer reads `data/task-catalog.json`. |
> | The ~48 major | Enumerated in §8, **not closed** — most rows there are still Open. Deferred to a follow-up branch; see the decision below. |
>
> **Decision — 2026-08-31 (deferral, recorded).** The ~48 major findings are enumerated in §8, not fixed. They stay Open there — including the reach leftover `G1`/`S3` (`consensus._draw` still runs `space.reset()` after every draw, wiping a caller-supplied sandbox) — and are deferred to a follow-up branch (`green/port-dod-majors`) rather than shipped under a "Closed" banner. This wrap branch closes the three §4 items — the waves bound (`E2`/`E3`), the cooldown (`F4`/`S8`), and the contract digest (`E1`) — and the reach leftovers it fixed (`best_of` repo-XOR-sandbox, gate-takes-sandbox, `token_env` removal, `_INPLACE_WORDS` negation, `_DEPRECATED_TYPING`), and nothing more of §8.
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
>   **Closed.** `sample` is `Callable[[int], str | Unusable]`. An unusable draw
>   is not written, not gated and not ranked — a synthetic rejection would put
>   "the gate refused this" into the record of a gate run that never happened —
>   and it is recorded in `Consensus.unusable` in the sampler's own words, with
>   `len()` still counting every draw that was paid for. Only a run in which
>   every draw refused raises, as `NoUsableDrawError`, which is the single-draw
>   behaviour unchanged.
> * **`best_of`'s `repo` and `sandbox` are mutually exclusive and the signature
>   does not say so**; a caller mid-attempt, the exact caller the docstring says
>   should pass its own sandbox, must still supply a dead `repo`. **Closed.**
>   `repo` is now `Path | None` and `sandbox` is the alternative: pass exactly
>   one, and passing both is refused at the top of `best_of` with the reason.
> * **`best_of`'s `gate: Callable[[Path], GateResult]` promises the workspace is
>   enough to gate**, and in this project it is not: acceptance commands are
>   arbitrary shell that must run in a sandbox (ADR-0005), so the real caller
>   closes over the sandbox and discards the `Path` it is handed. **Closed.**
>   `gate` is now `Callable[[Sandbox], GateResult]`: the sandbox is handed over
>   and the caller gates `space.workspace` through it, so `drive`'s gate no
>   longer closes over a sandbox it was not given.
> * **`worker_attempt`'s `verifier` parameter still has no production caller.**
>   `mcgyvr run` passes `None`, so every ladder acceptance is labelled
>   `unverified` even on an install with `verifier.enabled: true` and a bound
>   role. `verify.reviewer_for` exists and is unwired — a fourth gap of the same
>   shape as the three just closed. **Closed**, and it contradicted its own
>   signature the way the other three did: a `Callable[[], Review]` cannot be
>   built by a caller standing outside the attempt, because `verify` needs the
>   gate that has just run, the bytes it read and the model that wrote them.
>   `worker_attempt` takes the reviewer seam itself (`reviewer: Ask | None`) and
>   assembles the review per attempt; `mcgyvr run` passes `reviewer_for(pool)`
>   when `verifier.enabled` — the one place that flag is read, since `source_map`
>   binds the role whenever a source and a model are declared — and refuses
>   before the sandbox is opened when verification is asked for and the role
>   cannot run. The pre-change file is read off the workspace and passed with
>   it: `build_prompt`'s fallback is `contract.target_content`, which is the
>   orchestrator's copy and is empty on a hand-authored contract, so a review of
>   an edit would have opened "ORIGINAL FILE: not supplied".
> * **`mcgyvr run` never consults `delivery.mode`**, deliberately: `--commit` is
>   a person saying commit this, in the tree they are looking at. That keeps one
>   flag meaning one thing, and it means an operator who set
>   `delivery.mode: branch` does not get a branch from `run`. Worth a deliberate
>   decision rather than leaving it implicit. **Recorded.** The decision is the
>   one the code already carries: `run` passes no config to `deliver`, on either
>   path, so `--commit` keeps meaning "commit onto the branch I am looking at"
>   and cannot silently become `delivery.mode: branch` for ladder contracts.
>   An operator who wants the config's branch behaviour drives `deliver`
>   directly; the flag and the config stay one meaning each.
>
> Three more the earlier fixes surfaced, each load-bearing in a way it was not
> before:
>
> * `_INPLACE_WORDS` is a substring match, so a contract saying *"do not mutate
>   the caller's list"* stands the mutation rung down for the whole file. That
>   was inert while nothing could reach `contract_text`; threading the prose
>   through made it live, and reliable negation in prose is its own design
>   question. **Closed.** The match is word-boundary and negation-aware:
>   `_asks_for_mutation` reads the three words before the ask, so "do not
>   mutate" forbids what the rung flags and does not stand it down, while "sort
>   in place" still does.
> * `delivery.token_env` is read by nothing, because no mode talks to a forge.
>   A dead key implying a forge integration is the same species as the default
>   that was just fixed. **Closed.** The key is removed from the config schema
>   and from the generated config; a config that still sets it is refused as
>   unknown, which is the honest answer for a key nothing reads.
> * `typecheck.py`'s claim that "the verdict does not depend on which tools the
>   operator happens to have" holds for six names. `_DEPRECATED_TYPING` knows
>   `List, Dict, Set, Tuple, FrozenSet, Type` and nothing else, so on a machine
>   without ruff, `from typing import Mapping` is reported by nothing.
>   **Closed.** `_DEPRECATED_TYPING` is now a mapping to the pinned form, built
>   from the `collections.abc` names plus the builtin, `collections`, `re` and
>   `contextlib` generics, and `_pinned_form` reports the real destination
>   (`collections.abc.Mapping`, not `mapping`).

|                |                                                                                  |
| -------------- | -------------------------------------------------------------------------------- |
| **Subject**    | PR #380, branch `green/port-from-local-ai`, 19 levers ported from local-ai        |
| **Method**     | 11 adversarial agents, 2 independent teams — 7 per-module, 4 whole-system         |
| **Rule**       | Read-only on the repo. Every finding reproduced by running code, not by reading it |
| **Result**     | **9 critical, ~48 major.** 1,998 tests pass, ruff/mypy/docs-check clean throughout |

## 8. The major findings, enumerated

The record above names the 9 criticals and the 5 patterns but leaves the rest
as "~48 major". This section enumerates them, from the 11 agents' reports in
this session's records (`docs/archive` and the Claude session records). Each is
marked **Open** or **Closed**, and closed ones name the PR that closed them. A
finding is a defect, not a sentence: every one below was reproduced by running
code, and the severity is the reporter's own.

### Team 1 — per module

**T1-A · `telemetry`, `escalate` axis**

| # | Finding | Where | State |
| - | - | - | - |
| A1 | One torn line destroys the *next* complete record — `_append` never checks it starts on a line boundary, and can create the stump itself on a full disk with no signal | `telemetry.py:290-308` | Open |
| A2 | Clock skew defeats latest-wins — `fold` orders by `(ts, position)`, so the position tiebreak fires only on exact float equality | `telemetry.py:249,283-287` | Open |
| A3 | One undecodable byte makes the whole sink unreadable (`read_text` strict, before the skip-a-line logic) | `telemetry.py:321` | Open |
| A4 | `fold` silently deletes attempt rows that share an id (keys on `attempt_id` alone) | `telemetry.py:243-246` | Open |
| A5 | A surfaced orphan correction cannot say who wrote it (`orchestrator` optional, absent for orphans) | `telemetry.py:194` | Open |

**T1-B · `deliver`, `pending`**

| # | Finding | Where | State |
| - | - | - | - |
| B1 | A pre-commit hook ships ungated bytes and reports success — no check that the committed blob is the gated content | `deliver.py:501-514` | Open |
| B2 | Delivery commits into a detached HEAD or an in-progress rebase and reports `committed=True` (work silently lost; `resume` then deletes the stash) | `deliver.py:213-219,370-387` | Open |
| B3 | Non-UTF-8 content cannot be stashed — raw `UnicodeEncodeError`, leaked staging dir | `pending.py:192-194` | Closed — pattern A, `16a31cbc` |
| B4 | Replacing a stash `rmtree`s the old entry *before* the new one is renamed in — the exact window the module says it exists to prevent | `pending.py:199-203` | Open |
| B5 | The commit-time re-check narrowing lets a credential through; `resume` re-runs no gate at all (`accepted=True` default) | `deliver.py:239-250` × `pending.py:276-278` | Open |
| B6 | `meta.json`'s `target` is used as a filesystem path with no re-validation on the read side | `pending.py:261` | Open |
| B7 | A refused delivery leaves behind the directories it created ("byte-for-byte" claim is false for dirs) | `deliver.py:481,485-490` | Open |
| B8 | A `.gitignore`d target refuses with a false reason | `deliver.py:228-237` | Open |
| B9 | Git failure messages name the wrong subcommand and drop git's stdout | `deliver.py:553-559` | Open |
| B10 | `_slug` collides with its own output (`a/b` and `a-b-c14cddc0`) | `pending.py:287-301` | Open |
| B11 | Filesystem errors escape as raw `OSError`, not `DeliveryError` | `deliver.py:461-483` | Open |
| B12 | A symlink target silently redirects the delivery, and the trailer names a file the commit does not contain | `deliver.py:331-347,517-534` | Open |

**T1-C · `verify`, `cleanup`**

| # | Finding | Where | State |
| - | - | - | - |
| C1 | `reviewer_for` does not handle `SourceMap.role`'s third answer (`SourceUnavailableError`) — a degraded verifier hard-fails | `verify.py:460` | Closed — `6dd0f392`, verifier role has a caller |
| C2 | The self-verification refusal is defeatable by spelling (`strip().casefold()` equality) | `verify.py:368` | Closed — `verify.model_identity`, PR #383 |
| C3 | `tidy` rewrites every line ending of a CRLF file (universal-newline translation) | `cleanup.py:124-133` | Open |
| C4 | `pre = original if original is not None else (view["target_content"] or None)` collapses `""` into `None` | `verify.py:329` | Open |
| C5 | `read_verdict(reply)` sits outside the `try`, and `reviewer_for`'s `ask` has no fit check | `verify.py:428,463-476` | Open |

**T1-D · `repair`, `gate/typecheck`**

| # | Finding | Where | State |
| - | - | - | - |
| D1 | The STYLE demotion makes the gate accept a module that cannot be imported (UP035 covers two moves) | `gate/typecheck.py:121` | Closed — PR #385 |
| D2 | `show_absolute_path = true` silently disables the whole type-check rung (raw-string path compare) | `gate/typecheck.py:251,259` | Open |
| D3 | Auto-import insertion splices *above* a shebang, turning an executable into `Exec format error` | `repair.py:374,388` | Open |
| D4 | `_module_of` writes an import it never checks resolves — rejection becomes acceptance plus `ModuleNotFoundError` | `repair.py:278-298` | Open |
| D5 | `param-mutation` is order-blind — a later rebind anywhere erases an earlier real mutation | `gate/typecheck.py:450-493` | Closed — PR #385 |
| D6 | The `contract_text` stand-down is unreachable — the shipped signature cannot supply it | `gate/adapters/python.py:76-78` | Closed — PR #385 |
| D7 | Three `param-mutation` false positives (lambda shadow, comprehension shadow, slice copy) | `gate/typecheck.py:401-423` | Open |
| D8 | Repair's two ruff subprocesses have no timeout | `repair.py:191,312` | Open |

**T1-E · `waves`, `contract`, `preflight`**

| # | Finding | Where | State |
| - | - | - | - |
| E1 | The emitted contract form (and `sha256(dumps(contract))`) now depends on `data/task-catalog.json` | `contract.py:789` | Closed — wrap branch |
| E2 | `max_waves` bounds total waves, not re-planning — a failure-free 4-deep chain is truncated | `waves.py:174` | Closed — wrap branch |
| E3 | When the wave budget runs out, a contract whose dependency *failed* is labelled "not reached" (can never run at any budget) | `waves.py:206-208` | Closed — wrap branch |
| E4 | `docstring` is the only type whose cap moved *down* (512), and it is the type least bound to reply size (`whole_file`) | `contract.py:166-170,201-232` | Open |
| E5 | `depends_on` order is preserved into `dumps`, so two semantically identical contracts get two identities | `contract.py:685` | Open |
| E6 | An `attempt` that raises propagates and destroys the `WaveRun` — earlier waves' record is lost | `waves.py:181` | Open |

**T1-F · `capability`, `cooldown`, `read`, worker protocol**

| # | Finding | Where | State |
| - | - | - | - |
| F1 | `_definition` returns the first module-level match; Python binds the last — the splice lands on an `@overload` stub | `worker/scoped.py:161-166` | Open |
| F2 | `parse_pinned`'s fallback unwraps a `.json` target's object and deletes the other keys | `worker/reply.py:474` | Open |
| F3 | `_schema_field`'s carrier derivation mis-reads or refuses schemas a backend honoured correctly | `worker/reply.py:225-252` | Open |
| F4 | The cooldown lever is inert on a single-host install — `record_success` pops the whole record | `cooldown.py:171` | Closed — wrap branch |
| F5 | A scoped edit in a CRLF repo spends an attempt on a format diff whose two sides render identically | `worker/scoped.py:157-158` | Open |
| F6 | A reply that re-emits the whole file duplicates every top-level statement (costs an attempt as lint, wrong note) | `worker/scoped.py:158` | Open |
| F7 | `params_b` became a required key while `schema_version` stayed 1 — bare `KeyError` | `capability.py:275` | Open |
| F8 | A `NaN` `params_b` raises `StopIteration` out of `budget_for_model` | `orchestrator/read.py:297-299` | Open |
| F9 | `shipped_table()` returns one shared mutable instance; mutating a model changes selection process-wide | `capability.py:305-313` | Open |

**T1-G · `deterministic`, `consensus`, `route`, `attempt`**

| # | Finding | Where | State |
| - | - | - | - |
| G1 | `best_of` with a caller-supplied sandbox runs `git reset --hard` + `git clean -fdx`, destroying the caller's state and biasing draw 0 | `consensus.py:167` | **Open — reach leftover** |
| G2 | A `Degradation` record says work "is paid for with a model" when nothing above the floor can run it (no `reason` field) | `deterministic.py:283-296` | Open |
| G3 | `Ascent.ladder_budget` counts the un-climbable `ToolStep`; `Plan.rungs` and `Plan.budget` disagree | `route.py:181-183` | Open |
| G4 | `plan()` loads the whole gate package and tree-sitter parsers into a planning-only process | `deterministic.py:371` | Open |
| G5 | `route.py`'s module docstring states the opposite of what `plan()` does | `route.py:51-54` | Open |

### Team 2 — whole system

**T2-A · seams**

| # | Finding | Where | State |
| - | - | - | - |
| S1 | `attempt.run` and `route.climb` both loop attempts on one rung — composed, the budget squares (2 funds 6) | `attempt.py:72` × `route.py:494` | Closed by design — `drive.py` holds the note and does not nest |
| S2 | `cleanup.tidy` cannot fire on the case it was written for (gate emits `check="format"`, not `STYLE`) | `gate/runner.py:176` | Closed — pattern D, `16a31cbc`; wired in PR #385 |
| S3 | `consensus.best_of` destroys the caller's sandbox and biases draw 0 | `consensus.py:167` | **Open — reach leftover** (same as G1) |
| S4 | `delivery.mode` defaults to `pull_request`, and all three modes commit directly | `deliver.py:324-329` | Closed — PR #385 |
| S5 | The port did not produce a driver; 28 of 35 entry points have no production caller | `cli.py:680-996` | Closed — `drive.py` + `mcgyvr run`, PR #383/#385 |
| S6 | `telemetry.observe` cannot wrap an attempt (type is `Callable[[], Completion]`); on mismatch the answer is destroyed and nothing recorded | `telemetry.py:105,163` | Open |
| S7 | No shared error vocabulary — exceptions cross every seam uncaught and `disposition` cannot see them | `escalate.py:696` | Open |
| S8 | `cooldown.Cooldown` can never fire inside a task — `source_map` probes once, `escalate` holds the map | `cooldown.py:102` | Closed — wrap branch |
| S9 | `pending.resume` collapses `verify.py`'s three-state `Review` to a bool, misreporting `UNUSABLE` as a refusal | `pending.py:233` | Open |
| S10 | `worker/scoped.apply_scoped(node=…)` has no producer — nothing in the codebase names a definition | `worker/scoped.py` | Open |
| S11 | `output_schema: unified_diff` loads, prompts with no format instruction, and is refused after the dispatch is paid for | `worker/prompt.py:81` | Open |
| S12 | Three `Verdict` classes and two `Outcome` enums live on the composition path | `route.py`, `verify.py`, `availability.py` | Open |
| S13 | Asymmetric STYLE routing — the typecheck branch extends `findings` unconditionally | `gate/runner.py:186` | Open |

**T2-B · boundaries**

| # | Finding | Where | State |
| - | - | - | - |
| R1 | `#94` breached on the retry path — `RetryNotes.of` copies `str(finding)`, and acceptance findings carry the command in `Finding.path` | `attempt.py:66` | Closed — PR #383 |
| R2 | `verify.py` documents a boundary it does not hold (gate findings carry acceptance/demonstration strings) | `verify.py:260-266` | Closed — PR #383 |
| R3 | Telemetry's `error_detail` is an unfiltered, durable exception-string sink (credentials via `base_url` userinfo) | `telemetry.py:146` | Closed — PR #383 |
| R4 | The port introduced the only new global mutable in `src/` (`_CACHED_TABLE`) | `capability.py:305` | Closed — PR #383 |
| R5 | `telemetry.fold()` keys identity on `attempt_id` alone — one orchestrator's row erases another's | `telemetry.py:236-246` | Closed by design — orchestrator id is part of the attempt id (`drive.Recording`) |
| R6 | The pending stash has no orchestrator id and a deterministic staging path — two orchestrators share one staging dir | `pending.py:169-170` | Open |
| R7 | The endpoint seam guard checks *names*; the new module obtains the *value* (a live `RoleBinding`) | `verify.py:460` | Closed — PR #383 |
| R8 | `repair.py` is the first writer with no sandbox seam | `repair.py:112` | Open |
| R9 | New time-dependent verdict — a mypy timeout rejects on a loaded machine what a quiet one accepted | `gate/typecheck.py:228` | Open |

**T2-C · end-to-end smoke**

| # | Finding | Where | State |
| - | - | - | - |
| K0 | No `run` subcommand — all 12 are inspection | `cli.py:680` | Closed — `mcgyvr run`, PR #383 |
| K1 | `escalate()` raises on every deterministic-floor contract; no `ToolStep` executor exists | `route.py:488` | Closed — B1 fix + `drive.run_tool_step` |
| K2 | The retry note is lost on the only composition `src/` offers (`Judgement.as_result` strips `retry`) | `escalate.py:251` | Closed — `drive.worker_attempt` holds the note |
| K3 | `judge()` drops `value` on every FAILED verdict — the gate-passing bytes never leave the attempt | `escalate.py:294` | Closed — pattern B, PR #383 |
| K4 | The gate silently skips the contract's acceptance commands when the caller does not inject `Acceptance` | `gate/runner.py:212` | Closed — `drive.gate_workspace` builds it |
| K5 | `telemetry.observe` requires a `Completion`, so a deterministic-floor run cannot be recorded | `telemetry.py:105` | Open |
| K6 | `target_content` defaults to `""` and only the decomposer fills it — a hand-written YAML sends a prompt with no file | `contract.py:617` | Open |

**T2-D · edge cases**

| # | Finding | Where | State |
| - | - | - | - |
| X1 | A lone surrogate in a model reply crashes every writer in the port | `deliver.py:482`, `pending.py`, `consensus.py:159`, `scoped.py:115` | Closed — pattern A, `16a31cbc` |
| X2 | A glob target creates and commits a literal `**` directory and reports success | `deliver.py:331` × `contract.py:1005` | Open |
| X3 | The pending store destroys the entry it is replacing before the replacement exists | `pending.py:199-200` | Open (same as B4) |
| X4 | `repair` silently rewrites every line ending in a CRLF file (text-mode round-trip) | `repair.py:355-375` | Open |
| X5 | `apply_scoped` raises `RecursionError` instead of returning a `ReplyError` | `worker/scoped.py:105,115` | Open |
| X6 | `RecursionError` escapes both reply-parser JSON calls (`except ValueError` only) | `worker/reply.py:187,214` | Open |
| X7 | `consensus` is the one writer that does not name its encoding (locale-dependent) | `consensus.py:159` | Open |
| X8 | A refused delivery leaves behind the directories it created | `deliver.py:481,485` | Open (same as B7) |

That is the "~48 major": the count is approximate because the teams overlapped
(A2/R5, G1/S3, B4/X3, B7/X8 are the same defect seen from two angles) and because
several were closed by the same PRs that closed the criticals and the patterns.
The three §4 items and the reach leftovers named above are closed by the wrap
branch; the still-open rows below remain Open, and the ~48 major are deferred
to a follow-up branch (`green/port-dod-majors`) — not closed by this one.

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
