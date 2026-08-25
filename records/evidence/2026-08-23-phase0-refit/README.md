# Phase 0 refit — the three cells the declaration could not fit

Run 2026-08-23 at `0a990d6a`, tree clean, both rigs idle at 1 MiB before and
after. **#354.** Three vLLM cells, three `ok`, so the phase-0 footprint table is
**25 of 25** rather than 22.

## What these cells are, and what they are not

Phase 0 (`../2026-08-23-phase0-footprint/`) ran 25 cells and lost three to
`torch.OutOfMemoryError` inside `_allocate_kv_cache`, on an **empty** card, with
a declaration that was arithmetically correct in every case. This campaign
re-declares those three so they fit and measures them.

**The declaration changed, so these rows are not phase 0's re-measurement.** The
owner chose, 2026-08-23, between the two ways out the refusal names: hold
`max_num_seqs` at the campaign's 8 and shorten `max_model_len`, rather than hold
8,192 and narrow the width. Both reach the same KV bytes; they differ in what
the server can then serve. Phase 0's three refused rows stand as measured, and
neither table is the other's correction.

## Measured

| host | model | declaration | card MiB | process MiB | residue |
|---|---|---|---|---|---|
| srv1 | `thewimo/Qwen3-4B-AWQ` | seqs 8 × len 2,048 | 5,222 | 5,218 | 358 |
| srv2 | `thewimo/Qwen3-4B-AWQ` | seqs 8 × len 7,168 | 11,101 | 11,092 | 477 |
| srv2 | `Qwen/Qwen2.5-Coder-14B-Instruct-AWQ` | seqs 8 × len 1,024 | 11,479 | 11,470 | 337 |

`residue` = `card_mib_after_load − weights − declared_kv`: what the process holds
besides the two things it was told to hold. Card total and per-process figure
stay two columns (4–9 MiB apart, held by nobody) as ADR-0040 requires, and the
`fraction` column is empty with the engine's refusal beside it, because this
engine takes its whole allocation or does not start.

## What the residue settled

It is **337–477 MiB and does not track model size** — the 14B, with 9.38 GiB of
weights, holds the least of the three. It tracks the KV cache, which is what the
block padding sits on.

That refuted the constant this lane shipped one commit earlier.
`NON_KV_OVERHEAD_MIB` was 910, assembled from ADR-0039's terms, and the sum
double-counted: `nvidia-smi`'s card figure already contains the driver reserve
and the CUDA context. It over-stated all three footprints by 433–573 MiB. The
constant is now **733 = 477 + 256**, the largest residue plus one allocator
block, both readings. See ADR-0039's correction block of the same date.

The window every measured cell allows narrowed from **511–1,793** MiB (phase 0's
seven cells) to **511–1,145** (all ten). No verdict changed at either value.

## The cell that was run at a margin on purpose

srv2's 14B was declared with 235 MiB of predicted slack — under one allocator
block — rather than backed off to a safer `max_model_len`. If it had refused,
the engine's own words would have said whether the constant needs a term that
grows with the model. It loaded, with 808 MiB of real slack, and the answer is
that the prediction was too conservative rather than too tight.

## Provenance

- `config.json` — the three entries, each verified against
  `vllm.declaration_fits` before any rig time was spent
- `cells.jsonl` — the survey journal, one row per cell
- `survey.json` — the full survey
- `footprints.csv` — produced by `../2026-08-23-phase0-footprint/footprints.py`,
  unmodified, so both campaigns' tables are the same parse
- `driver.log` — the E14 driver, including the final releases
