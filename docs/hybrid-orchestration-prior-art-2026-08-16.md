# Hybrid orchestration prior art — what transfers, and what was refuted

Date: 2026-08-16. Baseline: `d67dab86` (the dig that raised these read `b7209c13`).

Five orchestration and routing projects were read against this repository and
distilled into ten proposed actions. This record states what each one turned out
to be. Four of them became [ADR-0027](decisions/0027-a-routing-policy-is-adopted-only-if-it-is-inspectable-here-and-measured-here.md),
[ADR-0028](decisions/0028-the-gate-is-the-scorer-so-there-is-no-answer-to-extract.md),
[ADR-0029](decisions/0029-throughput-is-not-the-ceiling-and-the-serving-bench-is-already-in-the-table.md)
and [ADR-0030](decisions/0030-the-pre-gate-heuristic-verifier-is-refuted-by-our-own-replies.md);
the rest became comments on issues that already owned them (#16, #69, #254,
#265, #268, #277), and two became new issues: #279 (a dead source is
re-dispatched once per contract) and #280 (the ripgrep drift below).

**Nothing here was taken on the strength of the briefs.** Every source path below
was re-fetched at its pinned commit and read, every mcgyvr-side claim was
re-checked against `d67dab86`, both cited abstracts were re-read, and one
proposal was tested against this project's own run records.

## The sources, pinned

| Repo | Commit | License (verified at the pin) |
|---|---|---|
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | `4eadf92adee832aa1ef3e52af6b66787614eda0d` | MIT core; `enterprise/` is BerriAI proprietary |
| [sgl-project/sglang](https://github.com/sgl-project/sglang) | `4d0c5a89af7061178e4b7ab11d84c4dd2bc92482` | Apache-2.0 |
| [microsoft/best-route-llm](https://github.com/microsoft/best-route-llm) | `fc9b896a814acf7c00565fbea0803a8c20812702` | MIT (one file Apache-2.0) |
| [jnormore/emerge](https://github.com/jnormore/emerge) | `727a346124903ce95aa8d3bca3bd18852ce829fc` | MIT |
| [NadirRouter/NadirClaw](https://github.com/NadirRouter/NadirClaw) | `e10cf977ac90e94569e7532f3b0ade615337e8d6` | PolyForm Noncommercial 1.0.0 |

NadirClaw's YAML headers say "MIT"; the `LICENSE` file says PolyForm
Noncommercial 1.0.0. The `LICENSE` file governs, so everything drawn from it
here is an idea, never a line.

## The verdicts

| # | Proposal | Verdict | Where it went |
|---|---|---|---|
| 1 | Deterministic zero-token difficulty classifier | Rejected — the shape is already decided and the evidence is absent | ADR-0027, prior art on #16 |
| 2 | Quality-tier → cost-tiebreak routing | Rejected — inherits (1)'s classifier | #277 |
| 3 | Price table for the `api` family | Real gap, deferred — needs a provenance rule first | #69 |
| 4 | Per-error-class retries + cooldown | Half real — cooldown approved, retries deferred | #279; #152 |
| 5 | Port tag-aware `compute_accuracy` | Rejected — no surface exists here | ADR-0028, #254 |
| 6 | Cache-aware routing + a serving bench | Rejected — the bench already exists; the lever is not the ceiling | ADR-0029 |
| 7 | Declarative cascade rule engine | Rejected — same ground as (1) | ADR-0027, prior art on #16 |
| 8 | Pre-gate text-response heuristic verifier | **Refuted, measured** | ADR-0030 |
| 9 | Contamination audit as a release gate | Already built here, and wider | #268 |
| 10 | Trained per-query router | Rejected — post-v1, and uninspectable by construction | ADR-0027 |

## What verification changed

Six of the ten verdicts turn on something the briefs did not have.

**The classifier is not small, and it is not calibrated.**
`litellm/router_strategy/complexity_router/complexity_router.py` is **1,974
lines**, carrying an LLM-classifier path, session pinning and embedding-based
keyword matching alongside the regex default. The four keyword lists are real
and modest (45 code / 19 reasoning / 31 technical / 29 simple terms), but
`DEFAULT_DIMENSION_WEIGHTS`, `DEFAULT_TIER_BOUNDARIES` and
`DEFAULT_TOKEN_THRESHOLDS` carry **no accuracy, AUROC or calibration figure
anywhere in the module**. The briefs flagged exactly this defect against the
*adaptive* router — whose `config.py` admits "All magic numbers are first-pass
guesses … Expect to retune after first 1000 sessions of real traffic" — and did
not apply it to the complexity router, which is in the same condition minus the
admission. The module also credits its own prior art
(`Inspired by ClawRouter: https://github.com/BlockRunAI/ClawRouter`), which the
briefs do not mention.

**The "22%" figure does not exist.** Both abstracts were re-read directly:
BEST-Route ([arXiv:2506.22716](https://arxiv.org/abs/2506.22716)) claims "reduces
costs by up to 60% with less than 1% performance drop"; HybridLLM
([arXiv:2404.14618](https://arxiv.org/abs/2404.14618)) claims "up to 40% fewer
calls to the large model, with no drop in response quality". Neither is 22%, and
`microsoft/best-route-llm` ships the recipe with no eval artifact to re-derive
either number from.

**The serving bench already exists.** `data/capability-table.json`
`concurrency_findings` holds CON-04 (continuous batching at 1/2/4/8/12/16
concurrent requests: 68 → 489 tok/s, 8.5×, ceiling bounded by memory bandwidth)
and CON-05 (prefix caching, 43.3% hit rate on a 39-token shared prefix, 19%
wall-clock). Both on rig_b, 2026-08-01. Building a serving bench would measure
what is written down.

**The contamination audit already exists, and is wider.** `tools/problems/admit.py`
screens HumanEval entry-point overlap and near-duplicates and pins by digest at
*admission*, and `tools/instruments.json` protects at the point of entry
(#230/#240). The only transferable detail is the hash recipe —
`sha256(NFC(text).strip().casefold().utf8)` over normalised prompt *text*, where
ours hashes entry-point *symbols*. That difference is #268's subject.

**Three issue references were wrong.** #152 is "Re-verify the retry-rescue figure
that justifies attempts=1", not a retry-policy gap; #22 is closed; #153, cited as
a future interleave-aware ascent, is closed and was about ladder family order.

**The stated moat is retired.** All eleven briefs name mcgyvr's edge as "a
*measured* HumanEval+ capability table with provenance". [ADR-0020](decisions/0020-retire-the-rulers.md)
retired HumanEval+ as a decision instrument on 2026-08-10, six days before the
dig ran and five commits before the baseline it read: the number is "reporting,
not evidence". This is not only an external misreading — `capability.py:174`
still reads `humaneval_plus_pass1` to order the ladder (#277), and
`initialize.py:332` and `propose.py:370` still quote it to the user as the reason
for a binding.

## The measurement that refuted proposal 8

A pre-gate heuristic verifier scores a cheap model's *reply text* — refusal
patterns, uncertainty patterns, JSON validity, length — before anything
expensive runs. The question is not whether it works elsewhere. It is what it
would find here.

Every candidate this project has recorded was counted: **23,902 replies across
31 run directories** under `records/measurements/`.

| stop_reason | parse_error | n | share |
|---|---|---:|---:|
| complete | — | 23,483 | 98.25% |
| truncated | `incomplete-reply` | 386 | 1.62% |
| complete | `unterminated-fence` | 16 | 0.067% |
| complete | `no-fenced-block` | 10 | 0.042% |
| complete | `ambiguous-blocks` | 7 | 0.029% |

Re-derivable:

```bash
python3 - <<'EOF'
import json, glob, collections
x = collections.Counter()
for f in glob.glob("records/measurements/**/results.jsonl", recursive=True):
    for line in open(f):
        if not line.strip():
            continue
        r = json.loads(line)
        x[(r.get("stop_reason"), r.get("parse_error") or "-")] += 1
for k, v in sorted(x.items(), key=lambda kv: -kv[1]):
    print(v, k)
EOF
```

Three things follow, and they are the whole of ADR-0030.

1. **`truncated` and `incomplete-reply` are the same event.** Not correlated —
   identical. Every truncated reply carries that parse error and no other row
   does, across all 23,902. The runner already labels it, at the transport layer,
   for free. A heuristic verifier re-detecting it adds a second name for one
   fact.
2. **The remainder is 33 replies, 0.138%.** That is the entire ceiling of what a
   reply-shape heuristic could newly catch here.
3. **There is no refusal class at all.** Refusal patterns are the core of the
   proposed verifier. This project's reply taxonomy has never needed the
   category, which is consistent with #212's finding that what reads as a parse
   refusal is usually the output cap.

For scale: #246 — normalising worker output *before* judging it, rather than
scoring its shape — is measured at **+13.7pp** on the same class of run data.
Two proposals aimed at the same stage of the pipeline, two orders of magnitude
apart.

## What survives

Three things, none of them code.

* **The keyword vocabularies** (LiteLLM `complexity_router/config.py:104-209`) as
  seed prior art for #16, when #233 unblocks it — a starting list, not a policy.
* **The per-domain verifier trust map** (NadirClaw `MODEL_CARD.md` §5: verifier
  AUROC ~1.0 on factual recall down to ~0.65 on code generation, encoded as
  force-escalate rules) as the shape of a risk floor keyed to where a checker is
  weak. Their numbers are self-reported and their eval harness is not shipped.
* **The negative-test discipline** for any matcher — emerge's
  `tests/test_experiment.py` asserts `"Both A and C"` does not match `"B"` and
  `"230"` does not match `"23"`. The scorer they defend has no analogue here, but
  the discipline applies directly to fence parsing, which is #254.

And one convergence worth recording: emerge content-addresses a measurement by
hashing its config (`config.py:29-54`, `sha256(...)[:12]`). That is #265's
premise, reached independently by a project with no bench doctrine — weak
external evidence that run identity by content is the ordinary answer rather
than an unusual one.
