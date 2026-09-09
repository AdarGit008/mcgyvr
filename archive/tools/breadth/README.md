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
- **A cell without an observation is not filled** ([#217](https://github.com/AdarGit008/mcgyvr/issues/217)).
  A `dispatch_error` row records that a draw reached no worker, so `done_keys`
  does not count it and a resume re-dispatches it. See below for what that
  costs and how it is kept honest.

## When the backend goes away

On 2026-08-08 a 269-problem sweep lost **152 of 807 draws** — 18.8% — to a
contiguous srv2 outage that opened and closed on its own; the host answered
0.14s later. The rig handled each failure correctly at the row level, and then
made the loss permanent: `done_keys` counted the error rows as filled cells, so
re-running the identical command printed `resuming: 807 draws already recorded`
and dispatched nothing. The sweep exited 0, the rows file had the expected line
count, and only a summary line that had scrolled past hours earlier said
otherwise. Three things answer that:

- **The resume refills, and rewrites the rows file to be able to.** The file is
  append-only, so re-dispatching without removing the old row would leave two
  rows for one cell and make three readers each learn a last-row-wins rule —
  including `tools/replies/pin.py`, which joins a capture to the *first*
  matching row and would die on `KeyError` where it otherwise raises a
  diagnosable `PinError`. The rewrite is deliberate in the way the run-identity
  discipline means: the displaced rows are kept verbatim in
  `dispatch-errors-invocation-<n>.jsonl`, the act is announced on stderr and
  recorded in `run.json` against the invocation that did it. It is **not**
  behind a flag — needing to notice is the defect's own first failure mode.
- **A holed run says so where it cannot be scrolled past.** `run.json` carries
  a `completeness` block naming every unobserved cell, `summary.md` leads with
  it rather than trailing, and the run exits non-zero. `--audit` asks the same
  question of every run directory under `records/measurements/` at once; all 87
  breadth-shaped directories on disk answer complete.
- **A dead backend stops the run.** Three consecutive tasks losing *every* draw
  to transport is not a model behaviour, so it aborts rather than spending the
  remaining hours re-learning it — the outage above cost five. Rows already
  written stay, and the resume fills them. `--abort-after-dead-tasks 0`
  disables it.

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
`docs/archive/claims/` — read those for what came out; this document is the
instrument.
