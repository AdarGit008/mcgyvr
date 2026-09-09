# rig-reality

## verdicts
### Q: Are srv1/srv2 up and running the ollama builds identity-surface claimed (0.32.4/0.32.5 on 2026-08-16)?
VERDICT: CONFIRMED
EVIDENCE: curl -s -m 5 http://srv1:11434/api/version -> {"version":"0.32.4"}; http://srv2:11434/api/version -> {"version":"0.32.5"} (2026-08-18). Matches docs/identity-surface-2026-08-16.md:137-138 exactly.

### Q: Which models are present on each host (qwen2.5-coder 1.5b/3b/7b? nemotron?), with digests?
VERDICT: CONFIRMED
EVIDENCE: curl /api/tags. srv1 (5 models): nemotron-3-nano:4b 6cc467f05439, qwen2.5-coder:7b dae161e27b0e, :3b f72c60cabf62, :1.5b d7372fd82851, llama3.2:3b a80c4f17acd5 — all Q4_K_M. srv2 (12 models): same three qwen2.5-coder sizes with byte-identical digests to srv1, plus qwen2.5-coder:14b 9ec8897f747e, nemotron-3-nano:4b (same digest as srv1) and :30b-a3b-iq2 200fc79ae2f6 (IQ2_XXS), qwen3-coder:30b 06c1097efce0, qwen3-coder-next-ud:q3_K_XL 499a5d0084fe, qwen3:30b-a3b ad815644918f, gpt-oss:20b 17052f91a42e, deepseek-coder-v2:16b 63fb193b3a9b, yi-coder:9b 39c63e7675d7.

### Q: Does POST /api/show {verbose:true} on srv2 return the 9-key surface identity-surface documented, with non-null tokenizer arrays?
VERDICT: CONFIRMED
EVIDENCE: Live POST for qwen2.5-coder:1.5b and :7b on srv2: top-level keys exactly [capabilities, details, license, model_info, modelfile, modified_at, system, template, tensors] = 9 keys, matching docs/identity-surface-2026-08-16.md:47-57. With verbose:true, model_info['tokenizer.ggml.tokens'] is a list of 151,936 (1.5b) / 152,064 (7b) and 'tokenizer.ggml.merges' 151,387 (both); with verbose:false both are null — confirming the load-bearing-flag claim at tools/bench/identity.py:360-365 including its exact '0 against 151,936' measurement. template is a 1,615-byte string, matching the doc's byte count.

### Q: Would the first r2 dispatch's model probe succeed as coded, or does the code's expectation mismatch the live response?
VERDICT: CONFIRMED
EVIDENCE: Ran the actual function: uv run --no-sync python with tools/ on sys.path, bench.identity.probe_model('http://srv2:11434', model) for 1.5b and 7b. All four MODEL_PROBE_FIELDS populated, reasons == {} (zero refusals). model_sha256 equals the /api/tags digest for each model (d7372fd82851... / dae161e27b0e...); merges_sha256 (df8a8d91b3b6...) and template_sha256 (47fca52d970e...) identical across the two models while vocabulary_sha256 differs — exactly the separability the docstring at identity.py:383-393 argues. This discharges ADR-0033's admission (docs/decisions/0033-...md:193-198) that the success path 'has not been exercised against a live endpoint': first rig contact confirms the code, no correction needed.

### Q: Are the hosts otherwise reachable / is ssh available (without ssh-ing)?
VERDICT: CONFIRMED
EVIDENCE: getent hosts: srv1=100.67.218.22, srv2=100.69.72.51 (tailscale, *.tailbaf744.ts.net). TCP port 22 open on both (bash /dev/tcp connect test only, no login). ~/.ssh/config has Host srv1 and Host srv2 entries (user adaramir, id_ed25519). Did not ssh per instructions.

## new_findings
- ADR-0033's open admission (the model-group success path never ran against a live endpoint) is now empirically discharged: probe_model executed against live srv2 ollama 0.32.5 and returned all four digests with zero refusals for both qwen2.5-coder:1.5b and :7b.
- The docstring's measured numbers are live-accurate to the digit: 151,936 tokens on 1.5b (identity.py:363), 151,387 merges, 1,615-byte template — the survey doc and the code describe the running rig, not a stale snapshot.
- qwen2.5-coder 1.5b/3b/7b digests are byte-identical across srv1 and srv2 (same manifest digest on both hosts), so a cross-host contrast on those models would pass the model_sha256 comparability check as currently coded.
- srv2 carries 12 models including qwen2.5-coder:14b and two nemotron-3-nano variants (4b Q4_K_M shared with srv1, 30b-a3b IQ2_XXS srv2-only); srv1 carries only 5 small models. Any nemotron-30b or 14b work is srv2-only.
- probe_model's 30s MODEL_PROBE_TIMEOUT_S is comfortably sufficient live: both verbose /api/show calls (multi-MB tokenizer arrays) completed well inside it.

## plan_input
- The first r2 dispatch's model probe will succeed as coded: probe_model was executed live against srv2 (ollama 0.32.5) for qwen2.5-coder:1.5b and :7b and returned all four MODEL_PROBE_FIELDS with reasons == {} — no code change needed before first dispatch.
- Rigs are up as of 2026-08-18: srv1 ollama 0.32.4 (100.67.218.22), srv2 ollama 0.32.5 (100.69.72.51), matching docs/identity-surface-2026-08-16.md; both reachable over tailscale, ssh port open, config entries present.
- Live digests to pin if the plan wants them: qwen2.5-coder:1.5b d7372fd82851..., :3b f72c60cabf62..., :7b dae161e27b0e... — identical on both hosts; probe-computed vocabulary_sha256 fca1c73411bc... (1.5b) / 5e8c08a17404... (7b), merges_sha256 df8a8d91b3b6... and template_sha256 47fca52d970e... shared across both models.
- ADR-0033's 'first rig contact will confirm or correct' clause is resolved as CONFIRM; the plan can drop any contingency for reshaping the model-probe code against the live API and can cite this verification when closing that admission.
- The verbose:true flag is verified load-bearing on the live rig: without it tokenizer.ggml.tokens/merges come back null on ollama 0.32.5, exactly as identity.py:360-365 claims — any alternative probe implementation must keep the flag.
