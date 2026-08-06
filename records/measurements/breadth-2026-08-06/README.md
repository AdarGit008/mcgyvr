# The first-pass index distribution — the result

Issue: [#121](https://github.com/AdarGit008/mcgyvr/issues/121), under
[#111](https://github.com/AdarGit008/mcgyvr/issues/111).
Claim: [CLM-0013](../../claims/CLM-0013.json).
Instrument and design: [`tools/breadth/README.md`](../../../tools/breadth/README.md).

**The distribution is entirely concentrated at index 0, and the default of 1
stands.** Over twenty tasks given five serial sampled draws each with no early
exit, a gate-passing candidate existed within five draws on all twenty — and on
all twenty it was the *first* draw. ADR-0008 named spread-out indices as the
only evidence that would justify raising the breadth default above 1; none
appeared. #119 should ship `breadth` defaulting to 1 on this record.

## What ran

One sweep: 20 tasks × (1 greedy + 5 sampled) draws = 120 candidates,
0 lost to dispatch errors, 26.6 minutes of measured wall clock.

| | |
|---|---|
| Host | srv2 (RTX 3060, 12 GB) |
| Model tag | `qwen3-coder-next-ud:q3_K_XL` |
| Model digest | `499a5d0084fe5fbfbee936c43c3493517de0c4bb4c26684f701e1be86b8fd1c8` |
| Serving | Ollama, ~11.0 GB of a 33.8 GiB blob in VRAM (heavy CPU offload) |
| Protocol | OpenAI-compatible (`/v1/chat/completions`) |
| Sampler | greedy arm T=0.0; sampled arm T=0.7, N=5, serial, **no early exit** |
| Cap | 768 output tokens (the bundle sweep's, so "truncated" means the same) |
| Prompt | the shipped assembly — `build_prompt` per contract, bundle by adapter |
| Rows | `results.jsonl`; every raw candidate under `candidates/` |
| Manifest | `run.json` (worker, sampler, bundle and per-task digests) |

**The model's identity is recorded, not asserted.** The tag says `q3_K_XL`;
Ollama's `/api/show` details for the same blob say `family qwen3moe,
parameter_size 30.5B, quantization_level Q4_K_M`; the blob's 33.8 GiB is
consistent with neither reading taken at face value (a 30.5 B dense Q4 is
~17 GiB) and fits an ~80 B-A3B MoE at ~3.4 bits/weight. The digest above is
what the rows describe. "Top local rung" here means: the largest coder model
the rig holds that serves without thrashing (CAV-04's distinction — it
answered every request; mean dispatch 13.3 s under offload).

## The result

| arm | pass |
|---|---:|
| greedy (T=0.0) | 18/20 |
| sampled draw 0 (T=0.7) | 20/20 |
| sampled draws overall | 96/100 |

First-pass index over the 20 tasks (all with all five sampled draws recorded):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 20 | 20/20 |
| 1–4 | 0 | 20/20 |
| none | 0 | — |

Per sampled draw: 20/20, 18/20, 20/20, 18/20, 20/20. Only two tasks ever
failed any draw — t03 (greedy, sampled 1, sampled 3) and t07 (greedy,
sampled 1, sampled 3). The matching draw indices are coincidence, not seed
structure: both tasks' five sampled candidates are five distinct texts (the
`candidate_sha256` column), and a per-request seed cycle would have shown as
repeats. One reply in 120 was refused by the parser (t03 sampled 1,
`incomplete-reply`: it hit the 768-token cap); every other failure was the
declared acceptance suite rejecting a complete, parseable candidate.

### The draws are not even diverse where the model is confident

The saved candidates add a mechanism the pass/fail totals cannot show. On 10
of 20 tasks at least two of the five sampled draws are byte-identical; on
five of them (t10–t13, t17) **all five sampled draws are one text, identical
to the greedy draw** — at T=0.7 the output distribution collapses to its mode
on the tasks this rung finds easy. Where every draw is the same candidate,
breadth has nothing to select over *by construction*, so part of the
concentration at index 0 is not "the later draws never got to win" but "there
were never five candidates at all". Diversity appears exactly where
confidence drops (t01–t08 and t20 each produced five distinct texts,
including both tasks that ever failed) — which is the regime where breadth
would operate, and there it still never beat draw 0.

## The price

Each additional candidate cost **12.5 s dispatch + 0.1 s acceptance** (mean
over the 100 sampled draws; mean completion 200 tokens, mean prompt 664
tokens). On this rung, N=5 therefore spends ~63 s per task against
`budgets.task_timeout_s`'s default of 900 — the issue's pricing concern
(a sixty-second declared suite at N=5 consuming a third of the budget) is
real but suite-bound, and this task set's suites run in ~0.1 s. The cost that
actually accrued here was dispatch, and it bought nothing: every task's
answer was already in hand after draw 0.

## Limits, none concealed by the totals

- **The task set sits near this rung's ceiling.** 18 of 20 tasks never failed
  any draw, so for them "first pass at index 0" is certain rather than
  informative. The regime where breadth could pay — tasks the rung sometimes
  fails (ADR-0008's Snell condition) — is sampled by exactly two tasks, and
  with per-draw pass rates around 0.6 on those two, both landing at index 0
  carries real but modest evidence (~0.36 under independence). The asymmetry
  is what decides: keeping the default at 1 needs no power; raising it needed
  spread-out indices, and there are none.
- **Sampling at 0.7 cost nothing measurable here** — sampled draws passed
  96/100 against greedy's 18/20, a difference inside the ±1-task noise floor
  the bundle sweep measured for re-rolls. This licenses "no variance penalty
  was observed on this rung", not "sampling helps".
- **"Gate-passing" is acceptance-passing**: parse refusal or the contract's
  declared suite, the same proxy CLM-0012 used. The full `Gate.run` adds
  scope/secrets/structured/adapter rungs and the sandbox; for this task set
  those reject nothing the suite does not, but the claim is scoped to the
  proxy.
- **One rung, one task set, one serving stack.** The distribution is a fact
  about the top local rung on the pinned 20-task JS/TS set over Ollama's
  OpenAI path; a weaker rung (where per-draw pass rates are far from 1) could
  show spread this run cannot, and nothing here measures it. That
  measurement, if ever wanted, is the same instrument pointed at a smaller
  model — but the *default* binds policy for the ladder as configured, and
  the top rung is where breadth's case was strongest (nowhere to escalate
  to).
