# The identity surface — what a run can observe, and what it records

**Measured 2026-08-16.** Issue #276. Every figure here was re-derived on the day
against the tree at `main` and the rigs as they were serving; the commands are
given so a reader can repeat them rather than trust the table.

This document is the evidence half of #276. The issue carries the decisions.

## 1. What a run records today

139 manifests under `records/measurements/`. By commit date the population grew
91 (2026-08-12) → 121 (2026-08-13) → 139 (2026-08-14), which is why the counts
in circulation disagree: ADR-0024's amendment says 133 and #265 says 123, and
neither matches the tree at any of those dates. **A manifest count is only
meaningful with its population and its commit stated.**

The newest and richest shape, `bench-control-norule-7b-2026-08-14/bench-py`:

```
endpoint  protocol  model  serving_build  tier  draws
greedy_temperature  sampled_temperature  max_output_tokens
condition  gate_rungs  gate_semantic  mode
bundle_sha256  tasks_sha256  round  product_sha256
invocations  completeness
```

Per row in `results.jsonl`: `task, type, model, arm, draw, temperature,
latency_s, prompt_tokens, completion_tokens, stop_reason, overran_cap,
candidate_sha256, passed, parse_error, acceptance_s, rejected_by,
rejected_before_acceptance, fail_output, environment_issues`. Raw completions
land in `candidates/`, pass or fail — which is what let the 2026-08-15 re-score
put 5,694 saved replies on a new bar for zero model cost.

**The pattern: what describes the corpus is fingerprinted; what describes the
instrument is named.** `serving_build` is the one content-derived identity field
the project has.

Coverage of the two fields that are not universal:

| field | manifests carrying it |
|---|---:|
| `gate_rungs` | 14 of 139 |
| `round` / `product_sha256` | newest runs only |

## 2. The observable surface, verified

### 2.1 The model — one call, nine keys

```
curl -s http://srv2:11434/api/show \
  -d '{"model":"qwen2.5-coder:1.5b","verbose":true}'
```

Returns `capabilities details license model_info modelfile modified_at system
template tensors` — **9 top-level keys, of which we take 0**. Within them:
`model_info` holds **33** GGUF metadata keys, `tensors` **338** entries,
`modelfile` 13,308 bytes, `template` 1,615 bytes, `system` 68 bytes.

**The `verbose` flag is load-bearing.** Without it the tokenizer arrays return
`null` rather than being absent:

| call | `tokenizer.ggml.tokens` | `tokenizer.ggml.merges` |
|---|---:|---:|
| default | `null` | `null` |
| `"verbose": true` | 151,936 | 151,387 |

A probe that omits it records "unobtainable" while the answer is one flag away —
which reads as having checked. Encode the flag in the probe, not in a comment.

Values on `qwen2.5-coder:1.5b`:

| property | source key | value |
|---|---|---|
| architecture | `general.architecture` | `qwen2` |
| parameters | `general.parameter_count` | 1,543,714,304 |
| quantization | `details.quantization_level` / `general.file_type` | `Q4_K_M` / 15 |
| effective context | `qwen2.context_length` | 32,768 |
| tokenizer model | `tokenizer.ggml.model` | `gpt2` |
| pre-tokenizer | `tokenizer.ggml.pre` | `qwen2` |
| BOS / EOS | `tokenizer.ggml.bos_token_id` / `eos_token_id` | 151,643 / 151,645 |
| add BOS | `tokenizer.ggml.add_bos_token` | `false` |
| vocabulary | `tokenizer.ggml.tokens` | sha256 `df83315e4347…` |
| merges | `tokenizer.ggml.merges` | sha256 `1aea6bc8727b…` |
| template | `.template` | sha256 `0a457b4bd4db…` |

**Two layers, and the split matters.** `model_info` and `tensors` are the GGUF
file's own metadata, verbatim. `details`, `template`, `system`, `modelfile`,
`capabilities`, `modified_at` and `license` are ollama's rendering on top —
`details.quantization_level` is `general.file_type` restated, `parameter_size`
is `parameter_count` restated. A `template` digest therefore fingerprints **how
ollama serves the model**, not the model, and belongs beside `serving_build`
rather than inside model identity.

### 2.2 Weights — the manifest digest is not the weights digest

`/api/tags` returns `digest: d7372fd828518a4d…` and `size: 986062089` for
`qwen2.5-coder:1.5b`. Both are widely misread.

```
ssh srv2 sha256sum \
  /usr/share/ollama/.ollama/models/manifests/registry.ollama.ai/library/qwen2.5-coder/1.5b
```

returns `d7372fd828518a4d…` — **exactly the `/api/tags` value.** So `digest` is
the sha256 of the *manifest file*, and the manifest lists five layers:

| layer | digest | bytes |
|---|---|---:|
| model | `sha256:29d8c98f…` | 986,048,576 |
| system | | 68 |
| template | | 1,615 |
| license | | 11,343 |
| config | | |

`size: 986062089` is the **layer sum**, not the weights.

Consequences:

- The manifest digest **moves when the template, system or license layer
  changes** — over-sensitive as a weights identity.
- The **model layer digest** is the separable weights identity, and it already
  exists. It is not exposed by `/api/show` or `/api/tags`; it needs manifest
  parsing over ssh.
- Both are **ollama's** content-addressing. Verifying the claim means hashing
  the blob: 986 MB in 9.8 s, and it matches its own `sha256-<digest>` filename.

`model_info + tensors` is **necessary but not sufficient** as model identity:
`tensors` carries name/shape/dtype and not weight values, so a fine-tune has
identical shapes. `general.finetune` and `general.base_model.*` exist but are
self-declared header strings. Different digest ⇒ different model is sound; same
digest ⇒ same model is not. The gap sits exactly where identity matters most —
#189 was a fine-tune contrast.

### 2.3 The serving build

```
curl -s http://srv1:11434/api/version   →  {"version":"0.32.4"}
curl -s http://srv2:11434/api/version   →  {"version":"0.32.5"}
```

The split ADR-0024 was written about is **still live**. Any identity contract
must keep refusing to mix them.

### 2.4 The bar

Obtainable now, none of it recorded:

| | command | value |
|---|---|---|
| ruff | `.venv/bin/ruff --version` | 0.16.1 |
| ruff rule inventory | `ruff rule --all --output-format json \| jq length` | 968 |
| ruff resolved settings | `ruff check --show-settings <f>` | 786 lines |
| node | `node --version` | v24.18.0 |
| eslint | `npx eslint --version` | 9.39.5 |
| prettier | `npx prettier --version` | 3.9.6 |

What the adapters actually run (`src/mcgyvr/gate/adapters/python.py:69`,
`javascript.py:123`), both with `cwd=repo` — so the **resolved** config is
whatever is staged in the sandbox, not mcgyvr's own:

```
ruff check --output-format=json --force-exclude -- <files>
ruff format --diff --force-exclude -- <files>
eslint --format json -- <files>
```

`tools/bench/score.py` stages that config: `pyproject.toml` derived from the
project's own at call time (`:125`), `eslint.config.mjs` copied (`:78`).

### 2.5 The host

```
ssh srv2 nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
  →  NVIDIA GeForce RTX 3060, 12288 MiB
```

Answers, and is unrecorded. srv1 and srv2 differ in GPU, CPU and memory
channel; today only the endpoint string implies which ran.

## 3. Demonstrated defects

### 3.1 `accept.py` is outside the task digest

`tier_digests` (`tools/breadth/measure.py:419`) hashes
`bundle.dumps(task.contract)`. A contract carries `acceptance: ['python
accept.py']` — the **command string**. The file is never hashed.

Copy a task, append a line to its `accept.py`, recompute:

```
original accept.py : 8cfc86051cdf5073
mutated  accept.py : 8cfc86051cdf5073
DIGEST MOVED: False
```

**The per-task grader is mutable with no record.** `reference.py` is likewise
unhashed, but `score.py:198` deliberately never stages it — *"it is the answer,
and it has no business sitting in a workspace a checker runs in"* — so it
cannot affect a verdict. The two need different dispositions.

### 3.2 The user message is outside every digest

`record_run`'s docstring states *"The prompt is pinned through the task digests
(the user message is a function of the contract)"*. That guarantee predates
`ablate()`, which transforms the contract before the prompt is assembled while
`tier_digests` hashes the **unablated** contract from disk.

The failure is asymmetric, and the asymmetry is the finding:

| lever | stage | no-op behaviour |
|---|---|---|
| `norule` | message | **raises** `MatrixError` (`tools/bench/matrix.py:215`) |
| `noscaffold` | contract | silently identical when `target_content` is already empty |
| `planonly` | contract | same |

`ablate()`'s own docstring says the no-op is by construction and the caller must
select the eligible set. So message-stage levers are guarded and contract-stage
ones rely on caller discipline — and the record cannot tell a lever that worked
from one that did nothing.

### 3.3 A crashed linter scores as a clean pass

Both adapters, identically (#261):

```python
except json.JSONDecodeError:
    return []          # no finding, no environment_issue
```

The receiving machinery is already complete — `GateResult.environment_issues`
(`src/mcgyvr/gate/runner.py:70`), `ToolUnavailableError` caught at `:182`, and
the row schema carries `environment_issues`, currently always `null`. The fix is
to raise rather than return.

### 3.4 The round pin does not cover the bar

`product.SURFACE` (`tools/bench/product.py:64`) declares `src/mcgyvr`,
`tools/breadth/measure.py`, `tools/bundle/measure.py`, `tools/bench/score.py`,
`matrix.py`, `matrix.json`, `product.py`.

Absent, and each affects a verdict:

| path | why it matters |
|---|---|
| `pyproject.toml` | `score.py:125` derives the staged ruff config from it |
| `eslint.config.mjs` | `score.py:78` copies it into every sandbox |
| `uv.lock` | a `uv sync` can move ruff between two runs inside one round |
| `data/task-catalog.json` | the `task_type` vocabulary the strata are built on |
| `tools/bench/gate_rescore.py`, `lintless.py` | they score, and are unpinned |

Separately, `surface_files` globs `*.py` for directories, so
`src/mcgyvr/prompts/*.md` — the system prompts — sit outside the product digest.
They are covered per run by `bundle_sha256`, which is **not in `COMPARABLE`**.

## 4. What 400 tasks buys

Re-derived with `tools/power/mde.py` on the one stratum that resolves today
(1.5B, `bench-ts`, `function_implementation`):

| n | psi=0.134 | psi=0.090 | psi=0.060 |
|---:|---:|---:|---:|
| 198 | 7.6pp | 6.6pp | 5.1pp |
| 257 | 7.0pp | 5.4pp | 4.7pp |
| 308 | 6.2pp | 5.2pp | 4.2pp |
| **400** | **5.5pp** | 4.5pp | 3.8pp |

About **1.3x**. It buys **nothing** for the seven strata that cannot resolve at
any n, because `delta <= psi` is hard. Worth paying for only if the new material
is more responsive than the old — and the existing corpus came out 88% frozen.
That is #224's unmeasured responsive fraction, gated by #272.

> **Corrected 2026-08-17 (#299).** This paragraph read *"About 1.3x, and still
> short of 5pp on the arm's own psi"*, and the half-sentence removed above is
> where a 5pp target entered the project. **ADR-0019 sets no bar.** Its D2 states
> fitness over a free variable `b`, and its D3 removes a fixed bar entirely for
> the cheapest lever class — *"the bar is whatever the bench resolves."* 5pp
> appears in that record three times and is, in turn, the quantum at n = 20, one
> row of a sizing table, and the *outcome* at n = 400. None of them is a
> threshold. The owner's note of 2026-08-17 is that the number was supplied in
> conversation and never decided.
>
> The rest of the paragraph is untouched and is the argument that survives: the
> case against 400 rests on 1.3x for the cost, on the seven strata no n reaches,
> and on an unmeasured responsive fraction — not on falling short of a bar.
> See ADR-0019's 2026-08-17 amendment.

## 5. The reproducibility bound, re-derived

`reproducibility.json` declares `bound_pp = 1.47` for
`(qwen2.5-coder:1.5b, bench-py, 5 rungs, 0.32.5)` from `flips = 0` over
`cells = 257`.

That reproduces exactly as the Wilson upper limit, which for `d = 0` collapses:

```
upper(0, n) = z^2 / (n + z^2)
upper(0, 257) = 3.8416 / 260.8416 = 0.014728  →  1.4728pp
```

Two properties matter for #276's admission rule:

- **In flips, the threshold is near-invariant in n while the null is clean** —
  `n x z^2/(n+z^2)` rises 3.22 (n=20) → 3.79 (n=257) → 3.81 (n=400), converging
  on `z^2 = 3.84` from below. This is why "about 4 flips" looked robust.
- **It stops being invariant the moment the null is not clean.** At `d = 1,
  n = 257` the upper limit is 2.17pp, i.e. ~5.6 flips — a ~50% move from one
  cell.

And `matching` keys on model, tier, `gate_rungs` and `serving_build` but **not
on `cells`**, so the rate transfers to subsets it was never measured on: applied
to a 34-cell eligible set it is ~7x too strict, where `upper(0, 34) = 10.15pp`.
The bound must be measured on the paired set that will be perturbed, and `cells`
must join `matching`.

## 6. Reading the list as complete

It is not, and cannot be shown to be. A complete field list is an absence claim.
What replaces it, in increasing power:

1. **Store the surface rather than a selection** — hash the whole probe response
   and keep its key list, so a new field is a diff. Narrowing later is always
   possible; widening retroactively never is.
2. **Mutate the world, require the record to move** (ADR-0026 lens 2). Status
   today: endpoint ✓, serving build ✓ — ablation ✗, re-pull ✗, lint rule ✗.
3. **The reproducibility bound** — the only mechanism that catches a field
   nobody has thought of, since any difference beyond it is by definition
   unrecorded.

**Residual, stated rather than closed:** a field that varies, was never varied,
and stays inside the bound is invisible to all three. The record should carry
what was done to look — surface digest, perturbations run, bound applied — not a
claim of completeness.
