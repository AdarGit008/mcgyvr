# 2026-08-24 — the knob surface: declared, accepted, effective (#357)

Built by `tools/bench/serving/knobs.py build` from
`records/evidence/2026-08-24-config-sweep/` (140 cells, both rigs, four
models, one image). `surface.json` is the record; `surface.md` is the same
table rendered. Both are regenerated, never edited:
`tests/test_knobs.py::test_the_committed_surface_is_what_the_evidence_produces`
rebuilds them from the sweep and refuses a difference. **No rig was touched
for this directory.** It re-reads runs already on disk, and every row cites
the file and the cell it came from.

## The three columns, and what each one holds today

**1. Declared — not captured.** `vllm serve --help=all` in the pinned image
needs a device: run on a host with no GPU on 2026-08-24 the image exits 1
with `Failed to infer device type` (vLLM constructs a `VllmConfig` while
printing help). The capture is `knobs.py declared <rig> <this dir>`; it
writes `declared-vllm-<digest12>.json` plus the raw text, and the builder
picks it up on the next `build`, at which point the **untried** list becomes
enumerable. Until then `surface.json` says `untried: {"unknown": true}` — a
count nobody has is not zero. Cost when a rig is free: one container start,
no model load, under a minute.

**2. Accepted — 140 rows, five states, per (rig, model).**

| rig · model | accepted | refused | refused, reason lost | harness defect |
|---|---|---|---|---|
| srv1 · 1.5B | 41 | 2 | 12 | 3 |
| srv1 · 7B | 0 | 0 | 4 | 0 |
| srv2 · 1.5B | 51 | 2 | 10 | 3 |
| srv2 · 7B | 6 | 0 | 0 | 0 |
| srv2 · Qwen3-4B | 6 | 0 | 0 | 0 |

Two things this column says that the sweep's own README could not:

- **26 of the 36 refusals have no reason on record.** The harness kept 25
  log lines; vLLM's failure path prints a traceback longer than that under
  the wrapper `RuntimeError: Engine core initialization failed. See root
  cause above`, and the cause scrolled off. Those rows are
  `refused_reason_lost`, not `refused`. The sweep README attributed srv1's
  `--dtype bfloat16`, fp8 KV and `FLASH_ATTN`/`FLASHINFER` refusals to
  compute-capability gates; that attribution is reasoning, and this table
  does not carry it. The 7B on srv1 is the same: "CUDA OOM loading weights"
  was learned by a hand re-run that nobody recorded. `sweep.py` now keeps
  2,000 lines and the image digest on every refusal, so the next sweep
  cannot write this state.
- **The three stage-1 speculative cells per rig are `harness_defect`.** The
  engine's parse error quotes the value it received (`{method:`); the record
  holds the JSON the harness meant to send; they differ. That is the
  shell-split defect the sweep README describes, now a state the reader
  computes rather than a paragraph. The two `refused` rows per rig that
  remain are real and carry their reasons: `--ubatch-size 2` (microbatching
  needs a DeepEP all2all backend) and `method: suffix` (needs
  `arctic-inference`, not in the image).

**3. Effective — 148 single-flag contrasts, each at every shared n.** A
contrast is two launched cells on one (rig, model) whose flag dicts differ in
exactly one key; the parent's other flags are the regime and the ratio is
given at each concurrency level both ran. Reading the column:

- `--kv-cache-dtype fp8` on srv2 1.5B at `len 1024, seqs 256`, graphs on:
  **0.94 / 0.72 / 0.86 / 1.02 / 1.04 / 1.06** at n = 1 / 8 / 32 / 64 / 128 /
  256. A cost below n=64, the winner above. The same knob on srv2's eager
  seqs-16 baseline: 1.05 at n=16. One number per knob would have said
  "+5%" and been wrong in both directions.
- `--enforce-eager` on srv1: **0.90 at n=1**, 1.00 at n ≥ 4, in three
  different contexts. The sweep README's "0.1%" was the maximum-aggregate
  comparison; at a single stream the flag costs srv1 10%. On srv2 the same
  contrast reads 0.17–0.20 at every n of the seqs-16 regime, and 0.18 at
  n=1 rising to 0.74 at n=128 in the `len 1024, seqs 128` regime — the gap
  narrows as the batch grows, and the sweep's "5.02x" is the seqs-16 figure.
- `--linear-backend triton` on srv1: 0.49 at n=1, 0.76 at n=16; marlin is
  the resolved default and reads 1.00–1.02 against it.
- `--speculative-config ngram-3` on srv2 at seqs 16 with graphs: 0.62 at
  n=1, **1.19 at n=2, 1.13 at n=4**, 0.89 at n=16. Speculation wins a narrow
  band this sweep's headline ("loses at every concurrency") did not resolve,
  because the headline was read at the maximum.

## What this does not settle

- Column 1, and with it the untried count. Owed: one `knobs.py declared`
  run on either rig.
- The 26 lost reasons. Owed: the same cells re-run under the fixed
  `sweep.py`, ~2 min per cell on graphs-on launches, 12 cells on srv1 1.5B,
  10 on srv2, 4 for the 7B on srv1.
- ollama's surface. Its declared column is an environment surface plus
  llama.cpp's per-request options, not a `--help`; nothing here reads it.
- Prefill-heavy shapes, and any model but the four the sweep ran.
