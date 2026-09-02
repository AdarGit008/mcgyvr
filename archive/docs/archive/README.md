# Archive — history, not authority

Everything under `docs/archive/` was authoritative once and is not any more. It is kept
because it is the record of how this project got here, and deleting it would not make the
history untrue — only unreadable.

**Nothing here governs anything.** No test reads it, no CI job checks it, no tool resolves a
path into it. A decision record in `archive/decisions/` describes what was decided on its date
and by whom; it does not bind current work, and a current change that contradicts one owes no
amendment, supersession note, or ADR of its own.

Archived 2026-08-25, in the same change that removed the vendored `baseline-skill` from
`tools/baseline/` and its gate from CI. That skill is what made these files load-bearing:
`baseline.config.json` declared `decision_globs`, `grounding_docs` and a `sources_of_truth`
map, and the `baseline` CI job enforced them. With the skill gone the enforcement is gone, and
leaving the records in their authoritative locations would have implied a governance that no
longer exists.

## Contents

| path | what it was |
|---|---|
| `decisions/` | 40 decision records (ADR-0001…0040) plus the generated `INDEX.md`. Forks and rationale, 2026-07 to 2026-08 |
| `decisions-machinery/` | `index.py`, which generated `INDEX.md`; `test_decisions.py`, which refused duplicate ADR numbers; `test_claims.py`, the CLM citation checks; `test_session_records.py`, which enforced baseline's FLOW-03 `next:` reading. All inert |
| `claims/` | The CLM-* register. A baseline-skill construct — its schema and its CLAIM-01/02/04 rules lived in the vendored tree, so nothing has validated these since the skill was removed |
| `sessions/` | 196 lane session records, the project's forensic tier. The only narrative of why most things are the way they are |
| `plans-302/` | The approved plan of record for the trunk review, and its evidence pack. It bound to ADR numbers throughout and carried an amendment protocol modelled on the ADR rule |

## One live check kept, one half of it dropped

`tests/test_finding_is_a_check.py` was ADR-0037's predicate in two halves. Rule 3 walked
`docs/decisions/0*.md` and required every `tests/<file>::<test>` a record named to resolve to a
real function — a check that enforced the prose of these records, which after this change would
be the archive governing by the back door. It is gone with its corpus. Rule 2 stands, because it
is a property of the suite rather than of a record: every `xfail` under `tests/` must be
`strict=True` with a dated reason.

## What moved out rather than in

`plans-302/evidence/verify/rig-reality-2026-08-25.md` was written the same day this archive was
created and describes the rigs as they are now. It moved to
`records/measurements/serving-sweep-2026-08-25/rig-reality-2026-08-25.md`, beside the sweep it
grounds, rather than into the archive with the rest of #302.

## Reading these

Prose citations to `docs/decisions/NNNN-…` survive throughout the source tree, in docstrings and
comments. Those paths are stale by one directory: the file is under `docs/archive/decisions/`.
Resolving **hyperlinks** were repointed, because a link that 404s is worse than a stale path.
Plain prose citations were left as written rather than rewritten en masse — a citation is a record of what its
author was reading, and 400-odd mechanical path edits would have been a large diff asserting a
currency these records no longer have.
