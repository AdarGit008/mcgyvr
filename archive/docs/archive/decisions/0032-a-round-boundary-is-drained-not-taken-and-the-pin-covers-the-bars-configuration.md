# ADR-0032 — a round boundary is drained, not taken, and the pin covers the bar's configuration

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0018 (Q3 — makes the round boundary's batching rule operational and
locates it in the repository), ADR-0027 (the `bar` group's stated justification,
which was false for the half of the bar that lives in configuration)
Relates: ADR-0025 (the eslint config binds the gate, not just the bench),
ADR-0021 (the paired ts/py denominator), ADR-0024 (the tool that applies a bar is
part of the instrument), #276 (the admission rule this defers to)
Date: 2026-08-17
Issue: #291

## Context

#276 closed with two of its four acceptance boxes unmet and no owning issue took
either. Both are properties of the round pin, and they fail in the same
direction: **the pin does not hold what the project believes it holds.**

### The batching rule existed only in the body of a closed issue

#276 decided that every identity change lands before `r2` opens — one
re-baseline rather than several — because each of them moves `product_sha256`,
and landing them piecemeal with runs in between converts one re-run into several
incomparable ones. Its own acceptance box asked for that rule in
`tools/bench/rounds.json`'s doctrine or an ADR amendment, *"so a fourth driver
cannot route around it"*.

Checked on the tree at `97173b2a`: `rounds.json` carried one top-level key,
`rounds`. ADR-0018 carried no amendment. `product.py` never mentioned batching.

What `product.py`'s docstring said instead is true and is the misleading half:

> A round is closed by opening the next one, which is the only place an adopted
> change may land; the new entry names what was adopted.

That says *a* change lands at a boundary. It does not say *all* pending identity
changes batch into one. A driver on lane/261 read exactly that paragraph on
2026-08-16, concluded their change warranted a round of its own, and recommended
it; the recommendation was withdrawn only because someone thought to re-read a
closed issue. The rule was one memory away from being lost, and `_open_cli`
appended unconditionally — no check, no warning, nothing between the conclusion
and a closed round.

### The pin covered the scorer and not the scorer's configuration

`product.SURFACE` declared `src/mcgyvr`, `tools/breadth/measure.py`,
`tools/bundle/measure.py`, `tools/bench/score.py`, `matrix.py`, `matrix.json`,
`product.py`. Absent, and each decides a verdict:

| path | how it reaches a verdict |
|---|---|
| `pyproject.toml` | `score.lint_config` (`score.py:146`) reads `[tool.ruff]` at call time and writes it into every workspace |
| `eslint.config.mjs` | `score.stage_js_toolchain` (`score.py:104`) copies it into every workspace |
| `uv.lock` | decides which `ruff` resolves under `uv run` — 328 rules as this project selects |
| `package-lock.json` | decides which `eslint` and `typescript-eslint` the linked `node_modules` supplies — 66 rules |
| `data/task-catalog.json` | the vocabulary `src/mcgyvr/catalog.py` and `contract.py` validate a contract against |

And `surface_files` globbed `*.py` for a directory, so `src/mcgyvr/prompts/`'s
`python.md` and `javascript.md` — the literal system prompts a worker is sent —
sat outside the digest of the code that sends them.

**Why this is worse than a missing field.** ADR-0027 files `round` and
`product_sha256` under the **`bar`** group with this justification:

> `round` and `product_sha256` sit here because the revision they pin includes
> the scorer.

The scorer, yes. The scorer's configuration, no. ADR-0025 clause 1 made
`eslint.config.mjs` the project's JavaScript lint standard *"and it binds the
gate, not just the bench"*, and this ADR's own consequence says a rule-set change
*"re-bases every JavaScript rate measured under it."* Nothing enforced that: a
rule flipped to `warn` narrowed the bar, the product digest did not move, and no
round refused. The grouping's stated reason was false for half of what it named.

## Decision

> **DECIDED (2026-08-17, owner).**
>
> 1. **A round boundary is drained, not taken.** Every identity change waiting
>    on a boundary lands in the same round. This is ADR-0018 Q3's batching
>    corollary and it is now doctrine rather than prose in a closed issue.
> 2. **The doctrine lives in `tools/bench/rounds.json` as data**, under a
>    `doctrine.clauses` array, read by `product.load_doctrine` and printed by
>    `--open`. A clause added to the file is stated by the tool without anyone
>    editing a module. `product.py`'s docstring carries the same rule, because
>    the docstring is where a driver actually looks and the file is the
>    authority.
> 3. **`--open` refuses without `--adopted`**, repeatable, naming each change the
>    boundary carries; the batch is recorded in the round entry, and what moved
>    since the previous round is printed beside it. The tool **records** the
>    batch and does not **verify** it — see below.
> 4. **The product surface covers the bar as configuration and as
>    implementation**: `pyproject.toml`, `eslint.config.mjs`, `uv.lock`,
>    `package-lock.json` and `data/task-catalog.json` join `SURFACE`. Both
>    lockfiles or neither.
> 5. **A declared surface directory contributes every file beneath it, whatever
>    the extension.** The only exclusion is a path derived from files already in
>    the digest — `__pycache__/`, `*.pyc`, `*.pyo` — because including those
>    would make the pin depend on whether the tree had been imported.
> 6. **`bundle_sha256` does not enter `identity.KEY`.** #276's admission rule
>    governs and no perturbation run has been done. Clause 5 closes the coverage
>    gap that made this look urgent.

### Why the tool records the batch and does not verify it

Nothing in `product.py` can know which identity changes are still open. The
checkable proxies are all wrong in the same way: "refuse a boundary carrying one
file" punishes a legitimate single-change round, and "refuse unless every
`v1, area:telemetry` issue is closed" makes a bench tool a client of the issue
tracker and fails closed the day the network does. A gate on a heuristic teaches
drivers to work around the tool rather than the rule.

What is enforceable is that the batch is **named**, in the record, at the one
moment the rule can be broken — and that the driver sees the doctrine and the
moved-file list at that moment rather than in a docstring they may not open. A
named batch is a claim someone can be held to afterwards. A silent append is not.

### Why both lockfiles, and why not neither

The arms are paired ts/py (ADR-0021), and ADR-0025's whole argument is that a bar
materially harsher on one language does not surface as "a stricter bar" — it
surfaces as a **language effect**, sitting inside every contrast the bench will
ever publish, and it is not separable after the fact. Pinning `uv.lock` while
`package-lock.json` floats is that asymmetry rebuilt at the level of the
instrument: ruff frozen inside a round, eslint free to move.

"Neither, and record the tool versions per run instead" is the real alternative,
and it is #262 and #285's mechanism, not this one. It is also strictly weaker
here: a per-run field says two runs differed; the round pin **refuses to
dispatch** the second one. Recording is what you do when you cannot prevent.

## Consequences

- **A dependabot bump now closes a round.** `uv.lock` moves on every Python
  dependency and `package-lock.json` on every JavaScript one, including bumps
  that cannot touch a verdict. Mid-campaign this is a refusal at dispatch, which
  is recoverable by opening a round; the failure it prevents — a ruff patch
  release landing inside a round and re-basing half its arms — is not. This is
  the cost `product.py` already admitted for the coarse surface, now paid on a
  path that moves weekly rather than rarely.
- **The refusal is the right shape for a dependency bump specifically.** A
  driver merging a ruff bump mid-round is told, at the next dispatch, that the
  bar moved. Before this, the sweep ran and the table was silently mixed.
- **The surface can get finer later, and only in one direction.** When #285's
  `bar_sha256` records the resolved rule list per run, "which lockfile entries
  can move a verdict" becomes a measured question rather than a curated guess,
  and dropping a lockfile from the surface becomes arguable. Until then the
  coarse pin is the honest one — a curated subset does not refuse what it omits,
  it permits it silently, which reads as having checked.
- **`identity.py`'s `bar` group justification is corrected, not moved.** `round`
  and `product_sha256` stay in the `bar` group, and the reason is now true: the
  revision they pin includes the scorer *and* its configuration.
- **The prompts are pinned twice, differently, and both are wanted.**
  `bundle_sha256` hashes the system prompt **as assembled at request time** for
  one run; `product_sha256` now covers the prompt **files** for a round. The
  first catches a render that differs from the files; the second catches files
  that moved between two runs. Neither subsumes the other.
- **`bundle_sha256` stays recorded and unkeyed, and this is now a decision
  rather than a gap.** It sits in `identity.GROUPS["request"]` and in `PENDING`.
  Clause 5 is why it is no longer urgent: the prompt files are inside
  `product_sha256`, which *is* keyed, so the round pin covers the prompts even
  though `bundle_sha256` does not enter the key. Admitting it would need the
  perturbation run #276 requires, and #276 corollary 1 is explicit that an
  untested field is recorded and not keyed. `require_comparable` already refuses
  two cells that name one condition and differ in it (ADR-0027 D6) — that is a
  mislabelling check inside the axis, and it is not an admission.
- **The read-time tools are still outside the surface, now stated.**
  `report.py`, `identity.py` and `mode.py` describe runs already on disk and
  neither dispatch nor score. A change to how a table is printed must not
  re-baseline the measurements it prints.
- **`r1-commissioning` no longer matches this tree, by construction.** Eight
  paths joined the digest, so `--check` refuses until a boundary is opened.
  Opening it is not this issue's — #291 is part of the batch that must land
  before `r2`, not the thing that decides the batch is complete.

## Fan-out

| what | where | owner |
|---|---|---|
| `tools/bench/gate_rescore.py` and `lintless.py` score and are unpinned. They restate rates under a *different* scorer, post hoc, so they are not the dispatch surface — but a reader quotes their figures against the gate-scored sweeps | #276 §3.4 named them; this issue's scope did not | unowned, file if `r2` wants it |
| The `bar` group's justification is corrected here; the *field* that records what the bar contained per run is not | `bar_sha256` | #285, #262 |
| `--adopted` records the batch; nothing re-derives whether the batch was complete after the fact | the round entry | out of scope, and probably unenforceable |

## Corrections to #291's own citations

Re-verified against the tree at `97173b2a`, as its fourth acceptance box
requires. Every code citation held except one:

- #291 says *"ADR-0025's 2026-08-16 amendment says in as many words that such a
  change re-bases every JavaScript rate measured under it."* Two errors, one
  harmless. ADR-0025's amendment is dated **2026-08-13** (ADR-0026), not
  2026-08-16; and the "re-bases every JavaScript rate measured under it" line is
  in ADR-0025's **Consequences**, not in the amendment. The claim the citation
  supports is unaffected — the line exists and says that — but the amendment it
  points at withdraws ADR-0025's *premise* and is a different argument.
