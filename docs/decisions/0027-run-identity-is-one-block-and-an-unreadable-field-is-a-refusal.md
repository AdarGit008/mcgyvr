# ADR-0027 — run identity is one block, and an unreadable field is a refusal

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0024 (its 2026-08-13 amendment said identity is content and did not
say what the record looks like; and its matching key, which transfers a null to
denominators it never saw)
Relates: ADR-0026 (lens 2, mutants; lens 3, a record states the property),
ADR-0019 D2 (a null is measured per tier), ADR-0018 Q3 (the round boundary)
Date: 2026-08-16
Issue: #265

## Context

Two decisions already exist above this one and neither closes it.

**ADR-0026** decided the principle: three fields change from a name to content —
the bar, the model and the condition. It did not say what the records look like.

**#276** decided which fields may enter the comparability key, and in what order
the work lands: *a field enters the key iff, holding all others fixed, changing
it alone flips more verdicts than the declared bound*, with recording explicitly
unconditional and ungoverned by that rule. It did not say what recording means
either.

Between the two sits the encoding, and three lanes are already waiting on it:
**#256** cannot pick a reserve stratum until a run says which model it ran,
**#262** needs the bar half, and **#231**'s check 2 cannot tell its two
conditions apart. Answered three times it produces three naming conventions,
three rules for "unobtainable" and three hashing conventions — and the guard is a
**single tuple**, so three lanes editing it is three chances to name one field
short. That is verbatim the defect ADR-0026 warns about, which would make this
the fingerprint machinery built by way of the failure it exists to prevent.

## What is on disk, measured 2026-08-16

139 manifests under `records/measurements/`, counted on the tree at `d67dab86`.
A manifest count is only meaningful with its population and commit stated — the
figures in circulation (123 on #265, 133 on ADR-0024's amendment, 139 on #276)
are three different days, not three disagreements.

| field | manifests carrying it | what it holds |
|---|---:|---|
| `protocol` | 139 | `openai` on 136 — ollama's OpenAI surface is identity-free |
| `endpoint`, `model` | 136 | the model is a **mutable tag** on all 136; 0 digests |
| `tasks_sha256` | 136 | the contract, **not** `accept.py`'s bytes (#276 §3.1) |
| `bundle_sha256` | 133 | the **system** prompt only (`tools/breadth/measure.py:915`) |
| `tier` | 132 | |
| `condition` | 40 | a bare string |
| `serving_build` | 28 | the one content-derived identity field the project has |
| `gate_rungs` | 14 | five **names**, byte-identical across 328 ruff rules and 66 eslint |
| `round`, `product_sha256` | 6 | |

Three of the 139 are hand-authored evidence records whose `protocol` is a
paragraph of prose rather than a wire protocol. They are not machine-written and
are not made to conform; they are excluded by shape, not by exception.

**And the guard fails open.** `require_comparable` compares
`manifest.get(key)` across cells, so a key **absent from every cell** yields one
value and passes:

```
model         {'"qwen2.5-coder:1.5b"'}  pass
tasks_sha256  {'"aaa"'}                 pass
model_sha256  {'null'}                  pass      <- nothing writes this field
```

This is the load-bearing fact for everything below. Adding `model_sha256`,
`bar_sha256` and `prompt_sha256` to `COMPARABLE` today would change no behaviour
whatsoever and would read, to every later reader, as having checked. **A record
shape and a refusal-on-absence have to land together or neither is worth
landing.**

Five lists disagree about what identity is: `report.COMPARABLE` (11 keys),
`report.read_cell`'s required set (4), `report.BOUND_MATCH` (4), the breadth
resume drift check (every key it writes, 14) and the bundle resume drift check
(6).

## Decision

> **DECIDED (2026-08-14 in session, owner; recorded 2026-08-16).**
>
> **D1 — identity is four groups, one block, one module.** The groups are the
> **model**, the **request**, the **server** and the **bar**. One block in
> `run.json`, produced by one module that both runners and the reporter read, so
> the guard cannot fall behind what is recorded. ADR-0026's three fields were
> not complete: the **server** is the missing one and it has already cost a
> contrast — 0.32.4 against 0.32.5 in the scaffold ablation.
>
> **D2 — three states for a value, and no sentinel string.** A **value** means
> obtained. **`null` with a reason** means asked and refused. An **absent key**
> means the record predates the contract. One rule, all four groups, so
> `read_cell` can treat them uniformly.
>
> **D3 — a field the guard cannot read is a refusal, not a match.** Absence
> agreeing with absence is the failure demonstrated above, and `null` agreeing
> with `null` is the same failure: an endpoint that would not name its build
> twice may have named two different builds. Where a record predates the
> contract the refusal names the record and the field, and the caller may read
> it under the old key **explicitly** — never silently. A **single** record is
> never refused for what it could not answer: the defect is two records agreeing
> by shared absence, and one record agrees with nothing. What the reader is owed
> either way is the *statement* of what went unchecked, printed beside the
> numbers rather than left in the shell history of whoever ran it.
>
> **D4 — every digest is computed by the module, never typed by a caller.**
> `--condition` was a caller-supplied identity field and eight manifests
> described a render nobody ran; ADR-0024 D4 already settled that a field
> derived at the point of recording cannot be forgotten by a fourth driver.
>
> **D5 — the key is the whole block minus one contrast axis, named in the
> call.** Membership follows #276's admission rule. The four bound-key fields —
> model, tier, bar, build — are admitted by construction and exempt from it
> (#276 corollary 3); everything else is **recorded now and keyed when
> perturbation admits it**.
>
> **D6 — the prompt as sent is hashed whole, and keyed within a condition
> immediately.** Two cells that name the same condition and differ in the
> rendered prompt are refused today, with no admission experiment, because that
> contrast is *within* the axis rather than across it. Prompt wording is the
> largest measured effect in the literature this campaign surveyed — up to 76pp
> — and we hash the system half.
>
> **D7 — a second block, `observed`, in its own file.** Captured as
> comprehensively as the endpoint will answer, compared by nothing, written
> beside `run.json` so identity stays diffable. Comprehensive *after* redaction
> and through baseline scrub like every other record. Promotion from `observed`
> into identity is the owner's, enforced by ownership of the module rather than
> by a sentence — a rule that is only written down is ADR-0026 lens 3's defect.
>
> **D8 — the 139 are tagged in place, and nothing is re-run.** Three tags:
> **`verified`** — ran with a full fingerprint, clean; **`backfilled`** — NOT
> clean, never read, a dormant insurance label; **`no_fingerprint`** — never
> trusted, no promotion path. Rig time goes to new runs done properly rather
> than to repairing old ones.
>
> **D9 — `cells` joins `matching` in `reproducibility.json`.** A bound keyed on
> model, tier, bar and build but not on its own denominator transfers to subsets
> it never saw: 1.47pp measured over 257 cells is ~7x too strict on a 34-cell
> eligible set, where `upper(0, 34) = 10.15pp`. The declaration states it now;
> the check that enforces it is named in the fan-out below, because what counts
> as "the paired set" at report time is #231's question and not this one's.

## Why re-running was rejected, and why archiving was

The owner's first proposal was to archive every pre-fingerprint manifest and
keep only what reproduces under the new one. Three findings closed it:

1. **"Reproduces" is not decidable here today.** `reproducibility.json` had
   `bounds: []` when the question was asked, and `report.py` refuses to qualify
   any delta without one. The bound is keyed on `(model, tier, gate_rungs,
   serving_build)`; there are 33 distinct combinations across the manifests at
   ~40 minutes each. The rule would have blocked #265 on #231 — the inverse of
   what #265 is for.
2. **A re-run would be replacement, not reproduction.** 136 of 139 name the
   model by mutable tag. A tag that has moved reads as "failed to reproduce" and
   archives a correct record.
3. **Three of the eight measurement directories the claims cite never call a
   model at all.** `tokens-2026-08-03` is CLM-0011 — the 2,387 units that are
   #265's own evidence for the 15.0pp model spread — and archiving it strands
   the shipped `ESTIMATE_RESERVE = 0.32` in `gate/preflight.py`.

Label-now-delete-later, with stricter tags than proposed. CLM-0011 stays dark
until a fresh measurement, and **#256 waits for that rather than for a
promotion.**

The tag is **computed on read, never stamped into a manifest** — a stamped tag
claims a fingerprint the run never carried, and goes stale the moment the key
moves. Run against the tree on 2026-08-16, over the 136 machine-written
manifests (`uv run --no-sync python tools/bench/identity.py`):

| tag | count |
|---|---:|
| `verified` | **6** — the 7B bench runs of 2026-08-14, the only ones carrying a round pin |
| `backfilled` | 126 |
| `no_fingerprint` | 4 |

`verified` here is against the key **as it stands**, which does not yet contain
the three digests ADR-0026 asked for, because nothing writes them. When the
fan-out adds a writer and #276's rule admits the field, those six demote to
`backfilled` on their own. That is the property being bought by computing the
tag rather than storing it.

## Consequences

- **`verified` means everything was recorded. It never means the run
  reproduces.** Greedy decoding is not deterministic and cannot be made so
  cheaply: the cause is batch-invariance, not atomics, and under continuous
  batching the batch shape is a function of other traffic. vLLM #23138 is the
  clean natural experiment — a single client deterministic over 70+ rounds,
  ~1/3 of pairs differing under concurrency. So re-run-and-compare is a
  **positive signal only**: identical is informative, different is uninformative
  without controlling concurrency, precision, tensor-parallel size and CUDA
  graphs. A tag that promised reproduction would promise what the physics does
  not give.
- **A seed at temperature 0 is a category error, and is observed rather than
  set.** Greedy bypasses the sampler RNG. Recording `seed: null` states a fact;
  setting one is a different experiment that would silently re-baseline every
  measurement made before it (#276's perturbation set, item 9).
- **The model digest is nearly free, on a path we do not use.** `/api/tags`
  carries a manifest digest that `src/mcgyvr/detect.py:353-358` already fetches
  and discards — it keeps `name` off each row and drops the rest. But it is the digest of the *manifest file*, and moves when the
  template, system or licence layer changes — the separable weights identity is
  the model **layer** digest, which needs manifest parsing. And `model_info +
  tensors` is necessary but not sufficient: `tensors` carries shape and dtype,
  not weights, so a fine-tune has identical shapes. **Different digest ⇒
  different model is sound; same digest ⇒ same model is not**, and the gap sits
  exactly where identity matters most — #189 was a fine-tune contrast.
- **The tag cannot be pinned, so identity is captured at request time.** The
  `@digest` grammar exists in ollama's `types/model/name.go` and the parser
  discards it. All 136 machine-written manifests use `protocol: openai`, whose
  `system_fingerprint` is the hardcoded constant `fp_ollama`; the native
  endpoints must be probed alongside the dispatch path.
- **It withdraws half of one ADR-0024 consequence and keeps the other half.**
  *"An endpoint that will not name its build records `null`"* stands — unknown
  is a value and a guess is not, and a rate from a single run whose build is
  unknown is still a rate. What does not stand is `null` counting as
  **agreement** between two runs. `report.read_cell` therefore still admits a
  cell with an unknown build, and `require_comparable` no longer lays two of
  them beside each other without being told to.
- **Every pre-round table was passing a check it was not performing.** `round`
  and `product_sha256` are carried by 6 of 139 manifests, so under the old guard
  every table of older cells compared them and found them equal. Those tables
  now need `--allow-unfingerprinted`, and print the fields they could not check.
- **This ADR widens what a resume refuses.** Every field in the block joins the
  drift check in both runners, which is the point: the breadth check already
  refuses a changed temperature, and a changed bar is a larger difference than a
  changed temperature.
- **The bar is hashed as the resolved rule list, not the config files.** A
  config that says "recommended" hides 328 ruff rules against 66 eslint. Both
  tools answer: `ruff check --show-settings` and `eslint --print-config`.
- **The round boundary applies.** Every field added here moves
  `product_sha256`, so the identity changes land as one range before `r2` opens,
  with no dispatch in between (ADR-0018 Q3, #276's sequencing).

## What this does not decide

Named so they are owned rather than absorbed, and so a reader does not mistake
this document for the work:

| | owner |
|---|---|
| computing the model, bar and prompt digests | #265 fan-out |
| the `observed` probe set and its schema | #265 fan-out |
| wiring the two runners' resume drift checks to the module — the reporter reads it today, the runners still carry their own lists | #265 fan-out |
| moving the 139 into tag directories, and the 164 machine-read path references it rewrites | #265 fan-out, separate from this shape |
| enforcing D9 — refusing a bound whose `cells` do not match the set being described | #231, with #276's rule |
| `bound_flips` — #276's formula, which nothing implements | #276 fan-out |
| the null re-measurement bill the new key multiplies | #231 |
| `accept.py` and `accept.mjs` outside the task digest | #276 §3.1 |
| a crashed linter scoring as a clean pass | #261 |
| `pyproject.toml`, `eslint.config.mjs`, `uv.lock`, `data/task-catalog.json` outside `product.SURFACE` | #276 §3.4 |
| sampler state — `num_ctx`, `top_p`, `top_k` sent explicitly | #231 |

**Stated residual:** a field that varies, was never varied, and stays inside the
bound is invisible to the record, to the mutants and to the guard alike. The
record carries what was done to look — the surface digest, the perturbations
run, the bound applied — rather than a claim of completeness.

## Amendment — 2026-08-16 (#289): the "~40 minutes each" is not a per-cell cost

The rejection argument above prices 33 distinct bound combinations at *"~40
minutes each"*. The count and the conclusion stand; the rate does not, and it is
amended here rather than left quotable, because the same constant was corrected
in `reproducibility.json` on the same day and a figure that survives in one
document has not been replaced.

Measured from the r1 nulls (`tools/bench/rate-card.json`, #289), a null's wall
clock at n = 257 runs **19.6 to 52.1 minutes** by `(model, tier)` — a 2.66x
spread, with the flat 40 being 2.0x too high for the cheapest cell and 23% too
low for the dearest. The cost is a rate, not a constant:

> `wall_minutes = 2 * (n * rate / 60 + 1.67)`

Two corrections that change how the number should be used rather than only its
size:

1. **The setup term is additive, not proportional** — 1.64-1.72 minutes per
   pass, flat across passes three times apart in duration. So a total depends on
   how many *passes* it is cut into, not only how many tasks it contains, and a
   percentage overhead gets both short and long sweeps wrong.
2. **The 33 combinations do not each need a run.** #289 established that a
   subset of an already-paired set is itself already paired, so a bound over any
   subset is a recomputation over verdicts on disk. Where the 33 differ only in
   denominator, the marginal cost is **zero** — which strengthens this section's
   rejection rather than weakening it.

Nothing in D1-D9 changes. The affected sentence is the cost estimate inside the
"why re-running was rejected" argument, and the rejection is more securely
grounded after the correction than before it.
