# Synthesis notes — #302 trunk review (pinned main 4e110156)

Working file. Facts distilled from maps/ + my own doc reads. Each fact carries its source map.
Deliverable defs: TRUNK = instrument+ground+process. DoD = trustworthy bench (same identity, one changed param, known resolution).

## A. The state in one paragraph (draft)
Every part of the instrument exists; commissioning is 5/6 done but holds on ONE cell only
(bench-ts@1.5B); the round pin is refusing all dispatch (tree moved off r1, 17 files); the
library's pipeline (route/escalate/dispatch) has no production caller — the bench IS the product
today; identity is defined once (identity.py: 27 fields, KEY=11) with 23/27 writers but the
admission machinery (#276 bound_flips) unimplemented and the guard protecting only report.py.

## B. Load-bearing facts (identity-deep)
- Identity defined ONCE: tools/bench/identity.py GROUPS 27 fields/4 groups; KEY=11; PENDING=15 w/ reasons.
- 23/27 fields have writers; missing 4 = #286 observed-block probe set (quantization, context_length, concurrency, seed). Observed block: NO writer, NO file.
- require_comparable guards ONLY report.py. gate_rescore/lintless/ablation_report/control/responsive print figures UNGUARDED. rounds.json doctrine clause 4 overpromises.
- Round pin REFUSING NOW: tree efadd362 vs r1 pin ed508e61, 17 files moved. No bench dispatch until r2 opened --adopted (drained boundary, ADR-0032).
- #287: two drift-check satellites remain (breadth resume own-dict one-directional; bundle guards 2 fields not in contract). identity.drift() written+tested, called by NOBODY.
- bound_flips admission formula (#276): pre-registered, implemented by NOTHING → no perturbation can admit the 6 new digests to KEY.
- Model probe success path NEVER run against live ollama (stubs only — ADR-0033 admits).
- accept.py (per-task grader) outside tasks_sha256 → grader mutable w/o record. UNOWNED in fan-out. (identity-surface §3.1)
- BOUND_MATCH_PENDING=('cells') enforced by nothing; 1.47pp@257 applied to 34-cell subset ~7x too strict (10.15pp honest).
- TWO ADRs both numbered 0035 (#262 bar-as-content; #301 bar-word-ban). All 10 code cites mean #262's.
- identity.py INTERNAL contradiction: :147 comment says 328 ruff rules; :648 docstring proves 250.
- identity.py:629 cites score.require_toolchain — doesn't exist (it's require_rungs at score.py:486 / require_toolchain lives in gate_rescore.py:148).
- External load-bearing claims w/ NO in-repo artifact: '76pp prompt effect', vLLM #23138 greedy nondeterminism. Cited in 4+ docs.
- Manifest counts: 6 verified / 126 backfilled / 4 no_fingerprint of 136 (reproduced live). report.py:23 says 139 — stale.
- ADR-0027 D5 headline describes END-STATE (whole block minus contrast); today's KEY is 11/27. Don't quote D5 verbatim.
- User's 2.6 model: right spirit; 4 refinements (see identity-deep notes ANSWER 4) — keyed-subset not all-27; contrast is named axis; prompt keyed within-condition; delta only quotable above ±bound.
- Sequencing: #286 + #287 (touch measure.py → move pin) should land BEFORE r2 opens. Pre-r2 cells never comparable with r2 cells.

## C. Load-bearing facts (bench-core)
- Commissioning #231: checks 1,3,4,5,6 met. Check 2 (positive control) holds ONLY bench-ts@1.5B (33→11, p=1.05e-5); INERT bench-py@1.5B (p=0.856) and both 7B arms (p=0.61/0.34). Mechanism: lint findings +124 @1.5B-ts vs +1 @7B-ts — norule control decays with capability. OPEN DECISION: control that survives above floor tier.
- 1.5B evidence base (null pair + norule control 2026-08-13) PRE-DATES round pin & digests → can never sit beside r2 runs without allow_unfingerprinted waiver.
- Corpus: 257 bench + 241 reserve (498 admissions, 2 retired via retired.json; superseded_by mechanism exists w/ 0 uses — two parallel withdrawal mechanisms).
- Eligibility: capacity levers live on 34 tasks/arm only (fn_impl + target_content). psi spread 0.029–0.134 (4.6x) across task types → pooling forbidden.
- Null: d=0/514 both tiers; acceptance drift 0. Bound ±1.47pp (Wilson d=0 n=257) × 4 (model,tier) combos.
- Enforcement present & firing: round pin, require_comparable (report.py only), mode.banner (8 tools + discovery test), require_rungs canary preflight, resume drift refusal, matrix load rules, admission battery.
- Enforcement gaps: admit.py --verify and product.py --check are HAND-INVOKED (no CI hook — searched Makefile+.github). superseded_by unused. resolution/eligibility key on labels, admit their own identity gap.
- Vocab collisions (verified): bar×2 (banned), arm×3, cell×3, tier×2, rung×2, STOCK×2.
- Cheap hygiene list: renumber ADR-0035 dup + audit cites; 328→250 in resolution.py:20 + responsive.py:17; 0.305 vs 0.1952 ceiling record discrepancy; report.py:23 139→136; superseded_by-vs-retired decision; ablation-sets.json '19 bug_fix' now 59 (stale present-tense).
- Rate card (#289): s/task per model×tier + 1.67min setup/pass; rates measured under r1 bar — re-derive across #261 boundary.
- Preflight non-negotiable: score.require_rungs before every sweep; `uv run --no-sync`.
- Families/#268 PAUSED by owner until emitter (#225) fixed. ablation-sets derived sets (analysis/strict) exist in prose only.
- ceiling 'every admitted problem' quietly means bench-half only (257×2=514; reserve never swept).

## D. src-library (from notification preview; full map on disk)
- State: partial. Every module works+tested (121 tests pass) but NO production pipeline: escalate()/climb() zero non-test callers; dispatch() zero non-test callers; nothing writes parse_reply() output to a file. #252's finding CONFIRMED at this tip.
- Only entry: cli.py, 12 inspect/scaffold subcommands. Only end-to-end loop in tree: tools/breadth/measure.py → score.py → Gate.run.
- decompose Proposer: no default binding; only RecordedProposer (replay fixture). No model-backed proposer exists.
- scope.py ReDoS CONFIRMED LIVE at this tip (12x '**/' pattern hangs >10s) — attacker-authored contracts hang the gate at load. (#248/#255 open)
- Docker sandbox + image cache: zero non-test callers (TempDirSandbox is the only mode used). open_sandbox zero non-test callers.
- risk field on 2,059 contracts read by no branch.
- Gate.run + GateResult.accepted (no findings AND no inconclusive rung — #261/ADR-0034 landed).
- Duplicate names in src: route.Verdict vs orchestrator resolve.Verdict (different things).

## E. Questions phase 2 must verify (adversarial)
1. Round-pin refusal + r2 procedure: reproduce product.py --check; enumerate the 17 moved files against the issues that moved them (drain list for r2).
2. Commissioning check-2 gap: re-read #231 acceptance vs control.py outputs — is 'ts@1.5B only' the full truth? What would a capability-robust positive control be?
3. accept.py-outside-digest: reproduce; assess blast radius (can a grader edit change past/future rates silently).
4. Unguarded readers: which published figures flowed through gate_rescore/lintless/ablation_report/control/responsive without require_comparable?
5. Corpus contamination guards: HumanEval/MBPP+ blocklists — can they refuse? (canary test?) Jaccard screen weakness (rewording only).
6. The 6-verified manifests claim + 1.5B-evidence-unmixable — confirm; what does that imply for r2 (re-run null+control at r2?).
7. ReDoS + crashed-linter + tier-map-dup: status at tip (fixed by #261/#259 or open?).
8. Tests: which trunk guards have no test / cannot fail?
9. External claims (76pp, vLLM) — mark as unverified doctrine inputs in report.
10. What did #243 (trunk exit gate) decide and does it overlap #302's plan?

## F. Facts from my own reads (docs)
- bench-design-2026-08-10: split rule blind-by-construction; campaign order Phases 3-4 (pilot→gate→pin→declare→calibrate→strata→refill→~800 problems→every stratum's 3B rate with n; ≥1 stratum interior or re-aim). Cap 2048. Reserve never swept.
- identity-surface-2026-08-16: the 5 demonstrated defects (accept.py digest; user-msg outside digest [now: prompt_sha256 landed via ADR-0033?]; crashed linter [fixed by #261]; round pin not covering bar [fixed by ADR-0032 surface widening]; manifest-digest≠weights-digest). Wilson math. 'Store the surface, not a selection.'
- four-lens-audit-2026-08-14: rung declarations vs emissions (2/9 literal); gate_rungs in 2/30 bench manifests; norule runs behind ADR-0026 evidence NEVER COMMITTED; twin-constant population 12 couplings/4 disagreeing; checks test_four_lenses.py exist w/ canaries.

## G. ADR enforcement (adr-enforcement map)
- TALLY: 15/36 machine-enforced w/ verified refusal (0002,0006,0007,0010,0011,0016,0020,0024,0025,0026,0027,0032,0033,0034,0035a); 10 structural-can't-refuse-drift (0001,0003,0004,0005,0008,0009,0014,0019,0023,0029); 11 enforced-by-nothing (0012,0013,0015,0017,0018-exc-Q3,0021,0022,0028,0030,0031,0035b). Dead letters naming unbuilt mechanisms: 0013 (family check at config.py:780 DOESN'T EXIST — refuted live), 0012 (no re-entry marker/cap/test), 0015 (verifier unbuilt).
- Amendment graph one-directional: back-pointers only on 0005+0025; 0016,0017,0018,0019,0021,0024,0027 amended w/o Amended-by header. Nothing ever marked Superseded. No ADR index. No numbering check (0035 collision merged green CI).
- Figure drift chains: '328 ruff rules' in 0026,0027,0032,0033 (refuted → 250 by 0035a); 'Eleven of twelve' in 0019(corrected),0020(uncorrected),instruments.json breadth-d2 retired.why (STILL WRONG — correction named the field and never applied); 5pp never a decision (#299); ADR line cites rot (contract.py:862→916).
- ADR-0019 D2 fitness gate + D4 EFFECT/NULL/UNDECIDED taxonomy: PROSE ONLY, no code emits UNDECIDED. #299 shows UNDECIDED→zero conversion already happened once.
- Every correction in 0017/0019/0020/0021/0022 caught by re-reading, never by a check (0026 says verbatim).
- Merge protection ADR-0002 live+verified (ruleset 20186295 active, bypass empty).

## H. Issues tracker (issues-tracker map) — THE PLAN SKELETON
- Classification of 92 open: TRUNK 33 / LEVER 14 / v2 5 / BASELINE 3 / OTHER-v1 37.
- ACTIVE trunk working set: #224 #225 #231 #243 #248 #254 #255 #256 #257 #258 #259 #263 #267 #268 #269 #271 #272 #277 #280 #286 #287 #288 #295 #302.
- Parked trunk (bind by default): #111 #118 #132 #134 #152 #171 #207 #211 #213 #226.
- GAP LIST to DoD: positive control 1/4 cells (#231/#225 — nointerface candidate UNCHOSEN, #267 fallback); canary proves 0/5 declared rungs (#258); #269 thin-acceptance vs precise-instrument indistinguishable in null; corpus defects (#295/#268: 5 containment families + 3 weak acceptances) BAKED INTO commissioning's met checks; rejected_by understates 6.7x (#257); stats defects (#263, #271 m>=6 wall); parser mislabels legal fences (#254); scope fails open + ReDoS (#248/#255); identity fan-out half-done (#286 #287 #288, digests AWAITING_ADMISSION); ESTIMATE_RESERVE pooled (#256).
- UNMADE DECISIONS needing owner: (1) adoption-bar per lever class (nobody owns; #224 sizing blocked on it); (2) positive-control route above floor; (3) psi_draw fate #272 before S1/S2 rig time; (4) family/weak-acceptance rulings before r2 (#295); (5) ADR-0035 renumber; (6) r2 drained boundary.
- Stale-substance bodies: #268 (title 'six families'), #246 (eslint claim false), #207 (partially), #286 (#285 landed), #231 (amendments stop 08-14), #224/#225 (top halves superseded by own feet). Blocker headers stale: #295←#262(closed), #256←#265(closed).
- Dependency spine: #295 unblocked NOW → gates 257→400 corpus growth + r2 dispatch rulings. #258 blocks #231. #272 blocks #224 S1/S2. #224 self-declared 'the binding constraint on everything'.
- Levers all quote 'after #231, against that round's pinned product'.
- Baseline REC-01 append-only: WARNS only (#171). test_claims.py: fails CI on citation pinning; schema itself NOT run (#134: 10/17 CLMs fail own schema — verified exact).

## I. History narrative (history-narrative map) — ELI5 BACKBONE
- ARCS: (1) Founding 08-01 (132 commits, ADR-0001..0016, successor to archived local-ai); (2) Measurement wave 08-04..08-08 (bundle-does-nothing, breadth, finetune +1.9pp, #197 499-corpus); (3) Floor 08-09 (ADR-0017/0018, corrected same day + #234 found 45/73 bodies stale); (4) Bench 08-10..08-14 (ADR-0019 bar, #240 retire rulers, #225 38-commit lane builds 498-problem bench, #113 harness, #249 four lenses, #231 commissioning); (5) Identity 08-15..08-17 (#266 #276 #265→ADR-0027, then 08-17 burst: 9 merges, 5 ADRs incl. TWO 0035s 70min apart).
- ALL history = 17 days (08-01..08-17), 283 commits. Last week: 21 first-parent commits; 14/19 lane merges corrective; ≥5 corrections-of-corrections; 08-17 8/9 corrective. Correction fraction RISING.
- DRIFT MECHANISM located: (a) issue-authoring figures nothing re-derives ('reproduces exactly'→false; exception never fires; 7-vs-8 retracted); (b) cross-lane parallelism over unversioned namespaces (ADR numbers, 'bar', task ids t01); (c) doc prose side-channel (5pp: conversation→quoted standard in 1 day); (d) same-day doctrine (0025 premise withdrawn same day; 0027 amended 14h after merge). Orient works; review is rubber-stamp at 103k-line squash scale.
- Near-colliding denominators: 498 (admissions) / 499 (#197 pool) / 514 (refs=257×2) / 257 (gate-passing problems). Nothing but reader care distinguishes.
- Session protocol: lane branches, append-only session records, 'next:' line = plan-of-record between sessions, orient reads it. 92 lane dirs. Records layer itself ungoverned (no code reads docs/decisions/).
- make-check green claims (1629 tests @lane/262) NOT re-run by reader — plan step 0: clean make check at tip.
- ADR Date: = authoring date, not landing date (0034 dated 08-16, merged 08-17).

## J. Claims plane (claims-plane map)
- 17 CLMs; all cited in-tree artifact paths EXIST; 5 headline recomputations (0004,0007,0012,0013,0017) match EXACTLY. Register discipline real; sync not enforced (no recompute mechanism).
- #134 nuance: gate DOES run schema; validate.mjs:40 skips '_' keys (dialect). Cheap fix: declare '_' convention in schema (patternProperties ^_). 10/17 fail strict draft-07.
- Register STOPS at CLM-0017 (2026-08-07); entire bench era (08-10→08-17) UNREGISTERED. Fine-tune lever has NO claim (only finetune-pilot summary: +1.9pp miss vs +3pp bar).
- CLM-0001/0002/0003 external-only cites into ARCHIVED local-ai repo — not re-verifiable from tree. CLM-0003 = the one EXISTENTIAL claim (offload premise), assumed-unmeasured, de-risk = v1 telemetry (doesn't exist).
- Claims edited in place (CLM-0012 by #167, CLM-0013 by #121/#196) — pin by git blob if quoting.
- Stale consequence sentences: CLM-0013/0014 say '#119 ships breadth' — #119 OPEN, no breadth in src/.
- CLM-0013 model identity self-contradictory (Q3_K_XL tag vs Q4_K_M reported vs 33.8GiB blob).
- CLM-0002 hedge stripped by capability-table CAV-01 (restated as severity-critical fact).
- Capability table: archived-repo provenance, no regeneration script, no schema; in-code structural checks only.

## K. Measurements/evidence (measurements-evidence map)
- 139 run.json manifests (136 machine + 3 hand-authored excluded by shape). Tag reproduction: 6 verified / 126 backfilled / 4 no_fingerprint EXACT.
- ZERO manifests carry model_sha256/bar_sha256/prompt_sha256/quantization/seed — writers landed post-every-run. FIRST new dispatch exercises them → schedule shakedown null early.
- COMPARABILITY GROUPS: (1) fully comparable nucleus = ONLY the six 7B arms 2026-08-14 (control-norule-7b + null-gate-7b-a/b); (2) 1.5B 257-family comparable w/ waiver, no round; (3) internally-comparable-externally-orphaned (f1 family, srv1 3B, mbpp, finetune, breadth); (4) orphaned outright incl. claim-load-bearing jsts-bundle (CLM-0012), python-bundle (CLM-0017), breadth (CLM-0013); (5) README contrasts the doctrine now REFUSES: scaffold 3B-vs-7B cross-rig, pool 7B-vs-14B cross-rig+cap, pool-sweep ts-vs-py cross-rig.
- srv1 serving build NEVER machine-recorded (0.32.4 = prose only) → srv1 rates permanently locator-grade (ADR-0024).
- pool-sweep-14b README headline contrast crosses rigs w/o caveat; 47 cap-truncations mislabeled refusals at 768.
- Superseded 08-12 nulls still read by tools/power/report.py (two tools disagree on liveness).
- 2026-08-12 null partials + pool-probe + f1-all near-orphans.
- Planner leverage: 'one changed parameter' achievable today only inside group (1) or by new dispatch; bounds honest only at cells=257 (D9); r2 must drain ALL identity changes; srv1 = capacity only.

## L. Problems/corpora (problems-corpora map)
- b430 weak acceptance REPRODUCED live (plain sorted() passes accept.py). 3 weak acceptances live in measured bench-py rates.
- Quota violations, enforced by nothing: f1 band 0/109 fn_impl-with-target_content (quota >=1/3, emitter CAN'T write that shape); g0a/g0b 0% multi_symbol (quota >=25%). --cells is a printout.
- Jaccard screens read TS-arm prose ONLY; py arm never screened; no cross-arm prose check.
- emit-time screens (divergence, skeleton .70) postdate g0-g4 problems (b001-b227 era) — never re-run at admission.
- 208/498 manifest entries carry 'amended' in-place edit (ADR-0023 checker repair) — append-only doctrine has a used escape hatch; pre-08-11 runs' tasks_sha256 no longer match tree.
- #295 body PARTLY WRONG: bench admit.py HAS declared-target anti-triviality since d3e5dd04 (its real point: stubs can't catch stand-ins). NOTE: this map says '#262 open' — CONTRADICTS other maps (closed). RESOLVE IN PHASE 2.
- 'Blind split' provable only from lane history (2489af9b before 9c3cbf16); main squash can't show it.
- Campaign arithmetic: target ~800/400; today 498/257. Growth blocked behind #295 rulings + #225 tranches.
- bench-design doc stale: 30s ceiling (now 120s), 3B calibration (floor now 1.5B), ~800 unreached — no amendment blocks.

## M. Tests (tests-reader map)
- FULL SUITE RUN AT TIP: 1630/1630 pass, ~8.5min. Honest suite (hunted tautologies, found none that can't fail).
- Untested trunk-critical (ranked): (1) tools/bench/resolution.py — THE resolution artifact, label-keyed, zero tests; (2) tools/breadth/campaign.py; (3) regrade.py (rewrites rows in place); (4) bench admission execution path.
- Static-only checks (weakest links): mode.declare substring; ci.yml text grep; ceiling summary pinned NOT recomputed from 32,601 rows; split goldens all map to 'bench' (none reserve).
- identity mutation-refusal tests per KEY field with self-coverage guard = the strongest pattern; test_four_lenses = the check template (registry+property+canary).
- ~20 by-path import slots across tests = internal duplicate-definition drift, managed but real.

## N. Support plane (support-tooling map)
- What a red build catches: ruff lint+format; mypy strict src+tests ONLY (tools/ untyped); docs-check; pytest twice; baseline blockers (BUILD-05). Ruleset 20186295 live, no bypass, but 0 human approvals required.
- make check WEAKER than CI (no docs-check, no baseline gate) — 'everything CI runs' comment false.
- docs/decisions read by NO code — ADR namespace ungoverned (how two 0035s merged green).
- eslint/prettier configs NEVER run on repo's own JS; package.json has no scripts.
- REC-06 vendored-baseline pin = warn only; effectively nothing refuses a baseline-engine edit.
- wire.py/body.py operator-run only; nothing compels them; bodies drift freely between manual runs.
- Most load-bearing unverified support number: #229's 'at n=20 no effect size reaches 80% power' (justifies retiring ALL local sets). PHASE 2: derive.
- gitleaks pre-commit opt-in; absent from CI.

## O. Measure-adjacent (measure-adjacent map)
- tools/breadth/measure.py IS the bench sweep engine (docstring still says #121 breadth) — biggest naming drift; classify-by-name plans will misfile it.
- 23,902 (lane/282 session) vs 23,767 (golden.json + disk, verified) — 135 replies unaccounted. PHASE 2.
- ESTIMATE_RESERVE=0.32 tied to CLM-0011 by comment only... BUT tests-reader says test_estimate_reserve_is_derived exists (four_lenses:429/444). CONTRADICTION — probably the test landed with #251; measure-adjacent's grep missed it. RESOLVE PHASE 2.
- power/report.py run lists hardcoded — new runs silently absent from recomputation.
- d1 = three things (retired tier, bundle tasks byte-identical, finetune source of 622/738 #189 examples).
- bundle rig half-live: library imported by breadth; sweeps refused; README still documents runnable sweeps.

## P. Docs/prior-art (docs-priorart map)
- Correction-discipline ASYMMETRY: identity-surface/what-a-tune/floor-audit/test-witness/identifier-naming carry dated in-place corrections; four-lens-audit + bench-design (the two MOST-CITED) do not.
- Four-lens 3.2: 'CONFIRMED, exactly' 328 → refuted to 250. Lesson: verification reproducing the original method reproduces the original error.
- identity-surface residue OPEN at tip: accept.py outside tasks_sha256; ablate() transforms contract AFTER tier_digests hashes disk form (contract-stage levers invisible to tasks digest; prompt_sha256 covers as-sent going forward); gate_rescore/lintless outside SURFACE; cells unenforced; srv builds last probed 08-16.
- ADR-0028..0031 = rejection records (do-not-build) — absence is the enforcement.
- #277: capability.py:174 still orders ladder by retired humaneval_plus_pass1 (routing on a retired ruler).
- Prior-art digs declare expiry/re-check discipline (90d in baseline.config) — no mechanism, no re-check ever recorded.
- Only resolving stratum today: (1.5B, bench-ts, function_implementation).

## Q. src-library full (src-library map)
- #252 CONFIRMED verbatim at tip: no attempt callable, no Proposer binding, no parse_reply consumer in src. Library = tested policies with no executor. Bench harness = the only code that runs models.
- BENCH-USED src surface (freeze list): gate/* minus semantic, scope.py, contract.py, worker/*, runner.py (Request/runner_for), pool Endpoint/Protocol types, sandbox base+tempdir, orchestrator/read.estimate_tokens, prompts/*.md. NOT bench-used (ignorable): route, escalate, capacity, availability, propose, initialize, detect, docgen, catalog, semantic*, docker/image/stack, orchestrator rest.
- Live reproduced defects ON the measurement path: scope.py ReDoS (12x '**/' >10s hang, reproduced); reply.py:100 info-string misdiagnosis ('```python:sol.py' → unterminated-fence) — contaminates #17's 47-refusal taxonomy. Both reported by #252 4 days before tip, unfixed → evidence issue tree not consumed.
- attempts default contradiction: contract Limits.attempts=2 vs config tier attempts=1; route takes min → effective 1 always.
- decompose sized to 32k input vs measured 4,096 served context (#158 open).
- 'Wire the pipeline' = exactly one function (attempt(Try)→Judgement); breadth/measure.py:636-666 + score.py:299-335 is the reference implementation minus judge.
- Duplicate names systemic: Rung, Proposal, Verdict, runner.py, Acceptance, families.

## R. PHASE 2 VERIFICATION RESULTS (verify/ dir has full detail)

### r2 drain (verify/r2-drain-list.md)
- 17 moved files = exactly 5 merges: #291(ADR-0032 surface widening), #261(crashed linter), #285(ADR-0033 digests), #262(ADR-0035a bar-as-content+prettier), #275(dependabot ruff bump — first live instance of 'a dependabot bump closes a round'). #265 NOT in batch (read-time only).
- Exact open command documented (product.py --open r2-<name> --opened --issue 231 --why --adopted ×N).
- MUST land pre-r2 (touch SURFACE): #286, #287, accept.py-into-digest (NEEDS NEW OWNING ISSUE — also repairs product.py:59-61's false exclusion premise), config.Tier docstring (identity.py:259 defers it), nointerface lever (matrix.json/py in SURFACE — from control-options).
- Defer/decide: #288→option 3 (no move, generated index, zero surface); gate_rescore/lintless into SURFACE = now-or-r3 decision, one sentence; D9 cells = read-path UNLESS cells becomes recorded field (then runners → pre-r2); ADR renumber = renumber #301's→0036 (all 6 code cites mean #262's), zero blast.
- Tree un-dispatchable since 2026-08-17 anyway → batch aggressively, only calendar cost.
- Surface 56→64 files; 7 of 17 'moved' never changed bytes (joined digest).

### Commissioning (verify/commissioning-verdict.md)
- '5/6 done' = honest bookkeeping, stale state: checks 3+6 are MACHINERY (survive rounds); checks 1,2,4,5 are MEASUREMENTS bound to dead r1 (#276 comment VOIDED both declared bounds). Re-purchase at r2: 4 null pairs = 2.33h + 1 norule pass ts@1.5B = 17.7min ≈ 2.6h total (control's stock arm IS null run A — amortized).
- Corpus defects = caveat not invalidation: bound moves 1.473→1.519pp w/o the 8; realized false-pass inflation ≤0.39pp (only b430 passed); ts@1.5B control survives worst-case deletion (26/6, p=5.4e-4).
- #269 = genuine gap vs #231's preamble ('fit for purpose') though in-scope-honest; fix = mutation score as SEVENTH commissioning check, model-free, CPU-only.
- #258 honest fix = hybrid: canaries for scope+secrets (reachable-but-silent), recorded 'structurally unreachable' for structured (would need corpus change), keep GATE_RUNGS STABLE (shrinking re-keys → voids all four bounds — hidden cost nobody priced).
- #272 S1/S2 (6.4-11.4h) NOT commissioning; premise invalidated; decide on committed data first.
- ts-vs-py contrasts carry acceptance-rung confound (ADR-0023 clause 4: 104/257 py checkers ValueError-only vs ts Error) — 'two instruments, not a language axis' (owner correction on #231).

### Control (verify/control-options.md)
- RECOMMEND: nointerface at ALL FOUR cells (~2h20m rig), matrix lever ~15 lines (SURFACE→pre-r2), pre-registered mechanism = acceptance-rung effect (adapter-rung effect = norule again, doesn't count); known risk: 99.2% of prose names the function → 7B may null; INTERFACE carries param/return shape prose doesn't.
- RUNNER-UP: anonymise #267 (strongest published prior; ~2.5x rig + biggest build incl. staged accept.py unreachable by ablate today; random-string headline; bug_fix sign-flip risk #270).
- PER-CELL COMMISSIONING IS ALREADY OPERATIVE DOCTRINE (owner-approved #231 amendments ×2: py@1.5B and both 7B 'not quotable'). Floor py arm as uncommissioned as 7B; ADR-0021 binds bench to floor → control must recover on all 4 cells or floor stays half-dark.
- 'Uncommissioned = not quotable' has ZERO machine enforcement → REQUIRED: commissioning registry (commissioning.json keyed model×tier, read by figure tools, discovery-test enforced).
- ERRATA: #225/#231 amendments misquote m=40(34/6); truth: ts m=26(2/24) p=1.05e-5; m=40(5/35) is pooled p=1.38e-6. ADR-0018 Q3 stale twice (names corrected CLM-0017 effect; ignores 3-of-4 null).
- nostop disqualified (plausible no-op); nolocate not recommended (prose surgery on 118 contracts, moves tasks_sha256); #246 excluded (bar effect).

### Retirement (verify/retirement-premise.md)
- ADR-0020 retirement SURVIVES adversarial re-derivation (0/12 rejected, min p=0.070; n=20 resolves nothing <+40pp; n=12 <+67pp). Training release NOT contaminated.
- 'Eleven of twelve' stale in 3 places: ADR-0020:35 (needs 2nd Correction), instruments.json:70 (knowingly left; ADR-0019 chose live-tool-authority), lane/229 session record (history, leave).
- Correct figures for restatement: 9/12 structurally unresolvable; 3 resolvable (p=1.000/0.453/0.070).

### Stats (verify/stats-defects.md)
- Resolution ground truth TODAY: 1 of 12 tier×arm×stratum cells resolves — 1.5B/ts/fn_impl: psi=.134, m=22, MDE 8.5pp. All figures re-derived live.
- 257→400: resolving stratum 8.5→6.7pp (1.27x); 5 newly resolve (3 solidly at 3.9pp — the fn_impl cells; 2 marginal); SIX stay unresolvable; 'seven strata at any n' DOES NOT REPRODUCE (required_n finite 58-272 everywhere) — restate.
- #263: item1 CONFIRMED unfixed (greedy+sampled pooled — ablation m/p contaminated); item2 CONFIRMED ~12x narrow CI (conclusion survives); item3 SOLVED = same function, two denominators (800 superseded vs 426; responsiveness.py ships superseded).
- #271: wall in 3 places + 2 significance impls; mid-p flips NO committed verdict; paper decision + consolidation.
- D9: enforcing breaks BOUND_MATCH⊆KEY invariant; two resolutions; cells-as-recorded-field touches runners→pre-r2 if chosen. #289: enforcement cost ~zero.
- Adoption-bar: NONE set (confirmed). Class R adoption-bar IS the MDE (no owner number needed!); Class O needs exchange rate; Class W needs b + replication. Decisions needed only when those lever classes run.
- psi_draw=0.659 must NEVER size anything.

### Process (verify/process-mechanisms.md) — check specs (a)-(g), all verified buildable
- (a) cite.py issue-body citation checker → reconcile-cron source. (b) test_decisions.py ADR uniqueness (canary'd; must land WITH the renumber or arrives red). (c) test_docs_thresholds.py comparative-threshold-vs-table check. (d) SAME_DAY_AMENDMENTS registry. (e) wire.py 'stale' subcommand → reconcile source. (f) bidirectional-amends test w/ seeded allowlist (~11 edges) + GENERATED decisions INDEX.md via docgen path (hand-maintained would trip CTX-12). (g) test_doctrine_has_a_home.py (≥3-file-cited issue# must have ADR or registry entry; seeds #243).
- ADR-0025's Amended-by ALSO stale (misses 0035a) — even the maintained back-pointer rotted in a day.
- reconcile cron (OPS-07) = ready-made home for forge-side checks; baseline severities static per vendored rules file (REC-06-pinned path for promotions); CTX-07 warn→blocker after allowlist drains.
- Declared residual risk (lane/266): doc→spoken-summary escalation uncatchable by tooling — STATE it, don't promise it away.

### Rig (verify/rig-reality.md)
- BOTH RIGS UP 2026-08-18: srv1 0.32.4, srv2 0.32.5 (matches doc). probe_model EXECUTED LIVE on srv2 for 1.5b+7b: all four digests, zero refusals — ADR-0033's 'first rig contact' contingency DISCHARGED. verbose:true confirmed load-bearing. qwen digests byte-identical across hosts. srv2 has 12 models incl 14b.

### Contradictions settled (verify/contradictions.md)
- #262 CLOSED (reader error); #295 blocker header stale.
- ESTIMATE_RESERVE test EXISTS and derives 0.32 from units.jsonl (measure-adjacent map was wrong).
- 23,902 vs 23,767 RECONCILED EXACTLY (rows vs stored files; jsts-bundle 160 rows no reply text; +25 retry files). jsts-bundle permanently outside byte-level reply re-verification.
- NEW DEFECT: acceptance-ceiling record self-contradictory FROM BIRTH: prose 0.305s (README, ADR-0035a:78,123, score.py:66) vs committed data 0.1952s; ratios 98x/393x should be ~154x/615x; ADR decision itself unaffected (rests on 28.718s, supported).
- '96 vs 99' and '139 vs 136': both right, different populations; '6 of 136' appears nowhere (phantom quote).
- #243 NEVER RAN (all boxes unchecked, no lane, unblocked since 08-13); #251 audit = 'partial down payment' only.
- ADR-0002 explicitly decides FOR 0 approvals — no contradiction with ruleset.
- 'refusal' terminology collision (parser vs model) in golden.json vs ADR-0031.

---

## Derivation status (2026-08-18, lane/304 — appended at commit; the notes above are unchanged)

This file is the review's working synthesis, kept for narrative context. Its facts cite the
review's conversation-side subsystem maps, which are not part of the record. The verified
subset lives in `verify/` — each claim there carries a VERDICT and an EVIDENCE line with its
in-tree re-derivation, and several synthesis figures were CORRECTED there. The rule for any
reader: a figure quoted onward is taken from `verify/` or re-derived from the tree; a synthesis
figure without a `verify/` counterpart or an inline in-tree source is a working note, not
evidence (lane/251's rule).
