# mcgyvr ← local-ai — porting base

**Read time: 3 min for the summary + index. Detail sections are lookup-only.**

|              |                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------- |
| **mcgyvr**   | main `5bdfaab` · `/home/adaramir/claude/mcgyvr` · `src/mcgyvr/` · 88 test files, 1708 tests |
| **Tests**    | `tests/red_port/` — 69 RED + 18 GREEN. PR #379.                                             |
| **local-ai** | main `f9c6cb7` · fresh clone in scratchpad · `mvp/orchestrator/` · 31 test files, 489 tests |
| **Scope**    | Orchestration core only. Code-grounded — no prose sources read.                             |

---

## 1. The one thing to know

> **mcgyvr is a library of seams with no assembled driver.
> local-ai is a complete running loop with weaker seams.**

Three facts, each verified by grep rather than taken from an agent report:

**1. mcgyvr cannot run a task.** There is no `mcgyvr run`. All 12 CLI subcommands are inspection — `capabilities, config, pool, catalog, contract, detect, sandbox, init, attach, index, resolve, read` (`cli.py:686-975`). The only code in the repo that writes a worker's output to a tree is `tools/missions/attempt.py`, **outside `src/`**.

**2. Every expensive step is an unbound parameter.**

| Seam                                   | Parameter  | Production binding |
| -------------------------------------- | ---------- | ------------------ |
| `escalate()` `escalate.py:522`         | `attempt`  | none               |
| `climb()` `route.py:407`               | `attempt`  | none               |
| `decompose()` `decompose.py:183`       | `propose`  | none               |
| `judge()` `escalate.py:260`            | `verifier` | none               |
| `runner.dispatch_role` `runner.py:545` | —          | **zero callers**   |

**3. Three declared surfaces are inert** — validated at load, read by nothing: `contract.risk`, `config.delivery.*`, `config.verifier.*`.

local-ai has all of this bound and running: `mvp/cli.py:138 main` → decompose → DAG waves → `run_task_orchestrated` → gate → verify → merge gate → commit.

**So the port is not "copy features."** It is: bind mcgyvr's sockets using local-ai's plugs, then port the ~8 behaviors mcgyvr has no socket for at all.

---

## 2. Index — 38 levers, sorted by what to do

Status: **●** full · **◐** partial · **○** absent

### 🔴 PORT — blocking (nothing works without these)

| #   | Lever                            | mcgyvr        | local-ai |
| --- | -------------------------------- | ------------- | -------- |
| D22 | Merge / apply to working tree    | ○             | ●        |
| X02 | Telemetry sink (attempt records) | ○             | ●        |
| D19 | Semantic / LLM-judge verifier    | ◐ socket only | ●        |

### 🟠 PORT — high value per line

| #   | Lever                                 | mcgyvr           | local-ai |
| --- | ------------------------------------- | ---------------- | -------- |
| D21 | Deterministic repair of worker output | ◐ normalise only | ●        |
| D07 | Per-task-type output-cap table        | ◐                | ●        |

### 🟡 PORT — after the above

| #   | Lever                                           | mcgyvr             | local-ai |
| --- | ----------------------------------------------- | ------------------ | -------- |
| D23 | Pending stash + `--reverify` recovery           | ○                  | ●        |
| D14 | AST merge-back for scoped edits                 | ◐                  | ●        |
| D02 | DAG waves + re-decompose on failure             | ◐ no driver        | ●        |
| X03 | Capability-**dimension** gating of model choice | ◐ scalar only      | ●        |
| D17 | mypy check + param-mutation detection           | ◐                  | ●        |
| X07 | Missing-dependency tier degradation             | ○ tier-0 is a hole | ●        |
| D06 | `retry_note` carried into the next attempt      | ○                  | ●        |
| D25 | Retryable-vs-terminal failure axis              | ◐                  | ●        |
| D09 | Failure-cooldown model degrade                  | ○                  | ●        |
| D12 | Model-size-aware context budget                 | ○                  | ●        |

### ⚪ PORT — optional / later

| #   | Lever                                             | mcgyvr | local-ai |
| --- | ------------------------------------------------- | ------ | -------- |
| X04 | Best-of-N gate-scored consensus                   | ○      | ●        |
| X06 | Tag affinity + vLLM sleep-swap                    | ○      | ●        |
| X05 | Style-vs-correctness split + zero-token cleanup   | ◐      | ●        |
| D13 | Structured output (`response_format` JSON schema) | ○      | ●        |

### 🟢 KEEP mcgyvr — do not port, do not regress

| #   | Lever                                            | mcgyvr             | local-ai                    |
| --- | ------------------------------------------------ | ------------------ | --------------------------- |
| D24 | Sandbox isolation                                | ● docker + tempdir | ○ `shell=True` in your repo |
| D11 | Context assembly (index/resolve/read)            | ●                  | ◐                           |
| D10 | Availability probing                             | ●                  | ◐ buggy                     |
| D16 | Acceptance — `failing_test_first`                | ●                  | ◐ exit-code only            |
| D20 | Secrets scan + credential-stripped env           | ●                  | ◐                           |
| D26 | Determinism / no RNG                             | ●                  | ◐                           |
| M1  | Sandboxed digest-pinned semantic resolver        | ●                  | ○                           |
| M2  | Repo attach as a first-class input               | ●                  | ○                           |
| M3  | Changeset via throwaway git index                | ●                  | ○                           |
| M4  | detect → propose → init (self-validating config) | ●                  | ◐                           |
| M5  | Host-wide capacity `flock`                       | ●                  | ◐ semaphore                 |

### ⚫ PARITY — leave alone

`D01` contract schema · `D04` tier ladder · `D15` scope enforcement · `D18` test execution

---


### ⏸ DEFERRED to v2 — decided 2026-08-28, out of the v1 test batch

| #   | Lever                                | Why deferred  |
| --- | ------------------------------------ | ------------- |
| D03 | Risk classification                  | user call: v2 |
| D05 | Routing: keyword triage + risk floor | user call: v2 |
| D08 | Cost model / rate card               | user call: v2 |
| X01 | Measured per-attempt energy          | user call: v2 |

Deferring these four also dissolved the "where does new config live" question (M4):
they were the only approved levers needing new config keys. What remains — `D22`,
`D19`, `X02`, `D23` — needs almost none, because `config.delivery.*` and
`config.verifier.*` already exist and already validate.

## 3. Detail — 🔴 blocking

### D22 · Merge / apply to working tree
- **mcgyvr:** ABSENT in core. Nothing in `src/` writes, commits, branches or pushes. `config.delivery.mode` / `.token_env` are validated and read by nothing (`config.py:252-271`). The nearest real code is `tools/missions/attempt.py:_write`, outside the package.
- **local-ai:** `apply_worker_output` writes the target; **every non-accepted attempt calls `reset_workspace` in a `finally`** so no attempt poisons the next; `run_merge_gate` re-confirms four things at commit time (accepted verdict, change still present, scope, **full gate re-run**); `commit_accepted` commits with an injected identity.
- **Port:** the whole chain, into a new `src/mcgyvr/deliver.py`. `config.delivery.*` already exists to configure it. The `finally`-reset invariant is the part that matters most.
- **Anchors:** `apply.py:194-333` · `merge.py:44-100` · `orchestrate.py:384-400`

### X02 · Telemetry sink
- **mcgyvr:** NONE. The word "telemetry" appears only in docstrings. No attempt is ever recorded, so nothing about a run is measurable after it exits.
- **local-ai:** Append-only JSONL. Two record kinds — `AttemptRecord`, and `OutcomeRecord` as an **append-only correction** keyed by `assignment_id`, folded latest-wins by `resolve_records` (orphans kept, never dropped).
- **Port:** the record shapes + the fold. This is the prerequisite for D08 pricing and for any before/after claim about the port itself.
- **Anchors:** `telemetry.py:20-183` · `tools/record_outcome.py:33-60`

### D19 · Semantic / LLM-judge verifier
- **mcgyvr:** the **policy is complete and the socket exists** — `judge()` reads the gate first and returns before `verifier` is so much as named on the rejected path; `Review` maps to `Assurance.VERIFIED` / FAILED+RetryNotes / FAILED+`reviewer_failed`. What is missing: nothing ever constructs a `Review`, and there is no verifier reply parser.
- **local-ai:** full implementation — prompt = contract + deterministic gate summary + **the full original file** + the applied diff; **refuses to let a model judge its own output**; requires one of `APPROVE / APPROVE_WITH_NOTES / REMEDIATE / ESCALATE` as the exact first token; reviewer-side failures bump the verifier tier.
- **Port:** `build_verifier_prompt` + `parse_verifier_output` + the self-verification refusal. Then `dispatch_role("verifier", …)` gets its first caller. **Cheapest big win — mcgyvr has the harder half already.**
- **Anchors:** `verifier.py:50-225` · mcgyvr `escalate.py:260-352`, `runner.py:545-569`

---

## 4. Detail — 🟠 high value

### D21 · Deterministic repair
- **mcgyvr:** normalisation only. `ruff format --diff` (report), `ruff check` **without** `--fix`. A format violation is a `Finding`, never a rewrite. No autofix anywhere.
- **local-ai:** on gate failure — ruff `--fix` + `format`, ghostcall comment-out, **auto-import insertion from `contract.deps`** (matched against ruff F821) — then **re-run the gate and accept on the same rung with no model retry**.
- **Port:** the repair-then-re-gate loop. It converts failed attempts into free passes; the value scales with how weak the local model is.
- **Anchors:** `deterministic_repair.py:25-267` · `acceptance.py:950-1031`

### D03 · Risk classification
- **mcgyvr:** `risk` is validated (`low|medium|high`), written by the decomposer, printed by the CLI — and **read by nothing**. `route.py:64-66` says so explicitly. A `risk: high` contract produces a byte-identical plan to `risk: low`.
- **local-ai:** pure rule-based — high-risk prompt keywords (31) or path fragments (8) → `high`; else low-risk task type → `low`; else `medium`. A contract's declared risk may only **raise**, never lower.
- **Port:** the classifier. Smallest diff on this list — the field already exists and validates.
- **Anchors:** `risk.py:16-104`

### D05 · Keyword triage + risk floor
- **mcgyvr:** `plan()` is pure and inspectable (zero I/O, diffable before a token is spent — keep that). Start rung = the catalog's `starts_on`, and **nothing is applied on top**.
- **local-ai:** `triage.by_type` → `by_keyword` → `default`, then `apply_risk_floor` raises the start to `risk[level].floor`. Pool tiers route a second time: quality floor from risk, capability-dimension filter, then cheapest-first by tok/s with source affinity.
- **Port:** the risk floor first (pairs with D03), keyword triage second, quality-floor model selection third.
- **Anchors:** `router.py:233-251,561-581` · `pool.py:284-325`

### D07 · Per-task-type output-cap table
- **mcgyvr:** four budgets already, including a measured **32% estimate reserve** (`preflight.py:57`) — that reserve is better than anything local-ai has. But `limits.max_output_tokens` is a flat default of 1024 for every task type.
- **local-ai:** a table keyed by task type (512–3072) plus a `function_impl` new-file allowance, rounded to 128, floored at 256. Verifier and worker **input** budgets are enforced at **zero spend** in preflight.
- **Port:** the cap table + the preflight budget refusal. Keep mcgyvr's reserve.
- **Anchors:** `token_cap_setter.py:27-175` · `acceptance.py:764-823`

### D08 · Cost model / rate card
- **mcgyvr:** `capability-table.json` holds measured HumanEval+ pass@1, tok/s, VRAM with provenance — a real capability rate card. But **there is no monetary or per-token price anywhere in `src/`**, and `Completion` records token counts without ever costing them.
- **local-ai:** effective-dated `rates.json`; local attempts priced as `joules/3.6e6 × usd_per_kwh`, API as `tokens/1e6 × per-Mtok`; **priced at read time**, so appending a later `as_of` re-prices only newer attempts. Unpriced buckets surface as UNPRICED, never as `0.0`.
- **Port:** needs X02 (telemetry) and, for the local half, X01 (energy). The read-time pricing and the UNPRICED≠0 rule are the design decisions worth keeping verbatim.
- **Anchors:** `rates.py:38-136` · `tools/cost_rollup.py:47-130`

---

## 5. Detail — 🟡 later ports, one line each

| #   | What to lift                                                                                                                                                                                                                                                                      | Anchor                                          |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| X01 | RAPL `energy_uj` diff + trapezoid-integrated `nvidia-smi` over exactly the attempt window; stamp `energy_joules`/`scope`/`source`                                                                                                                                                 | `power.py:80-348`                               |
| D23 | `data/pending_review/<id>` stash (patch + exact bytes + meta) and a `--reverify` recovery run for work stranded by an unreachable verifier                                                                                                                                        | `pending.py:23-107`, `router.py:1475-1642`      |
| D14 | AST `merge_back` — splice the worker's function/class over the matching node, so a scoped edit doesn't rewrite the file. Also `{"content": …}` unwrap                                                                                                                             | `apply.py:159-224`                              |
| D02 | DAG waves on `depends_on` + `_recompose` with a `PREVIOUS ATTEMPT RESULTS` block naming what failed                                                                                                                                                                               | `orchestrate.py:243-480`                        |
| X03 | task_type → dimension (algorithm, class_design, …); filter models by `capabilities[dim] >= floor`, not by scalar quality                                                                                                                                                          | `router.py:421-436`, `task_types.py:44-117`     |
| D17 | mypy gate step + compliance AST families; `param-mutation` = correctness (rejects), everything else = style                                                                                                                                                                       | `acceptance.py:290-346`, `compliance.py:34-260` |
| X07 | Tool missing → re-route to the pool **and record the cost in telemetry**. mcgyvr's tier-0 is worse than degraded: `route.py:369` states the deterministic family "binds no rung … not reached through the ladder", so every `starts_on: deterministic` type plans an empty family | `router.py:938-955`                             |
| D06 | `retry_note` — feed the gate's failure summary / verifier REMEDIATE notes into the next attempt's prompt                                                                                                                                                                          | `router.py:1415-1428`                           |
| D25 | The `REASSIGNABLE` axis — which failure categories may be retried elsewhere vs. which are terminal                                                                                                                                                                                | `failure_categories.py:82-85`                   |
| D09 | Failure cooldown: 3 consecutive failures on a model key → unavailable for 60 s                                                                                                                                                                                                    | `pool.py:712-719`                               |
| D12 | Model-size-aware context budget (≤3B → 4096 tokens, else 8192)                                                                                                                                                                                                                    | `context_prune.py:18-29`                        |

---

## 6. Do not port

| From local-ai              | Why not                                                                                                                                                                                                                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Execution model (D24)      | `shell=True` **directly in the caller's live checkout**; the only hardening is `start_new_session` + git rollback. `run_ghostcall` even puts the workspace on `sys.path` and imports in-process. mcgyvr's docker sandbox with resource ceilings and a credential-stripped env is strictly better. |
| Availability probe (D10)   | `check_ollama_available` treats **any** HTTP response as healthy — only a transport exception yields False. mcgyvr's classifies 401/5xx as down and 404/405 as live, and caches.                                                                                                                  |
| Context assembly (D11/D12) | mcgyvr's index → ranked resolve → windowed read, with deps as signatures and budget **deferral instead of truncation**, is a generation ahead.                                                                                                                                                    |
| Acceptance model (D16)     | No `failing_test_first` equivalent — local-ai cannot require a demonstration to fail on the unchanged tree.                                                                                                                                                                                       |

---

## 7. Defects found while reading

**Verified directly by me:**

1. **local-ai — `ContractError` used but never imported.** `mvp/orchestrator/orchestrate.py:332` and `:455` reference it in `except` clauses; imports at `:43-53` bring in only `TaskContract`. A malformed contract in the CLI wave path raises `NameError`, and `:332` sits **outside** the outer `except Exception` at `:373` — the whole batch crashes. This is the CLI's only intake path, and waves are untested.
2. **mcgyvr — three inert surfaces.** `contract.risk`, `config.delivery.*`, `config.verifier.*` all validate at load and are read by nothing.
3. **mcgyvr — `runner.dispatch_role` has zero callers.**
4. **mcgyvr — the deterministic family can never route.** `route._why_empty:369-378` states tier-0 binds no rung and "is not reached through the ladder."

**Reported by the local-ai team, not independently re-checked:**

5. `check_ollama_available` never returns False for a reachable-but-broken server (`mvp/workers/ollama_client.py:81-84`) — a 500-returning Ollama passes the probe and burns a tier attempt.
6. `configs/dimensions.json` is dead config — no loader references it; the router hardcodes `dim_floor = 0.5` at `router.py:427,714`.

---

## 8. Decisions taken (2026-08-28)

**Test shape.** A test states the behavior mcgyvr must have — observable outcomes only
(file content, refusal reason, what a record contains). It never asserts which module
does it or which function it calls. Where a lever has no code yet, the test names a
minimal entry point so it can run at all; that name is a placeholder the port may
rename, and the assertions are the contract.

### v1 batch — 24 tests

| Group                      | Levers                                           | State |
| -------------------------- | ------------------------------------------------ | ----- |
| 🔴 blocking                | D22, X02, D19                                    | RED   |
| 🟠 high value              | D21, D07                                         | RED   |
| 🟡 after                   | D23, D14, D02, X03, D17, X07, D06, D25, D09, D12 | RED   |
| ⚪ optional                | X04, X05, D13                                    | RED   |
| 🟢 keep — regression guard | D24, D11, D10, D16, D20, D26                     | GREEN |

**Written and verified 2026-08-28** — `tests/red_port/`, 24 test files:
**69 RED tests, all failing. 18 GREEN tests, all passing.** ruff and mypy clean under
the repo's own config.

The RED tests fail with a sentence, not a stack trace: `mcgyvr must be able to: <behavior>`.
That is the `required()` convention in `tests/red_port/conftest.py` — where a lever has no
code, the entry point it names is a **placeholder the port may rename**, and only the
assertions after it are the contract.

Three teams independently checked their RED was honest by writing throwaway stub
implementations, confirming all tests passed against them, then deleting the stubs. So
these fail because the behavior is absent, not because a fixture is broken.

The 18 GREEN pin mcgyvr's crown jewels so the port cannot quietly regress them. **No
`xfail` was needed: every claim this report made about mcgyvr's advantages held under
test.**

Two findings from writing them:

* `X07` is confirmed empirically, not by reading a comment: **4 of 4 deterministic task
  types in `data/task-catalog.json` plan nothing to run on their own floor.** mcgyvr's
  tier-0 is not weaker than local-ai's — it is absent.
* The `D19` M1 test is deliberately half-GREEN. The non-blocking half (finding lands in
  `observations`, gate still accepts) passes today; only "the note reaches the verifier"
  is RED. That is what makes a silent flip to blocking detectable later.

### M1–M5

| #   | Decision                                                                                                                                                                                                                                                                                      | Lands in |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| M1  | Semantic check stays **non-blocking**. Its findings are fed to the ported verifier as notes, the way local-ai's verifier receives its gate summary. mcgyvr ships ghostcall false-positive fixtures, so it measured the cost and chose this deliberately — the port must not silently flip it. | D19 test |
| M2  | Delivery **refuses to commit** when attach reported a dirty tree, with a named reason and the tree untouched. A dirty tree mixes the worker's change with the human's unfinished edits.                                                                                                       | D22 test |
| M3  | Delivery diffs against the **sandbox base commit**, not the attach revision — what ships is exactly this task's worker + repair output.                                                                                                                                                       | D22 test |
| M4  | **No action.** Dissolved by the four v2 deferrals.                                                                                                                                                                                                                                            | —        |
| M5  | Superseded by the queue architecture below.                                                                                                                                                                                                                                                   | §9       |

### Still unsettled — 5

`X06` tag affinity + sleep-swap (now a v2 prerequisite, see §9) · `D01`, `D04`, `D15`,
`D18` (parity — no action proposed).

---

## 9. v2 target architecture

Recorded as decided, not built:

> one `main_in_queue`, round robin over orchestrators' contracts, each orchestrator
> decides priority for its own `<tag>_queue`, one `main_out_queue` with outputs,
> pushback, refine.

**What mcgyvr has today:** nothing. No queue, tag, priority or backpressure concept
exists in `src/` — the only `tag` matches are docker image tags and code-fence
language tags.

**Two seams already exist:**

| Piece                   | Existing owner                                                                                                                                  |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Pushback / backpressure | `Capacity.Usage` reports per-source wait time; `Concurrency` reports cross-source in-flight. The saturation signal is produced and fed nowhere. |
| Priority within a tag   | `route.plan()` is pure and zero-I/O, so plans can be ranked before a token is spent.                                                            |

**Three things it costs:**

1. It cannot precede `D22`. A distribution layer over orchestrators that cannot
   complete a contract only relocates the hole.
2. It reverses a deliberate property. `capacity.py:463` returns batch results in input
   order "whatever order they finished in — a batch whose results were ordered by
   completion would be reproducible only on a quiet machine." A `main_out_queue`
   delivers by completion. `D26` is on the KEEP list, so this is a trade to make
   explicitly.
3. It promotes `X06` (source tags) from optional to prerequisite.

**Constraint on the v1 batch, so v2 stays reachable:** `D22` and `X02` must not bake in
single-orchestrator assumptions — no global mutable state, records carry an
orchestrator id, delivery is callable concurrently.
