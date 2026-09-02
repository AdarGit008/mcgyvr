# Identifier naming as a manipulation — the prior art, and the scan that got it wrong twice

Scan date: 2026-08-15. Lane: `lane/266`. For: **#267** (`anonymise`), and #231's
choice of commissioning control.

> **This file was rewritten the same day it was written.** Its first draft
> concluded that no source measured meaning-stripping identifier renaming in a
> generate-from-specification setting, and that conclusion was escalated in
> conversation to *"nobody has measured our case, so we'd be first."* The owner
> rejected that as an absence claim and commissioned an adversarial scan to
> falsify it. **It was falsified.** At least six published studies occupy the
> cell, one of them inside a paper this file had already cited and dismissed.
>
> The error record is kept rather than erased, in §7. The corrections it makes to
> *other* documents survive; the corrections it made to the literature did not.

---

## 1. The cell is occupied

The cell in question: **task** = generation from a specification plus a signature
with an empty body, scored by executing tests; **manipulation** = identifiers
replaced so their semantic content is removed or corrupted.

| source | task | manipulation | result |
|---|---|---|---|
| **RADAR** — Yang, Zhou, Yang, Yue, Chen & Chen, *ACM TOSEM* 33(3) 2024, arXiv:2211.15844 | spec + signature → body, HumanEval, Pass@1 | method name → `foo`; also random substitution | −5.6% to −17.2% on ≤3B models |
| **ReCode** — Wang et al., ACL 2023, arXiv:2212.10264, §3.4 | HumanEval + MBPP generation, `RP₅@1` | `VarRenamerNaive` → `VAR_0`; `VarRenamerRN` → random string; `VarRenamerCB` → natural name (control) | naive 1.5–16.7%, random 9–55% relative drop |
| **ObfusEval** — Zhang et al., **ICSE 2025**, arXiv:2412.08109 | spec + declaration + project context → whole C function, compiled and run against official suites | consistent identifier rewrite across target *and* context | TPR 21.1 → 15.8 (−25.1%) |
| **Yetiştiren et al.**, arXiv:2304.10778v2 | HumanEval, docstring retained | function name → `foo` | Copilot 46.3→42.1, ChatGPT 65.2→61.6 |
| **BioCoder** — Tang et al., *Bioinformatics* 2024, arXiv:2308.16458 App. M | spec + signature → body, Docker suite, Pass@K | names → `FUNCTION`, `VAR0` | GPT-3.5 Java Pass@1 34.7→30.7; **Pass@20 43.8→47.9 (rises)** |
| **ODEX** — Wang et al., arXiv:2212.10481 App. E.3 | NL intent + signature → body, executed | entry point named by post ID (`f_3844801`) vs meaningful | meaningless **47.15** > meaningful 43.23 — sign runs *against* |

`BigCodeBench` (ICLR 2025, arXiv:2406.15877) does not ablate, but records the
practice as routine: *"We first replace the semantic-rich program entry points
with dummy function names."*

**The three rulings the first draft got right, re-verified:** ClassEval-Obf
(2510.03178) is summarization + execution prediction; CodeCrash (2504.14119) is
output and input prediction; Orvalho & Kwiatkowska (2505.10443) is output
prediction. None generates code. Those exclusions stand.

## 2. The strongest citation

**RADAR** — *How Important are Good Method Names in Neural Code Generation? A
Model Robustness Perspective*, arXiv:2211.15844.

Its task is this bench's task, in its own words: models *"generate executable
code from functional descriptions in natural languages, possibly together with
signatures"*, the signature being *"the combination of the method name and the
parameter list"*, denoted **FDSig**. Its `Foo-Attack` baseline is *"the
replacement of all method names with the term 'foo'"*, with the functional
description retained — the prose stays, the name goes.

Pass@1 on HumanEval, models described as the best available within 3B parameters:

| model | FDSig | Foo-Attack | Random-Attack | RADAR-Attack |
|---|---:|---:|---:|---:|
| Replit (3B) | 18.90 | 15.85 (−16.1%) | 16.46 (−12.9%) | 12.80 (−32.3%) |
| CodeGen | 21.34 | 17.68 (−17.2%) | 15.24 (−28.6%) | 12.20 (−42.8%) |
| CodeT5+ | 21.95 | 20.73 (−5.6%) | 16.46 (−25.0%) | 12.20 (−44.4%) |

**Baselines of 18.9–22.0%.** That is this bench's regime, not the 76.6–99.3% the
first draft complained it could not transfer from.

## 3. The missed sub-experiment, and how it was missed

**ReCode contains two meaning-stripping renames with a full results table, and
the first draft ruled the paper out as meaning-preserving.**

It read only ReCode's *function-name* perturbation family — CamelCase,
ButterFingers, SwapCharacters — which is genuinely style-preserving, and
generalised from it. §3.4's **code-syntax** family was never opened:

- `VarRenamerNaive` — *"selects the most frequently referenced variable name in
  the partial code and replaces it with `VAR_0`"*
- `VarRenamerRN` — *"replaces it with a random string with half alphabetic and
  half numeric characters"*
- `VarRenamerCB` — a plausible natural name from CodeBERT: the meaning-preserving
  control

Robust Drop `RD₅@1`, relative %, nine models 1B–16B:

| | CodeGen 2B mono | 2B multi | 6B mono | 6B multi | 16B mono | 16B multi | InCoder 1B | InCoder 6B | GPT-J 6B |
|---|---|---|---|---|---|---|---|---|---|
| HumanEval CB | −3.03 | 8.33 | 8.24 | 10.00 | 5.56 | 9.38 | 22.58 | 11.32 | 4.88 |
| HumanEval Naive | 1.52 | 16.67 | 7.06 | 5.00 | 10.00 | 12.50 | 6.45 | 13.21 | 12.20 |
| HumanEval RN | 9.09 | 29.17 | 18.82 | 23.33 | 14.44 | 28.12 | **54.84** | **52.83** | 29.27 |
| MBPP RN | 21.00 | 33.09 | 24.38 | 37.89 | 25.36 | 31.71 | **47.89** | 42.25 | 35.09 |

**The first draft's stated reason for not obtaining ReCode's figures was false.**
It recorded: *"the ACL PDF did not extract and no HTML rendering was found."* The
arXiv PDF extracts cleanly — 82KB of text, in which `VarRenamer` appears fifteen
times. One failed fetch was treated as an exhausted search, and a paper was
excluded on a partial read of its own taxonomy.

## 4. What the generation evidence orders

Three findings the first draft could not have had, and each reverses one of its
conclusions.

**The conditions are ordered, monotonically:** natural rename < positional
placeholder < random string. The first draft concluded the forms were *"not
ordered"* — true of ClassEval-Obf's comprehension data, false in generation,
where ReCode resolves it across nine models and two benchmarks.

**`function_A` is the weak arm.** Positional placeholders cost 1.5–16.7%
relative; random strings cost 9–55%. #267 proposed the weakest condition on the
ladder.

**Small models take the largest relative hit.** ReCode's InCoder-1B — the
smallest model in the table — shows the biggest drop on both benchmarks (54.84%,
47.89%). The first draft argued from a regime gap that a low baseline meant the
lever could not read here. The evidence points the other way.

**The sign is still not guaranteed, and that conclusion survives the move to
generation.** ODEX finds meaningless names *best* (47.15 vs 43.23); BioCoder's
Java Pass@20 *rises* under placeholders (43.8 → 47.9); ObfusEval has a rising
cell (DeepSeek/redis 7.2 → 11.5); ReCode's `VarRenamerCB` reaches −18.13. The
first draft attributed sign-instability to the body being visible in
comprehension tasks. That reasoning was wrong, but its conclusion holds for a
different reason.

## 5. Forty years of human evidence, and the warning that matters most

The benchmarks say the lever is real. The empirical SE literature says something
the benchmarks cannot, and it bears directly on whether **this** instrument can
see it.

**The effects live on time, not correctness.** Hofmeister, Siegmund & Holt
(SANER 2017 / EMSE 2019, n=72): words give *"19% faster comprehension speed"*
than letters or abbreviations, `dz=0.32`. Schankin et al. (ICPC 2018, n=88): 14%
faster, `dz=0.27`, `R²=0.02` — and on the **fail rate**, `p=0.671`, `dz=0.09`.
Lawrie et al. (ICPC 2006): description ratings fall from 3.91 to 3.10, but **only
3 of 12 functions differ individually**. Beniamini et al. (ICPC 2017): two
experiments, both null, *"None of the p-values were even close to 0.05."*

**This bench has no time axis. Pass/fail is the whole measurement.** So the
neutral arm — the one #267 proposed — is the arm this instrument is *least*
shaped to detect.

**Misleading names are worse than neutral ones, and this is the strongest result
in the human literature.** Avidan & Feitelson (ICPC 2017): *"participants who
received the experimental treatment were found to perform better despite the
missing identifier names! … Obviously, bad names can mislead just as much as good
names inform."* Feitelson's later summary: misleading names are *"worse than
meaningless names like consecutive letters of the alphabet."* Fakhoury et al.
(ICPC 2018) give accuracy: bug-localization success **90.9% → 75.0%** under
linguistic antipatterns, cognitive load Cliff's `d = −0.81`. Arnaoudova et al.
(EMSE 2016): over 80% of developers rate as poor those names with *"a clear
dissonance between the code behavior and its lexicon."*

Feitelson's mechanism is the design-relevant sentence: ***"time reflects
difficulty, and the error rate reflects a 'surprise factor'."*** Neutral
anonymisation is a difficulty manipulation. Misleading naming is a surprise
manipulation. **An instrument that measures only errors is shaped to detect the
second.**

### Design pitfalls this literature flags for #267

- **Familiar-algorithm ceiling.** Lawrie found no effect on quicksort — *"the
  structure of the code alone is sufficient to determine its purpose"* — and
  concluded identifier names matter more for non-algorithms. Corroborated
  LLM-side: ClassEval degrades under obfuscation, LiveCodeBench barely does. A
  textbook-shaped corpus bakes in the null before a draw is taken. **Stratify.**
- **Item variance dominates; do not pool.** 3 of 12 significant (Lawrie), 3 of 6
  sign-reversed (Avidan). Pooling averages a real effect against a reversed one
  and reports nothing. This compounds #266's existing no-pooling rule rather than
  duplicating it.
- **`function_A` and `var1` are not fully neutral.** Feitelson recommends
  consecutive letters in order of appearance and warns that first-letter schemes
  *"may still convey information."* `var1`/`var2` carry ordinality and arity;
  `function_A` signals "anonymised benchmark", itself a conditionable cue. Run
  two neutral variants so the scheme is not mistaken for the effect.
- **The confusable arm is the weakest bet.** No controlled experiment establishes
  harm from visual confusability, and the camelCase/underscore evidence reversed
  under replication as a training-exposure effect. Feitelson also warns that
  mechanical abbreviation *"may lead to unnatural or misleading names, such as
  `str` for `start`"* — so a confusable arm may silently be a misleading arm.
- **Where the effect concentrates: the signature.** Avidan found parameters more
  useful than locals in 79% of cases, and masked the method name in *every*
  condition precisely because *"method names are expected to provide significant
  information … this is precisely why they need to be masked."* This bench
  renames the function name — outside the range of those experiments, and
  probably the dominant site.
- **Adversarial misleading names are far off-distribution.** Arnaoudova measured
  name/return-type opposites at **0.02%** of methods. `compute_max` for a summing
  function is a stress test, not an estimate of what naming is worth in practice.
- **Leakage audit.** Avidan's stated threat is information leaking through names
  that mirror each other and through library calls. Here that means doctest
  examples, type annotations, default values, module names, test names, and
  called libraries.

**Does the prose spec absorb the loss?** Partially, and asymmetrically. Lawrie's
large effect is an upper bound that does not apply — they deleted all comments,
and noted *"when functions are uncommented, as many are, comprehension is almost
exclusively dependent on the identifier names."* Hofmeister is the direct test: a
comment block mapping stripped names back to their originals was on screen and
the 19% penalty persisted. Beniamini gave subjects the full spec and got nulls.
**But redundancy is exactly what a misleading name destroys** — a prose spec does
not neutralise a contradicting name, it *creates* the contradiction. Predicted
pattern: the prose spec shrinks the neutral arm toward null; the misleading arm
does not shrink and may grow.

## 6. `style` — the negative control, now corroborated

The owner proposed a fifth condition on 2026-08-15: rename by convention only
(`scan_pairs` → `scanPairs`), all four sites rewritten, no meaning removed,
expected effect nothing. It is the lever's negative control, distinct from the
existing positive control on the transform (the renamed reference must still
pass).

**ReCode's `VarRenamerCB` is that control, already run** — a natural replacement
name, meaning intact — and it moves **−18.13 to +23%** across cells. Renaming at
all is **not** free. A design without this arm confounds the cost of removing
meaning with the cost of renaming, and the published spread is large enough that
the confound would dominate a small effect.

## 7. The error record

Kept because #243's lesson is that quoted figures survive until someone
re-derives them, and a document that erases its own failures teaches nothing.

**What the first draft got right, and stands:**

- *"+14pp from renaming on two 7B-class models"*, carried in the 2026-08-14
  session record, is **not in arXiv:2505.10443**. Its renaming tables show a
  largest rise of +3.0pp. Unaffected by the falsification — that paper is still
  an output-prediction study and the figure is still not in it.
- *"Misleading names are 3–6× stronger"* — the **number** remains unsupported.
  Its likely origin (CodeCrash's 23.2% divided by alpha-renaming's 4–7pp) divides
  misleading *natural-language comments* by *identifier renaming* across two
  papers. **But the first draft used this to reject the direction as well, and
  that was an over-correction**: §5 above shows the direction has strong human
  evidence the scan never looked for. A true claim was dismissed on a wrong
  citation.

**What the first draft got wrong:**

- It claimed no source covered the generation cell. Six do (§1).
- It excluded ReCode on a partial read and recorded a false reason for not
  reading further (§3).
- It argued the regime gap made prior effect sizes non-transferable *downward*.
  Prior art exists at 14–27% baselines, and the smallest model takes the largest
  hit (§4).
- It concluded the four naming conditions were unordered. In generation they are
  ordered (§4).
- It reasoned that sign-instability was an artefact of comprehension. The
  conclusion holds; the reasoning does not (§4).

## 8. What this changes for #267

1. **The manipulation is established, not speculative.** Cite RADAR and ReCode
   §3.4 as the design's antecedents and match their conditions so the result is
   comparable.
2. **Add a random-string arm; do not lead with `function_A`.** Positional
   placeholders are the weakest published condition; random strings are 3–5×
   stronger in the same tables.
3. **Expect the misleading arm to carry the result.** The instrument measures
   errors, and errors are where the surprise manipulation lands.
4. **Keep `style`.** It is `VarRenamerCB`, and its published spread proves the
   confound is real.
5. **Stratify away from familiar algorithms**, or the null is designed in.
6. **The low baseline is not an objection.** Two of six sources say the effect is
   largest exactly here.

## 9. What the record may claim

Not that this is unmeasured, and not that we would be first.

**The defensible statement:** no published work runs a HumanEval-scale,
multi-model, generate-from-specification pass@k measurement across the **full
four-condition ladder** (positional / ambiguous / cross-domain / misleading). The
taxonomy is fully worked out in ClassEval-Obf but attached to comprehension; the
task is covered by six studies, each carrying one or two conditions, mostly in
appendices, mostly on one or three models. **That is a coverage gap, not a virgin
cell**, and #267's contribution is completing a ladder others have sampled — in a
regime where two of the six sources say the effect is largest.

## Sources

**Generation-task benchmarks**
- Yang, Zhou, Yang, Yue, Chen & Chen. *How Important are Good Method Names in Neural Code Generation? A Model Robustness Perspective.* ACM TOSEM 33(3), 2024. arXiv:2211.15844. <https://arxiv.org/abs/2211.15844>
- Wang et al. *ReCode: Robustness Evaluation of Code Generation Models.* ACL 2023. arXiv:2212.10264. <https://arxiv.org/abs/2212.10264>
- Zhang et al. *Unseen Horizons / ObfusEval.* ICSE 2025. arXiv:2412.08109. <https://arxiv.org/abs/2412.08109>
- Yetiştiren et al. arXiv:2304.10778v2. <https://arxiv.org/abs/2304.10778>
- Tang et al. *BioCoder.* Bioinformatics 2024. arXiv:2308.16458. <https://arxiv.org/abs/2308.16458>
- Wang et al. *ODEX.* arXiv:2212.10481. <https://arxiv.org/abs/2212.10481>
- Zhuo et al. *BigCodeBench.* ICLR 2025. arXiv:2406.15877. <https://arxiv.org/abs/2406.15877>

**Comprehension-task benchmarks (excluded from the cell, taxonomy still used)**
- Le et al. *When Names Disappear / ClassEval-Obf.* arXiv:2510.03178. <https://arxiv.org/abs/2510.03178>
- Orvalho & Kwiatkowska. arXiv:2505.10443. <https://arxiv.org/abs/2505.10443>
- CUHK-ARISE. *CodeCrash.* NeurIPS 2025. arXiv:2504.14119. <https://arxiv.org/abs/2504.14119>

**Human studies**
- Avidan & Feitelson. *Effects of Variable Names on Comprehension.* ICPC 2017.
- Fakhoury et al. *The Effect of Poor Source Code Lexicon and Readability on Developers' Cognitive Load.* ICPC 2018.
- Hofmeister, Siegmund & Holt. *Shorter Identifier Names Take Longer to Comprehend.* SANER 2017 / EMSE 2019.
- Schankin et al. *Descriptive Compound Identifier Names Improve Source Code Comprehension.* ICPC 2018.
- Lawrie, Morrell, Feild & Binkley. *What's in a Name? A Study of Identifiers.* ICPC 2006 / ISSE 2007.
- Beniamini et al. *Meaningful Identifier Names: The Case of Single-Letter Variables.* ICPC 2017.
- Arnaoudova et al. *Linguistic Antipatterns: What They Are and How Developers Perceive Them.* EMSE 2016.
- Takang, Grubb & Macredie. *The Effects of Comments and Identifier Names on Program Comprehensibility.* 1996.

**Nearest misses — right manipulation, wrong task; recorded so they are not re-searched**
- *Is Your Benchmark Still Useful?* arXiv:2503.06643 — `VarNormI` (`var1, var2`) and `VarNormII` (random), run on CruxEval execution.
- *How Does Naming Affect LLMs on Code Analysis Tasks?* arXiv:2307.12488 — nonsense and misleading names, run on code search and clone detection.
- The contamination literature (Riddell et al. ACL 2024, LessLeak-Bench, EvoEval, DyCodeEval) measures overlap or rewrites narratives; **none touches identifiers**.

Retrieval: `WebSearch` and `WebFetch`, 2026-08-15, plus PDF text extraction.
Figures in §2 and §3 were read from extracted PDF text, not from the publishers'
typeset tables; RADAR's `Foo-Attack` and `FDSig` definitions and ReCode's
`VarRenamer` family were re-verified against the extracted source directly before
this file was written. Nothing here is vendored under #118, because nothing here
is registered in `records/claims/` — any figure above must be vendored or pinned
before a claim record quotes it.
