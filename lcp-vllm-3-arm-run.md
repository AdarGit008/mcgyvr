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

**Status.** Not run. Every behaviour below is a strict, dated `xfail`; the run
that closes one takes its marker off. Artifacts land in
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
| `B1` | vLLM v0.26.0, default (Marlin) | tensor-core PTX on sm75 |
| `B2` | vLLM v0.26.0, `--linear-backend exllama` | `__hfma2`, no `mma.sync` |

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

```
0  static     cuobjdump L0..L3                      free, can end the campaign early
1  build      L0 L1 L2 L3 L4 A3                     srv2 builds, direct-push to srv1
2  null       A/A on L3                             prices the instrument           #7
3  bench      llama-bench -p 512,2048 -n 128 -r 9   prefill verdict                 #5 #6
              -fa 0,1  x {L0,L1,L2,L3,L4,A3}
4  serve      sweep driver, resident models only,   end-to-end at width             #3 #4 #7
              levels 1,4,8, 5 interleaved reps
5  correct    breadth/measure.py -> bench/null.py   per arm, self-null first        #11
6  placement  Ling ncmoe 0 vs 99 through the same   tests the fingerprint fiat      #10
7  crash      L2 boundary sweep n=1..12, then       regression, 60 trials           #8
              L3 x 60 at each failing width
8  vllm       B1 vs B2 on one GPTQ checkpoint       capability, not a ranking;      #12
                                                    refusal is a result
9  floor      per-arm ncmoe floor + refusal below   VRAM-bound, not copied          #9
```

## Blockers

- **B2 has no valid checkpoint.** srv1's only GPTQ is `Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4`,
  a MoE; exllama has no fused-MoE path. A dense GPTQ 4-bit sym/g128/`desc_act=false`
  file must be fetched and its `quantize_config.json` read — two checkpoints on
  disk are already mislabelled.
- **`--linear-backend exllama` is unverified against `vllm/vllm-openai:v0.26.0`,**
  and srv1 has already recorded it refusing on an AWQ checkpoint. If the flag is
  absent, the contrast becomes `--quantization gptq` vs `gptq_marlin`, which is
  better anyway: same checkpoint, one variable.
- **`server-cuda-b10644` may not contain `llama-bench`.** If not, `A1` cannot be
  microbenchmarked as shipped and `L0` is the mandatory baseline.
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
