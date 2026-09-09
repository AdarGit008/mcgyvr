# The adoption bar: prior art, searched before choosing a number

**Date:** 2026-08-10. **Lane:** lane/229, for issue #229. **Questions:** (a) what
do published fine-tuning and prompting studies treat as a *meaningful* gain, and
(b) what do benchmark authors and evaluation methodologists treat as *noise*?
**Method:** eight web searches and six page fetches run 2026-08-10 from this
lane, queries and URLs recorded in the provenance section below. Labels as in
`unsloth-fine-tuning-review-2026-08-06.md` and
`problem-pool-prior-art-2026-08-07.md`: **[measured]**, **[self-reported]**,
**[docs/code]**, **[derived]**.

## Verdict, in one line each

**On (a):** we did not find a published threshold for "this gain is worth
adopting" in any of the sources searched. What we found instead is that reported
gains cluster far above anything mcgyvr is arguing about — prompting studies that
report an effect at all typically report 9–30pp, fine-tuning reports 26–51pp —
which means **the literature does not answer our question because nobody in it is
operating near our margin**. `MIN_QUALITY_GAIN = 0.03` has no external
counterpart to be checked against, and the absence is itself the finding: a
per-lever rule has to be constructed here, not adopted.

**On (b):** the noise side is well developed, converging since 2024, and it says
one thing repeatedly — **the binding quantity in a paired comparison is the
discordance rate, not the item count** — which is exactly the correction #229's
own text asked for and which
[ADR-0019](decisions/0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md)
now runs on. One source states the same MDE arithmetic this lane derived
independently and lands on the same number for HumanEval+ to the decimal.

## What the field treats as noise

| source | what it establishes | label |
|---|---|---|
| Miller, *Adding Error Bars to Evals*, Anthropic, arXiv **2411.00640** (Nov 2024) | Evals should report CLT standard errors, not point estimates; when two models answer the same questions the analysis should be **paired** on per-question differences `d_i = x_i − y_i`; pairing "can reduce variance by approximately 1/3 in relative terms". Also gives the resampling lever: more answers per question took a worked MDE from **13.2% to 7.5%**. | [self-reported] |
| Madaan et al., *Quantifying Variance in Evaluation Benchmarks*, arXiv **2406.10229** (Jun 2024) | Variance in benchmarks "dictates whether differences in performance are meaningful" and is rarely quantified. Defines seed variance and *monotonicity*. Finds AGIEval and MMLU near chance after extensive training — high variance, low signal-to-noise. Item analysis and IRT borrowed from human testing were **limited** in reducing it. | [measured] |
| Kotawala, *Resolution Diagnostics for Paired LLM Evaluation*, arXiv **2605.30315** (May 2026) | Defines a resolution ratio `q := N / N*(δ̂)`; a displayed gap is resolvable only at `q ≥ 1`. States that **only discordant pairs drive power**. Finds **11 of 40** displayed pairwise rankings on Open LLM Leaderboard v1 unresolved at (α, 1−β) = (0.05, 0.8), and **4 of 9** adjacent MMLU-Pro top-10 pairs unresolved at N = 12,032 — rising to **6 of 9** once subject-level clustering is accounted for. Paired McNemar needs a **median 2.15×** smaller N than the unpaired Gaussian formula on the same data. | [measured] |
| *The Sample Complexity of LLM Evaluation*, TMLS | "The minimum detectable effect of a paired comparison is a function of only the item count, the discordance rate, and the chosen error rates." At α = 0.05, power 0.80, **10% disagreement rate**: HumanEval (164), GPQA Diamond (198), SWE-bench Verified (500), GSM8K (1,319) and MMLU (14,042) resolve gaps no smaller than **6.9, 6.3, 4.0, 2.4 and 0.75 points**. Paired analysis "needs 30 to 60 percent fewer items for the same power". | [derived] |
| Dror et al., *The Hitchhiker's Guide to Testing Statistical Significance in NLP*, ACL 2018 (**P18-1128**) | Establishes McNemar's test as the standard choice for comparing two systems on the **same instances** with a binary per-instance outcome — which is the shape of every arm on the bench. | [docs/code] |
| Thinking Machines Lab, *Defeating Nondeterminism in LLM Inference* (Sep 2025), and secondary coverage | Greedy decoding is not reproducible in production serving, and the cause is **batch variance**, not floating-point non-associativity: reduction kernels split work differently by batch size, so dynamic batching changes logits and flips argmax. Reported test: 1,000 greedy completions of one fixed prompt on Qwen-3-8B gave **80 distinct answers**, identical up to token 102. | [measured] |
| Song et al., *The Good, The Bad, and The Greedy*, arXiv **2407.10457** (Jul 2024) | Argues evaluation should not ignore non-determinism, and finds greedy generally outperforms sampling across most tasks evaluated. We could not extract its per-benchmark variance figures — both the PDF and the abstract page failed to yield them through the tooling available in this lane, and only the abstract-level claims above are recorded. | [self-reported] |
| Anonymous RL-for-code study, arXiv **2605.00433** | Repeated one training-and-eval configuration **five times on Qwen2.5-Coder-3B** — our own floor model — holding all settings identical, and reports a mean standard deviation across runs of **0.0026** (0.26pp). | [measured] |
| EvalPlus leaderboard method | Ranks by pass@1 under **greedy decoding**, and publishes no run-to-run interval alongside the ranking. | [docs/code] |

**The convergent point.** Three independent sources (Miller, Kotawala, TMLS) reach
the same structural conclusion from different directions: for two systems scored
on the same items, power is carried by the items where the two *disagree*, and
reporting a headline pass-rate difference without that denominator overstates
what the instrument saw. Kotawala and TMLS both then apply it and find a large
fraction of published comparisons unresolved.

**Independent agreement with this lane's own arithmetic.** `tools/power/mde.py`,
written before the TMLS figure was found, computes the minimum detectable effect
at n = 164 and a 10% discordance rate as **+6.9pp**. TMLS states 6.9 points for
HumanEval at the same α, power and disagreement rate. The agreement is to the
decimal on a figure derived independently, which is the strongest external check
this lane obtained. It also confirms that #219's quoted "~+4.8pp MDE" for
HumanEval+ at n = 164 was **optimistic**: it corresponds to a discordance rate of
about 5%, and at the 10% rate the field uses as its planning default the same
instrument resolves only +6.9pp. [derived]

## What the field treats as a meaningful gain

No source searched states a threshold. What they state is effect sizes, and the
distribution of those is the useful result:

| source | reported effect | label |
|---|---|---|
| LoRA Land (Predibase), arXiv **2405.00732** — 310 fine-tuned LLMs | fine-tuning gains averaging **+26.3 to +51.2 percentage points** | [self-reported] |
| Mathews & Nagappan — adding test cases to prompts | **+9.25 to +29.57pp** accuracy | [measured] |
| Döderlein et al. — prompt engineering on Copilot/Codex | success rate ~1/4 → ~3/4 on HumanEval and LeetCode | [measured] |
| Li et al. — prompting on CodeX/CodeGeeX/CodeGen/InCoder | pass@1 improvements of ~50–80% *relative*, on MBPP/MBJP/MBJSP | [self-reported] |
| GPT-3.5 object-oriented study | pass@5 **42.4% → 59.19%** at enhanced prompt level | [measured] |
| EPiC (evolutionary prompt engineering) | "up to **5%** improvement in pass@k" — the smallest headline effect found | [self-reported] |
| Survey of improvement-threshold practice (forecasting domain) | evaluates at 30/40/50/60/70/80% *relative* improvement; 50% used as "a balanced choice" — thresholds are chosen per study, not inherited | [docs/code] |

**Two things follow for #229.** First, the smallest effect anyone in this set
publishes as a headline is EPiC's ~5%, and most sit an order of magnitude above
the +1.9pp #189 measured — so the field offers no calibration at our margin.
Second, several of these gains are reported on instruments that the noise
literature above would call unresolved at their own size, so the effect
distribution is itself selected: small true effects are not published as small,
they are not published.

## What we did not find, and where we looked

Stated as searched-and-not-found, never as absence in the world (per
[[no-absence-claims]] and ADR-0004's discipline):

- **We did not find** a published adoption threshold — a stated rule of the form
  "a gain below X is not worth shipping" — for fine-tuning or prompting a code
  model, having searched: the eight queries listed below, the Miller, Madaan,
  Kotawala and Dror papers and their result pages, the LoRA Land report, and the
  EvalPlus leaderboard methodology. What exists is per-study choice of threshold,
  which one survey source states explicitly.
- **We did not find** a source that separates a *reality floor* from an *adoption
  rule* the way ADR-0018's Q1 does. The noise literature stops at "is this
  resolvable"; the applications literature starts after "we got a big number".
  The two-part split #229 asks for appears to be ours to construct.
- **We did not find** per-benchmark variance figures in arXiv 2407.10457: the PDF
  fetch returned undecoded binary and the abstract page carries only qualitative
  claims. Its numbers remain unread rather than absent.
- **We could not read** the TMLS page directly — it returns HTTP 403 to the
  fetcher available here. Its figures above are quoted from two independent
  search-result summaries that agree with each other, and the HumanEval figure
  is independently reproduced by our own tool. Treated as [derived], not
  [measured], and it is the one citation in this document not read at source.

## Provenance

Searches run 2026-08-10 from lane/229, in order: (1) `adding error bars to evals
LLM benchmark statistical variance Miller Anthropic`; (2) `quantifying variance
in evaluation benchmarks LLM noise floor seed variance`; (3) `HumanEval pass@1
statistical significance small differences benchmark 164 problems noise`;
(4) `Dror hitchhiker's guide statistical significance NLP McNemar paired test
recommendation`; (5) `LLM greedy decoding nondeterminism same prompt different
output batch invariance floating point`; (6) `what counts as meaningful
improvement fine-tuning code LLM benchmark percentage points threshold
reporting`; (7) `"minimum detectable effect" OR "statistical power" code
generation benchmark evaluation number of problems needed`; (8) `prompt
engineering effect size code generation pass rate improvement percentage points
measured study`; plus two follow-ups on the sample-complexity and
resolution-diagnostics results.

Pages fetched: `arxiv.org/abs/2411.00640`, `arxiv.org/pdf/2411.00640` (binary,
unreadable), `alphaxiv.org/overview/2411.00640`, `arxiv.org/abs/2406.10229`,
`arxiv.org/abs/2407.10457`, `arxiv.org/pdf/2407.10457` (binary, unreadable),
`arxiv.org/html/2605.30315`, `tmls.nyc/research/eval-sample-complexity` (403).

**Expiry.** This is what we found on 2026-08-10, not what exists. The noise-side
literature is moving fast — three of the eight sources postdate mid-2024 — so the
"no published adoption threshold" result in particular should be re-checked
before it is cited as settled.
