# The first-pass index distribution — the measurement that settles breadth

Issue: [#121](https://github.com/AdarGit008/mcgyvr/issues/121), under
[#111](https://github.com/AdarGit008/mcgyvr/issues/111).
Instrument: `measure.py`. Task set: the bundle rig's
([`tools/bundle/tasks/`](../bundle/tasks/)), imported by path and pinned by the
same digests.

ADR-0008 fixed breadth as policy with a default of 1 and named the one cheap
measurement nobody in the lineage had proposed: given that a gate-passing
candidate exists among N draws, **at what index does it first appear?**
Concentrated at index 0 retires breadth outright. Spread out is the only
evidence that would justify raising the default — everything else on offer is
a pass@k bound, a ceiling on what selection could achieve rather than a
measurement of what it does. #119 (breadth as a `TIER_FIELDS` setting) is
explicitly blocked on this number.

## Design

- **Serial draws, no early exit.** Production breadth stops at the first gate
  pass; the instrument must not, or every observation is truncated at its own
  answer. `measure_task` runs the full plan regardless of what passes, and a
  test holds that.
- **Two arms.** Breadth requires sampling (N identical greedy draws are one
  draw), and moving off greedy can cost pass rate before breadth pays anything
  back. Each task runs once at temperature 0.0 (`greedy` — the anchor,
  comparable to the bundle sweep's c2 rows) and `DRAWS` times at 0.7
  (`sampled`). The variance cost is greedy vs sampled draw 0; the breadth
  benefit is draw 0 vs the rest.
- **N = 5, T = 0.7 — DEC-6's own numbers.** The inherited proposal ADR-0008
  stripped to one sentence proposed five draws at 0.7; measuring at its own
  operating point is what makes the result an answer to it.
- **The prompt is the shipped assembly** — `build_prompt` over each contract,
  bundle selected by adapter — so the distribution describes what production
  dispatches.
- **"Gate-passing" means the contract's declared acceptance, executed** — the
  same proxy CLM-0012 is quoted on. Parse refusals fail by refusal code. The
  full `Gate.run` adds scope/secrets/structured/adapter rungs plus the
  sandbox; the claim record labels the result "acceptance-passing" rather than
  borrowing the gate's full name.
- **Every candidate is kept** in `candidates/<task>/<arm>-<draw>.txt`, pass or
  fail — replies are the corpus #184 observes gets thrown away where it is
  free.
- **Provenance and resume** follow the bundle rig: `run.json` pins worker,
  sampler, cap, bundle and task digests; resuming into a directory measured
  under any other identity is refused.

## Usage

```
# verify the task set (no worker needed)
uv run --no-sync python tools/breadth/measure.py --selftest

# the sweep
uv run --no-sync python tools/breadth/measure.py \
    --endpoint http://srv2:11434 --protocol openai \
    --model qwen2.5-coder:14b \
    --out records/measurements/breadth-YYYY-MM-DD

# the table, from rows already collected
uv run --no-sync python tools/breadth/measure.py --out <dir> --summarise-only
```

The result lives in `records/measurements/` and its claim in
`records/claims/` — read those for what came out; this document is the
instrument.
