# tools/bench — the bench campaign's gate, split rule, and blocklists (#225)

The design of record is `docs/bench-design-2026-08-10.md`; #225's amendment
carries the decisions and their arguments. What lives here:

- **`split.py`** — the pre-declared bench/reserve split rule, committed
  before any generated problem existed. Keys on the problem id alone;
  stable under pauses; a problem's two language arms travel together. The
  salt never changes.
- **`mbpp-entrypoints.json`** — MBPP+'s 378 task ids and entry points
  (extracted from EvalPlus 0.3.1, 2026-08-10), joining HumanEval's 164 in
  the item-level decontamination blocklist. MBPP is pretraining-memorized
  *and* the band's locator (`records/measurements/mbpp-plus-3b-2026-08-10/`),
  so a bench problem restating an MBPP item would overstate the floor and
  couple the bench to its own ruler.
- **`admit.py`** — the bench admission gate: the pool gate's execution
  machinery with bench semantics — `b<nnn>-<slug>` ids, the `meta.json`
  sidecar (labels + `target_symbol`), the declared-target anti-triviality
  rule that degrades only the target symbol's behaviour with helpers
  intact, both front-door blocklists over *every* declared function, the
  near-duplicate screen that runs across the split by screening against
  the whole manifest, and `--pin`, which records the pre-declared split
  and places reserve problems outside the roots the declaration will
  walk. `--verify` holds the tree, the manifest, and the split rule to
  each other; `--cells` reports realized counts per steering cell.
- **`tasks/ts/`, `tasks/py/`** *(Phase 3+)* — the bench half's roots, flat
  per language, declared in `tools/instruments.json` (`retired: null,
  trainable: false`) in the same change that creates the first contracts.
- **`reserve/ts/`, `reserve/py/`** *(Phase 3+)* — the reserved training
  half. Deliberately outside the declared roots and never given a tier:
  not an instrument, never swept in this lane, consumed (or not) by #222.
- **`admissions.jsonl`** *(Phase 3+)* — the append-only digest-pin manifest,
  both halves in one file, split assignment recorded per entry.
- **`strata.json`** *(Phase 3+)* — measured stratum assignment from the
  calibration sweep; re-assignment is a new dated block, never an edit.

Sweep caps, tier names, and the campaign order are in the design doc.
