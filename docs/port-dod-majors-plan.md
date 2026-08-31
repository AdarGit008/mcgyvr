# green/port-dod-majors — the ~48 majors, as an ordered work plan

Forked from `green/port-dod-wrap` (which closed the 9 criticals, the 5
patterns, §4's items, and the reach leftovers). This branch closes the majors
enumerated in `docs/port-pressure-test-2026-08-29.md` §8 that are still Open.

Reconciled against current code on 2026-08-31: **9 rows the pressure-test
record marks "Open" are already fixed in code** and are *not* re-opened here
(see §Reconciled below). The rest are the work below.

## Discipline (carried from the pressure test)

- **RED first.** Every finding gets a failing test reproducing it by running
  code, then the fix, then the test stays as a regression guard.
- **Gate before done.** `make check` (ruff + format-check + mypy --strict +
  pytest) must be clean; report real output.
- **One PR per cluster.** Groups are by file so one pass closes several rows.

## Phase 1 — data loss & wrong bytes (highest blast radius)

| # | Finding | File |
|---|---|---|
| B4/X3 | pending store rmtree's the old entry before the replacement exists | `pending.py` |
| B6 | `meta.json` `target` used as a filesystem path, no re-validation on read | `pending.py` |
| B2 | delivery commits into detached HEAD / in-progress rebase, reports committed=True | `deliver.py` |
| B7/X8 | refused delivery leaves the directories it created | `deliver.py` |
| B12 | symlink target redirects delivery; trailer names a file the commit lacks | `deliver.py` |
| X2 | glob target commits a literal `**` directory (verify deterministic path) | `deliver.py` |
| F5 | CRLF scoped splice leaves mixed line endings | `worker/scoped.py` |
| F6 | whole-file re-emit duplicates every top-level statement | `worker/scoped.py` |

## Phase 2 — telemetry record integrity

A1 (append line-boundary), A3 (one undecodable byte kills the sink), A4 (fold
keys attempt_id alone and supersedes), A2 (fold `(ts, position)` tiebreak),
A5 (orphan correction can't name its author) — all `telemetry.py`.

## Phase 3 — gate / verification correctness

D2 (`show_absolute_path` disables typecheck), R9 (typecheck timeout =
time-dependent verdict), S13 (asymmetric STYLE routing), D7 (lambda/comprehension
shadow false positives), C5 (`read_verdict` outside try; no fit check), C4
(`""` collapsed to `None`) — `gate/typecheck.py`, `gate/runner.py`, `verify.py`.

## Phase 4 — repair robustness & the sandbox seam

D3 (splice above shebang), D4 (`_module_of` never checks resolution), D8 (no
subprocess timeout), R8 (repair has no sandbox seam), X5/X6 (RecursionError
escapes) — `repair.py`, `worker/scoped.py`, `worker/reply.py`.

## Phase 5 — composition seams

S7 (no shared error vocabulary), S12 (3 Verdits + 2 Outcomes), E6 (attempt raise
destroys WaveRun), S9 (resume collapses 3-state Review), S6/K5 (observe can't
record a deterministic run), S11 (unified_diff refused post-dispatch), S10
(apply_scoped has no producer) — `escalate.py`, `route.py`, `verify.py`,
`waves.py`, `pending.py`, `telemetry.py`, `worker/prompt.py`, `contract.py`.

## Phase 6 — capability table & data correctness

F7 (`params_b` required key, schema_version 1), F8 (NaN → StopIteration), F9
(shared mutable instance), E5 (`depends_on` order → identity), F1 (`_definition`
first-match), F3 (`_schema_field` heuristic), G2 (Degradation wording), G4 (plan
loads tree-sitter), K6 (`target_content` "") — `capability.py`, `contract.py`,
`worker/scoped.py`, `worker/reply.py`, `deterministic.py`, `worker/prompt.py`.

## Reconciled — already fixed in code, not re-opened

G1/S3 (best_of preserves caller sandbox — `62c24064`), B1, B5, B8, C3, F2, G3,
X4, X7. G5/E4/D7-slice-copy superseded by rewrite.

## Status log

- 2026-08-31 — branch created; plan written.
- 2026-08-31 — **Phase 1 complete** (8 findings, 3 commits):
  - `7c09e2b1` B4/X3 + B6 in `pending.py` — crash-safe entry swap (tombstone) and re-validated stored target.
  - `7c65c8b3` B2 + B7/X8 + B12 + X2 in `deliver.py` — detached/rebase refusal, created-dir undo, symlink refusal, glob-target refusal.
  - `a13a5c35` F5 + F6 in `worker/scoped.py` — CRLF fragment re-termination, whole-file re-emit refusal.
  - Full gate clean: `2374 passed, 6 skipped, 14 xfailed`, ruff + mypy strict clean.
- 2026-08-31 — **Phase 2 complete** (5 findings, 1 commit):
  - `ecb439ea` A1 + A3 + A2 + A4 + A5 in `telemetry.py` — torn-line/stump repair and counted writes, per-line decode, position-ordered fold, shared-id rows kept, required correction author.
  - Full gate clean: `2381 passed, 6 skipped, 14 xfailed`, ruff + mypy strict clean.
- 2026-08-31 — **Phase 3 complete** (6 findings, 1 commit):
  - `7754e508` D2 + R9 + S13 + D7 in `gate/typecheck.py` & `gate/runner.py`, C5 + C4 in `verify.py` — absolute-path attribution, timeout-as-skip, symmetric STYLE routing, shadow-aware mutation walk, protected verdict read, empty target_content kept.
  - Full gate clean: `2389 passed, 6 skipped, 14 xfailed`, ruff + mypy strict clean.
- 2026-08-31 — **Phase 4 complete** (6 findings, 1 commit):
  - `6c588af4` D3 + D4 + D8 + R8 in `repair.py`, X5 + X6 in `worker/reply.py` — shebang-safe splice, existing-dependency-only imports, bounded ruff subprocesses, sandbox seam, deep-reply refusal by name.
  - Full gate clean: `2395 passed, 6 skipped, 14 xfailed`, ruff + mypy strict clean.
