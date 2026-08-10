# The bench campaign: names, the split rule, the gate, and the order (#225)

**Status:** design of record for lane/225's Phases 2–4. Decisions #225's
amendment fixed are cited, not re-argued; what this document adds is every
name and mechanism the implementation needs, so that the split rule and the
gate exist in committed form **before any generated problem exists** — that
ordering is what makes the split provably blind. Consumers: `tools/bench/`
(the gate and split tool), `tools/breadth/measure.py` (tier wiring, Phase 3),
`tools/instruments.json` (the declaration, same change as the first
contracts), #113 (the harness reads the bench), #224 (the band is measured
on it), #222 (consumes the reserve).

## 1. Names

| thing | name | why |
|---|---|---|
| instrument sets | `bench-ts`, `bench-py` | the `bundle-ts`/`bundle-py` convention: one instrument, two language arms, `paired_with` each other |
| roots | `tools/bench/tasks/ts/`, `tools/bench/tasks/py/` | flat per set — `tools/instruments.json` walks `root/<id>/contract.yaml`; the pool's two-level layout under one root would empty the declaration's id/digest maps |
| tiers | `bench-ts`, `bench-py` | the pool pattern: the language arm lives in the tier *name* so `run.json`'s tier + `tasks_sha256` carry it; `d1`–`d3`, `d1r`, `pool-*` are all taken, and a retired tier name raises at record time |
| task ids | `b<nnn>-<slug>` (e.g. `b001-ring-buffer`) | globally unique by construction: no other set uses the `b` prefix (checked 2026-08-10); hyphens in ids are safe for `pin.py`'s stem parsing, which splits conditions and draws, not task ids |
| reserve root | `tools/bench/reserve/ts/`, `tools/bench/reserve/py/` | **outside** the declared roots — the declaration walks its root, so a reserve dir under `tools/bench/tasks/` would classify as instrument material and `build_dataset.py` would refuse the very half that exists for training |
| manifest | `tools/bench/admissions.jsonl` | the pool's append-only digest-pin discipline, one entry per admitted problem, both halves in one manifest with the split assignment recorded per entry |
| strata record | `tools/bench/strata.json` | written by Phase 3's calibration, versioned and append-only in spirit: a re-assignment is a new dated block, never an edit |

The campaign driver never climbs into bench tiers, exactly as it never climbs
into `pool-*` — they are not rungs of the retired ladder.

## 2. The split rule, declared before anything is read

Every admitted problem id is assigned to exactly one half by:

```
assignment(id) = "bench"   if int(sha256("mcgyvr-bench-split-2026-08-10:" + id).hexdigest()[:8], 16) % 2 == 0
                 "reserve"  otherwise
```

- **Blind by construction.** The rule is committed here, in `tools/bench/split.py`,
  and in this document's date — before any generated problem exists to read.
  It keys on the id string alone: no prose, no difficulty, no measurement can
  move a problem across the line.
- **Stable under pauses.** Assignment depends only on the id, so a
  spend-limit pause, a refill batch, or a retired id changes nothing already
  assigned — the #197 record makes pauses a certainty, not a risk.
- **A problem moves as a unit.** The id names the problem; both language arms
  travel with it. A one-armed problem is never split — it is deleted (#197's
  both-arms-or-nothing discipline).
- **Representative in expectation, and reported rather than repaired.** Each
  steering cell (band × type) splits ~50/50 in expectation with binomial
  noise. The gate's report states the realized split per cell; a skewed cell
  is recorded and lived with, because any post-hoc rebalancing is exactly the
  fitting the pre-declared rule exists to prevent. (#222's
  "difficulty-representative by construction" is bought by the rule's
  content-blindness, not by forcing counts.)
- The reserve is **never swept** in this lane: its representativeness comes
  from the construction, its difficulty is never measured here, and no rig
  tier serves it.

## 3. The gate: `tools/bench/admit.py`

The pool's gate rehearsed the measurement; the bench gate inherits that and
tightens what the levers need. Checks, in order (deltas from
`tools/problems/admit.py` **bold**):

1. **Structure** — both arms present (`contract.yaml`, reference, checker),
   **id matches `b<nnn>-<slug>`**, arms agree on `task_type`,
   **`file_shape` label present** (`single_definition` | `multi_symbol`),
   **shape label present** (#162's axis: `recursion`, `iteration`, `string`,
   `numeric`, `data_structure`, `error_handling`). The labels live in a
   gate-owned **`meta.json` sidecar** per problem (one per id, beside the
   arms), pinned in the manifest like every other file — the contract
   schema is strict and its `target` names a *file*, so the target
   **symbol** a `multi_symbol` problem stubs is `meta.json`'s
   `target_symbol`, which must appear among the interface's declarations;
   a `single_definition` problem's target symbol is its interface's single
   declared function, exactly the pool's rule.
2. Contract validity via the real loader; `task_type` ∈ {`function_implementation`,
   `bug_fix`} (type_annotation deferred with #211, per #225's amendment).
3. Selftest — the reference passes its own checker in a fresh directory.
4. Failing-first for `bug_fix` — the buggy `target_content` fails the checker.
5. **Anti-triviality, declared-target form.** The pool stubs the *first*
   declared function, which on a multi-symbol file stubs helpers or fails
   structurally — vacuous either way. The bench gate resolves the **target
   symbol named by the contract** in the interface (a named check: an
   unresolvable target is a structure failure), then replaces **only that
   symbol's body** in the *reference* with the no-op and echo stubs, helpers
   intact. The checker must reject both. This is what makes a `multi_symbol`
   problem's checker guarantee mean the same thing as a single-definition
   one's. The generator brief mandates declaration style (`export function
   name(...)` / `def name(...):`) so body replacement is mechanical.
6. Checker floor — ≥5 assertions per arm (the pool's floor; CLM-0016 is the
   reason the brief asks for richness beyond the count, but the floor is the
   gate's part).
7. **Front-door overlap, two blocklists** — no arm implements a symbol whose
   normalised name is one of HumanEval's 164 entry points **or MBPP+'s 378**
   (`tools/bench/mbpp-entrypoints.json`, extracted from EvalPlus 0.3.1's
   MBPP+ on 2026-08-10). MBPP is pretraining-memorized *and* the band's
   locator as of `records/measurements/mbpp-plus-3b-2026-08-10/` — a bench
   problem restating an MBPP item would overstate the floor and couple the
   bench to its own ruler.
8. Near-duplicate screen — lexical Jaccard ≥ 0.55 over task prose rejects,
   screened against: every candidate in the invocation, everything already in
   `tools/bench/admissions.jsonl` (**both halves — this is how the screen
   runs across the split by construction**), the pool's 499, and the retired
   sets' prose (via `tools/instruments.json` task roots). The lexical
   screen's weakness is stated where it lives: it catches rewording, not
   re-ideation; the #197 campaign's diversity came from never-repeated domain
   assignment, and the bench campaign plans domains the same way.

Execution mechanics (fresh temp dir per candidate, contract-declared
commands, 30s ceiling, exit 126/127 aborts as environment fault) are the
pool's, imported by path — orchestration is bench-owned, machinery is shared.

Admission requirements the levers put there (from #225's amendment, made
checkable): per steering cell the realized counts of `file_shape:
multi_symbol` (quota ≥ 25% per stratum, both languages — #126's arm needs the
large-file/small-target case to exist, and its acceptance checks the bench
for it before dispatch), of `bug_fix` (a declared mix per cell — it passes
~2× fn_impl, so drift masquerades as difficulty), and of non-empty
`target_content` on fn_impl (≥ ⅓ — #17's sizing input, #198's placement
variant). The gate reports these; starved cells drive refill batches rather
than silent acceptance.

## 4. Serving, caps, and the declaration

- `tools/breadth/measure.py` gains `BENCH_TIERS = ("bench-ts", "bench-py")`,
  served **manifest-pinned only** (the pool's `pinned_pool_ids` pattern
  against `tools/bench/admissions.jsonl`, filtered to `split == "bench"`),
  language from the tier name at both existing inference points.
- **Cap for every bench sweep in this lane: `--max-output-tokens 2048`**,
  stated in `run.json` as part of run identity. The inherited 768 censors
  d3-class references (#212, audit C8) and the gap strata are *designed* to
  carry longer references; 2048 is the floor probes' value, and the fitted
  per-type formula stays #17's.
- The declaration (`bench-ts`, `bench-py`; `retired: null, trainable: false`;
  `paired_with` each other; tiers as named) lands in `tools/instruments.json`
  **in the same change that creates the first admitted contracts, before any
  sweep** — an undeclared bench run classifies as clean and becomes training
  fuel, which is #189 with fresh material. Declaring the roots also extends
  the pool gate's exclusion to the bench automatically (`admit.py` reads
  `instruments.task_roots()`), and the reserve — undeclared by design — is
  excluded from the *bench* gate by its own manifest instead.
- Capture shape: the runner is `measure.py`, so rows, `run.json`, and
  `candidates/<task>/<arm>-<draw>.txt` stay `pin.py`-total with no pin
  changes. Replies stay `WHOLE_FILE`.

## 5. The campaign order (Phases 3–4)

1. **Pilot per band** (small steered batches at four target bands
   interpolating reference size and assertion count between d3-class and
   pool-class — the MBPP+ record settled that the gap is a unit-of-work
   cliff, not trickier small functions).
2. Gate → pin (split assigned and recorded; reserve dirs moved to the
   reserve root) → **declare** (same change) → **calibration sweep** of the
   bench half only: 3B, greedy, one draw, cap 2048, through `measure.py`.
3. `tools/bench/strata.json` assigns measured strata; starved bands get
   refill batches (ids over-assigned ~3% for mid-write loss, retired ids
   never reused).
4. Full campaign to ~800 admitted problems, pause-tolerant throughout; the
   gate's cell report is the completeness check; per-type reference-length
   distributions recorded at generation time (#17's input).
5. Every stratum's realized 3B rate is reported with its n; at least one
   stratum must land interior (#119's arm dies otherwise) — if none does,
   steering is re-aimed and refilled *before* any lever arm runs.

## 6. Deliberately not decided here

Stratum boundaries (measured, Phase 3); the per-type cap formula (#17); the
condition matrix and the rule-ablation knob (#113); how #224 reads the band
from the strata (its own acceptance, re-read at Phase 5); whether a future
annotation set joins as its own instrument (#211's gate design first).
