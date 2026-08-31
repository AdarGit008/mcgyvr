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
- 2026-08-31 — F5/F6 closed in `worker/scoped.py`: a CRLF splice re-terminates its fragment to the source's terminator (head/tail untouched), and a reply that re-emits the whole file is refused as `scope-mismatch` naming the extra statements. RED tests: `tests/red_port/test_dod_scoped_crlf.py`, `tests/red_port/test_dod_scoped_wholefile.py`.
