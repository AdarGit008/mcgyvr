# ADR-0002 — Merge protection on the default branch

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

GOV-01 (merge protection active on the default branch) and GOV-02 (strict
up-to-date merges plus conversation resolution) stood as open warnings. Both
are live reads of the forge, not greps of intent: before this record the
answer was `rules: none, protected flag false` — no ruleset, no classic
protection, nothing.

`main` was nonetheless green. It was green because `baseline admit` was run
by hand before every merge, on every lane so far. That is a habit, not a
control: it holds exactly as long as the person merging remembers, and it
cannot survive the delivery path this project is building, where mcgyvr
itself opens the pull requests.

The reason to hesitate was real. This is a solo repository worked by parallel
agent lanes, and strict protection changes the surface that mcgyvr's own
delivery path (#54, #55) gets dogfooded against. There is precedent for
skipping these two: the vendored baseline's own demo repo carries them as a
named private case.

That precedent does not transfer. It rests on CONTRACT.md's third rung —
*private repo, free plan: nothing is bindable* — where admit can only ever be
advisory and the honest guarantee is detection rather than prevention. This
repository is **public**, which puts it on the second rung: a required check
plus "require branches up to date" is available on any plan, at no cost. The
choice here was not between prevention and detection under a constraint. It
was between prevention and detection with prevention sitting free on the
table.

## Decision

**Merge protection is enabled**, as a repository ruleset on the default
branch, configured as code in [`.github/rulesets/main.json`](../../.github/rulesets/main.json)
and created from that exact file:

```sh
gh api -X POST repos/{owner}/{repo}/rulesets --input .github/rulesets/main.json
```

Four rules, each answering something that could otherwise go wrong:

- **`required_status_checks`** on `baseline` and `test`, both pinned to the
  GitHub Actions integration id so another app cannot post a check by those
  names. `strict_required_status_checks_policy` is **true** — this is the bit
  that carries GOV-02 and the one that matters most. It forces re-derivation
  at the merge-relevant SHA, so a branch that was green against an older
  `main` cannot merge green against the current one.
- **`pull_request`** with `required_review_thread_resolution` true and
  **`required_approving_review_count: 0`**. Zero is not a weakening; it is the
  only honest number. GitHub does not let an author approve their own pull
  request, so on a solo repository any value above zero is not "more review",
  it is a deadlock. The gate here is CI plus up-to-date plus resolved
  conversations — not multi-party authorization, which this repository does
  not have and should not pretend to.
- **`non_fast_forward`** — blocks force-pushing `main`, the other half of what
  GOV-01's title names.
- **`deletion`** — blocks deleting it.

**No bypass actors.** `bypass_actors` is empty, deliberately. CONTRACT.md's
"Layer 0, named" reasons that a repo admin can always bypass protection so the
valve should be documented rather than hidden — but that reasoning describes
*classic* protection, where admin exemption is implicit. Rulesets grant no
implicit exemption: a bypass exists only if it is listed. Listing one would
have created a standing valve that classic protection's logic assumes but
rulesets do not actually impose.

The escape hatch is therefore **disabling or editing the ruleset**, which
requires admin, is recorded in the audit log, and takes a deliberate act. That
is strictly better than a standing bypass: same capability, more friction,
same visibility.

## Consequences

- GOV-01 and GOV-02 pass, on a live read of enforcement rather than a
  committed file. The file in `.github/rulesets/` is the reproducible source;
  it is not what the gate believes.
- Every lane now merges through the same gate by construction, and the
  hand-run `baseline admit` becomes a check rather than the control.
- Strict up-to-date incidentally kills a recurring lane failure: a branch cut
  from an older `main` whose CI lacked a later workflow fix could pass its own
  PR run and fail on push. It must now carry current `main` before it can
  merge, which is exactly the fix that was being applied by hand.
- **The deadlock this creates, named:** if a change breaks the workflow file
  such that `baseline` or `test` never report at all, a required check that
  never arrives blocks every pull request, including the one that would fix
  it. With no bypass actor the recovery is to disable the ruleset, merge the
  fix, and re-create it from `.github/rulesets/main.json`. This is the
  accepted cost of the empty `bypass_actors`, and re-creation is a single
  command precisely so that it stays cheap.
- Open dependabot pull requests predating this record will need to be brought
  up to date before they can merge. That is the rule working.
- Nothing in the toolchain pushes to `main` directly — lanes push to `lane/*`
  and merge by pull request — so the lane workflow is unaffected apart from
  the merge point, which is the point.
