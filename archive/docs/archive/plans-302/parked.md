# The frozen not-now set

Everything below stays open and untouched until the trunk ships. Parked is not blocked and not
judged: these wait because the trunk outranks them, not because they are wrong. At P5.2 each
entry gets its dated stamp comment; unparking before that is an owner call recorded on the issue.

## Levers — the bench's future customers (14)

The six declared arms and their satellites measure AGAINST the commissioned bench; none may run
before it. #17 output caps · #119 sampling breadth · #126 target granularity · #198 prompt
assembly · #221 weights/fine-tune · #232 decomposition · #233 combinations · #162 routing matrix
(behind #233) · #190 distillation (behind #221) · #222 weights-arm corpus (behind #221+#225) ·
#270 naming arm (behind #267) · #168 bundle cost · #149 serving ceiling · #246 normalisation
(its +13.7pp is a scoring-bar effect measured pre-commissioning; re-measured, if at all, as an
r2 arm). At P5.2 each lever issue gets one comment: which cells are commissioned for it and what
its lever class (R/O/W) requires before sizing.

## Product pipeline, v1 epics (37)

E2–E11 and their children (#13 #16 #18 #19 #40 #41 #42 #44 #45 #53 #54 #55 #56 #57 #58 #59 #60
#61 #62 #63 #64 #65 #67 #81 #116 #132 #141 #146 #158 #159 #173 #179 #204 #205 #206 #264 #279):
the offload pipeline that would USE the library. Downstream of a trusted instrument by
ADR-0017/0018; the library parts are built and tested, the joining loop is one function that can
be written when measurement says which shape earns it.

## v2 (5)

#68 #69 #70 #71 #72 — explicitly post-v1 by their own labels.

## Parked trunk-adjacent (10)

#111 (historical trunk index) · #118 (binds by default) · #132 · #134 (its live half — the
schema dialect note — is folded into the plan's hygiene; the rest waits) · #152 · #171 · #207
(its mechanism check landed with the four-lens work; pooling half is #256, which IS in the
plan) · #211 · #213 · #226. Each binds by default or waits for a consumer that doesn't exist
yet.

## Baseline-filed (3)

#3 #4 #66 — #4 ('advanced' profile) is a v1-release-cut requirement by baseline.config's own
note; #66 (reconcile shipped claims with shipped behaviour) is partially discharged by the
review's claims-plane verification and completes naturally at P3.5 when the register catches up.

## Corpus growth 257→400 (explicitly parked, with its arithmetic)

Growth buys: the one resolving stratum 8.5→6.7pp (1.27x); three function-implementation strata
newly resolve at ~3.9pp; six strata never resolve at 400. It waits on three things the trunk
will produce: measured per-lever psi at r2, the #271 wall decision applied, and a lever-class
adoption-bar conversation. Growing earlier is spending authoring effort on unmeasurable cells.

## Bench hardening — multi-model residency (4)

**Owner ruling, 2026-08-23.** The bench stands up first. Around 90% of the measurements this
instrument owes — levers, configs, the four commissioning cells — are one model, one engine, one
family on a card. Multi-model, cross-family and cross-engine residency is bench *hardening*, and
hardening is post-bench and post-trunk. Whatever can be tested quickly now stays; the rest parks
here. This is a re-prioritisation, not a judgement: the four issues below are confirmed defects
with their evidence in the tree, and none of them is withdrawn.

**Stays, and needs nothing new.** Phase 0 of `records/headers/2026-08-22-coresidency-matrix.json`
— every (rig, engine, model) loaded **alone**, recording the measured footprint in the shape its
engine can state. 25 cells, ~60 min, single-model by construction, so it clears none of the four
gates below and does not need to. #345 landed 2026-08-23 (ADR-0040) and unblocked its vLLM arm.
Phase 5 is arithmetic over that footprint table, not extra cells.

**Parked.** Phases 1 (ordered pairs), 2 (multiplicity), 3 (sets) and 4 (transitions), and the
harness work that exists only to serve them: **#343** (`run.py:353-358` releases every other
backend with no per-cell opt-out) · **#344** (`ollama.py:486` gates on `card_idle_before_load is
True`, so a declared shared card is refused by construction) · **#346** (`ollama.py:361-378` is
the only neighbour loader and can only speak ollama, in the wrong layer) · **#347** (vLLM's
launch precondition is `free >= ceil(total × util)` at its default 0.92 — 5,160 MiB demanded on
srv1's 6,144 MiB card against a 3,126 MiB real footprint, so a vLLM cell cannot load second
there).

**Two of the four are not about cross-engine at all**, and they return the moment multiplicity
does rather than the moment mixed engines do: #344 fires on a second *ollama* model loading onto
a card its sibling already holds, and #347 fires on a second *vLLM* instance on a second port.
Parking multi-model parks them; a narrower "no cross-engine" ruling would not have.
