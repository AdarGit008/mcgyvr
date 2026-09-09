# Unsloth and fine-tuning: the field, read and priced

**Date:** 2026-08-06. **Lane:** lane/187, for issue #187. **Method:** five
delegated investigations — (1) this codebase's fine-tuning surfaces, (2)
Unsloth ground truth at pin, (3) the ecosystem's measured evidence, (4) the
grammar-enforcement rival, (5) the concrete recipe priced against the owner's
rigs — composed and cross-checked here. Every claim carries a label:
**[measured]** (a run or peer-reviewed result exists, independently of the
claimant), **[self-reported]** (the claimant's own numbers, no independent
replication found), **[docs/code]** (read in source or documentation at the
cited location), **[derived]** (our extrapolation, stated as such),
**[anecdotal]** (practitioner reports, no systematic eval). Where evidence is
thin, that is stated rather than smoothed over.

**The one-line verdict:** fine-tuning is affordable and real for this project
($1–3 rented, or hours on rig_b), but it is the *third* move, not the first.
Two zero-training moves beat it on measured evidence; one fine-tune path is
genuinely well-evidenced; two others are measured anti-patterns.

---

## 1. Where mcgyvr stands (from code, not docs)

- **No training corpus exists, and no producer for one.** Zero raw model
  replies are stored anywhere in the repo. The parser's input is dropped at
  the single point that holds it: `tools/bundle/measure.py:627` passes
  `completion.text` to `parse_reply` and keeps only derived scalars. This is
  #184's finding; ADR-0016 fixes the capture format, and the capture point is
  not yet built. [docs/code]
- **No end-to-end worker loop in production code.** `parse_reply`,
  `build_prompt`, `route.climb`, `escalate()` are joined only in tests and the
  bundle measurement tool; no CLI subcommand runs a task. Any "train on our
  own accepted work" plan is sequenced behind that loop existing. [docs/code]
- **A tuned model cannot enter the ladder without a measurement.**
  `capability.py:118-122` structurally refuses unmeasured models
  (`quality: []` → unbindable) and `propose.py:63` demands
  `MIN_QUALITY_GAIN = 0.03` separation before a rung is worth proposing. The
  admission ticket is a measured `humaneval_plus_pass1` row. [docs/code]
- **The serving path a tuned artifact must land on** is an explicit GGUF quant
  under llama-server (CAV-01/CAV-02: the ollama `/api/generate` path is
  quality-unsafe for the Qwen coder family; enforced at
  `runner.py:303-308`). [docs/code]
- **The output contract is narrow**: `whole_file` — one fenced block — is the
  only implemented `output_schema`; the seven refusal codes in
  `src/mcgyvr/worker/reply.py` enumerate the failure surface a format
  intervention must close. [docs/code]
- **The cheap prompt-side lever is already measured**: a 2 KB system bundle
  moved qwen2.5-coder:3b from 45% → 70% pass on the Python sweep (CLM-0004)
  and did nothing on JS/TS (CLM-0012). Any fine-tune competes with that
  baseline, which cost zero training. [measured, this repo's records]
- **Rigs** (`data/capability-table.json`): rig_a = GTX 1660 SUPER 6 GB
  (Turing, no bf16), rig_b = RTX 3060 12 GB (Ampere). The dev VM this lane
  runs on has no GPU at all. Note: `vendored_from.status: "archived"` for
  `AdarGit008/local-ai` is stale as a current description — the repo is not
  archived and was pushed 2026-08-06; the EvalPlus bench tooling
  (`tools/bench_*.sh`) is alive there. [docs/code]

## 2. Unsloth at pin (2026-08-06)

- **Versions:** PyPI `unsloth` 2026.8.5 (2026-08-05); GitHub release track
  (Studio app) v0.1.522-beta (2026-08-04). Two release tracks and 1,031 open
  issues — pin the version for any reproducible run. [docs/code]
- **License:** core Apache-2.0; some optional components (Studio UI)
  AGPL-3.0. 69.6k stars; maintained by Unsloth AI (Daniel and Michael Han).
  [docs/code]
- **Small-model support:** Qwen2.5-Coder 0.5B–14B is a first-class family
  (dedicated blog + free notebooks); also Qwen3/3.5, Llama 3.2 1B/3B,
  Gemma 3, Phi-4, DeepSeek-R1 distills. [docs/code]
- **Hardware floors (their own numbers):** QLoRA minimum VRAM ≈ 3.5 GB for
  3B, 5 GB for 7B, 6 GB for 8B; minimum CUDA capability 7.0.
  [self-reported]
- **Export:** merge LoRA to 16-bit → GGUF (`q4_k_m` documented as
  "Recommended") → llama-server/ollama; or merged safetensors → vLLM. The
  documented #1 post-export failure is a chat-template mismatch between
  training and serving. Known live GGUF-export bugs on specific families
  (Gemma 3 control tokens #5070, Qwen3.5 mis-detection #4534); the
  always-works fallback is `save_pretrained_merged` + llama.cpp's
  `convert_hf_to_gguf.py` + `llama-quantize`. [docs/code]
- **Qwen2.5-Coder specifics:** ChatML template; two Unsloth-patched bugs —
  pad_token must not be `<|endoftext|>` (infinite generation after tuning),
  and base-model ChatML tokens are untrained (moot for instruct). Use their
  patched instruct checkpoints. [docs/code]
- **Verification status of the headline claims:** "2× faster / 70% less
  VRAM" has **no neutral independent replication** found. One independent
  measurement exists (Chronicals, arXiv 2601.02609) and is
  competitor-authored and adversarial (reports one Unsloth config with zero
  gradient norms). The redeeming factor: their notebooks are public and
  reproducible — verification is a run, not a citation. [self-reported /
  measured-adversarial]

## 3. What the field has measured, by use case

**Ranked by evidence strength for mcgyvr's shape (≤14B, coding-agent work):**

1. **Training on verified test-pass signal — the best-evidenced win.**
   DeepCoder-14B (Agentica + Together): GRPO on test-pass reward,
   LiveCodeBench 53% → 60.6%; dataset, code, recipe and logs open.
   SWE-Gym (ICML 2025): SFT on **491** successful agent trajectories →
   +12.3pp SWE-Bench Lite / +13.6pp Verified; also measured *behavioral*
   gains — fewer empty-patch and stuck-in-loop failures (4.6–18.6pp), i.e.
   SFT improved protocol compliance as a side effect. [measured]
2. **Narrow-task distillation (frontier → small).** Distilling Step-by-Step
   (ACL 2023): 770M T5 beats few-shot 540B PaLM on-task. [measured]
   LoRA Land (Predibase, arXiv 2405.00732): 310 LoRA tunes, fine-tuned 7B
   beats GPT-4 by ~10pp on average across 31 (mostly classic-NLP) tasks,
   ~$8/tune. [self-reported → measured, methodology public] Consistent
   caveat everywhere: distilled models are specialists; gains do not
   transfer off-task.
3. **Tool-call formatting.** ToolACE-8B (ICLR 2025): LoRA r16 on Llama-3.1-8B
   → top-tier BFCL. [measured] Relevant as an existence proof that small
   models learn strict output protocols from modest data.
4. **Repo-specific fine-tuning — the thinnest area, flagged.** One vendor
   blog (CGFT, site now dead: ~50% relative completion gain, favorable
   metric, unreplicated) [self-reported]; one enterprise paper on
   proprietary data (RAG vs FT winner depends on the base model)
   [measured, unreproducible]. **No reproducible study shows repo-specific
   tuning improves an interactive coding agent on that repo.**

**Measured failures (as valuable as the wins):**

- **Fine-tuning for format/JSON validity loses to decode-time control.**
  "When Correct Isn't Usable" (arXiv 2605.02363): prompt optimization took
  format accuracy 0% → 84–95% with no training. The "Let Me Speak Freely"
  degradation claim was rebutted by dottxt's matched-prompt re-run
  ("Say What You Mean"): constrained ≥ unconstrained on all three tasks.
  [measured]
- **Fine-tuning for knowledge injection loses to RAG.** Ovadia et al.
  (EMNLP 2024): RAG ~0.875 vs FT ~0.50 on current-events QA. [measured]
- **Format engineering can dwarf fine-tuning ROI.** aider's unified-diff
  switch: GPT-4 Turbo 20% → 61% on its laziness benchmark, zero training.
  [self-reported, public benchmark]
- **Pitfall canon:** chat-template mismatch (the #1 "worse after
  fine-tuning" cause per Unsloth's own docs), overfitting past 1–3 epochs,
  catastrophic forgetting on continued pretraining, vendor evals as upper
  bounds (LLM-as-judge, exact-match on own held-out data). [docs/code +
  measured background]

## 4. The grammar rival — decisive for the format candidate

- **llama-server takes a raw GBNF `grammar` field per request on
  `/v1/chat/completions`** — read in `tools/server/server-common.cpp`
  (`oaicompat_chat_params_parse` reads `grammar` and `json_schema`,
  mutually exclusive), not just in the README. That is the endpoint
  mcgyvr's `OpenAIRunner` already posts to. [docs/code]
- **A fence grammar closes 4 of the 5 refusal codes structurally** — no
  block, two blocks, empty block, unterminated fence — because grammar
  sampling only permits EOS where the grammar can terminate. **Truncation
  is not closable** by grammar or by fine-tuning: a `max_tokens` cut still
  yields an unterminated fence. [docs/code + analysis]
- Expressibility: fixed fence length is trivially GBNF-expressible
  (per-line exclusion of fence-opening lines); arbitrary matching backtick
  counts are not — enumerate n=3,4 branches, or force the reply to start
  with the fence. [analysis]
- **ollama cannot do this** (JSON-schema structured outputs only; raw
  grammar PR #5348 closed in favor of #7900) — but ollama's native path is
  already the CAV-01 quality-unsafe one. vLLM accepts a near-identical
  grammar via xgrammar (`structured_outputs.grammar`, dialect "follows the
  specification of GBNF"). [docs/code]
- Quality under constraint, measured: SynCode (full-language CFGs, ~96%
  fewer syntax errors), type-constrained decoding (halves compile errors,
  improves functional correctness), dottxt matched-prompt re-run (no
  degradation from loose constraints). Known caveat: greedy grammar
  masking distorts the distribution (NeurIPS 2024, Grammar-Aligned
  Decoding) — bites tight grammars, not a loose fence-placement grammar on
  a prompt that already asks for a fence. [measured]
- Production practice: no mainstream agent enforces fences by grammar;
  aider chose lenient-parse + bounded retry (max_reflections=3) after
  benchmarking formats. Grammar here is additive hardening on the backend
  we already prefer, not exotic. [docs/code]

**Consequence:** the "fine-tune for reply well-formedness" candidate from
#187's filing is retired. #71 (grammar-enforced worker output) wins that
ground on measured evidence and on price.

## 5. The recipe, priced

- **rig_b (RTX 3060 12 GB) is the trainer.** 1.5B/3B comfortable, 7B
  workable at seq ≤4k. Nearest strong measurement (mlabonne, HF blog:
  Llama-3.1-8B QLoRA, 100k samples, seq 2k — A100 4h45m, T4 ~47h) scales
  to roughly 10–20 min/epoch at 500 examples and 1–2 h/epoch at 5,000 for
  7B-class on a 3060; halve for 3B. [measured source, derived scaling]
- **rig_a (GTX 1660 SUPER) must not train.** FP16 matmul on that exact
  card measured 5–9× slower than FP32 (pytorch#121957, no tensor cores);
  the 16-series fp16 NaN pathology is a documented family trait; no
  16-series training success report found. It is the eval/serving box.
  [measured + anecdotal]
- **Rented alternative: $1–3 per run.** RTX 4090 at ~$0.34/h (RunPod
  community, 2026-08); a 5k-example 2–3-epoch 7B QLoRA ≈ 1–2 h. Colab free
  T4 covers 1.5B/3B runs at zero cost with babysitting. Local-vs-cloud is
  convenience, not cost. [docs + derived]
- **The eval loop closes out of the box.** EvalPlus v0.3.1
  `--backend openai --base-url http://localhost:8080/v1 --greedy` runs
  directly against llama-server; ~5–45 min per 164-task greedy pass
  depending on model size [derived]. The bench tooling already exists in
  the live `AdarGit008/local-ai` repo.
- **Open measurement nobody has published:** whether QLoRA gains survive
  q4_K_M quantization (tuned-fp16 vs tuned-q4 vs base-q4). No rigorous A/B
  found anywhere. The pilot answers it as a side effect, since the table
  only accepts measurements on the quant actually served. [thin — flagged]

## 6. The decision table

### Do now — no training

| # | What? | How? | Why? |
|---|---|---|---|
| 1 | Enforce the reply format with a grammar, not a fine-tune (#71) | Per-request GBNF `grammar` on llama-server's `/v1/chat/completions`; ~10-line fence grammar; same grammar on vLLM via xgrammar; not possible on ollama (already the CAV-01-unsafe path) | Zero training and zero tokens; closes 4 of 5 refusal codes structurally; measured evidence says loose constraints don't hurt and syntax constraints help; fine-tuning for format is the measured loser |
| 2 | Start keeping worker replies and outcomes (#184, ADR-0016 shape) | Capture at the point that already holds the text (`tools/bundle/measure.py:627`); raw reply + provenance; failures kept as gold | Every fine-tune path needs this corpus; zero replies stored today; SWE-Gym shows 491 kept successes moved a benchmark double digits — the needed scale is small |

### Do next — the one fine-tune worth running

| # | What? | How? | Why? |
|---|---|---|---|
| 3 | Pilot: tune Qwen2.5-Coder-3B on verified-pass data (#189) | Unsloth QLoRA r16, ChatML both ends, patched instruct checkpoint, pinned version, on rig_b; merge-16-bit → q4_K_M GGUF → llama-server; EvalPlus base-q4 vs tuned-q4 | Best-evidenced category in the field (DeepCoder, SWE-Gym — both replicated); $1–3 rented or hours on rig_b; the +3pp table gate is the pre-registered success criterion; also settles the unpublished q4-survival question |
| 4 | Later: distill accepted API-tier work into the local tier (#190) | Same recipe; training data = gate-accepted API-model outputs once the production loop produces them | Narrow-task distillation is well-measured (Distilling Step-by-Step, LoRA Land); blocked today on the corpus (#184) and the worker loop — sequenced, not speculative |

### Don't

| # | What? | Why not? |
|---|---|---|
| 5 | Fine-tune for JSON/format validity | Measured anti-pattern; row 1 gets it free |
| 6 | Fine-tune to teach a model repo facts | RAG wins measured; repo-specific FT evidence is one dead vendor blog and one unreproducible paper |
| 7 | Train on rig_a | Measured 5–9× fp16 slowdown on that card; NaN-prone family; no success reports |

### Facts that gate

| # | What? | Why it matters |
|---|---|---|
| 8 | Truncation is the failure nothing fixes | Grammar guarantees hold only at EOS; budget + retry handling needed regardless |
| 9 | Unsloth's headline claims are self-reported | No neutral replication; verify by running their reproducible notebooks; pin the version |
| 10 | Ladder entry is by measurement only | `capability.py` refuses unmeasured models; EvalPlus on the served quant is the admission ticket |

## 7. Sources

Primary: llama.cpp `tools/server/server-common.cpp` and
`grammars/README.md`; ollama PRs #5348/#7900; vLLM structured-outputs
docs; xgrammar docs; Unsloth docs (requirements, model catalog, GGUF
saving, Qwen-coder blog, fine-tuning guide, RL guide, multi-GPU) and
GitHub issues #5070, #4534, #4970, #3773, #3817; PyPI `unsloth`;
DeepCoder (together.ai blog + HF); SWE-Gym (arXiv 2412.21139); ToolACE
(arXiv 2409.00920); Distilling Step-by-Step (arXiv 2305.02301); LoRA Land
(arXiv 2405.00732); Ovadia et al. (arXiv 2312.05934); When Correct Isn't
Usable (arXiv 2605.02363); Let Me Speak Freely (arXiv 2408.02442) and
dottxt's "Say What You Mean"; SynCode (arXiv 2403.01632);
Type-Constrained Code Generation (arXiv 2504.09246); Grammar-Aligned
Decoding (arXiv 2405.21047); aider unified-diffs and edit-formats docs;
mlabonne SFT blog (HF); pytorch#121957, pytorch#77955; EvalPlus v0.3.1;
RunPod/Lambda pricing pages; MarkTechPost framework comparison
(2026-07-22); Chronicals (arXiv 2601.02609). In-repo: capability table +
CAV-01/02, CLM-0003/0004/0012, ADR-0016, `reply.py`, `runner.py`,
`capability.py`, `propose.py`, `tools/bundle/measure.py`.
