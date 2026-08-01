# Join keys (C38)

The relational join (`src/join.mjs`) may relate work items **only** through the keys declared
here. A relationship it cannot resolve through a declared key is a **finding**, never an
inferred guess — the discipline that keeps derived state honest (no NLP, no heuristics). The
descriptor's `join_keys` (M2) names which keys a repo has opted into.

## Active (M3b)

| Edge | Key | Plane | How it's produced |
|---|---|---|---|
| PR ⇄ branch | `headRefName` | forge | GitHub sets it when the PR is opened |
| PR ⇄ issue | `closes` | forge | a `closes` / `fixes` / `resolves #N` reference in the PR body (GitHub closing keywords) |

An unresolvable `closes #N` (no such issue) is emitted as an `unresolvable-join` finding, surfaced by `orient`.

## Reserved (inert until the records that carry them exist)

| Edge | Key | Arrives with |
|---|---|---|
| session ⇄ lane | branch namespace (`records/sessions/<lane>/`) | M4 records |
| session ⇄ issue | `Baseline-Issue` trailer | M4 records; `lane claim` stamps it since M5a (one home: `src/util.mjs` TRAILER_ISSUE) |
| lane ⇄ agent | `Baseline-Agent` trailer | M5 lanes; `lane claim` stamps it since M5a (one home: `src/util.mjs` TRAILER_AGENT), the join reads it at M5b |
| JDG ⇄ rule | `rule` field | M4 judgment ledger |
| CLM ⇄ claim unit | record id | M4 claims |

`src/join.mjs` consumes only the keys whose records exist; the reserved rows activate as M4/M5
create them, so no key is joined before it can be resolved.
