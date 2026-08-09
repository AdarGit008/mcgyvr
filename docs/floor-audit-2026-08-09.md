# The floor-before-ceiling audit — every open issue read against ADR-0017

**Issue:** #220. **Date:** 2026-08-09. **Doctrine:** [ADR-0017](decisions/0017-the-floor-is-the-product.md), P1–P3.

#220 asked for four things: the principles written somewhere citable (ADR-0017,
landed in `b5839178`); every open issue read against them; landed decisions taken
under ceiling-first reasoning corrected rather than quietly reinterpreted; and a
plain statement of which open work raises the floor, which raises the ceiling and
which does neither.

This is that. 69 open issues, read in full on 2026-08-09.

## Method, and what a verdict means

Each issue gets one verdict. The categories are ADR-0017's, not new ones:

| verdict | meaning |
|---|---|
| **FLOOR** | Raises what the smallest tier can complete, or lowers what the offload costs at that end. Per P1 this includes decomposition, prompt assembly, the gates and the caps — not only weights. |
| **CEILING** | Improves or measures the upper tiers only. Not condemned; priced per P2 as a bounded gain on a track that will not replace the API tier. |
| **NEITHER** | Infrastructure, delivery, packaging, records discipline, release. Aimed at neither end. Most of the tree, and correctly so. |

A **†** marks work that is neither floor nor ceiling but *instrumentation* — it
exists to tell one from the other. ADR-0017's largest open gap is in this column.

Two verdicts carry an asterisk (**\***) where the issue's text and its verdict
disagree — those are the conflicts, listed in full after the table.

## The finding that changes the most

**The repository already owns a floor instrument, in both languages, and
ADR-0017 says it owns none.** That sentence in the ADR is wrong and is corrected
below rather than reinterpreted.

`tools/bundle/tasks/` (20 JS/TS) and `tools/bundle/python/tasks/` (20 Python) are
real contracts — `task_type`, `target`, `interface`, `stop_conditions`, a runnable
`acceptance` command, `risk`, `scope` — against a checked-in reference. They have
been measured repeatedly on **qwen2.5-coder:3b Q4_K_M**, the floor model itself:

| set | n | 3B first-pass, by condition | source |
|---|---:|---|---|
| bundle JS/TS (= breadth `d1`) | 20 | 45% / 55% / 50% / 45% (c0–c3) | CLM-0012, two full 80-cell sweeps on two rigs |
| bundle Python | 20 | 35% / 50% / 55% / 65% (c0–c3) | CLM-0017 (CLM-0004's instrument on Ollama) |

Both sit where a floor instrument has to sit: well above 0, well below 100, with
gains *and* regressions visible. They are held out by construction —
`tools/problems/admit.py:104` names both roots as "every task set whose ids and
prose the pool must stay distinct from". And `tools/breadth/measure.py:202` is
explicit that `d1` **is** the bundle JS/TS set byte for byte, so the 50.0% that
ADR-0017 quotes as a breadth rung is this instrument already, under another name.

That is #113's first scope bullet — *"real contracts against a checked-in target,
sized like CLM-0004's twenty and chosen so a small local worker neither floors nor
ceilings on it"* — satisfied, in the repository, since before the pool was built.

**What keeps this honest.** n=20 per set against a declared ±1-task noise floor;
13 of 20 tasks are condition-insensitive on the JS/TS arm (CLM-0012), so the band
where anything can show is narrow; one greedy seed per cell; and CLM-0004's
never-passing set (t02, t03, t06, t17, t18, t19) reproduces across both stacks, so
part of the set is at *its* ceiling. It is underpowered for a small effect. It is
not absent, and the difference between "underpowered" and "absent" is what #225
and #224 are currently sized against.

## The verdicts

### Floor-raising

| # | issue | why |
|---|---|---|
| 13 | E2 — contract and catalog (epic) | The contract is the unit of work a small worker receives; the catalog states what each type guarantees. |
| 16 | Risk classification and routing floors **\*** | Decides how cheap a task may start — the floor lever stated from the other side. P3 conflict, C9. |
| 17 | Deterministic output-cap sizing **\*** | An under-sized cap truncates a correct small-model answer. P3 conflict, C8. |
| 18 | Contract authoring guide | Direct mode's public API; the doctrine's other half. |
| 19 | E3 — source pool and workers (epic) | The workers are the floor. |
| 44 | Keyless degradation: gate-only acceptance | The default path, and the whole bar for an install with no API tier at all. |
| 45 | E7 — orchestrator and index (epic) | Decomposition is floor machinery per P1, explicitly. |
| 71 | v2 — grammar-enforced worker output **\*** | Malformed output is a small-model failure mode. Filed as v2 hardening; see C10. |
| 81 | Deterministic tool tier: exact edits at zero tokens | The only free rung. The cheapest floor raise in the tree; see C5. |
| 110 | E12 — semantic checks in the gate (epic) | Gates are floor machinery per P1. |
| 113 | The harness †**\*** | Its first scope bullet *is* the floor instrument. See the finding above. |
| 116 | Contract residue: stop-condition floors | Tells a small worker what its type's failure modes are. |
| 119 | Sampling breadth as tier policy **\*** | N cheap draws instead of one dear one is a floor lever. P3 conflict, C9. |
| 126 | Target granularity: file or symbol | Narrowing what the worker sees attacks the whole-problem-ceiling gap directly. See C5. |
| 146 | Who supplies the acceptance command | Decides whether a type is reachable at all without a paid tier. |
| 158 | No rung declares its context window | Sizes the work a small model is handed. |
| 159 | Delegated path cannot create a file | A whole shape of task the pipeline cannot express. |
| 162 | Retire the ladder: routing matrix **\*** | Allocates work across tiers. P3 conflict, C9. |
| 168 | The JS/TS bundle costs ~386 tokens for nothing | Per-request cost on every small-worker call, already measured. See C5. |
| 173 | Prompt-fit reserve is multiplicative | "The error runs in the dangerous direction exactly where the reserve is smallest" — i.e. on small prompts. |
| 179 | The verifier role **\*** | Q1 (which tier it binds to) is a P3 question; a verifier that only works at the API tier makes the keyless path second-class. |
| 190 | Distill API-tier work into the local tier **\*** | Floor-raising in intent, ceiling-measured in its acceptance. Correction C3. |
| 198 | Is our own prompt assembly near-optimal? | One line was worth +4 tasks in 20, costs nothing at inference, ships to every rung. See C5. |
| 211 | `type_annotation` has no anti-triviality gate **\*** | Small single-symbol work — plausibly floor-band material, not only pool completeness. C12. |
| 221 | How should we train the small models | The floor question itself. |
| 222 | Build the corpus the research calls for | Ditto. |
| 224 | Map the resolution band †**\*** | The floor instrument's calibration. Partly answered already; C1/C2. |
| 225 | Anchor material †**\*** | Ditto. |
| 61 | The offload doctrine (SKILL.md) | Where measured floor capability becomes product behaviour. |

### Ceiling-raising

| # | issue | why |
|---|---|---|
| 149 | Idle-RAM-optimized local models **\*** | A 30B-A3B MoE worker is P2's named ceiling class, by name. The issue does not say so. Correction C7. |
| 70 | v2 — source-side model swapping | A control plane that pays only where VRAM cannot hold the ladder; serves the large end. |
| 213 | Read the pool for clarity | Maintenance of a ceiling instrument. Its *criterion* transfers to #222; the reading itself does not. |
| 226 | Sweep the pool's Python arm | More whole-problem pool exhaust. The issue already reached this verdict itself. |

### Neither

| # | issue | note |
|---|---|---|
| 3, 4 | E0 / advanced baseline profile | Repo hygiene; #4 gates the release cut. |
| 40, 41, 42 | E6 verification, verdict parsing, fresh context | Assurance, not capability at either end. |
| 53, 54, 55, 56 | E8 — delivery | How accepted work survives the sandbox. |
| 57, 58 | E9 — telemetry, per-task record | Product-side recording. |
| 59 | Value-per-token rollup † | Tests CLM-0003; attributing escalation cost to the failing rung is a floor measurement in disguise. |
| 60, 62, 63 | E10 — packaging, install, activation modes | Delivery of the skill. |
| 64, 65, 66, 67 | E11 — release cut | #66 is the natural consumer of this audit's corrections. |
| 68, 69, 72 | v2 — `/command` mode, energy accounting, more adapters | Deferred, and neither end. |
| 111 | E13 — calibration harness (epic) † | The instrument epic. |
| 118 | Vendored evidence and claim discipline | Records discipline. |
| 132 | A sampling frame for absence † | One number over a new frame. |
| 134 | Claims register vs its own schema | Records discipline. |
| 141 | Availability verdicts expire | Dormant until a long-lived process exists. |
| 152 | Re-verify the retry-rescue figure **\*** | Evidence hygiene — but the default it justifies is a floor/ceiling choice. C6. |
| 171 | REC-01 flags a citation repair | Upstream rule design. |
| 204, 205, 206, 207 | Test-witness findings from #201 | Assertions that check a product number against itself. |
| 217 | A dispatch error occupies its cell **\*** | Rig defect — and a precondition for every sweep this tree will run. C11. |
| 219 | Fine-tuning in or out **\*** | Design survives; target and eval set are dead. Correction C4. |
| 220 | This audit | — |

## Corrections to landed decisions

Per #220's third acceptance item. Each is stated here rather than folded silently
into the issue it affects.

**ADR-0017's consequence "a floor instrument has to be built" is wrong as
written.** It says *"Nothing in the repo can currently measure a small model
getting better at work mcgyvr would actually hand it."* Two 20-task contract sets
measured on the 3B in the 35–65% band do exactly that, at low power. The ADR was
right that the *pool* is a ceiling instrument and right that the project had been
measuring the wrong thing; it overshot in concluding nothing existed. What is
actually missing is **power and coverage**, not the instrument. The amendment is
recorded in the ADR itself.

**#189's verdict remains unresolvable, not negative** (established by #219, and
not disturbed by this audit). #190 inherits it as settled and is corrected in C3.

**The `attempts=1` default was taken under ceiling-first reasoning.** "Escalate
rather than retry" spends the dearer rung the moment the cheaper one fails. That
is the ceiling-first choice by construction, and the figure justifying it (2 of 35
rescued) is inherited from local-ai and has never been re-verified here (#152). It
may well be right; it has not been decided under P1. Recorded on #152.

**#220's own starting list was incomplete**, which it said it would be. It named
#219, #190, #197, #162, #119, #113, #17/#216, #158, #173. The audit adds #16, #71,
#81, #126, #149, #152, #179, #198, #211, #217 as issues whose text conflicts with
P1–P3 or whose priority changes under them.

## The conflicts, and what settles each

**C1 — The floor instrument exists.** Stated above. ADR-0017 amended; #224's item 2
("the band is unmapped for Python entirely") is factually wrong and is corrected on
the issue; #225's "check what exists before generating anything" is redirected to
start in-repo rather than at MBPP+.

**C2 — The Python half of that instrument is unreachable by the measurement rig.**
`TIERS = ("d1", "d2", "d3")` and all three are JS/TS. `bundle.PYTHON` already
exists as a `Language` and the rig already uses it to serve `pool-py`
(`tools/breadth/measure.py:207`), so exposing the Python bundle set as a tier is a
name in a tuple, not a mechanism. Filed as a new issue.

**C3 — #190's acceptance names the instrument ADR-0017 rejects.** Its "Done when"
requires measurement "through the same front door as the pilot (EvalPlus on served
quant, +3pp gate)" — underpowered at n=164 (MDE ~+4.8pp) and contamination-prone
after fine-tuning in Qwen2.5 bases. Its sequencing behind #189 also inherits an
empty verdict. Both recorded on the issue.

**C4 — #219 still reads as live.** ADR-0017 supersedes its tune target and eval
set, but the issue body still specifies "the pool, both languages, held-out
problems only." A reader arriving at #219 gets the dead design. A superseded banner
is added, naming what survives (null calibration first, paired and interleaved on
one backend, a pre-registered UNDECIDED box, the MDE arithmetic).

**C5 — The blanket block is itself a ceiling-first sequencing error, and it is the
largest one this audit found.** Five nodes now block all 64 remaining issues.
Frozen behind them are the cheapest floor raises in the tree:

- **#198** (prompt assembly) — needs no band and no rig-time corpus, because its
  instrument is the very set C1 describes. One line of prompt was worth +4 tasks
  in 20. It costs nothing at inference and ships to every rung and backend at once.
- **#81** (deterministic tier) — zero tokens, no measurement dependency, open since
  founding.
- **#168** (JS/TS bundle) — a decision, already measured, ~386 prompt tokens per
  request either way.
- **#126** (target granularity) — narrowing a worker's view from file to symbol
  attacks the whole-problem-ceiling gap ADR-0017 identifies, and needs the band
  only to *size* the effect, not to decide the design question.

P1 says a floor raise beats a ceiling raise. It does not say a floor raise must
wait for a floor *measurement* when the change is cheap, reversible and shipped to
every rung. Holding these behind ~10h of rig time prices them at zero for as long
as the chain takes. **Recommendation, for the owner: unblock #198, #81, #168 and
#126 from the tree** — keep #221/#222 blocked, since those genuinely consume the
band. Not actioned unilaterally; the tree's dependencies were the owner's call.

**C6 — `attempts=1` is a floor/ceiling choice, not bookkeeping.** Recorded on #152.

**C7 — #149 is ceiling-only and must say so.** P1: "an issue that raises only the
ceiling says so in its own text." A 30B-A3B MoE worker is P2's named class, and
the issue's success criterion is a task-acceptance improvement from running one.
Its serving half also belongs to local-ai, not here. Recorded on the issue.

**C8 — The cap formula is fitted on one worker.** #216's 1151/805 per-type
percentiles came from 14B TypeScript alone; P3 makes that incomplete until it is
shown to transfer or made tier-aware. New evidence the audit can hand it: the
floor probes recorded the 3B's max completion tokens per rung — `d2` **338**, `d3`
**818**, `d1` 2048 with a single runaway — so a small worker's output distribution
is visibly not the 14B's. Recorded on #17.

**C9 — Three issues allocate work across tiers without naming which tier is the
floor.** #162 (routing matrix), #119 (sampling breadth) and — not on #220's list —
#16 (risk floors). P3 requires the floor tier to be a parameter in all three.
Recorded on each.

**C10 — #71 is floor machinery filed as v2 hardening**, and the evidence cuts both
ways. Malformed output is a small-model failure mode, which promotes it under P1;
but #212 found that what reads as a parse refusal is usually the output cap, not
the reply format, which demotes it. Both stated on the issue so it is priced on
evidence rather than on category.

**C11 — #217 gates every sweep this tree will run.** A `dispatch_error` row
occupies its cell, so a resume can never fill it, and a holed run is publishable
and citable today. #225, #224 and #226 all put rig time through `measure.py`. This
should not sit behind an audit that costs no rig time. Recorded on the issue and
included in the C5 recommendation.

**C12 — #211 may be floor-band material generation.** A `type_annotation` problem
is small, single-symbol work — plausibly nearer the band than the pool's median
60-line reference. Its anti-triviality question stands on its own, but #222 should
know the type exists as a candidate shape. Recorded on both.

**C13 — #50 has landed, so decomposition can be tested against P1 now.** #50
(decompose a prompt into contracts) closed on 2026-08-03. #221 rejected "measure
the pool through the pipeline" on four objections and closed with: *"It remains a
reasonable way to measure whether decomposition raises the floor, once #50
lands."* That precondition is met. P1 names decomposition as floor machinery in
exactly the same sense as weights — so "does decomposition raise the floor?" is
now answerable **without training anything**, which makes it the cheapest test of
P1's central claim available. Recorded on #221 as an input to its recommendation.

## What this audit did not do

It did not re-open closed decisions except where a landed verdict was taken under
ceiling-first reasoning, which is the correction list above. It did not change any
issue's dependencies — C5 is a recommendation, not an action. It did not measure
anything: every figure here is quoted from a record already in the repository.
