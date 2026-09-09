# The `mmvq` patch — FOUND

Status: **retrieved**, and verified to apply cleanly to b10644 (`d7a207411`).
It blocks L3 (`RUN_MMVQ_PATCH`, `tools/runs/srv1-build-ladder.sh:56,132,245-259`)
and blocker 1 of `RUN-ORDER.md:60-64`.

The patch was never a `.patch` file and was never committed to this repo. It
exists as a **Python rewriter script**, `patch_mmvq.py`, in the scratchpad of the
session that built the v3 image:

```
/tmp/claude-1000/-home-adaramir-claude-mcgyvr/66a5afe5-2eda-4019-9649-fa6e55340d76/scratchpad/patch_mmvq.py
```

alongside `Dockerfile.v3` in the same directory, which is the build recipe that
produced `llamacpp:b10644-nomma-dp4a-v3` — the image still present on srv1
(`docker images`, srv1, verified 2026-09-02). `lcp-vllm-3-arm-run.md:44` maps
`L3` = "the ship candidate (= v3)", so this is L3's one variable.

**This is scratch storage under `/tmp` and is not durable. Copy it out.**

## Provenance — that this is the patch, not a patch

1. `Dockerfile.v3` and `Dockerfile.v2` in that scratchpad differ by **exactly two
   lines** (`diff Dockerfile.v2 Dockerfile.v3`):
   ```
   > COPY patch_mmvq.py /tmp/patch_mmvq.py
   > RUN python3 /tmp/patch_mmvq.py
   ```
   plus `python3-minimal` in the apt line. Same commit `d7a207411`, same
   `-DCMAKE_CUDA_ARCHITECTURES="61-virtual;80-virtual"`, same
   `-DGGML_CUDA_FORCE_MMQ=ON`. That is the L2→L3 single-variable step the ladder
   asserts (`srv1-build-ladder.sh:207`, `test_a_six_variable_diff_...:73-79`).
2. The campaign transcript describes A2 as
   `llamacpp:b10644-nomma-dp4a-v3` — "a one-line patch making
   `get_mmvq_mmid_max_batch` use `ggml_cuda_highest_compiled_arch(cc)`"
   (session `66a5afe5`, `subagents/agent-abf239dc2ddf6ddfd.jsonl`).
3. The script's own comment reproduces behaviour 8's docstring almost verbatim,
   including the "`get_device_table_id` … already does the right thing; this
   function was simply missed" line.

## What it touches

One file, one function: `ggml/src/ggml-cuda/mmvq.cu`,
`int get_mmvq_mmid_max_batch(ggml_type type, int cc)` (line 256 at b10644).

It introduces `const int cc_c = ggml_cuda_highest_compiled_arch(cc);` and
switches the two NVIDIA branch conditions from raw `cc` to `cc_c`. The AMD
branches are untouched. Nothing else in the file, and no other file, changes.

### What it changes about MoE kernel selection

`get_mmvq_mmid_max_batch` is the host-side gate on
`ggml_cuda_mul_mat_vec_q` for `MUL_MAT_ID` (the MoE expert GEMV). Unpatched, on
srv1's TU116 the host sees `cc == 750` and returns the **Turing** per-quant batch
limits (`get_mmvq_mmid_max_batch_turing_plus`). But the arch list is
`61-virtual;80-virtual`, so `__CUDA_ARCH__` is 610 and the device kernel
`mul_mat_vec_q_moe` was compiled with `__launch_bounds__` from
`get_mmvq_mmid_max_batch_for_device<type>()` — the **Pascal** table. Host and
device disagree about the maximum batch.

Patched, the host reads `ggml_cuda_highest_compiled_arch(750)` → 610, takes the
Pascal branch, and hands out batches the compiled kernel can actually launch.
Batches above the Pascal limit fall through to MMQ instead of MMVQ. So the patch
does not add a kernel; it **moves the MMVQ→MMQ crossover for MoE down** to where
the compiled binary can honour it.

Because it changes which kernel runs for MoE at 5–8 concurrent slots, the
recorded **1.5–1.7x is L2's number and cannot be carried to L3**
(`lcp-vllm-3-arm-run.md:209`).

## The retrieved patch, verbatim

`patch_mmvq.py` as found (asserts its anchor matches exactly once, then rewrites):

```python
import sys
p = "/src/ggml/src/ggml-cuda/mmvq.cu"
s = open(p).read()
old = """    if (GGML_CUDA_CC_IS_NVIDIA(cc)) {
        if (cc == GGML_CUDA_CC_VOLTA || cc >= GGML_CUDA_CC_ADA_LOVELACE) {
            return MMVQ_MAX_BATCH_SIZE;
        }
        if (cc >= GGML_CUDA_CC_TURING) {
            return get_mmvq_mmid_max_batch_turing_plus(type);
        }
        return get_mmvq_mmid_max_batch_pascal_older(type);
    }"""
new = """    if (GGML_CUDA_CC_IS_NVIDIA(cc)) {
        // PATCH: select on the highest COMPILED arch, not the raw runtime cc.
        // The device kernel's __launch_bounds__ are baked from __CUDA_ARCH__, so a build
        // without Turing SASS/PTX gets the Pascal table on the device while this host
        // function handed out Turing limits. The mismatch is a hard
        // "CUDA error: invalid argument" in ggml_cuda_mul_mat_vec_q at 5-8 concurrent
        // MoE decode slots. get_device_table_id(cc) at line ~108 of THIS FILE already
        // does the right thing; this function was simply missed.
        const int cc_c = ggml_cuda_highest_compiled_arch(cc);
        if (cc_c == GGML_CUDA_CC_VOLTA || cc_c >= GGML_CUDA_CC_ADA_LOVELACE) {
            return MMVQ_MAX_BATCH_SIZE;
        }
        if (cc_c >= GGML_CUDA_CC_TURING) {
            return get_mmvq_mmid_max_batch_turing_plus(type);
        }
        return get_mmvq_mmid_max_batch_pascal_older(type);
    }"""
assert s.count(old) == 1, f"patch anchor matched {s.count(old)} times - ABORT"
open(p, "w").write(s.replace(old, new, 1))
print("mmvq.cu patched OK")
```

## As a `git apply` patch

The ladder wants a diff (`srv1-build-ladder.sh:326`,
`git apply --verbose /patch/mmvq.patch`), not a script. The diff below was
**derived mechanically** by running the retrieved script against b10644's
`mmvq.cu` and taking `git diff` — the anchor matched exactly once, so this is the
same edit, not a re-authoring. Content: retrieved. Diff framing: derived.

```diff
diff --git a/ggml/src/ggml-cuda/mmvq.cu b/ggml/src/ggml-cuda/mmvq.cu
index 9705348..70a7233 100644
--- a/ggml/src/ggml-cuda/mmvq.cu
+++ b/ggml/src/ggml-cuda/mmvq.cu
@@ -256,10 +256,18 @@ static constexpr __host__ __device__ int get_mmvq_mmid_max_batch_rdna4(ggml_type
 int get_mmvq_mmid_max_batch(ggml_type type, int cc) {
     // NVIDIA: Volta, Ada Lovelace, and Blackwell always use MMVQ for MUL_MAT_ID.
     if (GGML_CUDA_CC_IS_NVIDIA(cc)) {
-        if (cc == GGML_CUDA_CC_VOLTA || cc >= GGML_CUDA_CC_ADA_LOVELACE) {
+        // PATCH: select on the highest COMPILED arch, not the raw runtime cc.
+        // The device kernel's __launch_bounds__ are baked from __CUDA_ARCH__, so a build
+        // without Turing SASS/PTX gets the Pascal table on the device while this host
+        // function handed out Turing limits. The mismatch is a hard
+        // "CUDA error: invalid argument" in ggml_cuda_mul_mat_vec_q at 5-8 concurrent
+        // MoE decode slots. get_device_table_id(cc) at line ~108 of THIS FILE already
+        // does the right thing; this function was simply missed.
+        const int cc_c = ggml_cuda_highest_compiled_arch(cc);
+        if (cc_c == GGML_CUDA_CC_VOLTA || cc_c >= GGML_CUDA_CC_ADA_LOVELACE) {
             return MMVQ_MAX_BATCH_SIZE;
         }
-        if (cc >= GGML_CUDA_CC_TURING) {
+        if (cc_c >= GGML_CUDA_CC_TURING) {
             return get_mmvq_mmid_max_batch_turing_plus(type);
         }
         return get_mmvq_mmid_max_batch_pascal_older(type);
```

### Exact command to reproduce the diff

```sh
SRC=/tmp/claude-1000/-home-adaramir-claude-mcgyvr/66a5afe5-2eda-4019-9649-fa6e55340d76/scratchpad/patch_mmvq.py
W=$(mktemp -d); mkdir -p "$W/ggml/src/ggml-cuda"
curl -sSL -o "$W/ggml/src/ggml-cuda/mmvq.cu" \
  https://raw.githubusercontent.com/ggml-org/llama.cpp/b10644/ggml/src/ggml-cuda/mmvq.cu
cd "$W" && git init -q . && git add -A && git -c user.email=a -c user.name=a commit -qm base
sed 's#/src/ggml/src/ggml-cuda/mmvq.cu#ggml/src/ggml-cuda/mmvq.cu#' "$SRC" >p.py && python3 p.py
git diff > records/evidence/2026-09-02-srv1-kernel-arms/mmvq.patch   # adjust dest
```

A verified copy is at
`/tmp/claude-1000/-home-adaramir-claude-mcgyvr/900783a7-45cd-4deb-bc61-19e752dde5ed/scratchpad/mmvq.patch`.
It has **not** been installed at the ladder's default path
(`records/evidence/2026-09-02-srv1-kernel-arms/mmvq.patch`); doing so is what
lifts the preflight refusal, and is left as a deliberate act.

## Upstream corroboration

Verified against `ggml-org/llama.cpp` (fetched 2026-09-02):

- b10644 = `d7a207411`, 2026-08-27. `mmvq.cu` in this region is byte-identical
  between b10644 and master `3466812d1`.
- `get_mmvq_mmid_max_batch` is at line 256 and uses raw `cc`;
  `get_device_table_id(int cc)`'s NVIDIA branch at line 108 already uses
  `ggml_cuda_highest_compiled_arch(cc)`. **256 − 108 = 148** — behaviour 8's
  "148 lines above" is exact.
- The device side: `get_mmvq_mmid_max_batch_for_device<type>()` (line 377,
  `__CUDA_ARCH__` ladder), consumed at line 777 as
  `__launch_bounds__(get_mmvq_mmid_max_batch_for_device<type>()*ggml_cuda_get_physical_warp_size(), 1)`;
  the host asserts at line 1376
  `GGML_ASSERT( !ids || dst->ne[2] <= get_mmvq_mmid_max_batch(src0->type, cc));`
- **The defect is a known, open upstream bug.**
  [Issue #28018](https://github.com/ggml-org/llama.cpp/issues/28018) (opened
  2026-08-30, still open, no linked PR): GTX 1660 Ti, `61-virtual;80-virtual` +
  `GGML_CUDA_FORCE_MMQ=ON`, Qwen3.6-35B-A3B, `CUDA error: invalid argument`
  through `ggml_cuda_mul_mat_vec_q`; also reproducible via
  `test-backend-ops test -o MUL_MAT_ID -b CUDA0`. **The reporter's proposed fix
  is this patch** (`const int carch = ggml_cuda_highest_compiled_arch(cc);`).
- Introduced by [PR #20905](https://github.com/ggml-org/llama.cpp/pull/20905)
  (`ec16a072f`, "Optimize MOE GEMV kernel for BS > 1"), which added both the host
  function and the device `__launch_bounds__`.
- Precedent for the same class of fix:
  [PR #21238](https://github.com/ggml-org/llama.cpp/pull/21238) (`88d5f8ffc`),
  "Fix kernel slection for mmvq mmid kernel to align host selection with device
  launch bounds" — fixed the vendor half, not the compiled-arch half. Closes
  [issue #21191](https://github.com/ggml-org/llama.cpp/issues/21191).
- Adjacent live PR that would conflict:
  [PR #27828](https://github.com/ggml-org/llama.cpp/pull/27828), "cuda: always
  use MMVQ for MUL_MAT_ID on sm_60" — edits lines 256 and 377 in lockstep and
  keeps the raw-`cc` pattern.
- No upstream fix is merged or open. The one-line fix is unclaimed.

UNVERIFIED: that the `llamacpp:b10644-nomma-dp4a-v3` image on srv1 was built
from *this* copy of `patch_mmvq.py` rather than a revision of it. The build stage
is squashed out of the image (`docker history` shows only runtime layers), so the
applied source is not recoverable from the image. The Dockerfile.v2/v3 pair and
the two-line delta are the evidence; a byte-level tie to the image is not
available. Rebuild L3 from the diff above rather than reusing the v3 tag —
`RUN-ORDER.md`/C14 already flags `nomma-dp4a-v3` as a mutable local tag.

## The crash it fixes, as behaviour 8 describes it

`tests/test_a_crash_not_reproduced_is_not_a_crash_fixed.py`:

> `get_mmvq_mmid_max_batch` branches on the raw runtime `cc` (750, Turing) while
> the device kernel's `__launch_bounds__` are baked from `__CUDA_ARCH__` (610,
> Pascal, because the build ships only `61-virtual` PTX). The host hands out a
> batch the compiled kernel cannot launch, and llama.cpp aborts with
> `CUDA error: invalid argument` inside `ggml_cuda_mul_mat_vec_q`.
> `get_device_table_id` 148 lines above in the same file already reads the
> compiled arch; this function was missed.

The test's demands on the run, which the patch alone does not satisfy:

- `CRASH_MARKS = ("ggml_cuda_mul_mat_vec_q", "invalid argument")` must both
  appear in the reason of a recorded L2 `CRASH` row, with `http_000` = all/all.
  A bare `ERR` says a cell made no tokens; it does not say the kernel died.
- It is a **batch-size boundary**, not a point defect: L2 must be measured at
  `n = 1..12`, and a `### BOUNDARY` stamp must name `first_failing_n`.
- L3 must be soaked at **every `(cell, n)` L2 died on**, ≥ **60 trials** each,
  `failed == 0`, `otok > 1`. 0/60 bounds the failure rate at 5%; 30 only reaches
  10%; one clean run bounds nothing.
- ≥ 2 MoE checkpoints with different expert geometry — the batch limit is
  per-quant-type, so one checkpoint shows one window.

Consistent with upstream #28018's report and with the transcript note that the
window is 5–8 concurrent MoE decode slots, but the boundary must be **measured
on srv1**, not assumed. UNVERIFIED until the run produces it.
