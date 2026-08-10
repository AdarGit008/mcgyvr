# MBPP+ on the floor model (#225): a band locator, and the hypothesis it refutes

One greedy pass of MBPP+ (378 tasks, EvalPlus 0.3.1) against the floor model
as every sweep sees it — `qwen2.5-coder:3b` Q4_K_M served by Ollama on
srv1:11434 — because #225's sourcing acceptance requires MBPP+ measured
against the 3B specifically before anything is generated.

## The number

| | pass@1 |
|---|---|
| MBPP (base tests) | **70.6%** |
| MBPP+ (base + extra tests) | **60.6%** |

Greedy, one seed, cap 768 (the EvalPlus default, same as #189's HumanEval+
arms), codegen 10m54s + evaluate ~1m.

## Where that lands in the graded band

| instrument | 3B first-pass |
|---|---|
| bundle-py | 65–70% |
| **MBPP+** | **60.6%** |
| d1 (bundle-ts) | 50.0% |
| d2 | 41.7% |
| d3 | 16.7% |
| pool | 0% |

**The "#225 hypothesis" — MBPP+ plausibly between d3 and the pool — is
refuted.** MBPP+ reads above d1, in bundle-py's neighbourhood. It contributes
no anchors to the d3→pool gap; the gap material must be generated, which the
campaign was already sized to do.

The secondary reading matters more for the campaign: the 3B's collapse from
16.7% (d3) to 0% (pool) is **not** explained by small-function-synthesis
difficulty — MBPP+-scale units stay easy for it. That is consistent with
ADR-0017's unit-of-work reading (the pool's median 44-line reference / 16
assertions versus MBPP's 5–15-line functions), and it tells the generation
campaign that the gap strata must interpolate **reference size and assertion
count** between d3-class and pool-class, not "harder small functions".

## The caveat that travels with the number

MBPP is a front door: 12.2–20.8% of its gold solutions appear in major
pretraining corpora (Riddell, Ni & Cohan, NAACL 2024, arXiv 2403.04811), and
contamination inflates the score — 60.6% is an **upper bound**, and the
uncontaminated level could sit lower, so the caveat cuts *against* the
easy-end placement rather than for it. What survives: the measured number
cannot support placing MBPP+ in the gap, the task shape independently argues
the easy end d1 already covers, and a front-door set was never admissible as
bench material anyway — this number locates, it does not anchor.

## Protocol notes

- Served through Ollama's OpenAI endpoint (the rig sweeps' own path), not
  #189's llama-server front door: this number's job is comparability with the
  floor probes, which all ran against Ollama on 11434. Backend numerics move
  greedy deltas ~2.6pp on this model (#189's cpu/gpu cross-check); no
  conclusion here is that fine.
- Client: the #189 EvalPlus venv on srv1 (`~/evalplus031`), 0.3.1.
- Raw generations, sanitized samples and per-task eval results are in this
  directory; the eval JSON's `pass_at_k` recomputes the two headline figures.
- For the campaign's decontamination screen: MBPP+'s 378 ids/prose should
  join HumanEval's 164 entry points in the item-level blocklist — MBPP is
  both pretraining-memorized and, as of this record, the band's locator.
