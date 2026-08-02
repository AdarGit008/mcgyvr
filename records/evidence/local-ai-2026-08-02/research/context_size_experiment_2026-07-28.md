# Context Size vs Quality Experiment — Design

**Issue:** #27 · **Lane:** lane/27 · **Date:** 2026-07-28
**Source claim:** `research/REVIEW_ARCHITECTURE_2026-07-28.md` via digestion #23

## Hypothesis under test

The project operates on an unverified assumption: **minimal context per task is
optimal** for small local models on 6GB VRAM. The counter-hypothesis is that a
compact skill bundle (role + rules + conventions, a few KB) buys enough quality
to pay for its token cost — or that past some size it degrades the model.

This experiment measures the tradeoff instead of assuming it.

## Design

### Conditions (context ladder)

| Condition | System prompt | Approx size | What it tests |
|-----------|---------------|-------------|---------------|
| `c0` | none — contract only | 0 KB | current strict-minimal policy |
| `c1` | role + output rules | ~0.4 KB | cheapest possible bundle |
| `c2` | c1 + coding standards + pitfalls checklist | ~2 KB | the "compact skill bundle" from the review |
| `c3` | c2 + full project engineering handbook | ~8 KB | context-budget blowout / degradation end |

Bundles live in `data/context_exp/bundles/`. The contract is always the user
message, unchanged across conditions — only the system prompt varies.

### Models

| Key | Model | Quant | Engine | Offload |
|-----|-------|-------|--------|---------|
| `q3b` | qwen2.5-coder:3b | Q4_K_M (Ollama blob) | llama-server | `-ngl 99` (full) |
| `qwen3` | qwen3-coder-30b-a3b | Q2_K | llama-server | `-ngl 10` |

Both run through the same engine (Ollama-bundled `llama-server`, CUDA env per
`docs/llama_cpp_cuda_gotchas.md`) at `--ctx-size 4096`, greedy (temp 0),
`max_tokens 768`. Same engine for both models removes template/sampler
confounds; the 3b blob is loaded directly from the Ollama store.

### Task set

`mvp/instrumentation/context_tasks.py` — a fixed regression set of **20 real
task contracts** (template: `mvp/workers/task_contract_template.md`), not
HumanEval. Composition:

- 8 × `function_impl` (easy → hard: RLE, interval merge, semver parse, LRU,
  chunking, CSV field parse, flatten, topo sort)
- 5 × `bug_fix` (factorial base case, binary search bounds, mutable default
  arg, dict mutation during iteration, string slice off-by-one)
- 3 × `refactor` (loop→comprehension with banned-pattern check, dedup two
  functions behind wrappers, recursion→iteration where recursion can't scale)
- 2 × `type_annotation` (checked via `typing.get_type_hints`)
- 2 × `edge_case` hardening (safe divide, KEY=VALUE config parser)

Every task carries a runnable acceptance script (isolated, stdlib-only, 30s
timeout) and a **reference solution**. `--selftest` runs every reference
against its acceptance script; the experiment is invalid unless selftest is
100% green.

### Metrics (per task × condition × model)

- `pass1` — first-pass acceptance (primary quality metric)
- `pass_final` + `remediation_used` — one remediation round max: on failure,
  the acceptance error output is fed back and the model retries once
- latency (wall), prompt/completion tokens (server-reported usage)
- VRAM sample per run (`nvidia-smi`)

### Procedure

`mvp/instrumentation/run_context_exp.sh`:

1. Phase A — 3b: start llama-server on the Ollama blob (`-ngl 99`), run all
   4 conditions × 20 tasks, kill server.
2. Phase B — 30b: start llama-server on the Q2_K GGUF (`-ngl 10`), same sweep,
   kill server.
3. Cleanup per repo convention (no stale processes, VRAM back to baseline).

Results append to `data/context_exp/results_<model>.jsonl` (one line per task
× condition; resume-safe — completed keys are skipped on restart).

## Analysis plan

- Acceptance rate per condition per model; c0 is the baseline.
- Cost per condition: mean prompt tokens + mean wall latency.
- **Break-even:** smallest condition whose acceptance gain over c0 is
  non-trivial (≥ +5 pp on 20 tasks = 1 task) at acceptable latency cost;
  degradation flagged if any condition scores *below* c0.
- Slice by task type — bundles may help refactor/edge-case tasks and do
  nothing for pure function_impl.

## Threats to validity

- n=20, single greedy seed — small differences (±1 task, 5 pp) are noise;
  only consistent, direction-agreeing deltas across both models are signal.
- Q2_K quantization may interact with long prompts in ways Q4+ would not.
- Acceptance scripts proxy "accepted production-quality work"; they check
  behavior + a few contract constraints, not style.
- Written by the same author as the reference solutions — task-selection bias
  toward testable tasks.

## Deliverable

Verdict in a results doc: **keep strict-minimal** or **adopt minimal+skills
with a measured size cap**. Feeds the skill-spike decision deferred in #23 and
the hard constraint recorded in lane/16 ("no change may inflate worker
prompts" — this experiment is the sanctioned way to revisit it).
