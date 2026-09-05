# Wrap-up task: finish the port-from-local-ai DoD

This branch (`green/port-dod-wrap`) is cut from `origin/green/fix-b1-b9`
(tip `16bf1490`), which holds the entire orchestration-port chain:
the 19-lever port, the B1–B9 critical fixes + 11 more, pattern B ("the tree
owns the bytes"), the §4 fixes, and the reach work (fourth lever + sampler).

The authoritative record of what is left:

- `docs/port-pressure-test-2026-08-29.md` — status table + full findings.

## What this branch closes (done, verified in code + tests)

### §4 — three items
1. **`max_waves`** now bounds *re-planning*, not plan depth. A correct,
   failure-free 4-deep chain runs to completion; a contract whose dependency
   failed is reported "did not land", never "not reached"
   (`src/mcgyvr/waves.py`, rows E2/E3).
2. **Cooldown lever** is wired. `record_success` resets the failure count
   without cancelling an armed sentence, and the lever is wired into
   `worker_attempt` so it fires inside a task; `mcgyvr run` passes a stub-probe
   `Cooldown` (`src/mcgyvr/cooldown.py`, `drive.py`, `cli.py`, rows F4/S8).
3. **Contract digest identity** no longer reads `data/task-catalog.json`.
   `dumps()` emits the *declared* output cap, `null` when derived
   (`src/mcgyvr/contract.py`, row E1).

### Reach-work leftovers (surfaced by wiring the levers)
- `best_of`'s `repo` / `sandbox` mutual-exclusion is enforced at the top of the
  call, and `gate` receives the sandbox rather than a bare path
  (`src/mcgyvr/consensus.py`).
- `delivery.token_env` is removed (`config.py`, `initialize.py`).
- `_INPLACE_WORDS` is negation-aware and word-boundary (`gate/typecheck.py`).
- `_DEPRECATED_TYPING` is a full map, so a ruff-less install still reports
  deprecated typing imports (`gate/typecheck.py`).

## What this branch does NOT close — the ~48 major (decision recorded)

The ~48 major findings were **enumerated, not fixed**. They are listed per
finding in `docs/port-pressure-test-2026-08-29.md` §8 with a State column, and
most rows remain **Open**. This branch closes none of them.

One reach leftover is still open in code and stays Open in §8: `G1`/`S3` —
`consensus._draw` runs `space.reset()` after every draw, so a caller-supplied
sandbox gets its state wiped (`src/mcgyvr/consensus.py`).

**Decision — 2026-08-31 (deferral).** The ~48 major are deferred to a
follow-up branch (`green/port-dod-majors`), not shipped under a "Closed"
banner. This branch merges the §4 items and the reach leftovers above, and the
record states the ~48 as enumerated-and-open.

## PR context (upstream merge path)
- `#383` `green/fix-b1-b9` → `green/port-from-local-ai` — OPEN
- `#380` `green/port-from-local-ai` → `main` — OPEN
- `#379` `red/port-from-local-ai` → `main` — OPEN (RED baseline)

## Gate
`make lint` / `make test` / `make typecheck` / `make docs-check` must stay
green — see `Makefile` and the `verify-before-claiming-done` rule.
