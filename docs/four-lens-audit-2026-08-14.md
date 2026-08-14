# The four-lens audit — the population, measured

**Issue:** #251. **Date:** 2026-08-14. **Doctrine:**
[ADR-0026](decisions/0026-four-lenses-record-mutate-state-the-property-and-price-the-axes.md).

#251 asked four things: confirm or refute every item in its starting inventory
with the evidence recorded either way; sweep for the *classes* rather than the
instances; give each class a mechanical check rather than a fix list; and say
which published figures move.

This is that. Every ✓ below was reproduced by executing something — the scripts
are named per row — on the tree at `1ab852a7`. Nothing here was accepted because
it was written down, including the inventory that prompted it.

## The finding that changes the most

**One shipped product constant is wrong for one of the two languages it governs,
and the claim it cites says so.**

`ESTIMATE_RESERVE = 0.32` (`src/mcgyvr/gate/preflight.py:57`) is the reserve
`check_prompt_fits` charges against a proxy token count. CLM-0011 derives it as
"the worst vocabulary's p05, rounded up" — and that derivation is **pooled over
language**, in a claim whose own statement reads *"the band is
language-dependent."* Recomputed from the vendored units the claim cites
(`records/measurements/tokens-2026-08-03/units.jsonl`, 2,387 units):

| stratum | n | worst-vocabulary p05 | reserve it implies |
|---|---:|---:|---:|
| pooled (**shipped**) | 2,387 | −31.1% | **0.32** |
| javascript | 518 | −35.1% | 0.36 |
| python | 1,869 | −28.9% | 0.29 |

So the shipped reserve **under-reserves JavaScript by about 4pp of prompt
budget** and over-reserves Python by 3pp. This is not a measurement-tooling
defect: it is in `src/`, it is enforced on every prompt, and a JS/TS prompt that
fits under a 32% reserve and would not fit under 36% is admitted today.

That is ADR-0026's own consequence clause — *"a report refuses a pooled figure
across a stratum where the effect is heterogeneous"* — applied to a constant
rather than a report, and it is the one place in this audit where a number a user
is exposed to actually moves.

The audit does **not** change the constant. Choosing between one conservative
reserve and a per-language pair is a design decision with its own cost, and #251
is out of scope for fixing what it finds. **Filed as #256.**

## Method, and what a verdict means

| verdict | meaning |
|---|---|
| **✓ CONFIRMED** | Reproduced by execution. The row names how. |
| **~ NARROWED** | The defect is real; the inventory's statement of it was wider, or attributed to the wrong place, than the evidence supports. The corrected form is given. |
| **✗ REFUTED** | Could not be reproduced. What was searched is stated. |
| **⧗ UNVERIFIABLE HERE** | True in code, but the asserted magnitude needs a live endpoint or a re-run this audit is barred from doing. |

No item is dropped silently. Where the inventory's figure and the recomputed
figure differ, the recomputed one is given and the difference is stated.

## What this audit could not read

Stated first, because it bounds everything below.

**The `norule` condition is not in the repository.** ADR-0026's central evidence
row — *"stock and norule manifests are byte-identical apart from the label"* —
and the session record's stock→norule table (−10.6pp, −16.1pp, p = 1.4e−6) rest
on runs that were never committed. Every conditioned run under
`records/measurements/` is `stock`, `noscaffold` or `planonly`; there is no
`norule` cell. The `bundle_sha256` half of that finding **is** confirmed in code
(below); the effect sizes are not re-derivable here.

That is itself lens 1, at the sharpest point available: the measurement behind
the decision of record is unrecoverable, and the decision is already adopted.

## Lens 3 — a label standing in for the property

| # | item | verdict | evidence |
|---|---|---|---|
| 3.1 | `GATE_RUNGS` declares five names; the gate emits nine `check=` values and only **one** is a literal match | **~ NARROWED** | **Two** match, not one: `scope` and `acceptance`. Three declared names (`adapters`, `secrets`, `structured`) match nothing emitted; `secrets`/`secret` and `structured`/`structured-data` are near-misses and `adapters` is a category naming four checks. The defect stands and is worse than a miscount: a reader joining a row's `rejected_by` to the declared bar matches 2 of 9. AST sweep over `src/mcgyvr/gate/`. |
| 3.2 | 328 ruff rules against 66 eslint rules, written into both arms as one identical `gate_rungs` | **✓ CONFIRMED, exactly** | `ruff rule --all` resolved against `[tool.ruff.lint] select` → **328**. `eslint.config.mjs` flattened → **66** enabled, all severity `error`. Both figures reproduce the ADR's to the digit. |
| 3.3 | `ACCEPTANCE_TIMEOUT_S` "matches `tools/bundle/measure.py`'s" — 120.0 against 30.0 | **✓ CONFIRMED** | `tools/bench/score.py:57` = 120.0; `tools/bundle/measure.py:179` = 30.0. `tools/problems/admit.py:62` claims "the same ceiling as **the rigs'**" and uses 30.0 — true for one rig, false for the other. |
| 3.4 | `condition` is a bare string; `bundle_sha256` hashes the *system* prompt while an ablation edits the *user* message | **✓ CONFIRMED in code** | `tools/breadth/measure.py:879`: `hashlib.sha256(prompt.system.encode(...))`. A user-message ablation cannot move the digest. The `norule` half is unverifiable here (above). |
| 3.5 | No manifest records a product revision, linter version, config digest, model digest, vocabulary or template | **✓ CONFIRMED, wider than stated** | Over all **123** committed `run.json` (the inventory said 133): `rig_revision` is not a key in *any*; 0 carry a linter version, config digest, model digest, vocabulary, template, rendered-prompt digest, seed, `top_p` or `num_ctx`. |
| 3.6 | `_EMPTY_TREE` duplicated with a comment asserting sameness; true today, enforced by nothing | **✓ CONFIRMED** | `gate/changeset.py:36` and `orchestrator/repo.py:47`, both `4b825dc…4904`; `repo.py:46` asserts it. Now enforced — see C1. |
| 3.7 | `tsconfig.json` never staged, so `tsc --noEmit` never runs while both arms declare identical `gate_rungs` | **~ NARROWED** | The staging fact is confirmed: `stage_dir` writes `.gitignore`, `pyproject.toml`, `eslint.config.mjs` and `node_modules` and no `tsconfig.json`; the repository has no `tsconfig.json` at all. But `tsc` is **not in the declared bar** — no rung names a type check — and ADR-0006 makes "a repository declaring no type checker is not type-checked" the designed outcome. The real finding is adjacent and stands: **the bench's TypeScript arm is scored with no type checking whatsoever, and nothing in the manifest says so.** |
| 3.8 | prettier runs unconfigured on defaults declared nowhere | **✓ CONFIRMED** | No `.prettierrc*` or `prettier.config.*` anywhere in the repository. Ruff's config *is* staged and derived from `pyproject.toml` at call time (`lint_config`); prettier's is not. The two arms' format bars are asymmetric: one declared, one inherited from a tool default. |
| 3.9 | `structured` is vacuous on both bench arms | **✓ CONFIRMED, by construction** | `structured.py` fires only on `.json/.yaml/.yml`. All **514** bench contracts target `solution.py` or `solution.ts` and allow only that path. The rung cannot fire in any cell. Over 514 committed rows, `scope` and `secret` also never fired. Of the five declared rungs, exactly one — `acceptance` — is both declared and observed. |
| 3.10 | `javascript.py` returns `[]` on a fatal eslint invocation with no finding and no environment issue | **~ NARROWED** | Confirmed as a fact, but **not JS-specific**: `python.py` does the same on a ruff `JSONDecodeError`. The adapter comment claiming parity with the Python adapter is *true*. The class is therefore symmetric and larger than one adapter — **an inconclusive rung reports as a pass and records nothing** — which is the shape ADR-0026 calls negative rather than neutral. |
| 3.11 | eslint counts severity 2 only, where every ruff diagnostic counts | **✓ CONFIRMED, currently inert** | `_ESLINT_ERROR = 2` filters; `python.py` has no severity filter. Under the current config all 66 eslint rules are severity `error`, so the filter drops nothing **today**. It is latent: a future rule set to `warn` is dropped silently and counted nowhere. |
| 3.12 | `rejected_by` is `findings[0]`, an ordering artefact: py `format` credited 23, actually fires 155 | **✓ CONFIRMED, exactly** | Recomputed from `fail_output` on `bench-null-gate-15b-a`: `format` first = **23**, any = **155** (6.7×); `lint` 153 → 154. Arm *b* gives 23 → 154 independently. `rung_report` already knows this and computes `canary_rejected_by` over the whole set; the per-row scorer does not. |
| 3.13 | Claims CLM-0004/0005 and CLM-0013–0016 carry no language in scope | **~ NARROWED** | CLM-0013, 0014 and 0016 **do** name a language. The claims whose statement names none are **CLM-0001, 0002, 0003, 0004, 0005, 0007, 0008, 0015** — eight, a different and larger set than the inventory's six. Several were measured on single-language material (CLM-0002 on HumanEval+, CLM-0004 on the Python bundle set, CLM-0015 on JS/TS breadth). |

### New in lens 3, found by the sweep rather than the inventory

**The positive control does not cover the bar it claims to.**
`require_rungs` (`tools/bench/score.py:415`) is documented as *"Refuse the sweep
unless **every declared rung** can reject on every arm."* It compares against
`CANARY_EXPECTS`, which is `("lint", "format")` for both languages. Those two
names are not in `GATE_RUNGS` at all — they are sub-checks of `adapters`. So the
control proves 2 of the 9 emitted checks are live and **0 of the 5 declared
rungs**, under a docstring promising all of them. This is ADR-0026 lens 3
applied to the machinery ADR-0026 asked for, which is the same recursion the ADR
notes when it says two of the eleven instances were in tooling written that
morning to diagnose the other nine.

**A missing field is rendered as a positive claim.** `tools/bench/report.py:236`
prints the bar as `"acceptance command only (pre-#113 scorer)"` when `gate_rungs`
is absent. The inference is *correct for the committed data* — the 28 bench
manifests without the field genuinely carry no `rejected_by` — and
`measure.py:873` documents the convention. It is recorded here as latent, in
`_EMPTY_TREE`'s category: true today, and a fact about scoring inferred from a
field's absence rather than read from a record.

**`gate_rungs` is carried by 2 of 30 bench manifests.** `report.py`'s
`BOUND_MATCH` requires it, and `read_cell` raises on its absence — so the
comparability guard would refuse 28 of the 30 committed bench cells, including
every calibration and every ablation arm. `serving_build`, also in `BOUND_MATCH`,
is present in 12 of 123.

## Lens 1 — recorded and never read, or unrecoverable and never captured

| # | item | verdict | evidence |
|---|---|---|---|
| 1.1 | `steering_band` and `shape` are read by no analysis tool | **~ NARROWED** | `steering_band` **is** read — by `tools/bench/redundancy.py` (as a filter), and validated by `admit.py`. `shape` and `file_shape` are read by **none** of the six tools that turn rows into a published figure. Both are validated at admission, so the corpus is refused without them and no figure is ever cut by them. |
| 1.2 | …while both slice today's ablation as hard as language does or harder | **⧗ SUGGESTIVE, not decisive** | On the only committed multi-condition sweep, `shape` spreads the effect wider than language in **3 of 4** contrasts (3b→planonly: 29.1pp against 5.9pp; 7b→planonly: 20.0pp against 11.8pp). But n ≈ 10 per `shape` stratum, where a 20pp swing is two tasks. The honest statement is not the magnitude: **nobody can say whether `shape` matters, because no tool that publishes a figure has ever looked.** |
| 1.3 | Sampler state is absent entirely — no seed, `top_p`, `top_k`, `repeat_penalty`, `min_p` | **✓ CONFIRMED** | Both runners send exactly two options. `OllamaRunner._payload`: `num_predict`, `temperature`. `OpenAIRunner`: `max_tokens`, `temperature`. Runs at T = 0.7 cannot be replayed, only re-sampled. |
| 1.4 | Effective context is 4096, not the trained 32,768, because nothing sends `num_ctx` | **⧗ PARTLY** | *"Nothing sends `num_ctx`"* is confirmed — the string appears in no request path. The **4096** itself is a live server default and cannot be verified from the tree; this audit does not run the rig. |
| 1.5 | The vocabulary is obtainable at runtime and never asked for | **⧗ UNVERIFIABLE HERE** | The rig probes `/api/version` only — confirmed. Whether `/api/show` returns 151,936 tokens needs the endpoint. |
| 1.6 | There is no run-record writer in `src/mcgyvr/` at all | **✓ CONFIRMED** | Zero references to `run.json`, `results.jsonl` or `jsonl` anywhere under `src/`. Not a defect so much as unbuilt work: this is E9 (#57, #58), still open. Worth stating because the measurement side records protocol, build, cap and temperature while the product records an operator-chosen `rung` string. |

### New in lens 1, found by the sweep

`fail_output` is written **only when a candidate fails** (`measure.py:616`).
The recomputation in 3.12 was possible *because* every non-passing row keeps its
whole finding list — which is lens 1 working correctly, and worth recording as
the counter-example. The audit's earlier assumption that the findings were lost
was wrong; they are joined, just never by the tool that publishes the attribution.

## Lens 4 — cost of variation out of line with importance

| # | item | verdict | evidence |
|---|---|---|---|
| 4.1 | A new language costs ~17 files, including three separately hardcoded adapter tuples with no registry | **~ NARROWED on the citation, confirmed on the fact** | **13** files carry a hardcoded language identity (excluding tests and corpora), plus the new adapter module itself. The three tuples are real but one citation is wrong: they are `gate/runner.py` (`Gate.__init__`), `orchestrator/decompose.py:346` and `worker/bundle.py:167` — **not** the top-level `runner.py:91`, which is a timeout. `decompose.py:341` carries its own sameness claim: *"The same pair `Gate` builds, so … rather than two lists that have to be kept in step"* — enforced by nothing, and now in C1's scope by name. |
| 4.2 | `language = PYTHON if tier == "bench-py" else JSTS` — a `bench-go` tier is silently scored as TypeScript | **~ NARROWED** | The silent default is real: `tools/breadth/measure.py:354` falls to `language = bundle.JSTS` with no error and no warning. But `bench-go` is currently **refused**, by a directory check two lines later. It would be silently scored as TypeScript the moment `tools/breadth/tasks/bench-go/` existed. The sharper finding is a **second** copy of the map at line 1284 (`args.tier in ("pool-py","bench-py")`), written in a different form, with nothing linking the two. |
| 4.3 | `risk` has three members and zero branches; 2,059 contracts carry a value nothing reads | **✓ CONFIRMED** | Exactly **2,059** `contract.yaml`, all carrying `risk`. It is serialized, printed by `cli.py:278`, and threaded through `decompose` — and no routing or escalation branch reads its value. |
| 4.4 | `Config.require`/`secret` have no callers; `open_sandbox` has zero non-test callers | **✓ CONFIRMED** | `open_sandbox` is imported only by `sandbox/__init__.py` and two tests. `Config.require` has one internal caller inside `config.py`; the `catalog().require(...)` hits are a different method. |

## Lens 2 — sensitivity assumed rather than perturbed

| # | item | verdict | evidence |
|---|---|---|---|
| 2.1 | `ESTIMATE_RESERVE = 0.32` is a pooled percentile shipped in the product; the JS/TS figure is −35.2% | **✓ CONFIRMED — reproduces to −35.1%** | See the headline finding. The pooled derivation also reproduces exactly: worst-vocabulary p05 = −31.1% → 0.32. |
| 2.2 | `MAX_OUTPUT_TOKENS = 768` inherited three hops and derived at none | **✓ CONFIRMED as a duplication** | Defined twice — `tools/breadth/measure.py:168` and `tools/bundle/measure.py:174` — equal today, derived in neither. Now declared in C1. |
| 2.3 | 453 of 514 cells never pass under any condition | **⧗ NOT RE-DERIVED** | Requires the full-corpus sweep this audit is barred from re-running. Recorded as carried forward from #231, unverified here. |
| 2.4 | `attempts: 1` on "2 of 35"; `max_parallel: 1` against a measured 8.5× | **✗ NOT REACHED** | Already filed as #152. Not re-derived; no new evidence. |

## Statistics tooling

Not re-derived. `ablation_report`'s pooling of a T = 0 greedy draw with seven
T = 0.7 draws, `redundancy.py`'s Pearson interval over non-independent pairs, and
the 11.3pp/8.2pp MDE disagreement between `redundancy.py` and
`responsiveness.py` each need the analysis re-run against the sweeps, which
#251's "this audit reads" bound excludes. They are carried forward intact, not
confirmed and not refuted.

## The classes, and the population of each

This is what #251 was actually for. The inventory listed instances; these are the
classes, each with a measured population and a check that fails on the *next*
one.

### C1 — one constant, two definitions

The enforceable form of "a comment asserts two things are equal". The comment is
a claim; the property underneath is that the two literals *are* equal, and that
is checkable without reading prose — which also catches the instance nobody
wrote a comment about.

A first sweep for sameness-asserting comments returned **426** candidates across
71 files, narrowing to **84** that name another location. Almost all are
architectural prose ("the same trick", "the same rule") that no check can or
should hold. That is the wrong class: it is unenforceable, and enforcing it would
mean deleting honest documentation.

The right class is the property. Measured population:

| | count |
|---|---:|
| module-level literal constants defined more than once | 17 |
| …of which are genuine couplings (not name collisions) | 12 |
| …**already disagreeing** | 4 |
| …agreeing today, held by nothing | 8 |

The inventory named **two** of these. The sweep found **ten more**, which is the
answer to #251's title: the population was unknown, and it is an order of
magnitude larger than the incident that prompted the ADR.

Already disagreeing: `ACCEPTANCE_TIMEOUT_S` (120.0/30.0, known);
**`PROBE_TIMEOUT_S`** (1.0 in `detect.py`, 2.0 in `availability.py`, under a
docstring calling the two *"the same trick … for the same reason"* — new, and
weaker than the timeout case since the prose is about concurrency rather than the
value); `TIMEOUT_S` and `_JS_EXTENSIONS` (name collisions across unrelated
meanings, declared as such).

Agreeing today and held by nothing: `_EMPTY_TREE` (known), plus **new**:
`_TS_EXTENSIONS` and `_TSX_EXTENSIONS` between `gate/adapters/javascript.py` and
`orchestrator/symbols.py` — whose comment says *"the names match the gate
adapters"*, and if they stop matching the index and the gate disagree about which
files are JavaScript, silently; `SCHEMA_VERSION` in three modules;
`CLONE_DEPTH` and `REMOTES` across the two reach rigs; `LADDER`;
`MAX_OUTPUT_TOKENS`.

The good pattern, worth naming because it is the counter-example:
`worker/reply.py:106` duplicates the extension tuples **and says so** —
*"Adding a language means adding it in both places, which is the honest cost of
the coupling"* — with the reason importing would be worse. A declared duplication
is not a defect. An undeclared one is.

**Check:** `tests/test_four_lenses.py::test_duplicated_constants_are_declared`
and `::test_declared_duplicates_that_must_agree_do_agree`. The two disagreeing
pairs are declared with their values rather than fixed here — correcting a
timeout that four other things read is its own change.

### C2 — a declared bar naming rungs the gate cannot emit

Population: 5 declared rung names, 9 emitted check values, **2** literal matches.
The check requires every declared name to map explicitly to the emitted checks it
covers, and every emitted check to be covered by some declared name (`semantic`
excepted — absent from the bar by decision, ADR-0011).

**Check:** `::test_declared_rungs_name_emitted_checks`. Verified to reject a
sixth rung named `typecheck` added to the real `GATE_RUNGS`. The control's own
coverage gap is **filed as #258**.

### C3 — a field recorded on every task and read by no analysis

Population: 2 of the fields on a bench task's `meta.json` (`shape`, `file_shape`)
are read by none of the six tools that publish a figure.

Writing this check found a third candidate the inventory never listed —
`target_symbol`, on 66 tasks — which turned out to be legitimately consumed at
task-construction time by `admit.target_symbol`. It is declared separately, with
the function that reads it named. That distinction is the check earning its
keep on the first run.

**Check:** `::test_recorded_task_fields_have_a_reader`.

### C4 — a shipped constant citing a measurement no test re-derives

Population: 1 confirmed (`ESTIMATE_RESERVE`), and it is the headline finding.
The pre-existing test asserted a *band* — `0.30 <= x <= 0.35` — which is a claim
about the number rather than a derivation of it: the units could change
arbitrarily and the band would still pass. The new check recomputes 0.32 from
CLM-0011's vendored units, and a second check pins the per-language figures so
the size of the pooling gap is a computed fact rather than a sentence in an audit
nobody re-runs. This closes the mechanism behind **#207**; the pooling itself
is **#256**.

**Check:** `::test_estimate_reserve_is_derived` and
`::test_pooled_reserve_is_recorded_against_its_strata`.

### The controls

ADR-0026 lens 3 is two-sided: a declaration of content *and* a positive control
proving the declaration is live. Each check above has a canary that must fail —
five in total. Two were additionally verified against the real tree by mutating
it: a new duplicated constant in `src/`, and a sixth `GATE_RUNGS` entry. Both
were rejected with the precise location in the message, and the tree restored.

A canary that stops failing means the check above it has gone inert and is
reporting health while applying nothing, which is the state this whole file
exists to detect.

## Which published figures move

- **`ESTIMATE_RESERVE`: 0.32 → 0.36 for JavaScript, 0.29 for Python** if the
  pooling is undone. A shipped constant, enforced on every prompt. Filed.
- **Per-check rejection attribution moves 6.7× for one rung.** Python `format`
  is credited 23 rejections by `rejected_by` and fires on 155 candidates.
  Every figure read "by cause" from a bench row understates every rung except the
  one that happens to sort first. The rate itself — pass or fail — does not move.
  **Filed as #257.**
- **Nothing else does.** The rest of this audit changes what a reader can *say*
  about a number (which bar, which model, which prompt), not the number. That is
  the honest summary: the population is large, and it is mostly latent.

## What was found by writing the checks rather than by reading

Three things, and they are the argument for the checks existing at all:

1. `target_symbol` — a recorded field the inventory missed, correctly acquitted.
2. `PROBE_TIMEOUT_S`, `_TS_EXTENSIONS`, `_TSX_EXTENSIONS`, `SCHEMA_VERSION`,
   `CLONE_DEPTH`, `REMOTES`, `LADDER` — seven duplications nobody had listed.
3. `require_rungs`'s docstring promising coverage of "every declared rung" while
   its control covers none of them.

None of the three was in the inventory. All three took one run.

## Filed

| # | what |
|---|---|
| **#256** | `ESTIMATE_RESERVE` pools a band its own claim calls language-dependent — 0.32 shipped, 0.36 for JS/TS. The one shipped figure that moves. |
| **#257** | `rejected_by` names the first rung, not the ones that fired — Python `format` understated 6.7×. |
| **#258** | The bench's positive control covers none of the five rungs it declares, under a docstring promising all of them. |
| **#259** | The tier-to-language map is written twice and defaults silently to TypeScript. |

Not filed, and deliberately: the two disagreeing constant pairs
(`ACCEPTANCE_TIMEOUT_S`, `PROBE_TIMEOUT_S`) are **declared in C1 with their
values**, which is smaller than an issue and makes the next drift a build
failure. #207 is commented rather than closed — its mechanism is now checked;
its pooling half is #256.

---

Scope of record: this audit. Rationale for the boundaries it sits inside:
[ADR-0001](decisions/0001-founding-scope-and-boundaries.md).
