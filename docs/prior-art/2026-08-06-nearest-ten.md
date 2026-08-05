# Prior art — the nearest ten repositories (#175)

Status: in progress — 1 of 10 reviewed.
Started: 2026-08-06. Lane: `lane/175`.

## Why this document lives in `docs/` and not `records/`

`records/evidence/` is the precedent for vendored material and `records/` is
append-only under REC-01. This document is written incrementally — one repository
at a time, with earlier sections corrected as later ones contradict them — so
committing it under `records/` would manufacture exactly the unclearable
mutation warns #171 is open about. A review that must be revised while it is
written belongs in `docs/`. Anything here that hardens into a claim moves to
`records/claims/` through ADR-0004's re-measurement, not by being filed in a
different directory.

## The filter, restated

Take only what a reader who does not trust this review can re-derive: code at a
pinned sha, a test and what running it did, a number with its run. Leave README
architecture, self-reported benchmarks, and roadmaps. Where a README and the
code disagree, the code wins and the disagreement is itself recorded.

Because selection is fit-first rather than star-ranked (#175, amended
2026-08-06), the evidence bar rises rather than falls for the small repositories:
last-push and archived status are recorded for every entry, cited tests are run
or reported as not-run with the reason, and anything surviving only because
nobody has checked it is labelled unverified rather than quietly promoted.

## Environment constraint, stated once

The review host has `node` and `python3` but **no Go toolchain**. Go repositories
therefore have their tests read but not run, and every such case says so at the
point it matters. This is a real limit on extraction 2 for those repositories and
is not softened anywhere below.

---

# 1. plandex-ai/plandex

- **Pinned:** `e2d772072efadbe41d2946d97d79be55532dbab5`
- **Last push:** 2025-10-03 (10 months before this review). Not archived.
- **Stars:** 15.6k. **Criteria:** 5/5 — the closest fit of anything surveyed.
- **Tests:** 6 `_test.go` files repo-wide. **Not run — no Go toolchain on the
  review host.** Read only.

## Code / features

**Nine named roles, each bound to its own model, with typed fallback chains.**
`app/shared/ai_models_roles.go:6-17` declares `planner`, `coder`, `architect`,
`summarizer`, `builder`, `whole-file-builder`, `names`, `commit-messages`,
`auto-continue`. `app/shared/ai_models_packs.go:125-192` binds them: the planner
takes `anthropic/claude-sonnet-4` or `openai/o3-high`, the builder takes
`openai/o4-mini-medium`. Judgment gets the strong model; execution gets the cheap
one.

That is **#178's decision, reached independently by a shipping product** — but
recorded here as convergence, not as evidence. Nothing in the repository measures
the split; it is their design choice sitting next to ours. It raises confidence
that the shape is natural, and it proves nothing about whether it is right.

**Model selection is a function of input size, not a fixed rung.**
`ModelRoleConfig.GetRoleForInputTokens` (`app/shared/ai_models_large_context.go:47`)
takes the estimated input tokens, compares them against the role's declared
`MaxTokens`, and walks `LargeContextFallback` until one fits.
`GetRoleForOutputTokens` does the same against `GetReservedOutputTokens`.

**This is the closest thing in the survey to #158.** Our issue says no rung
declares its context window, so the decomposer's ceiling is a chosen number.
Plandex declares the window per model and *routes on it* — the ceiling is derived
rather than picked, and input and output are separate chains because they fail
differently. Whatever #158 builds, this is the shape to argue against.

## Tests / verification

**A differential syntax gate.** `app/server/model/plan/build_structured_edits.go:224`
runs tree-sitter validation on the post-edit file **only if** three things hold:
a parser exists for the path, the *pre-edit* file parsed clean
(`preBuildStateSyntaxInvalid`, set at `build_load.go:189`), and the pre-check did
not time out (`syntaxCheckTimedOut`, 500ms limit at `validate.go:15`). Three
different not-a-worker-failure conditions, each tracked separately.

**mcgyvr already holds this line, and holds it finer.** `gate/acceptance.py:123`
refuses to judge against a baseline it cannot establish
(`acceptance-baseline-failing`, `acceptance-baseline-timeout`), and
`gate/adapter.py:17` attributes findings to added lines so pre-existing state
cannot fail a worker at all — per-line where plandex is per-file. **No new issue.
Recorded as convergent and already covered**, which is a result rather than a
gap.

**Six test files in a 15.6k-star repository**, none covering role selection,
fallback, or model dispatch. The tested surface is the deterministic string
machinery — `structured_edits_test.go` (33k), `unique_replacement_test.go`,
`subtasks_test.go`, `reply_test.go`, `whitespace_test.go`,
`tell_stream_processor_test.go`. Extraction 2 from this repository is therefore
thin, and the thinness is the honest finding: the parts a reader would most want
corroborated are the parts nothing corroborates.

## Insights / wisdom

**The fallback chain degrades silently at its end, and the code says so.** The
comment above `GetRoleForInputTokens` reads: "note that if the token number
exceeds all the fallback models, it will return the last fallback model." So a
request larger than every declared window is dispatched to a model that provably
cannot hold it, rather than refused. `maxFallbackDepth = 10`
(`ai_models_large_context.go:3`) does the same on the other axis — it `break`s
out of the walk and returns whatever it was holding.

mcgyvr has already chosen the opposite, in writing: `decompose.py`'s "a request
that cannot be decomposed produces an explanation… a degenerate single contract
is worse than a refusal, because it looks like a plan." **This is the failure
mode #177's second rider names — a silent stop at a depth nobody chose —
observed in production code rather than argued from first principles.** Worth
citing there; no new issue.

**The token reserve is multiplicative, and flat.**
`inputTokens = int(float64(inputTokens) * (1 + paddingPct))`
(`ai_models_large_context.go:53`), with `TokenEstimatePaddingPct: 0.10` repeated
across every model in `ai_models_available.go` (`:148`, `:177`, `:205`, `:233`,
`:250`).

**#173 argues this exact shape is wrong** — that a prompt-fit reserve is
multiplicative while the backend's overhead is additive, so a percentage cannot
cover both. Plandex ships the multiplicative form at a flat 10% for every model.

State the limit of that observation precisely: **it corroborates that a second
system needed a reserve and reached for a percentage; it is not evidence that the
percentage works, and nothing in the repository measures whether it does.** A
second system making the same modelling choice is a reason to check the
reasoning, not a reason to adopt or to dismiss it.

**Decomposition is parsed out of markdown with a string split and a regex.**
`app/server/model/parse/subtasks.go:10` splits the model's reply on `### Tasks`,
falls back to `### Task`, and returns `nil` — logging, not erroring — when
neither heading appears. Tasks are then recognised by `^\d+\.\s`. One test
covers it.

The whole plan for a coding run is recovered from prose by heading match, with a
silent empty result as the failure mode. mcgyvr's decomposer emits through the
public contract loader as its only exit, so a malformed proposal becomes a
refusal carrying the loader's own message. **#174 — a fenced refusal parsing as
file content — is this same family of bug in our own codebase**, and this is
what the mature version of that mistake looks like at 15.6k stars.

## What has no home

Nothing from this repository was left homeless — but nothing from it became a new
issue either. Every transferable item landed as corroboration for a decision
mcgyvr had already made (#178, #177) or as an argument-shaped input to one that is
open (#158, #173). **A first repository that files zero new issues is a
legitimate outcome**, and per #175 it is stated rather than padded.
