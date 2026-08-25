# 2026-08-24 — the knob surface: declared, accepted, effective (#357)

Built by `tools/bench/serving/knobs.py build` from
`records/evidence/2026-08-24-config-sweep/` (140 cells, both rigs, four
models, one image) plus `reruns/` in this directory (26 cells, the same
image, the fixed harness). `surface.json` is the record; `surface.md` is the
same table rendered. Both are regenerated, never edited:
`tests/test_knobs.py::test_the_committed_surface_is_what_the_evidence_produces`
rebuilds them from the two evidence directories and refuses a difference.
Every row cites the file and the cell it came from.

Two sessions built this directory. The first (session 28) had no rig and
re-read the sweep; it found that 26 of the sweep's 36 refusals carried no
reason. The second (session 30) spent ~40 minutes of rig time on exactly two
things: the declared capture, and those 26 cells again.

## The three columns, and what each one holds

**1. Declared — captured on srv2.** `declared-vllm-ffb2d59b1c05.json` (raw
text beside it), image digest
`sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52`:
**275 flags, 250 with a printed default**, 31 with a choice set. The issue
said 274; the extra one is `--help` itself. The capture needs a device — on
a host with no GPU the same image exits 1 with `Failed to infer device type`,
because vLLM constructs a `VllmConfig` while printing help — so it is
`knobs.py declared <rig> <this dir>`, one container start, no model load,
under a minute. A moved image is a second file and a diff.

**The sweep tried 20 of 275 knobs. 255 are untried**, and `surface.json`
lists them by name. Untried is a state, not a refusal: nothing here says
what any of the 255 does on either rig.

**2. Accepted — 166 rows (140 sweep + 26 re-runs), five states, per (rig,
model).**

| rig · model | accepted | refused | refused, reason lost | harness defect | lost reasons outstanding |
|---|---|---|---|---|---|
| srv1 · 1.5B | 41 | 2 + 12 | 12 | 3 | 0 |
| srv1 · 7B | 0 | 0 + 4 | 4 | 0 | 0 |
| srv2 · 1.5B | 51 | 2 + 10 | 10 | 3 | 0 |
| srv2 · 7B | 6 | 0 | 0 | 0 | 0 |
| srv2 · Qwen3-4B | 6 | 0 | 0 | 0 | 0 |

"2 + 12" is two refusals whose reason the sweep kept, plus twelve re-runs
whose reason the fixed harness kept. The sweep's rows keep the state they
were recorded in and carry a `rerun` pointer; the re-run rows carry
`rerun_of`. **All 26 re-runs refused again** — no lost reason was a
transient — and every one now carries the engine's own sentence:

- **srv1's four capability gates are now record, not prose.** `--dtype
  bfloat16`: `Bfloat16 is only supported on GPUs with compute capability of
  at least 8.0. Your NVIDIA GeForce GTX 1660 SUPER GPU has compute capability
  7.5`. `--kv-cache-dtype fp8` / `fp8_e5m2` / `fp8_e4m3`: `FP8 KV cache is
  not supported by the Triton attention backend on NVIDIA GeForce GTX 1660
  SUPER (compute capability 7.5)`. `--attention-backend FLASH_ATTN` and
  `FLASHINFER`: `Selected backend ... is not valid for this configuration.
  Reason: ['compute capability not supported']`. The sweep README asserted
  all four; the table can now cite them.
- **The 7B on srv1 is `torch.OutOfMemoryError`** at every utilization tried
  (0.85 / 0.90 / 0.95, eager and not): `Tried to allocate 518.00 MiB. GPU 0
  has a total capacity of 5.61 GiB of which 151.88 MiB is free`. It is the
  weights, not the KV cache — the allocation fails before profiling.
- **Every `--max-num-seqs ≥ 320` refusal is `torch.OutOfMemoryError`** on
  both rigs, including srv1's seqs-512 and the fp8-KV cells on srv2 at
  320/384/448/512. srv2's plain seqs-512 too. So the ceiling the sweep found
  (srv2 fp8 at 256, plain at 448) is a memory ceiling, and the engine says
  how much it was short by.
- **`--linear-backend {exllama, machete, cutlass}`**: `Failed to find a
  kernel that can implement the WNA16 linear layer`, with the per-kernel
  reasons on the following lines (the surface keeps them); **`torch`**:
  `--linear-backend=torch was requested but no 'torch' kernel exists for
  mixed-precision layers`. Same on both rigs: these are AWQ-kernel facts,
  not card facts.

The other two facts this column states that the sweep's README could not:

- **The three stage-1 speculative cells per rig are `harness_defect`.** The
  engine's parse error quotes the value it received (`{method:`); the record
  holds the JSON the harness meant to send; they differ. That is the
  shell-split defect the sweep README describes, now a state the reader
  computes rather than a paragraph. The two `refused` rows per rig the sweep
  itself kept are real: `--ubatch-size 2` (microbatching needs a DeepEP
  all2all backend) and `method: suffix` (needs `arctic-inference`, not in
  the image).
- **`refused_reason_lost` is a state the next sweep cannot write.**
  `sweep.py` keeps 2,000 log lines (`LOG_LINES`) and the image digest on
  every refusal; the 25-line tail that produced 26 unattributable rows is
  gone.

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

- **The 255 untried knobs.** Column 1 names them; columns 2 and 3 have
  nothing on any of them. Trying them is a campaign, not a box, and #322's
  header is where a run says which of them it turns.
- The declared column was captured on srv2 only. Same image digest on both
  rigs (`image_digest` is on every re-run record), and `--help=all` is a
  property of the image, not the card — but that is one capture, not two.
- ollama's surface. Its declared column is an environment surface plus
  llama.cpp's per-request options, not a `--help`; nothing here reads it.
- Prefill-heavy shapes, and any model but the four the sweep ran.
- The re-runs were `levels [1]`, `cap 1`: they answer "why did it refuse",
  and had one launched they would have recorded one level, not a curve.
