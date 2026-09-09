---
record: session/2
lane: lane/266
agent: adar
started: 2026-08-14T12:30:00Z
---

# Session — lane/266 — 2026-08-14

## Did

Opened lane/266 and answered #266's material question. It ended somewhere else:
the bench's resolution, measured honestly, is far worse than any figure the
project has quoted, and the reason is a pooling error I made and the owner
caught.

**#266's own question, answered.** The eligibility count reproduces (198
`function_implementation` per arm of which 34 carry `target_content`, 59
`bug_fix`, 257 total). The finding the issue lacked: those 34 cells are the
**hardest stratum on the bench** — 2.9% at the 7B against 55.9% for `bug_fix`.
A cell passing under neither condition is concordant whatever the lever does, so
the count passing under *either* is an arithmetic ceiling on `m`. That ceiling is
**1, 4, 2, 2** across the four tier×arm cells against ADR-0019's wall of 6, and
both capacity levers make the task *harder*, so the ablated arm can only lose
cells. **Undecidable by construction, at any effect size.** `tools/bench/
eligibility.py` derives it; `tests/test_bench_eligibility.py` pins it.

**The survey that followed, and the two candidates it killed.**
`docs/positive-control-candidates-2026-08-14.md` applied #266's four criteria to
everything the corpus can carry. `nointerface` looked strongest on cost — until
the scan. `tools/bench/prose.py`: the task prose names the function on **99.2%**
of contracts, both arms. The ablation removes a section whose content the model
already has.

**A non-sequitur of mine, caught by an agent and corrected in code.** I argued
`nointerface` was dead partly because "types cannot affect pass/fail — Python
annotations are runtime-inert and no `tsconfig.json` is staged." The premise is
true and the conclusion does not follow: the annotation is an *output* and an
unscored one; the type in `INTERFACE` is an *input* that steers the shape of the
value returned, which the assertions do score. `b244-seat-block` is the standing
case — `-> list` against prose that a tuple satisfies. `type_channel_is_live` is
now `annotation_is_scored`, and the docstring records the misuse rather than
deleting it.

**The corpus contains families, and the screen that would catch them is a third
one nobody has built.** `tools/bench/families.py` cross-executes every
shape-compatible pair — A's reference aliased to B's expected names, run against
B's acceptance, both directions. All three corpora, 115,830 runs:

| corpus | tasks | pairs | duplicates | families |
|---|---:|---:|---:|---:|
| `bench-py` | 257 | 9,806 | 0 | 6 |
| `bench-ts` | 255 | 8,019 | 0 | **6, the same six** |
| `tools/problems` | 499 | 40,090 | 0 | 1 |

The two arms returning identical pairs from independent runs on different
runtimes says the families are a property of the **problem specifications**, not
of either rendering. `b094-relay-chain` and `b172-trace-relay` are one
computation under two stories, at prose Jaccard **0.27** against a 0.55 reject
threshold.

Then the owner pointed at `c0686889`, where `b080`/`b090`/`b168` were removed as
one problem three times — differing only in `{name}` / `%name%` / `<name>`.
**Replayed, this scan misses them entirely**: `b080`'s reference fails `b168`'s
first substantive assertion, because the constant differs. So the prose screen
catches the *parameterised* kind and this catches the *re-skinned* kind, neither
is sufficient, and a duplicate that is both is invisible to both. Filed #268 with
that taxonomy and the third screen it implies.

**Three independent prior-art scans**, at the owner's direction. They converged:
our positive control is **assay sensitivity** (ICH E10, and its rationale is ours
verbatim), the commissioning gate is a **system suitability test** (USP <621>),
null calibration is an **A/A test**, headroom is a **floor effect** with a
citable >15% threshold (Terwee 2007), and `function_A` is **alpha-renaming**,
already built and released as ClassEval-Obf (arXiv:2510.03178). Three unanimous
criticisms: clustered standard errors, exact-vs-mid-p, and post-hoc stratum
exclusion. One decisive warning: arXiv:2505.10443 measured renaming *raising*
accuracy by +14pp on two 7B-class models, so #267's control has an unstable sign.

**The error that mattered, and the owner caught it.** I computed a pooled MDE of
2.9pp and called the bench viable. Both objections are fatal: `bench-py` and
`bench-ts` are not a language contrast but **two bars** (328 ruff rules against
66 eslint, prettier unconfigured, no staged `tsconfig.json`), and *within* one
arm `psi` ranges **0.029 to 0.134** across task types — a 4.6x spread, exactly
the heterogeneity ADR-0026 forbids pooling over. The record said so on
2026-08-13 and check 4's bound was already declared per arm for the same reason.
Recomputed per stratum:

| tier | strata that resolve anything | best |
|---|---|---|
| 1.5B | **1 of 6** | `bench-ts` `function_implementation`, 8.5pp |
| 7B | **0 of 6** | — |

`tools/bench/resolution.py` prints no pooled row and carries both objections as
its reason. The clustering hour is moot: it measured correlation across arms to
justify pooling across arms, which is not permitted. (Its numbers, for the
record: outcome ICC +0.21/+0.33, discordance ICC +0.09/+0.12, design effect
1.09/1.12 — small, because clusters of size 2 cap the effect at 2 regardless.
The "up to 3x" I quoted was imported from a different cluster structure.)

## Left open

- **The chain, settled with the owner and now on #224's body:** signature →
  stratum → required effect size → assumed `psi` → N → N/yield → the price.
  Two terms are unmeasured and they move the price most: the **responsive
  fraction** we can author to (#224) and the **authoring yield** of responsive
  problems. #225's campaign produced 498 and 88% came out frozen.
- **Three corrections that chain must keep**, each got wrong once today: the
  responsive fraction is measured not chosen; `delta <= psi` is hard, so seven of
  twelve strata cannot show a 5pp effect at *any* n; and higher `psi` needs *more*
  n, because `psi` is churn.
- **#265 is upstream of everything**, including the `bench_<tier>_<arm>_<stratum>`
  naming the owner proposed — those are still four labels for three properties we
  do not record. And #265 only *decides* the shape: the model and condition digests
  have no builder issue.
- **#231 check 2 is unchanged.** The known-groups contrast (1.5B vs 7B, m=108 per
  arm 60/48) is the only candidate covering all four cells and costs one same-round
  1.5B re-run — its pair is currently round-mixed. It commissions gross
  sensitivity, not resolution.
- **#267's body predates the scans** and still recommends neutral placeholders;
  the evidence now favours misleading names by 3-6x and warns on sign.
- The prior-art vocabulary has no home in `docs/` yet.

next: #224 is the load-bearing issue now — measure the responsive fraction we can
author to, and the yield, because every other number depends on them
