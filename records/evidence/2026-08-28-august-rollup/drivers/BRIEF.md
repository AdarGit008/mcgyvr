# Extraction brief — mcgyvr August serving evidence

ROOT: /home/adaramir/claude/mcgyvr/records/evidence/

## Goal
Extract EVERY measured decode-throughput data point from your assigned directories into
one normalized JSONL. A downstream step ranks setups by `tok/s x model_size_B x n`
for srv1 and srv2. Your job is extraction + provenance ONLY. Do not rank. Do not
guess model parameter counts — that mapping is applied centrally.

## Ground rule: every cell must be linked to a run
Each emitted record MUST carry enough provenance that a human can `sed -n 'Np'` the
source file and see the number. No number without a locator.

## Output schema — one JSON object per line
{
  "rig":        "srv1" | "srv2",            // aka host
  "engine":     "llamacpp" | "vllm" | "ollama" | other-as-found (lowercase),
  "engine_ver": "b10644" | "v0.26.0" | null,
  "model":      raw model string as found (HF id, gguf tag, ollama tag),
  "quant":      "Q4_K_M" | "AWQ" | "IQ4_XS" | "MXFP4" | null,
  "config":     compact config string (np/ncmoe/util/max-model-len/max-num-seqs/cell id),
  "n":          integer concurrency,
  "agg_tok_s":  float   // AGGREGATE decode tok/s summed across the n streams
  "per_stream_tok_s": float | null,
  "p50_latency_s": float | null,
  "tokens_per_request": int | null,
  "date":       "YYYY-MM-DD" (run date; from dir name or record timestamp),
  "src_file":   path relative to ROOT,
  "src_locator":"line:1234" | "$.levels[3]" | "cell=A1-1" | "record 12" — must be precise,
  "note":       free text: caveats, attempt/retake, control-run flag, anything odd
}

Refusals/OOM/launch failures — emit too, so empty cells are explained, not silent:
{"kind":"refusal","rig":..,"engine":..,"model":..,"config":..,"reason":"<engine's own words, <=200 chars>","date":..,"src_file":..,"src_locator":..}

Measured rows may omit "kind" (defaults to "level").

## Gotchas already confirmed — apply them
1. `agg_tok_s` is AGGREGATE across streams, not per-stream. Verify on any file you touch:
   at high n, agg/n should be << agg at n=1. If a field is clearly per-stream, convert
   and say so in "note".
2. The SAME model is measured under MANY configs (np, ncmoe, gpu-memory-utilization,
   max-model-len, max-num-seqs, tokens-per-request). Emit ALL of them as separate rows
   with distinct "config". Do NOT dedup — dedup happens centrally.
3. `tokens_per_request` matters: the 2026-08-28 protocol is 475 tokens, ignore_eos,
   temp 0, one fixed prompt. Other dirs sweep token counts (128/475/2048...). Record it;
   rows at a non-475 token count must say so in "note" — they are NOT comparable.
4. Ramp-style files nest levels: `"levels":[{"n":1,"wall_s":..,"agg_tok_s":..},...]`.
   Explode them into one row per level, locator `$.levels[i]` plus the line number.
5. Control / bridge runs (e.g. llama.cpp b10481 control cells) are NOT candidate setups.
   Emit them but set note "CONTROL RUN — not a candidate setup".
6. Retakes/attempts: fields like `attempt`, `attempts`, `all_attempts_agg_tok_s`,
   `retakes`. Emit each attempt separately; note the attempt index.
7. A launch that failed produces a row with launch.ok=false — that is a refusal, not a 0.
8. Some files carry precomputed `max_agg_tok_s` / `max_at_n`. Prefer the underlying
   `levels` array; use the precomputed value only if levels are absent (note it).

## Reference (read, don't copy blindly)
- records/evidence/2026-08-28-setup-selection/drivers/analyze.py — canonical tag->model
  name/type/total_B/active_B/quant map. Use it to normalize `model` strings where you can,
  but keep the raw string too.
- records/evidence/2026-08-28-setup-selection/README.md — the protocol and the wall list.

## Deliverables
1. Write your JSONL to the exact path you are given.
2. Return (as your final text, not a file) a SHORT report: row count, distinct
   (rig,engine,model) combos, token-counts present, which files you found nothing in and
   why, and any gotcha you hit that this brief did not list.
Be exhaustive within your dirs. Missing data is worse than extra rows.
