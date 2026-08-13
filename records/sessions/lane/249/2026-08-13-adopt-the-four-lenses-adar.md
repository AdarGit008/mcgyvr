---
record: session/1
lane: 249
agent: adar
started: 2026-08-13
---

## Did

**Landed ADR-0026 on its own lane.** It was written on `lane/231`, because that
is where its evidence came from, and moved here so it is reviewed as doctrine
rather than inside a 103k-line measurement PR where nobody would read it. No
substantive change from the version drafted there.

Also carried the two amendment blocks its acceptance requires:

- **ADR-0024** — this ADR pinned the serving build because two builds are two
  instruments. The amendment records that the same argument applies to every
  other manifest field, and that where it was applied elsewhere it was applied to
  a *name*: 133 manifests carry a model tag with no weight digest, vocabulary,
  template or quantization content; five rung names byte-identical across two
  arms whose rule sets are 328 against 66; and a condition as a bare string,
  because `bundle_sha256` hashes the system prompt while an ablation edits the
  user message.
- **ADR-0025** — its decision clauses stand unchanged. Its *premise* is
  withdrawn: `recommended` was chosen to mirror ruff's select and argued to "move
  together" from rule intent, never measured. Measured the next day it is 66
  rules against 328, with **41% of the ruff set in families eslint has no
  member of at all**, and the consequence is the one the ADR existed to prevent
  one level down — the bar reverses which arm leads (py 8.9/ts 12.8 under it, py
  27.3/ts 23.9 on correctness alone).

### Lens 3 gained its strong form (owner, same day)

*"A bar, test, check or measurement that does not explicitly state what it
contains is worse than dead weight."* Dead weight is neutral; an unstated bar is
**negative**, because it reports health while applying something unknown and a
reader cannot tell "this passed" from "nothing ran".

Five live instances are now tabled in the ADR — the JS lint rung scoring absent
tooling as a pass, ruff running an unstaged rule set where `TRY004` alone
rejected 75 of 257 references, `gate_rungs` identical across 328-vs-66 rule sets,
`tsc --noEmit` named in the bar with no `tsconfig.json` ever staged, and
`structured` matching no file either arm produces.

The rule it adds: a check declares its content **and** something proves the
declaration is live. A digest with no positive control records exactly which
inert bar was applied; a control with no digest proves something rejected without
saying what.

`make check`: 1356 passed.

## Left open

- **The consequences are not implemented here, deliberately.** The three
  name-to-content digests (bar, model, condition), the report's refusal to pool
  across a heterogeneous stratum, and the language registry are each their own
  work. This lane lands the standard they will be judged by.
- **#248 was found by lens 3** and blocks; it is not this lane's.
- **ADR-0021's sizing figures are computed on pooled arms** and are untouched
  here. Whether they need their own amendment is #225's call, not this one's.

next: land this, then build the three digests as one change on a fresh lane —
bar, model and condition are the same defect in three fields, and the model half
was proven obtainable from the serving endpoint on 2026-08-13.
