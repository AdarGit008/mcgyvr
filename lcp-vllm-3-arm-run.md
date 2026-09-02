# lcp/vllm arm run — srv1 kernel attribution (planned, 2026-09-02)

**Intent.** srv1's GPU reports compute capability 7.5 but is a TU116 die with the
tensor cores removed, so every capability gate in both engines hands it kernels
its silicon emulates. A custom llama.cpp build measured 1.5–1.7x over stock. This
run decides **which variable earned that**, whether it survives correctness, and
whether a Vulkan build — whose backend detects tensor cores by querying
`VK_KHR_cooperative_matrix` rather than reading an integer — makes the whole
CUDA workaround unnecessary.

**This is a capability question, not a controlled comparison.** Only the
`L`-ladder is controlled: one variable per rung, inside one engine. The vLLM
arms are not on that ladder and never join it. vLLM and llama.cpp differ in
scheduler, batching, KV management and quantisation format, so a tok/s ratio
between them measures two stacks, not two kernels. What vLLM is asked here is
what it *can* do on TU116: which kernel it selects, whether a path that is not
`mma.sync` exists at all, and what it refuses.

**Decisions it enables.** *Which llama.cpp build srv1 should serve on* — from the
`L`-ladder, controlled. And, separately, *what vLLM is capable of on this card* —
a capability finding, whose honest answer may be "no viable non-tensor-core path
exists here". Neither answers the other, and no arm ranks the two engines.

**Status.** Run 2026-09-02. Behaviours 1-8 and 12 are green and their markers
are off; 9's distinctness check, 10 and 11 stay strict, dated `xfail`. Artifacts:
`records/evidence/2026-09-02-srv1-kernel-arms/`.

## Rig, as measured 2026-09-01

```
srv1  GTX 1660 SUPER 6144 MiB  cc 7.5  TU116, no tensor cores  driver 580.173.02
      i5-9600K 6c/6t  cpu_max 4600 MHz (read 4800 on 08-31, reset by a hard lock)
      16 GB DDR4-3600  40.3 GB/s pure-read, linear to 6 threads (core-limited)
      PL1 95 W / PL2 120 W held from the OS   non-ECC
```

## Arms

| arm | build | isolates |
|---|---|---|
| `L0` | `75-real;75-virtual`, FORCE_MMQ **off** | local-build baseline |
| `L1` | `75-real;75-virtual`, FORCE_MMQ **on** | `GGML_CUDA_FORCE_MMQ` alone |
| `L2` | `61-virtual;80-virtual`, FORCE_MMQ on | the arch spoof (= shipped v2) |
| `L3` | `L2` + the `mmvq` patch | the ship candidate (= v3) |
| `L4` | `L0` + `GGML_NATIVE=ON`, no `CPU_ALL_VARIANTS` | the CPU build flags alone |
| `A3` | `GGML_VULKAN=ON` | a non-CUDA path — a **bound**, never an attribution |
| `A1` | `ghcr.io/ggml-org/llama.cpp:server-cuda-b10644` | what "stock" means to a user |

Separately, and never on the same axis as the table above:

| arm | build | isolates |
|---|---|---|
| `B1` | vLLM v0.26.0, `--linear-backend marlin` | `MarlinLinearKernel`, tensor-core PTX on sm75 |
| `B2` | vLLM v0.26.0, `--linear-backend exllama` | `ExllamaLinearKernel`, `__hfma2`, no `mma.sync` |

`A1` vs `L2` moves six variables at once — arch list, `FORCE_MMQ`, `GGML_NATIVE`,
the CPU-variant dispatch, the toolkit, the base image. The ladder exists so
"the arch spoof is worth X" is a sentence the evidence can support.

## Guidelines

1. **Five replicates, interleaved, never blocked.** The prior A/B ran all of one
   arm then all of the other, confounding arm with elapsed time and card
   temperature.
2. **Two rows are comparable only if `ptok` and `otok` match.** The prompt draw
   comes from a per-process counter; changing the level list desyncs it, measured
   at **6.2%** — larger than most effects here. One cell per process invocation.
3. **`prefill=` from the sweep drivers is not a measurement.** `agg = gen/wall`
   and `prefill = pin/wall` over the same wall, so `prefill/agg ≡ ptok/otok`.
   Prefill verdicts come from `llama-bench -p N -r 9`.
4. **Microbenchmarks carry no workload digest.** File them apart; never mix them
   into a serving claim.
5. **No number crosses the engine boundary.** The `L`/`A` arms and the `B` arms
   are two studies sharing a rig and a workload. The shared workload makes rows
   *honest* — same prompts, same token counts — it does not make them
   *comparable*: vLLM pages its KV, batches continuously and reads GPTQ;
   llama.cpp does none of those and reads GGUF. `B1` vs `B2` is the only vLLM
   pair, and there is no `L`-vs-`B` row to write.
6. **Check the mechanism statically before spending rig time.** `cuobjdump` the
   built libraries. If `mma.sync` is still on the selected paths in `L2`/`L3`, no
   throughput number can be attributed to removing it.
7. **Stamp the rig on every row**, and re-read it at the end. A hard lock wipes
   the BIOS profile. Read `constraint_0_power_limit_uw`, never `..._max_power_uw`.
8. **A refusal is a result.** Retry three times before believing it — a launch
   near the memory edge is a 1-in-3 coin flip — and record the reason.
9. **Score correctness with what exists**: `tools/breadth/measure.py --endpoint
   ... --protocol openai --tier bench-py`, paired through `tools/bench/null.py`.
   Each arm is a new `serving_build`, so no committed bound in
   `tools/bench/reproducibility.json` covers it — every arm prices its own null
   first.

## Behaviours → RED tests

| # | behaviour / question | test |
|---|---|---|
| 1 | The parser reads real artifacts, and the prior A/B cannot tell its arms apart | `tests/test_a_row_parser_that_reads_nothing_proves_nothing.py` |
| 2 | One workload across every driver; microbenchmarks filed apart | `tests/test_one_workload_or_no_comparison.py` |
| 3 | Every row names its arm and its image; local tags resolve to a build stamp | `tests/test_a_row_that_does_not_name_its_arm_is_not_a_measurement.py` |
| 4 | Every row carries the live rig state; start equals end | `tests/test_a_row_without_the_rigs_live_state_is_not_comparable.py` |
| 5 | Prefill is timed by an instrument that measures prefill, `-r 9`, `-fa 0,1` | `tests/test_a_prefill_verdict_needs_an_instrument_that_measures_prefill.py` |
| 6 | Each ladder rung moves one variable; the binary confirms the mechanism | `tests/test_a_six_variable_diff_does_not_attribute_a_gain.py` |
| 7 | Five replicates, interleaved, matched draws, an A/A null | `tests/test_one_observation_is_not_an_effect.py` |
| 8 | The unpatched build re-crashes; the boundary is located; L3 survives 60 trials | `tests/test_a_crash_not_reproduced_is_not_a_crash_fixed.py` |
| 9 | Each arm derives its own `--n-cpu-moe` floor; a refusal establishes it | `tests/test_an_ncmoe_floor_is_derived_and_not_copied.py` |
| 10 | Placement is not output-neutral by fiat — Ling `ncmoe` 0 vs 99, `flips == 0` | `tests/test_placement_is_not_declared_output_neutral_without_a_measurement.py` |
| 11 | No arm wins on speed without passing the gate, against a bound it measured | `tests/test_a_faster_arm_that_answers_differently_has_not_won.py` |
| 12 | The vLLM arms hold the checkpoint fixed; the log names the kernel that ran | `tests/test_two_backends_on_one_checkpoint_is_the_only_pair.py` |

Shared parser and helpers: `tests/sweeprows.py`.

## Steps, in the order that loses least if srv1 locks

Nine steps, ten invocations: **step 1 runs the ladder script twice**, once either
side of step 3. The order below is not advisory — each script checks its own
preconditions before it does any work and exits non-zero if they are not met, so
running one out of turn costs nothing and writes nothing. `tools/runs/` holds
one script per step; `records/evidence/2026-09-02-srv1-kernel-arms/RUN-ORDER.md`
is the same list with the artifacts and the blockers against it.

```
0+1  static+   srv1-build-ladder.sh --stage build    cuobjdump runs INSIDE each
     build     L0 L1 L2 L3 L4 A3                     build; the gate can end the
                                                     campaign before step 2      #6
2    null      srv1-aa-null.sh        A/A on L3      prices the instrument       #7
3    bench     srv1-llama-bench.sh                   prefill verdict             #5
               -p 512,2048 -n 128 -r 9 -fa 0,1
               x {L0,L1,L2,L3,L4,A3,A1}
3'   ladder    srv1-build-ladder.sh                  RE-RUN. The ladder's BENCH
     pass 2    (default --stage all)                 rows ARE step 3's numbers,
                                                     copied not re-measured
                                                     (CONTRACT 6.4). Images are
                                                     reused, so it is cheap. The
                                                     default stage REFUSES to
                                                     start before step 3 has
                                                     written its file.           #6
4    serve     srv1-kernel-arms.sh --step serve      end-to-end at width      #3 #4 #7
               resident models only, levels 1,4,8,
               5 interleaved reps
5    correct   srv1-correctness.sh                   per arm, self-null first    #11
               breadth/measure.py -> bench/null.py
6    placement srv1-moe-slots.sh                     tests the fingerprint fiat  #10
               Ling ncmoe 0 vs 99. CREATES
               srv1-moe-slots.tsv (owner; step 7
               only appends to it)
7    crash     srv1-kernel-arms.sh --step crash      regression, 60 trials       #8
               L2 boundary n=1..12, then L3 x 60
               at each failing width. APPENDS to
               step 6's file and refuses to run
               before step 6 has written it
8    vllm      srv1-vllm-arms.sh                     capability, not a ranking;  #12
               B1 vs B2 on one GPTQ checkpoint       refusal is a result
9    floor     srv1-ncmoe-floor.sh                   VRAM-bound, not copied      #9
               per-arm ncmoe floor + refusal below
```

Two orderings are enforced in code rather than trusted to this page:

- **step 3 before the ladder's second pass.** `srv1-build-ladder.sh` with no
  `--stage` will not start unless `srv1-llama-bench.tsv` exists, and exits
  non-zero if any built rung ends with no `BENCH` row. `--stage build` is the
  only way to get the stamps without the rows, and it says on stdout what it
  still owes.
- **step 6 before step 7.** `srv1-moe-slots.sh` creates `srv1-moe-slots.tsv` and
  refuses to overwrite an existing one; `srv1-kernel-arms.sh --step crash`
  appends to it and refuses to start until that file carries step 6's
  `### INSTRUMENT step=6` marker.

## Blockers

- **B2's checkpoint must be fetched — but NOT because srv1 has no GPTQ.** An
  earlier correction in this file said "srv1 holds no GPTQ checkpoint of any
  shape", citing the 2026-08-31 inventory
  (`records/evidence/2026-08-31-inventory/srv1-scan.txt:96-109`). **That
  correction was wrong and this page's original premise was right.** Verified on
  srv1 on 2026-09-02: `~/.cache/huggingface/hub/models--Qwen--Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4`
  exists — 7.9 G, three shards, snapshot `81b132adfae5`, `config.json` declaring
  `Qwen2MoeForCausalLM` and `gptq / bits 4 / group_size 128 / desc_act false /
  sym true`. The 2026-08-31 scan simply does not list it. The conclusion is
  unchanged and the reason for it is not: that checkpoint is **MoE**, so
  `--linear-backend` would bind only its attention and dense projections while
  the expert GEMMs go through `--moe-backend` (`auto_gptq.py:467,489`), and the
  arm would not isolate a kernel; 7.9 G would not fit the 6144 MiB card either.
  A **dense** GPTQ 4-bit sym/g128/`desc_act=false` file must therefore still be
  fetched. Resolved candidate:
  `Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4` — 1.071 GiB of weights, `bits 4 /
  group_size 128 / desc_act false / sym true`, leaving ~4.1 GiB for KV on the
  6144 MiB card. Its quantisation parameters live in `config.json` under
  `quantization_config`; these repos ship **no** `quantize_config.json` (HTTP
  404), so the instruction to read that filename was wrong — read `config.json`.
  (`records/evidence/2026-09-02-srv1-kernel-arms/B2-CHECKPOINT.md`)
- **A checkpoint's name is not evidence of its format.** Two logged mismatches on
  the shared store: `~/models/moe/nemotron-30b-awq/` resolves as
  `quantization=compressed-tensors` in two srv1 logs
  (`records/evidence/2026-08-31-inventory/srv1-vllm-nemotronh-moe-loadtest.log:20`,
  `srv1-vllm-nemotronh-offload12-mml1024.log:21`), and both
  `~/models/dense/nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_{M,S}.gguf` are
  qwen2-arch per `records/evidence/2026-08-27-spec-decoding/store/README.md`.
  `checkpoint_quant` carries what was read from `quantization_config`, not what a
  path implies.
- **`--linear-backend exllama` is verified to exist in v0.26.0.** The flag is
  captured in-repo at
  `records/evidence/2026-08-24-knob-surface/declared-vllm-ffb2d59b1c05.json`
  flag 255, read out of the pinned image digest, with `exllama` among its
  choices. The August refusal was `ExllamaLinearKernel` rejecting `uint4` — the
  AWQ scalar type — not the flag failing to parse; GPTQ 4-bit sym is `uint4b8`,
  which it accepts. The proposed fallback is **invalid**: in v0.26.0 `gptq` and
  `gptq_marlin` both map to `AutoGPTQConfig`, so `--quantization gptq` vs
  `gptq_marlin` moves nothing and would print two flags while running one kernel.
  The pair is `--linear-backend marlin` (B1) vs `--linear-backend exllama` (B2)
  on one checkpoint, and `kernel_observed` comes from
  `Using {Marlin,Exllama}LinearKernel for AutoGPTQLinearMethod` in the engine log.
- **Unexecuted:** `AutoGPTQLinearMethod.__init__` calls
  `verify_marlin_supported()` unconditionally, before the kernel chooser runs.
  Source says it passes for `uint4b8`/`g128` on sm75; that path has not been run.
  If B2 dies with a Marlin message rather than an Exllama one, this is the cause
  — a REFUSED row with the reason, not a setup error.
- **RESOLVED: `server-cuda-b10644` contains no `llama-bench` FILE, and A1 is
  benchable anyway.** Checked on srv1 on 2026-09-02: `/app/llama-bench` is not in
  the image. The capability is: it ships `libllama-bench-impl.so` and a single
  `/app/llama` dispatcher whose `llama help all` lists
  `bench   Benchmark prompt processing and text generation`, and
  `/app/llama bench --help` prints llama-bench's own options (`-m -p -n -r -o`).
  `tools/runs/srv1-llama-bench.sh` now probes `/app/llama-bench` first and
  `/app/llama bench` second, per image, and refuses only when both are absent —
  verified to resolve `A1 -> /app/llama bench` and `L0 -> /app/llama-bench`
  against the real images. **So A1 is microbenchmarked as shipped, and `L0` is
  NOT the mandatory baseline.** A1 is on step 3's arm list for that reason.
- **The recorded 1.5–1.7x is `L2`'s, not `L3`'s.** The patch changes MoE kernel
  selection. Re-measure or stop quoting it.

## Not worth rig time

Any llama.cpp-vs-vLLM ratio, at any width, on any model · `prefill=` as an
independent quantity · ncmoe cells for the *kernel* question
(the bottleneck moves to host RAM and srv1 hard-locks under that load) · the full
n=1..32 ladder (srv1 already refuses d7b at np≥16) · `A3` across the whole grid
(one model, `llama-bench`, as a bound) · re-deriving the fp8 KV 2.000x ratio or
the co-residency ceiling · `--kv-cache-dtype fp8` on cc 7.5 (refuses) ·
quantised KV (measured once: freed 36 MiB, cost 1.6 tok/s) · `--no-mmap` as an
A/B in this campaign (fix it, stamp it — it is a ±63% lever and would swamp
everything).
