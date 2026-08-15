# Identifier naming as a manipulation — prior art, and two figures that did not survive re-derivation

Scan date: 2026-08-15. Lane: `lane/266`. For: **#267** (`anonymise`), and #231's
choice of commissioning control.

The 2026-08-14 scans recorded their conclusions in
`records/sessions/lane/266/2026-08-14-resolution-per-stratum-and-the-chain-adar.md`
in two compressed lines and nowhere else. This file gives that half of the
vocabulary a home, and corrects it: **two of the figures the session record
carries are not supported by the sources they were attributed to.**

The correction matters because #267's design decision turns on them. Read the
"What this changes for #267" section if you read nothing else.

---

## 1. The manipulation already exists, and it has a name

`function_A`, `function_B`, … in order of first appearance — #267's proposed
naming rule — is **alpha-renaming**, and it is built, evaluated and released.

**ClassEval-Obf** — *When Names Disappear: Revealing What LLMs Actually
Understand About Code*, Le, Pham, Van, Phan, Phan & Nguyen, arXiv:2510.03178
(submitted 2025-10-03), <https://arxiv.org/abs/2510.03178>.

It evaluates **four** naming conditions, not one, and the distinction between
them is the part #267's body is missing:

| condition | what it does | example from the paper |
|---|---|---|
| **alpha-renaming** | role-preserving positional placeholders | `class1`, `method1`, `var1`, `var2` |
| **ambiguous identifiers** | visually confusable tokens | `llllIII`, `IlllIllllIlI` |
| **cross-domain terms** | identifiers from an unrelated field | `adrenaline_fd`, `glucagon_d6` |
| **misleading semantics** | names implying *incorrect* behaviour | a summing function named `compute_max` |

#267's `function_A` is exactly row 1. The other three rows are the ladder it
does not currently propose, and they are not interchangeable — see §3.

This is a benchmark this project can compare against rather than a design it has
to justify from scratch. It is also, on its own terms, evidence that the
manipulation is measurable: the paper's stated purpose is that ClassEval-Obf
*"reduces inflated performance gaps, weakens memorization shortcuts."*

## 2. The sign is unstable — and it is unstable on our own model family

*Are Large Language Models Robust in Understanding Code Against
Semantics-Preserving Mutations?*, Orvalho & Kwiatkowska, arXiv:2505.10443
(submitted 2025-05-15, last revised 2026-05-07),
<https://arxiv.org/abs/2505.10443>.

Nine models up to 8B — the size class this bench actually runs — under five
semantics-preserving mutations, one of which is renaming variables. The
per-mutation rows for renaming, as printed in the v1 HTML (Tables 2 and 3):

| model | LiveCodeBench: orig → renamed | CruxEval: orig → renamed |
|---|---|---|
| CodeGemma | 38.6 → 34.0 (**−4.6**) | 35.0 → 32.0 (**−3.0**) |
| GraniteCode | 34.0 → 34.0 (0.0) | 32.0 → 32.0 (0.0) |
| Llama3.2 | 41.1 → 35.0 (**−6.1**) | 28.0 → 31.0 (**+3.0**) |
| Mistral | 32.0 → 32.0 (0.0) | 24.0 → 23.0 (−1.0) |
| **Qwen2.5-Coder** | 62.0 → 62.0 (**0.0**) | 59.8 → 61.0 (**+1.2**) |
| SemCoder | 48.0 → 49.0 (**+1.0**) | 50.6 → 50.0 (−0.6) |

Three of twelve model×benchmark cells move **up** under renaming. The largest
drop is 6.1pp; the largest rise is 3.0pp. Seven cells move by 1pp or less.

**Qwen2.5-Coder is this project's model family**, and it is one of the flattest
rows in the table: 0.0pp and +1.2pp.

### Correction 1 — the "+14pp" is not in this paper

The session record states: *"arXiv:2505.10443 measured renaming raising accuracy
by +14pp on two 7B-class models."* **Re-derived against the paper's own renaming
tables, the largest rise on any model is +3.0pp** (Llama3.2, CruxEval), and only
three cells rise at all. No +14pp appears in the renaming rows.

The paper's headline *"drops reaching up to 70%"* is across all five mutations
and is a **drop**, not a rise; it is the most likely source of a transcription
slip, but the two numbers are not related.

What survives: **the sign is genuinely unstable** — that conclusion is correct
and is the important one. What does not survive: **the magnitude**. A manipulation
whose true effect on our model family is somewhere in ±3pp is a different
proposition from one worth +14pp.

*Caveat on this correction:* the numbers above were read from the v1 HTML at
<https://arxiv.org/html/2505.10443v1>. The paper was revised 2026-05-07 and the
revision's tables were not checked. The correction is "not supported by v1", not
"impossible in any version".

## 3. Misleading names are **not** established as stronger than neutral ones

### Correction 2 — the "3–6×" does not hold

The session record's open item states: *"the evidence now favours misleading names
by 3-6x."* ClassEval-Obf's Table 3 measures exactly this comparison, and it goes
**both ways**:

| model | benchmark | alpha-renaming drop | misleading drop | which is larger |
|---|---|---:|---:|---|
| GPT-4o | ClassEval | 6.4 (76.6→70.2) | 5.5 (76.6→71.1) | **alpha** |
| Qwen3-Coder 480B | ClassEval | 6.2 (92.6→86.4) | 8.9 (92.6→83.7) | misleading |
| DeepSeek V3 | ClassEval | 4.5 (90.0→85.5) | 1.2 (90.0→88.8) | **alpha, by 3.8x** |
| GPT-4o | LiveCodeBench | 7.4 (82.9→75.5) | 0.6 (82.9→82.3) | **alpha, by 12x** |
| Qwen3-Coder 480B | LiveCodeBench | 4.8 (99.3→94.5) | 5.5 (99.3→93.8) | misleading |
| DeepSeek V3 | LiveCodeBench | 0.7 (99.3→98.6) | 2.1 (99.3→97.2) | misleading |

Three cells each way, and the two largest ratios in the table run **against**
misleading names. There is no 3–6× advantage; there is no consistent ordering at
all. The paper's own reading is that *"misleading names sometimes produce smaller
accuracy reductions than neutral alpha-renaming."*

### Where the "3–6×" probably came from, and why the comparison is invalid

**CodeCrash** — *CodeCrash: Exposing LLM Fragility to Misleading Natural Language
in Code Reasoning*, CUHK-ARISE, arXiv:2504.14119, NeurIPS 2025,
<https://arxiv.org/abs/2504.14119>. 1,279 questions from CruxEval and
LiveCodeBench, 17 LLMs, **average degradation 23.2%** on output prediction under
misleading textual cues (13.8% with chain-of-thought).

23.2% against alpha-renaming's ~4–7pp is a ratio of roughly 3–6×, which is very
likely the origin of the figure. **The comparison is not like-for-like on any
axis:** CodeCrash's perturbation is misleading *natural-language comments and
output hints inserted into the code*, not identifier names; the task is execution
prediction, not implementation; the datasets differ from ClassEval; and the two
numbers come from different papers with different baselines. Nothing licenses
dividing one by the other.

CodeCrash remains a real and relevant result — it is the strongest evidence that
*misleading NL* is a large lever. It is simply not evidence about *misleading
identifiers* relative to *neutral identifiers*, which is the choice #267 faces.

## 4. The regime gap, stated so it is not forgotten

Every number in §3 comes from frontier models sitting at **76.6%–99.3%** baseline
accuracy. This bench's subjects are a 1.5B and a 7B, and #266's measurement puts
them at **2.9%–55.9%** per stratum, with 88% of cells never passing under any
condition.

A manipulation worth 5–9pp against a 92.6% baseline says close to nothing about
what it is worth against a 2.9% one. Terwee's >15% floor-effect threshold — the
citation the same scan recorded for headroom — is the reason this gap is a
methodological objection rather than a hedge. **No effect size from §1–§3 may be
carried into a power calculation for this bench.** They establish that the lever
is real, that its sign is not guaranteed, and that its neutral and misleading
forms are not ordered. They do not establish a `psi`.

## 5. What this changes for #267

#267's body predates this scan. Read against the above, three of its positions
need to move:

1. **It is not a novel manipulation.** It is alpha-renaming, published as
   ClassEval-Obf. The build is still ours (the four-site staging reach is real
   work), but the *design* should cite and match the published condition rather
   than invent a naming rule.
2. **Its single condition should become the published four.** Alpha-renaming,
   ambiguous, cross-domain and misleading are separate levers with separate
   effects and no established ordering. Collapsing them into one loses the only
   axis the prior art actually resolves.
3. **It is a weak candidate for a *positive control*, and the reason is now
   specific.** A positive control needs an effect of known, reliable sign. On
   Qwen2.5-Coder — our family — renaming measured 0.0pp and +1.2pp. Against
   #266's per-stratum resolution (0 of 6 strata resolve anything at the 7B under
   `norule`; the best 1.5B stratum resolves 8.5pp), an effect plausibly inside
   ±3pp is **not detectable on this bench at any n we can author.**

   That is a stronger objection than "the sign is unstable". It says the
   commissioning control cannot be this, and #231's known-groups contrast
   (1.5B vs 7B) stays the only candidate covering all four cells.

As an **arm** under ADR-0018 Q1 — a thing worth measuring for its own sake —
#267 is unaffected by all of this and the four-condition ladder makes it a better
arm than it was. As #231's **fallback control**, it should be withdrawn.

## Sources

- Le, Pham, Van, Phan, Phan & Nguyen. *When Names Disappear: Revealing What LLMs Actually Understand About Code.* arXiv:2510.03178. <https://arxiv.org/abs/2510.03178>
- Orvalho & Kwiatkowska. *Are Large Language Models Robust in Understanding Code Against Semantics-Preserving Mutations?* arXiv:2505.10443. <https://arxiv.org/abs/2505.10443>
- CUHK-ARISE. *CodeCrash: Exposing LLM Fragility to Misleading Natural Language in Code Reasoning.* arXiv:2504.14119, NeurIPS 2025. <https://arxiv.org/abs/2504.14119>

Retrieval method: `WebFetch` against the arXiv abstract and HTML renderings on
2026-08-15; the CodeCrash figures are from its abstract and project page, not
from its tables. Numbers quoted from HTML renderings rather than the PDFs of
record. Nothing here is vendored under #118, because nothing here is registered
in `records/claims/` — if any figure above is ever quoted in a claim record, it
must be vendored or pinned first.
