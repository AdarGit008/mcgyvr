# Shipped data — provenance

Two files ship as data rather than as code:
`capability-table.json` (measured model capability, below) and
`task-catalog.json` (the vocabulary of what mcgyvr can be asked to do, at the
end of this file).

## Capability data

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


# The decomposition catalog — validation

`task-catalog.json` is the vocabulary of what mcgyvr can be asked to do (#15).
Each entry states what accepting it promises (`guarantee`), which family of the
ladder it may start on (`starts_on`), and what evidence a contract of that type
must carry (`required_evidence`).

It is data, not code, for a reason with teeth: adding a task type must be an
edit to this file and nothing else. `tests/test_catalog.py` proves that by
inventing a type (`sql_migration`) in a temporary file and driving it through
contract validation — a test that only passes while the code is genuinely
generic over the vocabulary.

## Why a family, not a rung

An entry says it starts on `deterministic`, `local` or `api` rather than naming
a rung. Rung names are chosen by whoever wrote the config, so a catalog naming
them would only be valid on the machine it was written for. A family resolves
against any ladder — a rung is `api` exactly when its source declares an
`api_key_env` — and it is a *floor*: a dearer rung satisfies a cheaper family,
never the reverse.

The start is the *type's* floor only. Risk raises it per contract (#16) and
escalation climbs from it (#24). Neither is decided here.

## How the inherited vocabulary was validated

The starting list came from local-ai's triage map and was inherited, not
validated. The evidence available to judge it is the capability table above,
and its limits decide most of the answers: HumanEval+ ranks models on short,
self-contained function synthesis against a stated signature, and says nothing
about multi-hunk edits or about behaviour on a repository the model can see.

So `function_implementation` is the one entry the measurements directly warrant
— it is that shape exactly. Every other entry is carried on a *structural*
argument instead, recorded per entry in its `warrant` field: the evidence is a
tool's output (`format`, `import_sort`, `lint_fix`), the index's own resolution
(`rename_symbol`), a checker's verdict (`type_annotation`), a structural
comparison the gate can make without running anything (`docstring`), or a scope
boundary that removes the failure mode (`test_scaffold` cannot make a test pass
by editing what it tests).

`bug_fix` is the honest weak spot, and its `warrant` says so: nothing measured
covers diagnosis. What makes a cheap attempt safe to make anyway is
`failing_test_first` — with a demonstration required up front, a worker that did
not understand the defect produces a change that visibly fails rather than a
plausible one that lands.

## What was removed, and why

Removals live in the `excluded` block rather than being deleted, for the same
reason the capability table keeps its known-bad measurements: the next person to
reach for `multi_file_refactor` should find out why it is absent instead of
rediscovering it. Both the loader and `mcgyvr catalog <name>` surface the reason
rather than reporting "unknown type".

They fall into three groups:

- **Structurally unservable.** `multi_file_refactor` — the worker output
  protocol is one file's complete content in one fenced block (#25), so no model
  rung can emit a coordinated multi-file change at all. `rename_symbol` is the
  one multi-file operation the catalog carries, and it is deterministic
  precisely because the index resolves the references instead of a model
  guessing them.
- **No acceptance evidence exists.** `interface_design` has no command that can
  fail, so the gate cannot accept it and a model verifier would be the only
  judge — spending expensive tokens to decide whether expensive tokens were well
  spent. `comment_addition` has nothing the gate can distinguish from no change
  at all. `config_edit` has no language adapter (ADR-0001 boundary 8), so
  acceptance would rest on the file still parsing.
- **Not a distinct guarantee.** `algorithm_implementation` differs from
  `function_implementation` only in how hard the prompt is.
  `simple_bug_fix`/`complex_bug_fix` encode difficulty in the type name, and
  difficulty is already routing state held by risk (#16) and escalation (#24) —
  a second copy in the vocabulary is a copy that can disagree with the first.
  `string_literal_edit` is an edit primitive for the deterministic tier (#81),
  not a kind of work to route.
