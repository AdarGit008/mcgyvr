# ADR-0025 — the JavaScript lint bar is the project's, and it mirrors Python's

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0021 (a paired arm's bar is part of the contrast, not of the
language)
Amended-by: ADR-0026 (2026-08-13) — the premise is withdrawn, the decision
stands; ADR-0034 (2026-08-16) — this record's Context reads the adapter as
recording an environment issue on a failed invocation, and it records nothing;
ADR-0035 (2026-08-17) — this record's Context leaves the *format* half of the
JS/TS scoring-bar undeclared, and the ceiling record declares and pins it
Date: 2026-08-13

## Context

`src/mcgyvr/gate/adapters/javascript.py` shells to `eslint`. eslint 9 requires a
flat config file, there was none anywhere in this repository, and the adapter's
own error handling classifies a failed invocation as an **environment issue**
rather than a finding. No findings is a pass.

So the JavaScript lint rung has never rejected anything — not on a rig, and not
in the product. It appeared in `Gate.run`'s rung list, it appeared in every
manifest that recorded which rungs scored a run, and it was decorative.

This was found in #113, which makes the bench score through `Gate.run` so that a
bench verdict and a production verdict are the same verdict. It is the third
instance of one shape inside a week:

| what looked healthy | what was true |
|---|---|
| ruff, installed, no config staged | applied a rule set far wider than the project selects — `TRY004` alone rejected 75 of 257 reference solutions |
| eslint, absent | scored as "inconclusive", so the TypeScript arm was scored by three rungs while Python was scored by five |
| eslint, installed, no TypeScript parser | emitted severity-1 warnings while the adapter counted severity-2 — the rung ran and could not reject |

**The decision could not be deferred, because deferring it makes a choice.** The
options were never *"author a standard, or have none."* They were *"author a
standard, or keep a rung that reports health while passing everything."* An
absent rung is visible in an inventory; an inert one is not.

## Why this is not the bench's decision to keep local

The bench forced the question but cannot own the answer. There is no prior
JavaScript configuration in this repository to inherit, so the first one written
*is* the project's statement of what the gate rejects in JavaScript — for every
consumer of `Gate.run`, not for `tools/bench/` alone. Recording it here rather
than leaving it as an unremarked file in a bench lane is the point of this ADR.

## Why the arms must be matched, not each optimised

Every arm on #113's bench is a **paired ts/py comparison** — ADR-0021's whole
denominator, and where ADR-0019 showed the power actually lives. A bar that is
materially harsher on one language does not surface as "a stricter bar." It
surfaces as a **language effect**, sitting inside every contrast the bench will
ever publish, and it is not separable after the fact.

`pyproject.toml` selects a moderate, correctness-leaning set — E, F, W, I, N, UP,
B, SIM, RUF — and deliberately not the whole catalogue. The matching choice for
JavaScript is the analogous tier, not the strictest available one.

## Decision

> **DECIDED (2026-08-13, owner).**
>
> 1. **`eslint.config.mjs` at the repository root is the project's JavaScript
>    and TypeScript lint standard**, and it binds the gate, not just the bench.
> 2. **The rule set is `@eslint/js` `recommended` plus `typescript-eslint`
>    `recommended`** — real defects and dead code, not house style. It is chosen
>    to be the analogue of `pyproject.toml`'s select, and the two move together:
>    a change that hardens one arm without the other is a change to every paired
>    contrast.
> 3. **What is excluded mirrors `extend-exclude`.** `tools/baseline/` is vendored
>    and hash-pinned (REC-06); the task corpora are instrument material fixed by
>    digest in their admission manifests. A formatter run in either does not tidy
>    anything — it invalidates a pin.
> 4. **A declared rung must be shown able to reject, per language, or the run is
>    refused.** `CANARY_EXPECTS` in `tools/bench/score.py` names which rungs each
>    language's canary must trip. "Installed" is not the property; "able to say
>    no" is.
> 5. **The toolchain is pinned and installed, not assumed.** `package.json` and
>    `package-lock.json` pin eslint, prettier, typescript and typescript-eslint;
>    CI installs them with `npm ci`; and every package the config imports by name
>    is a *direct* dependency.

## Consequences

- **Changing the rule set re-bases every JavaScript rate measured under it.** It
  is cheap to overrule today, while nothing has been measured. After the arms run
  it costs a re-run of every JS cell. That asymmetry is the reason this record
  exists now rather than after the first result.
- **A rung that cannot reject stops the run instead of shrinking the bar.** This
  is the honest failure and it is louder than the alternative: a sweep refuses
  with a named reason rather than publishing a rate scored by fewer rungs than it
  declares.
- **`@eslint/js` is a direct devDependency although eslint already provides it.**
  As a hoisted transitive it resolved by luck, and the failure mode if hoisting
  changed is exactly the one this record removes: config fails to load, adapter
  scores inconclusive, rung passes everything.
- **CI installs the JS toolchain in the `test` job**, so the able-to-reject check
  runs there rather than skipping. A check that silently skips is the same defect
  as a rung that silently passes, one layer out.
- **Pinning the toolchain makes the parser version part of the instrument.** A
  lint bar is only reproducible if the tool that applies it is; this is the same
  argument ADR-0024 makes for the serving build, applied to the scorer.
- **This does not settle formatting.** `prettier` and `ruff format` are the
  `format` rung and were already able to reject. The separate finding that a
  zero-token deterministic normalisation before the gate is worth +13.7pp is a
  *lever* to be measured on the bench, not a change to this bar.
- **The repository's own JavaScript is not yet held to this bar.** `make lint`
  runs ruff only; `npx eslint .` is clean today but nothing keeps it so. That is
  a separate decision, because it makes every contributor's setup depend on
  `npm ci` — and it is a smaller question than this one, which is about what the
  gate rejects in a *worker's* output.

## Amendment — 2026-08-13 (ADR-0026): the premise is withdrawn, the decision stands

**The decision clauses of this ADR are unchanged.** JavaScript has a bar, it is
the project's rather than the bench's, and the preflight positive control that
proves a rung can reject stays exactly as adopted.

**The premise is withdrawn.** This ADR chose eslint `recommended` to mirror
ruff's moderate select, and argued the two "move together" because a bar
materially harsher on one side reads as a language effect inside every paired
contrast. That was asserted from rule *intent* and never measured. Measured the
next day:

| | eslint, in the scored workspace | ruff, as this project selects |
|---|---|---|
| rules | **66**, all `error` | **328** |
| whitespace / line-length / import-order / naming | **none** | **133 (41%)** in `E W I N UP` |
| rejections, same 257 problems | 32 | 154 |

The consequence is the one this ADR was written to prevent, one level below where
it looked: **the bar reverses which arm leads.** Under the full bar the arms read
py 8.9% / ts 12.8%; scored on correctness alone they read py 27.3% / ts 23.9%.

Two arms cannot be laid beside each other under these bars, and ADR-0026 records
the rule that follows — no pooled figure across a stratum where the effect is
heterogeneous, and no lever result transfers across languages without
measurement. Matching two rule sets by intent is not matching them; the bar is
now a property to be recorded and compared, not a claim to be made in prose.

## Amendment — 2026-08-16 (#261): the severity filter is a decision, and here it is

`javascript.py` counts only eslint severity `2`; `python.py` counts every ruff
diagnostic it is handed. The asymmetry was written as a comment on a constant
and had never been recorded as a choice, which under ADR-0026 lens 3 makes it
an unstated part of the bar. #261's four-lens sweep found it while auditing the
adapter's error handling, and it is settled here rather than in the code.

**It changes nothing today.** Under the current `eslint.config.mjs` all 66
enabled rules are severity `error`; the filter drops zero messages. The
asymmetry is real in the code and not yet real in the output.

> **DECIDED (2026-08-16, owner). The filter stays**, and this clause — not
> `_ESLINT_ERROR` — is where it is changed.

The two tools do not mean the same thing by a non-fatal finding, so counting
"every diagnostic" on both sides would match the *implementations* while
unmatching the *bars*:

- eslint's severity is a **property of the project's config**. Setting a rule to
  `warn` is this repository saying, in the file ADR-0025 clause 1 made the
  standard, that tripping it is not fatal. Rejecting a worker for it would have
  the gate overrule the standard it is enforcing.
- ruff has no such dial in what the adapter receives. `pyproject.toml` selects
  rule *families*; a selected rule that fires is a diagnostic, full stop. There
  is no severity to honour, so counting them all is honouring the config, not
  ignoring a severity.

Symmetry here is between what each config *declares fatal*, which is what both
adapters now implement — and the 2026-08-13 amendment above is the standing
warning against matching two rule sets by intent instead of by measurement. The
day a rule in `eslint.config.mjs` is set to `warn`, that is a deliberate
narrowing of the JavaScript bar by the file that owns it, and ADR-0026's rule
applies: it is a bar change, recorded per run, and it re-bases every JavaScript
rate measured under it.
