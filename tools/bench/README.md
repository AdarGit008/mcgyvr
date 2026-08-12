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
- **`tasks/ts/`, `tasks/py/`** — the bench half's roots, flat per language,
  declared in `tools/instruments.json` (`retired: null, trainable: false`)
  in the same change that created the first contracts (the 2026-08-10
  pilot, 40 problems pinned, 22 bench / 18 reserve). Served as tiers
  `bench-ts`/`bench-py` by `tools/breadth/measure.py`, manifest-pinned only.
- **`reserve/ts/`, `reserve/py/`** — the reserved training half.
  Deliberately outside the declared roots and never given a tier: not an
  instrument, never swept in this lane, consumed (or not) by #222.
- **`admissions.jsonl`** — the append-only digest-pin manifest, both halves
  in one file, split assignment recorded per entry.
- **`strata.json`** — measured stratum assignment from the calibration
  sweep; re-assignment is a new dated block, never an edit.
- **`matrix.json`** — the condition matrix (#113): every lever, every cell,
  and the rules the loader holds them to. A cell names a set of levers and
  the empty set is the baseline. Each lever declares the one **slot** it
  writes, so two levers that would fight over the same field are refused
  when the matrix loads rather than producing an order-dependent cell
  nobody can read. `tools/breadth/measure.py --condition` takes its choices
  from here — the runner reads the cells, it does not know them, which is
  what lets #233 consume the same format for leave-one-out without a
  second one being invented.
- **`matrix.py`** — the loader, the two application stages (`contract`
  levers change the task the worker is given; `message` levers change only
  how it is asked, and the prompt is re-costed afterwards so an ablation
  that removes text is not priced as free), and the **interaction term** —
  combined effect minus the sum of the singles. It returns *absent* rather
  than zero when a single-lever arm is missing: a gap in the run is not
  evidence that two levers are additive.

Sweep caps, tier names, and the campaign order are in the design doc.
