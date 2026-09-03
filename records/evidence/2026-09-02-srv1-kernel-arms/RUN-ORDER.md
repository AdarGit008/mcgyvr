# RUN-ORDER — the eight scripts of the srv1 kernel-arms campaign, as run

Ten invocations of eight scripts, all sourcing `tools/runs/_common.sh`, run on
srv1 on 2026-09-02. Steps: `tools/runs/campaigns/srv1-kernel-arms/PLAN.md`;
artifact shapes and the behaviour numbers: `ARTIFACT-CONTRACT.md`. A record, not
a plan. The scripts ran as `tools/runs/srv1-<name>.sh`; later on 2026-09-02 they
moved to `tools/runs/campaigns/srv1-kernel-arms/<n>-<name>.sh` (the campaign's
own step numbers) and are started through `tools/runs/run.sh`, which is how the
table names them below.

**Two orderings are enforced in code, not trusted to this page**, checked before
any rig work so an out-of-order invocation exits non-zero having written nothing:
`1-build-ladder.sh` without `--stage` will not start unless
`srv1-llama-bench.tsv` exists, nor finish if a built rung has no `BENCH` row; and
`6-moe-slots.sh` owner-creates `srv1-moe-slots.tsv` while `7-crash.sh` (which
execs `4-kernel-arms.sh --step crash`) only appends, once it carries
`### INSTRUMENT step=6`.

| # | step | invocation | produces | turns green |
|---|---|---|---|---|
| 1 | 0+1 static+build | `1-build-ladder.sh --stage build` | `srv1-build-ladder.tsv` — `WORKLOAD/START/RIG/BUILD/KERNELS/END`, no `BENCH` rows | part of #6 |
| 2 | 2 null | `2-aa-null.sh` | `srv1-aa-null.tsv` | part of #7 |
| 3 | 3 bench | `3-llama-bench.sh` | `srv1-llama-bench.tsv` | #5; half of #2 |
| 4 | 3′ ladder pass 2 | `1-build-ladder.sh` (through the door: `--suffix pass2` on the same day) | rewrites `srv1-build-ladder.tsv` **with** the `BENCH` rows, copied from #3; the door keeps pass 1 beside it as `srv1-build-ladder.superseded-<run_id>.tsv` | #6; other half of #2 |
| 5 | 4 serve | `4-kernel-arms.sh --step serve` | `srv1-lcpp-arms.tsv` | #3, #4, rest of #7, #2 here |
| 6 | 5 correct | `5-correctness.sh` | `correctness.json` | #11 |
| 7 | 6 placement | `6-moe-slots.sh` | **creates** `srv1-moe-slots.tsv`; `placement-null.json` | #10 |
| 8 | 7 crash | `7-crash.sh` (execs `4-kernel-arms.sh --step crash`) | **appends** to `srv1-moe-slots.tsv` | #8 |
| 9 | 8 vllm | `8-vllm-arms.sh` | `srv1-vllm-arms.tsv` | #12 |
| 10 | 9 floor | `9-ncmoe-floor.sh` | `srv1-ncmoe-floor.tsv` | #9 |

Behaviour #1 was green off the 2026-09-01 A/B. Steps 5–10 need only step 1's
images (the ladder also needs step 3); the order above loses least if srv1 locks.

## What the run found

- **1 · static+build.** Seven images built; `cuobjdump` separates the ladder
  before any timing — `L0`/`L1`/`L4` and A3 carry sm_75 SASS, `L2`/`L3` are
  `tensor_core_instructions=absent`, PTX-JIT off sm_61.
- **2 · null.** `### NULL spread_pct=15.3103` on an L3 A/A — the instrument's own
  noise, and the bar any ladder gap has to clear.
- **3 · bench.** At `-p512 -fa1`: `L2` 1275.2 and `L3` 1274.0 tok/s prefill
  against `L0`/`L1`/`L4` 355.0 and `A1` 357.7 — **3.6x**, the arch spoof alone.
  Generation moves the other way, 95.2 against 101.1. `A3` read 90.5/19.7 and it
  is **not Vulkan**: `libggml-vulkan.so` was dlopened and silently skipped
  (`undefined symbol: ggml_backend_score`), so only the CPU backend registered —
  A3 is llama.cpp on the six-core i5-9600K. Both TSVs with an A3 number stamp
  `### CORRECTION arm=A3`, over `refusals/A3-vulkan-never-loaded.txt`.
- **4 · ladder pass 2.** Six `BENCH` rows copied, not re-measured, each stamped
  `projected_from=srv1-llama-bench.tsv:<line>`; one variable per rung holds.
- **5 · serve.** Mean aggregate, five interleaved reps, d3b: `L2`/`L3`
  68.3/~118/~131 at n=1/4/8 against ~43/~69/~75 for `L0`, `L1`, `L4`, `A1` —
  **1.6-1.8x**. `A1` is indistinguishable from `L0`, and `L3` adds nothing over
  `L2` here, so its patch is not a throughput lever.
- **6 · correct and 7 · placement.** **Neither ran.** `tools/breadth/measure.py`
  refused all three attempts on L0's own null, and again at placement cell A
  (`ncmoe=0`): the product has moved off round `r1-commissioning` (ADR-0018, one
  revision per round). No `correctness.json`, no `placement-null.json`, no
  `flips` count — #10 and #11 stay xfail. Step 6 did write its `CONFIG` rows and
  `### INSTRUMENT step=6`, which is all step 7 needs.
  `refusals/step5-correctness.log`, `refusals/step6-moe-slots.log`.
- **8 · crash.** `### BOUNDARY arm=L2 first_failing_n=2` — the unpatched build
  re-crashes at the second concurrent request, 20 `CRASH` rows, all
  `ggml_cuda_mul_mat_vec_q` / `CUDA error: invalid argument`. `L3` ran 60 trials
  at every failing width without crashing.
- **9 · vllm.** One checkpoint (`Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4`, one
  `weights_sha256`), one 65536-token KV pool; `kernel_observed` came back
  `MarlinLinearKernel` for `B1` and `ExllamaLinearKernel` for `B2`, so the
  non-`mma.sync` path exists and runs. B2−B1 changes sign across widths (+6.1,
  −0.6, −2.3 at n=1/4/8): `### VERDICT status=unresolved`, the honest reading.
- **10 · floor.** Predicted 28.0, measured **27** for every arm, established by a
  `REFUSED` at 26 retried three times — but it is the same 27 three times, and
  `L3`, `A1` and `L0` reached it from byte-identical inputs. #9's distinctness
  check stays a strict `xfail`: nothing here separates an honest coincidence
  (one checkpoint, one card, one context size) from a copied floor.

## The re-run, 2026-09-02 22:00 – 2026-09-03 07:13 UTC, under round r2-02-09-2026

Every invocation through `tools/runs/run.sh`, from the checkout on srv1. Steps
6 and 7 landed in this envelope; the door dates its envelope, and everything
after midnight UTC is in `records/evidence/2026-09-03-srv1-kernel-arms/`
(`tools/runs/rows.py:ENVELOPE` says which file lives where).

| # | step | run id (suffix) | result |
|---|---|---|---|
| 1 | 6 placement | `moe-slots` | **`flips=9` of 257** between `ncmoe=0` and `ncmoe=99` on L3 / Ling-3.0-tiny, own null 0 flips, bound 1.47pp: **placement is not output-neutral** at this bound. Behaviour 10 now fails on a measurement, not on a missing file. The pre-door file is kept as `srv1-moe-slots.pre-door-2026-09-02.tsv` |
| 2 | 7 crash | `crash` | reproduced: `### BOUNDARY arm=L2 first_failing_n=2`, 20 `CRASH` rows, L3 clean |
| 3 | 1 ladder pass 1 | `build-ladder-a3fix` | A3 rebuilt with `libX11 libXext libGLdispatch` |
| 4 | 3 bench | `llama-bench-a3fix` | **A3 `REFUSED`**: declared vulkan, measured CPU (the verdict working). Kept as `srv1-llama-bench.a3fix-refused.tsv` |
| 5 | 1 ladder pass 2 | `build-ladder-a3fix-pass2` | exit 1, correctly: no BENCH row for A3 |
| 6 | 1 ladder pass 1 | `build-ladder-egl` | A3 rebuilt with `libEGL` too (`icd_deps=x11-egl`) |
| 7 | 3 bench | `llama-bench-egl` | **A3 `REFUSED` again**, on srv1 only: the same image lists Vulkan0 on srv2. Kept as `srv1-llama-bench.egl-refused.tsv` |
| 8 | 1 ladder pass 2 | `build-ladder-egl-pass2` | exit 1, correctly |
| 9 | 3 bench | `llama-bench-cdi` | A3 requested through CDI (`--device nvidia.com/gpu=all`): **`backend=Vulkan`, 677 tok/s prefill at p512 fa1**, 89 gen — 1.9x the native sm_75 CUDA build (355), half the arch spoof (1275). The filed `srv1-llama-bench.tsv` |
| 10 | 1 ladder pass 2 | `build-ladder-cdi-pass2` | green; the filed `srv1-build-ladder.tsv`, every rung priced, A3 on Vulkan |
| 11 | 5 correct | `correctness-b` | L0 reference, L2 and L3 each **1 flip / 257 = 0.39pp** drift, inside every arm's own 1.47pp bound (0 self-null flips each); winner L3 has not answered differently. Behaviour 11 green |

Three layers stood between A3 and the card, each found inside the container
and each refused rather than filed: the ICD's linked libraries (`libXext`),
the library it dlopens at init (`libEGL`), and the ICD manifest, which docker
29.1.3 on srv1 does not mount for `--gpus all` (29.7.1 on srv2 does). The
full trace: `refusals/A3-vulkan-never-loaded.txt`.

## Cross-script contracts

`1-build-ladder.sh` is the sole producer of `llamacpp:b10644-*`;
`4-kernel-arms.sh` reads `org.mcgyvr.build.<key>` off them to write
`### BUILD`, failing loudly on a missing key, and falls back to `docker image
inspect {{.Id}}` for `image_sha256` — the one key an image cannot label on
itself. `checkpoint_quant` is demanded on every refusal, `none` or `unread`
(`_common.sh`). `otok_req` is emitted only where a test reads it. CONTRACT §3,
§6.3, §7.

## The three blockers — all closed

1. **L3 built.** `mmvq.patch` and `patch_mmvq.py` sit beside this file;
   `MMVQ-PATCH.md` records how they were recovered and that the patch applies
   cleanly to b10644. `RUN_MMVQ_PATCH` preflights green, `L3` carries
   `patched=yes`, and it is the only rung that survives step 7.
2. **The GPTQ question is settled and B2 ran.**
   `Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4` was fetched and verified — 4-bit,
   `group_size 128`, `desc_act false`, `sym true`, read from `config.json`, not
   the `quantize_config.json` these repos do not ship. srv1 also holds a GPTQ the
   2026-08-31 scan missed (`Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4`), **unusable
   here**: MoE, so `--linear-backend` binds only its dense projections, and 7.9 G
   exceeds 6144 MiB. `B2-CHECKPOINT.md`.
3. **A1 is benchable as shipped.** `server-cuda-b10644` ships no
   `/app/llama-bench` file, but it has `libllama-bench-impl.so` and a
   `/app/llama` dispatcher whose `bench` subcommand takes `-m -p -n -r -o`.
   `3-llama-bench.sh` probes both, per image, so A1 is on step 3's arm list
   and `L0` is **not** the mandatory baseline.
