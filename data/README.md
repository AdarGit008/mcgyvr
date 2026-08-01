# Capability data — provenance

`capability-table.json` is the decision data behind `mcgyvr init`. It exists
so that setup can propose worker bindings from detected hardware **without
benchmarking the user's machine**, which would turn a 30-second install into
an hour.

## Where the numbers come from

Every measurement was taken in
[`AdarGit008/local-ai`](https://github.com/AdarGit008/local-ai) (archived)
between 2026-07-26 and 2026-07-31, on two rigs described in the table's
`measurement_rigs`. Quality is HumanEval+ pass@1, greedy decoding, EvalPlus
v0.4.0.dev44, 164 tasks. Throughput is single-request eval rate on a trivial
prompt, which measures generation speed and deliberately excludes prompt
processing.

Nothing in the table is estimated or interpolated. A model with no valid
measurement carries an empty `quality` array rather than a guess.

## What the table is not

HumanEval+ ranks models on short, self-contained function synthesis. It is a
usable proxy for "can this worker execute a tightly-scoped contract" and a
poor proxy for anything else. It says nothing about a model's behaviour on a
repository it can see, on multi-hunk edits, or on instruction adherence
under a constrained output protocol. Treat it as an ordering, not a
prediction.

Two rigs is a small sample. The VRAM figures generalize; the throughput
figures are specific to those two GPUs and are present to express *ratios*
(a small model is ~2.4x faster on the small card; a marginal fit costs ~1.9x)
rather than absolute expectations.

## Known-bad measurements

The table carries a `harness_caveats` block, and models carry
`invalid_measurements` / `disputed_measurements` arrays alongside their valid
ones. These are kept rather than deleted because the failures are
instructive and repeatable:

- **CAV-01** — Ollama's `/api/generate` returns invalid HumanEval+ scores for
  Qwen2.5-Coder 7B and larger (32.3% vs a true 84.1%). Anyone regenerating
  this table through that path will silently produce a table that routes away
  from the best models available.
- **CAV-02** — Ollama resolves `qwen3-coder-30b-a3b` to F16 weights, not a Q4
  quant; the resulting CPU spill scores 3.7%.
- **CAV-03** — the published gpt-oss-20b score is attributed to an
  insufficient output budget in the harness rather than to the model, and is
  therefore not used.
- **CAV-04** — a marginal VRAM fit degrades rather than failing, which makes
  it look like a working binding.

## Regenerating

There is no regeneration script in this repo yet, by design: `mcgyvr init`
consumes this table and does not produce it. When re-measuring, use an
OpenAI-compatible endpoint (llama-server or vLLM) rather than a
backend-native generate API, and pin quantization explicitly — CAV-01 and
CAV-02 are both consequences of not doing so.
