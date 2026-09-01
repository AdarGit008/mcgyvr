# RUN-ORDER — the eight scripts of the srv1 kernel-arms campaign

Ten invocations of eight scripts in `tools/runs/`, all sourcing `_common.sh`.
Campaign steps: `lcp-vllm-3-arm-run.md`. Artifact shapes: `ARTIFACT-CONTRACT.md`.
Behaviour numbers are that doc's "Behaviours → RED tests" table.

**Two orderings are enforced in code, not trusted to this page.** Each check runs
before any rig work, so an out-of-order invocation exits non-zero having written
nothing:

- **step 3 before the ladder's second pass.** `srv1-build-ladder.sh` with no
  `--stage` refuses to start unless `srv1-llama-bench.tsv` exists, and exits
  non-zero if any built rung ends with no `BENCH` row. `--stage build` is the one
  way to get the stamps without the rows.
- **step 6 before step 7.** `srv1-moe-slots.sh` is the **owner-creator** of
  `srv1-moe-slots.tsv` and refuses to overwrite an existing one (`--force` to
  replace). `srv1-kernel-arms.sh --step crash` is the **appender** and refuses to
  start until that file carries `### INSTRUMENT step=6`.

| # | step | invocation | produces | turns green |
|---|---|---|---|---|
| 1 | 0+1 static+build | `srv1-build-ladder.sh --stage build` | `srv1-build-ladder.tsv` — `WORKLOAD/START/RIG/BUILD/KERNELS/END`, no `BENCH` rows | part of #6 (one variable per rung, cuobjdump gate) |
| 2 | 2 null | `srv1-aa-null.sh` | `srv1-aa-null.tsv` | part of #7 (the A/A null) |
| 3 | 3 bench | `srv1-llama-bench.sh` | `srv1-llama-bench.tsv` | #5; half of #2 |
| 4 | 3′ ladder pass 2 | `srv1-build-ladder.sh` | rewrites `srv1-build-ladder.tsv` **with** the `BENCH` rows, copied from #3 | #6; other half of #2 |
| 5 | 4 serve | `srv1-kernel-arms.sh --step serve` | `srv1-lcpp-arms.tsv` | #3, #4, rest of #7, #2 for this file |
| 6 | 5 correct | `srv1-correctness.sh` | `correctness.json` | #11 |
| 7 | 6 placement | `srv1-moe-slots.sh` | **creates** `srv1-moe-slots.tsv`; `placement-null.json` | #10 |
| 8 | 7 crash | `srv1-kernel-arms.sh --step crash` | **appends** to `srv1-moe-slots.tsv` | #8 |
| 9 | 8 vllm | `srv1-vllm-arms.sh` | `srv1-vllm-arms.tsv` | #12 |
| 10 | 9 floor | `srv1-ncmoe-floor.sh` | `srv1-ncmoe-floor.tsv` | #9 |

Behaviour #1 is already green: it reads the 2026-09-01 A/B and needs nothing new.

Steps 5–10 are independent of each other and of their own order. They depend only
on step 1 (the images) and, for the ladder, on step 3. The list above is the order
that loses least if srv1 hard-locks.

## Cross-script contracts

- **image labels.** `srv1-build-ladder.sh` is the sole producer of
  `llamacpp:b10644-*`. `srv1-kernel-arms.sh` reads `org.mcgyvr.build.<key>` off
  those images to write `### BUILD`, and fails loudly on a missing key. The
  ladder sets all of them: the five build variables by `LABEL` in the
  Dockerfiles, and `commit` in a metadata-only relabel afterwards, read out of
  the image's own `/app/commit.txt`. `image_sha256` is the one key with no label
  — an image id cannot be a label on the image it names — and the consumer's
  documented fallback is `docker image inspect {{.Id}}`.
- **`checkpoint_quant` sentinels.** `refused()` demands the field on every
  refusal, including build and missing-binary refusals that never load a
  checkpoint. Two words, campaign-wide, enforced in `_common.sh`: `none` (no
  checkpoint was involved) and `unread` (one was, and its declared quantisation
  was never read). Which kind of unread goes in the reason. See CONTRACT §6.3.
- **`otok_req`** is emitted only where a test reads it: `srv1-lcpp-arms.tsv`
  (and, from the same emitter, `srv1-aa-null.tsv`). `srv1-vllm-arms.sh` omits it
  — the vLLM driver never lets the budget out of `post()`. CONTRACT §3, §7.

## Blockers — three, none of them fixable off the rig

1. **L3 cannot be built: the `mmvq` patch is not in this repo.**
   `srv1-build-ladder.sh` preflights `RUN_MMVQ_PATCH` (default
   `records/evidence/2026-09-02-srv1-kernel-arms/mmvq.patch`, absent) and stops
   before building anything, because "the ship candidate, minus its patch" is L2
   wearing L3's label. Blocks #6 and #8, and L3 rows in #7 and #11.
2. **B2 needs a GPTQ checkpoint fetched.** srv1 holds none of any shape
   (`records/evidence/2026-08-31-inventory/srv1-scan.txt:51-122`). Candidate:
   `Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4`, quantisation read from
   `config.json` and not `quantize_config.json` (see `B2-CHECKPOINT.md`).
   Until then `srv1-vllm-arms.sh` writes both arms as `REFUSED` with
   `checkpoint_quant=unread` and a `VERDICT status=unresolved`, which is a
   result, and #12 stays red.
3. **`server-cuda-b10644` may ship no `llama-bench`.** `srv1-llama-bench.sh`
   tests for `/app/llama-bench` before loading a model and files a `REFUSED` row
   with `checkpoint_quant=none` if it is absent. If so, A1 cannot be
   microbenchmarked as shipped and L0 is the mandatory baseline for #5.
