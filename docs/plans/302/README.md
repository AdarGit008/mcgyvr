Current phase: P1

# The plan of record — main@4e110156 → trunk shipped (v2, post-red-team)

Status: **approved by the owner, 2026-08-18** (#302; DEC-1 ratified with that sign-off).
This directory is the plan's home. The conversation and review-notes copies are dead: a plan
living outside the tree is drift vector (c), and this document is amended the way a decision
record is — see the amendment protocol below. The trunk-review report itself (ELI5 narrative,
rationale, the 26 issue bodies) lands under docs/ at P5.2; until then #302 holds it.

Companions in this directory: `evidence/` (the review's verification reports, every figure
beside its derivation, plus its working synthesis) · `parked.md` (the frozen not-now set) ·
the phase issues on the tracker, which bind to this file's §-numbers and DEC-numbers by
reference and never restate them.

## Phase status

Definition-of-done checkboxes. The PR that completes a phase flips its box and updates the
`Current phase:` line — the file's first line, fixed and grep-able, so the session-start survey
can surface it. Item-level boxes inside §2 are ticked by each completing lane's PR.

- [x] **P0 — Anchor** (#304): the plan has a home under docs/plans/302/; the ADR namespace is
  governed (0035 collision resolved, `tests/test_decisions.py` refusing duplicates, generated
  INDEX.md); the first machine check landed.
- [ ] **P1 — The instrument's code**: all ten numbered SURFACE lanes merged in order; ends with
  the enforced freeze (dependabot paused, frozen-digest tripwire red on any SURFACE move).
- [ ] **P2 — Pre-dispatch gates**: mutation scores, standing-corpus screens, the rulings through
  ONE withdrawal mechanism, guards on every figure printer, the commissioning registry, and
  `bound_flips` — all off-SURFACE.
- [ ] **P3 — r2 opens**: derived drain list, shakedown, four null pairs + norule control,
  the nointerface campaign at all four cells, the §4 decision gate read, perturbation
  admissions, the r2 record written.
- [ ] **P4 — Trailing record & process work**: corrections at source, body refresh, process
  checks, remaining stats hygiene.
- [ ] **P5 — Trunk shipped**: the exit ADR; levers re-pointed at r2; parked set stamped;
  #302 closes with the report landing under docs/.

## Amendment protocol

This plan holds itself to the record rule it enforces elsewhere (ADR-0036 clause 4:
records are history):

1. **Corrections are dated appended blocks, never in-place edits.** A correction names what it
   corrects, the date, and the lane it rides.
2. **Reversing any DEC-n is a dated amendment carrying the owner's explicit sign-off.** No
   session reverses a DEC on its own reasoning; the amendment block quotes the owner's decision.
3. The only in-place edits this file accepts are the mechanical state flips named above:
   checkbox ticks and the `Current phase:` line, each by the PR that earns it.

## Vocabulary (pinned; the plan binds itself to run.json's senses — cite tools/bench/identity.py:254-264)

- **tier** = the served language arm as run.json records it: `bench-py` / `bench-ts`. The model-size
  ladder is always called **model** here (1.5B / 7B), never "tier".
- **commissioning cell** = one (model × tier) unit — four exist: 1.5B×bench-py, 1.5B×bench-ts,
  7B×bench-py, 7B×bench-ts.
- **paired-cell count** = D9's denominator: the number of (task × verdict) pairs under a bound
  (257 today). Never shortened to "cells" in this plan.
- **scoring-bar / adoption-bar** per ADR-0036 (#301; written as 0035, renumbered on lane/304 —
  the collision P0 resolved) — the bare word does not appear in this plan.
- **round** = one pinned product revision (rounds.json). r1 is dead; r2 is this plan's round.

## 0. Definition of done — six clauses, each with its enforcing mechanism named

**Trunk shipped** = the bench is commissioned on a live round and a comparison it produces can be
trusted. A trusted comparison is:

1. Both measurement rows answer and agree on **every field of `identity.KEY` as it stands at
   r2-close** (11 fields today; D9 and the #276 digest admissions grow it — bind by reference,
   never by count), measured inside one round. Enforced by `identity.require_comparable`, wired
   into **every figure-printing tool** (today: report.py only; P1.9 wires the two newly-pinned tools, P2.4
   the remaining three, with the discovery census extended so a new figure tool cannot ship
   unguarded).
2. Exactly one named contrast axis differs (default `condition`).
3. The quoted delta is read against the reproducibility bound declared for that (model, tier,
   scoring-bar, serving-build) **at the table's own paired-cell count** — D9 enforced read-side:
   the reader compares its table's denominator to the bound's, and on mismatch recomputes the
   subset bound from verdicts on disk (~zero cost, #289) or refuses. A recorded `cells` field
   alone does not close D9 (it goes green on D9's own 34-cell counterexample).
4. Both commissioning cells involved are **commissioned**: a recovered positive control on record
   in `tools/bench/commissioning.json`, where "recovered" is machine-checkable (acceptance-rung
   delta exceeding that cell's r2 bound under the consolidated significance test), banner on every
   figure tool, hard refusal on quoting an uncommissioned cell (explicit `--allow-uncommissioned`
   waiver prints what went unchecked — the D3 pattern).
5. The corpus's known defects are ruled on (the 8 from families.json plus anything the standing-
   corpus screens and mutation scores surface), through ONE withdrawal mechanism.
6. Each drift mechanism that ate the last week has a machine check — **including the round pin
   itself** (the mechanism that killed r1): a CI-visible round-integrity check, a freeze tripwire,
   and a mechanically derived drain list at open time.

**The commissioning gate for shipping is the floor:** both 1.5B cells must be commissioned
(ADR-0021 binds the bench's obligation to the floor unit). The 7B cells are measured by the same
campaign but may ship **dark** — registry-marked uncommissioned and refused for quoting — without
blocking the trunk. This reverses the draft's all-four-cells gate, which pre-committed the plan to
an r3 on its own most-probable branch.

## 1. The three laws

**Law 1 — the drained boundary (ADR-0032).** Every change to `product.SURFACE` lands before r2
opens, in one batch. The five already-landed movers: #291, #261, #285, #262, #275 (the dependabot
ruff bump — named in the round record as the precedent ADR-0032 predicted). #265 is NOT a mover
(read-time only — verified).

**Law 2 — the freeze is a mechanism, not a sentence.** P1's final PR: (a) pauses dependabot for
the uv ecosystem (`open-pull-requests-limit: 0`); (b) commits a frozen-surface-digest file plus a
pytest asserting `product.digest() == frozen` — any SURFACE merge after the freeze goes red in CI;
(c) the r2-opening PR deletes both and replaces them with the permanent round-integrity check:
while a round is open, a PR that moves the surface digest fails CI unless it carries an explicit
round-closing marker. The next dependabot bump becomes a red PR, not a silently dead round.

**Law 3 — serialized lanes.** One lane at a time, numbered order within a phase, next lane
branches only after the previous merges (four P1 items rewrite the same two files — parallel
lanes on them is drift vector (b) by construction). Line-number citations in this plan are
pinned to main@4e110156; inside P1, re-locate by symbol (`tier_digests`, `_FENCE_OPEN`,
`ACCEPTANCE_TIMEOUT_S`…), not by line.

## 2. The phases

### P0 — Anchor (1 session; no SURFACE) — #304, done

Goal: the plan has a home; the ADR namespace is governed; the first check lands.

1. - [x] Commit this plan + the evidence pack (synthesis, verification reports, with each figure
   carrying its derivation command) under `docs/plans/302/`. The plan doc carries: per-phase DoD
   checkboxes flipped by the completing PR; a dated-correction amendment protocol (owner signs DEC
   reversals); a one-line "current phase" field that `baseline orient` surfaces.
2. - [x] Renumber the vocabulary ADR (written as 0035, #301) → **ADR-0036** (all twelve code,
   config, and test citations of "ADR-0035" mean #262's ceiling record; renumbering the other
   way would edit two SURFACE files). Repair ADR-0025's Amended-by (the ceiling ADR was
   missing). Same PR: `tests/test_decisions.py` — number uniqueness + title/filename match +
   bidirectional Amends/Amended-by with a seeded allowlist (15 one-way edges — the draft's
   line-1 derivation counted ~11; the whole-field header read surfaced four more, correction
   recorded on #304) + SAME_DAY_AMENDMENTS registry; canaries per the four-lenses pattern.
   Plus a generated `docs/decisions/INDEX.md` from a **new off-SURFACE generator**
   `tools/decisions/index.py` (make target + generated_globs marker). `src/mcgyvr/docgen.py`
   is SURFACE — untouched.

### P1 — The instrument's code (all SURFACE work; 10–14 sessions; ends in the enforced freeze)

Goal: after P1, no known defect contaminates a row, identity doesn't lie, and nothing else needs
the SURFACE before r2. Sub-items land in numbered order, one lane each.

1. - [x] **#287** — both runners' resume-drift checks route through `identity.drift()`.
   DEC-9: `language`/`conditions_sha256` join GROUPS at this boundary (adopted line included).
2. - [x] **#286** — the observed block: writer in both runners; probe set (quantization,
   context_length, concurrency, seed); file beside run.json. (probe_model verified live on srv2,
   2026-08-18.) DEC-14: `serving_resolved_sha256` joins GROUPS and KEY on this lane (#358).
3. - [ ] **NEW issue — the grader joins the digest**: accept.py/checker bytes join tasks_sha256
   (breadth `tier_digests`; bundle equivalent); reference.py stays out, reason stated in code.
   Repairs product.py:59-61's false exclusion premise. Without it, P2's grader rulings would be
   silent re-baselines.
4. - [ ] **Scorer-path defects**: #254 fence info-string (+ one-time refusal-taxonomy re-read on
   committed candidates); #248+#255 scope matcher (fail-closed, linear translation); #259
   tier→language single source; #257 `fired_rungs` full set per row (keep `rejected_by`).
5. - [ ] **#256** ESTIMATE_RESERVE by model stratum (0.23 for the floor worker); derivation test
   updated.
6. - [ ] **#258** — canaries for scope + secrets (reachable-but-silent); a recorded structural-
   unreachability entry for `structured`; GATE_RUNGS unchanged (shrinking it re-keys `gate_rungs`
   and voids all four declared bounds).
7. - [ ] **The nointerface lever** (matrix.json entry + strip branch mirroring
   `strip_output_section`, ~15 lines + tests), pre-registration in the issue: recovery =
   acceptance-rung effect exceeding the cell's r2 bound; an adapter-rung effect is the norule
   mechanism again and does not count.
   **Plus the anonymise (#267) machinery, landed dormant**: matrix entry, staging reach for the
   accept.py site, renamed-reference self-check — no campaign, just the SURFACE bytes, so the
   fallback branch costs ~3.5h of rig instead of an r3. (The tree is un-dispatchable anyway;
   this costs only calendar.)
8. - [ ] **D9, full shape (DEC-3)**: `cells` (paired-cell count) joins RECORDED **and KEY** (the
   BOUND_MATCH ⊆ KEY invariant demands it — KEY grows 11→12, which is why §0.1 binds by
   reference); PENDING entry dropped same change; per-KEY-field mutation-refusal test extends
   itself (its self-coverage guard will demand it); absent-`cells` handling: refusal for
   cross-round comparison, tolerated for single-run row reads. Dated ADR-0027 amendment rides
   this PR. The read-side subset-bound enforcement (§0.3) is off-SURFACE and lands in P2.4.
9. - [ ] **Ride-alongs**: score.py:66 ceiling comment 0.305→0.1952; the config.Tier cross-reference
   docstring (identity.py:259's own deferral); **DEC-5**: gate_rescore.py + lintless.py join
   SURFACE — dated ADR-0032 amendment rides the PR, with the priced cost stated: a mid-round fix
   to either now forces r3 (accepted: they score, so their bytes are part of what a verdict means).
   Their require_comparable guard calls ride this same PR — once pinned, a post-freeze edit would
   move the pin, so their guard wiring cannot wait for P2.4 (which then covers only the
   still-off-SURFACE printers).
10. - [ ] **Freeze PR** (Law 2): dependabot pause + frozen-digest tripwire + the drain-list
    preflight script (diffs `product.py --check`'s movers against the batch the plan predicts).

### P2 — Pre-dispatch gates (off-SURFACE; 3–5 sessions)

Goal: everything a trustworthy r2 figure needs that doesn't touch the SURFACE.

1. - [ ] **#269 mutation scores** — the seventh commissioning check: acceptance commands vs
   mutated references, model-free, per-arm. Ships with: a pre-registered condemnation threshold;
   the bulk-ruling path (retire-only via the ONE withdrawal mechanism, DEC-12; fixes deferred to
   the parked growth epic); the recompute trigger — condemned > 15 ⇒ re-run
   bound/wall/eligibility arithmetic and escalate to the owner before r2 opens.
2. - [ ] **Standing-corpus screens** (the P4.2 slice whose customers exist now): py-arm prose
   screened (it never has been), skeleton screen run over the existing 257, cross-arm
   consistency. Findings feed the rulings.
3. - [ ] **The rulings** (#295's owed set): the 8 known + anything 1–2 surface, recorded through
   the one mechanism; erratum comments on #225/#231 (the m=40(34/6)→m=26(2/24) misquote) ride
   along.
4. - [ ] **Guards before figures**: `require_comparable` (or the shared guarded reader) wired into
   the still-off-SURFACE printers — ablation_report, control, responsive (gate_rescore/lintless
   got theirs in P1.9's pinning PR); discovery census extended so an
   unguarded figure tool fails by construction; D9 read-side subset-bound enforcement;
   resolution.py gets real tests + round/identity awareness (DEC-10 — not the caveat);
   responsiveness.py's superseded 800-cell denominator fixed; **#271 consolidation** (one shared
   wall/significance implementation — the registry's recovery criterion depends on it; exact
   conditional test kept, decision recorded).
5. - [ ] **The commissioning registry (T2.4 → P2.5, DEC-13)**: `tools/bench/commissioning.json`
   keyed by the run.json fields (model, tier); lands with zero commissioned cells (r1's ts@1.5B
   control listed as voided-by-#276); banner on all figure tools now; hard refusal wired into
   quoting paths with `--allow-uncommissioned`; recovery criterion encoded in the schema so
   entries are computed, not asserted. The all-uncommissioned window until P3 is expected and
   stated.
6. - [ ] **bound_flips** (#276's admission formula) implemented (identity.py, off-SURFACE).

### P3 — r2 opens; the instrument is re-commissioned (2–3 sessions + ~5–6h rig on srv2)

1. - [ ] **Open r2.** The `--adopted` list is **derived at open time** (run `--check` on the
   merged tip; enumerate movers via git log over `surface_files()` since r1's pin — the plan's
   list is a prediction to reconcile, never the authority; any surprise mover is batched, not
   deferred). Rig-freeze recorded: ollama versions + model digests pinned in the round record;
   no-pull/no-upgrade window declared for P3's span. **The triage rule goes in the round record**
   (§5).
2. - [ ] **Shakedown** — one small null slice exercises the full record path (first manifests
   ever to carry the six digests). r2 is explicitly sacrificial: a writer defect found here means
   r3 is the real round and only the shakedown slice is lost. Then: **four null pairs** (~2.4h at
   r1-card planning-grade prices) + **norule control on 1.5B×bench-ts** (~18min; its stock arm is
   null run A). Bounds re-declared from r2 nulls at their paired-cell count; rate card re-derived
   (r1 prices don't transfer across the #261 gate change).
3. - [ ] **The nointerface campaign** at all four commissioning cells (~2.3h incl. stock passes
   that double as the floor's first round-stamped comparators). **Decision gate before anything
   else is spent**: per-cell verdicts computed against the registry's criterion, then the
   pre-signed outcome table (§4) says what happens. Registry updated per cell.
4. - [ ] **Perturbation admissions** (#276): the digest fields whose perturbation needs no new
   dispatch (bar_sha256 via re-score under a varied staged config; prompt_sha256 via render
   variation) run first at ~zero rig cost; model-digest perturbations (quant/template variants)
   priced from the r2-re-derived rate card, ceiling 2h — admit what clears bound_flips, record
   what doesn't.
5. - [ ] **The r2 record**: per-stratum resolution statement through the now-guarded, now-tested
   reader; claims register catches up (CLM entries: r2 null + bounds, recovered control(s),
   acceptance ceiling, resolution statement — the register currently stops at 2026-08-07).

### P4 — Trailing record & process work (3–5 sessions; may interleave with P3's rig wall-clock, still one lane at a time)

1. - [ ] **Corrections at source** (dated correction blocks ONLY — never in-place ADR edits;
   ADR-0036 clause 4 is the standing rule): ADR-0020 second Correction (nine-not-eleven);
   acceptance-ceiling README + the ceiling ADR-0035's figures (0.305→0.1952, ratios
   ~154x/~615x); resolution.py/responsive.py docstrings 328→250; report.py:23 population
   phrasing; four-lens-audit + bench-design correction blocks; the 'refusal' terminology gloss
   in golden.json's totals.
2. - [ ] **Body refresh** via tools/issues/body.py (#295 blocker strike, #268, #256, #286, #231
   brought to date with the machinery-vs-state distinction).
3. - [ ] **Process checks**: test_docs_thresholds.py (vector c); test_doctrine_has_a_home.py
   (vector g, seeds #243); tools/issues/cite.py + tools/deps/wire.py `stale` as reconcile-cron
   finding sources (vectors a, e); round-integrity check goes permanent (Law 2c) if not already.
   **DEC-11 (was T2.5)**: the bare-word check is NOT built now — the dated decline is recorded
   citing ADR-0036's own clause 5 and single-vs-twice trigger arithmetic; build only on a second
   unambiguous load-bearing instance.
4. - [ ] **Remaining stats hygiene**: #263 items 1–2 (ablation greedy/sampled split; redundancy
   CI unit) — they touch no r2 commissioning figure, hence trailing; #243's residual
   quoted-figure sweep.

### P5 — Trunk shipped (1 session)

1. - [ ] **The exit ADR**: the trusted-comparison definition (§0), per-cell commissioning
   doctrine (absorbing #231's amendment-prose rules), the re-derivation rule (#243's — deleting
   its registry seed proves the fix), amendments to ADR-0018 Q3 (stale twice) and ADR-0021 as
   needed.
2. - [ ] **Close-out**: levers re-pointed at r2 (each told which commissioning cells are live for
   it and what its lever class needs before sizing); parked set stamped (parked.md); #302 closes
   with the report landing under docs/ on lane/302.

## 3. Decisions — all thirteen, none floating

Each DEC's dated record (ADR amendment or judgment) rides the SAME PR as its enforcing change.

- **DEC-1** Control = nointerface; commissioning gate = both floor cells; 7B may ship dark;
  anonymise = dormant-machinery fallback (§4 table governs). [Ratified by the owner with plan
  sign-off, 2026-08-18]
- **DEC-2** Adoption-bar: no number needed for the trunk. Class R's adoption-bar IS the bench MDE
  (doctrine); Class O (exchange rate) and Class W (b + replication) are decided at lever time —
  recorded in P5.1 so nobody re-litigates.
- **DEC-3** D9 = cells into RECORDED+KEY + read-side subset enforcement (P1.8 + P2.4); ADR-0027
  amendment rides P1.8.
- **DEC-4** #288 = option 3 (generated index; no physical move — a move would drag SURFACE files).
- **DEC-5** gate_rescore/lintless into SURFACE; ADR-0032 amendment rides P1.9; mid-round-fix-
  forces-r3 cost accepted and stated.
- **DEC-6** #271 = keep the exact conditional test (m≥6); one shared implementation (P2.4);
  revisit only at growth sizing.
- **DEC-7** #257 = row-side `fired_rungs` addition.
- **DEC-8** Quotas: standing corpus report-only; enforcement ships with the parked growth epic.
- **DEC-9** `language`/`conditions_sha256` join GROUPS at the r2 boundary, adopted line
  included (P1.1).
- **DEC-10** resolution.py gets round/identity awareness, not a caveat (P2.4).
- **DEC-11** Bare-word check declined for now; the dated judgment (P4.3) cites ADR-0036's own
  clause 5 and the single-vs-twice trigger arithmetic — build only on a second unambiguous
  load-bearing instance.
- **DEC-12** One withdrawal mechanism: supersede-under-new-id via admissions.jsonl's existing
  `superseded_by`; retired.json frozen for new entries (its two stay as history). [P2.1/P2.3]
- **DEC-13** Registry semantics: banner always; refusal on quote; starts empty (r1 control entry
  recorded as voided); criterion computed from run data, never asserted. [P2.5]
- **DEC-14** `serving_resolved_sha256` joins GROUPS and KEY (#358, owner ruling 2026-08-25:
  admitted, by qualification not perturbation); ADR-0027 amendment rides P1.2's PR. KEY is 12;
  §0.1 binds by reference. A writer for the scored runners is owed as its own issue.

## 4. The control campaign's pre-signed outcome table (read at P3.3's decision gate)

| Outcome (per-cell recovery) | Action | Trunk ships? |
|---|---|---|
| 4/4 recover | registry: all four commissioned | Yes — full brightness |
| Floor cells (both 1.5B) recover; any/all 7B null | 7B cells recorded dark + refused; anonymise NOT invoked for 7B now (parked as a future r-round campaign; its machinery is already landed) | **Yes** |
| ts@1.5B recovers; py@1.5B nulls | Invoke dormant anonymise at the floor only (~1.5h rig, py-arm focus, random-string headline; bug_fix sign-flip pre-registered) | Only after py@1.5B commissions (ADR-0021: the floor is the obligation) |
| py@1.5B nulls under BOTH candidates | Halt; the finding is about the py acceptance rung (the ValueError-only confound, 104/257 checkers) — escalate to owner with the ADR-0023 clause-4 evidence; candidate next step: checker-repair tranche, then re-run | No — and the plan says so rather than shipping a half-dark floor |
| 0/4 recover | Halt; instrument-level diagnosis before any further rig spend | No |

## 5. Triage rules (written into the r2 round record at P3.1)

- **Mid-round defect**: off-SURFACE → fix, stay in r2. SURFACE but touched no recorded byte or
  verdict of runs already made → record as known-defect in the round record, stay, queue for r3.
  SURFACE and verdict-contaminating → halt, re-derive the drain list (never reuse the plan's),
  open r3. The shakedown exists to hit writer defects while r2 is still cheap to abandon.
- **Rig drift** (ollama bump, re-pull): serving_build/model_sha256 are rig-side, recorded per run,
  not SURFACE — **never forces r3**; re-run affected passes inside r2 at the new build; the
  rig-freeze window exists to make this rare.
- **Mass condemnation** (mutation scores condemn >15): stop, recompute bound/wall/eligibility
  arithmetic, owner decides retire-vs-repair scope before r2 opens.

## 6. Why this shape (the rationale spine — expanded ELI5 in the report)

- **Why the floor is the gate**: ADR-0021 binds the bench to the floor unit; per-cell
  commissioning is already the operative doctrine (two owner-approved #231 amendments). Requiring
  the 7B would let the plan's own pre-registered most-probable outcome (a 7B null) force a full
  re-baseline. Dark-but-refused is honest by construction — the registry makes "uncommissioned"
  a machine state, not a footnote.
- **Why SURFACE work is one phase**: the drained boundary makes "all SURFACE, then freeze, then
  open once" the only shape that avoids r3. The freeze is enforced (Law 2), not declared.
- **Why the earliest trustworthy number moved up**: the draft buried it under 10–15 sessions of
  off-SURFACE hygiene that gates nothing. v2 reaches it at P3.2/P3.3 (~sessions 12–16 realistic),
  with hygiene trailing behind the rig work instead of in front of it.
- **Why rulings precede nulls**: D9 keys bounds on the paired-cell count; a null measured on 257
  does not describe a 249-cell corpus.
- **Why anonymise lands dormant**: the fallback must not cost the round. SURFACE bytes are free
  while the tree is un-dispatchable; the campaign stays optional.
- **Why growth is parked**: the current corpus commissions the floor; growth's value depends on
  measured r2 psi, the #271 decision, and lever-class adoption-bars that don't exist yet.
- **What is NOT promised**: the doc→conversation escalation channel (lane/266's residual) has no
  machine check — named as accepted risk. And the plan does not promise the 7B cells; it promises
  honesty about them.

## 7. Estimates (honest, throughput-based: repo median ~1 issue-lane/session, #225=20, #231=9)

P0: 1 · P1: 10–14 · P2: 3–5 · P3: 2–3 + ~5–6h rig · P4: 3–5 · P5: 1.
**Total ≈ 20–29 sessions.** The rig hours: nulls ~2.4h, control ~0.3h, nointerface ~2.3h,
shakedown ~0.3h, perturbations ≤2h (r1-card planning-grade; re-priced at P3.2). First
commissioned, quotable floor number: end of P3.3.

## 8. Parked (see parked.md — the frozen not-now set)

14 levers · 37 v1-pipeline · 5 v2 · 10 parked-trunk · 3 baseline · corpus growth with its
arithmetic stated.

## 9. Residual risks, named and accepted

- Conversation-channel drift (uncatchable by tooling — lane/266's own words).
- The 7B cells may stay dark indefinitely; levers targeting them wait or fund the anonymise
  campaign.
- The py acceptance rung's ValueError-only shape (104/257) may be the floor-py control's real
  obstacle; outcome table row 4 owns it.
- KEY growth (11→12→~18) makes some historical cross-round reads refuse harder over time — by
  design, but stated.
