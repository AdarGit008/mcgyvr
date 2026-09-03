# touching-engine

Before choosing an engine, a quantisation format, or a kernel flag. Every claim
here is a capability gate in vLLM v0.26.0 or llama.cpp b10644, read from source
or from a rig's own startup log — none of it is rig-conditional, so it survives
the next hardware swap.

## Compute-capability gates

srv1's card is cc **7.5** (Turing TU116), srv2's is cc **8.6** (Ampere GA106).

| feature | 7.5 | 8.6 | gate |
|---|---|---|---|
| Marlin W4A16 (AWQ / GPTQ) | **yes** | yes | `if device_capability < 75: return []` — the floor is **75, not 80** |
| Marlin W4A8-INT8 | yes | yes | `has_device_capability(7,5)` |
| Marlin W4A8-FP8 | no | no | SM89 or SM12x only |
| Machete | no | **no** | `get_min_capability() == 90` — exact equality, Hopper only |
| CUTLASS native FP8 GEMM | no | **no** | `cuda_device_capability >= 89` |
| FP8 *weights* (W8A16 via Marlin-FP8) | yes | yes | `Fp8Config.get_min_capability() == 75`; the 1 byte/weight saving is kept |
| FlashAttention 2 | **no** | yes | FA2 needs cc ≥ 8; srv1 falls to `TRITON_ATTN` |
| bfloat16 | auto-cast | yes | srv1 logs `doesn't support torch.bfloat16. Falling back to torch.float16` |
| `--kv-cache-dtype fp8` | no | yes | srv1's `modelopt` refusal: `Minimum capability: 89. Current capability: 75` |

**Marlin's floor being 75 means srv1 is not excluded from AWQ/GPTQ.** Its poor
vLLM numbers are not a kernel-availability problem. See the TU116 entry below
for what they actually are.

## Two free flags nothing in this repo sets

**`--dtype float16` on every vLLM cell.** Marlin logs its own complaint on
pre-SM90 hardware: *"sm8x doesn't support atomicAdd + bfloat16 natively"* and
*"You are running Marlin kernel with bf16 on GPUs before SM90. You can consider
change to fp16 to achieve better performance."* Both rigs are pre-SM90. No
config in the tree passes it. Untested, free.

**`--kv-cache-dtype fp8` is not free on Ampere — it changes the attention
backend.** FLASH_ATTN accepts only `auto`/`float16`/`bfloat16`; fp8 additionally
requires FA3 **and** cc 9.x. On srv2 the request therefore falls through to
FLASHINFER. You get exactly 2.000x the KV pool and a different attention
implementation in the same change. Do not attribute the result to the pool alone.

## `--cpu-offload-gb` is not "streaming", it is worse

**vLLM maps offloaded weights as a UVA zero-copy host view and the GPU reads
them across PCIe on every GEMM, with no VRAM caching at any point.** Its own
config docstring: *"loaded from CPU memory to GPU memory on the fly in each
model forward pass."*

Two penalties compound on srv2: the bus (PCIe Gen3 x16 ≈ 12.5 GB/s practical
against ~28 GB/s of RAM) and the format (vLLM cannot load 3-bit GGUF-class
quants, so the same model costs 1.35–2.7x more bytes per token as AWQ-INT4 or
FP8). **Measured consequence: llama.cpp beats vLLM ~4x on offloaded MoE** —
srv2, Qwen3.6-35B, llama.cpp `ncmoe=24` at 28.6 tok/s against vLLM
`--cpu-offload-gb 26` at 6.1.

**Rule: if the model fits on the card, vLLM, and the margin grows with
concurrency. If it does not, llama.cpp, and it is not close.**

## llama.cpp picks tensor-core kernels on a card with no tensor cores

**TU116 (GTX 1650/1660/1660 Super/1660 Ti) is the Turing die shipped with the RT
cores and the tensor cores removed — and it still reports cc 7.5.** NVIDIA
substituted 128 plain FP16 ALUs per SM, so FP16 runs at 2x FP32, but there is no
tensor core and **no CUDA API exposes that fact**.

llama.cpp tests only the integer:

```c
static bool turing_mma_available(const int cc) {
    return GGML_CUDA_CC_IS_NVIDIA(cc) && ggml_cuda_highest_compiled_arch(cc) >= GGML_CUDA_CC_TURING;
}
```

`ggml_cuda_should_use_mmq()` calls it **first**, before any DP4A fallback, and
`ggml_cuda_get_best_fattn_kernel()` likewise selects `BEST_FATTN_KERNEL_MMA_F16`.
So the stock image runs the int8 tensor-core MMQ kernel and the tensor-core
flash-attention kernel on hardware that emulates both. Upstream calls the result
correct but *"abysmal"*.

**The measured cost is a 2.4–2.8x roofline deficit on cards 7% apart in
bandwidth.** srv1 extracts 25.0–26.9% of its memory roofline where srv2 extracts
59.1–74.1%.

**The fix is a build flag, plus a one-function patch for MoE.** Compiling for
`-DCMAKE_CUDA_ARCHITECTURES="61-virtual;80-virtual" -DGGML_CUDA_FORCE_MMQ=ON`
makes `ggml_cuda_highest_compiled_arch(75)` return 61 — below Turing — so the
MMA paths cannot be selected and the Pascal DP4A kernels run instead. The arch
list alone (`L2`, built 2026-09-01 as `llamacpp:b10644-nomma-dp4a`) leaves the
host and the device disagreeing about the MoE MMVQ batch limit:
`get_mmvq_mmid_max_batch` reads the raw cc 750 and hands out Turing batch sizes
to a `mul_mat_vec_q_moe` kernel compiled with Pascal launch bounds. That is a
CUDA `invalid argument` in `ggml_cuda_mul_mat_vec_q` on every MoE model at
`np=8` from n=2 up — the `mling n=8 ERR` this entry used to call unexplained.
`L3` = L2 + `patch_mmvq.py` (one function in `ggml/src/ggml-cuda/mmvq.cu`,
made to read the compiled arch) survived 60 trials at every width n=2..12 with
zero crashes.

**Serve srv1 on `llamacpp:b10644-L3`.** `llamacpp:b10644-nomma-dp4a` is retired.
It changes nothing on srv2, whose Ampere card has real tensor cores and should
keep the stock image. Build recipe:
`tools/runs/campaigns/srv1-kernel-arms/1-build-ladder.sh`, through `run.sh`.
→ `records/evidence/2026-09-02-srv1-kernel-arms/{mmvq.patch,patch_mmvq.py,MMVQ-PATCH.md}`

**Attributed 2026-09-02/03 by a one-variable ladder, round r2-02-09-2026.** Six
builds of commit `d7a207411`; `llama-bench -r 9` on Qwen2.5-Coder-3B Q4_K_M for
prefill and decode; serving at n=1/4/8 on the measured workload, five
interleaved replicates, for the aggregate:

| arm | moves | prefill p512 fa=1 tok/s | decode tok/s | serving mean agg tok/s |
|---|---|---|---|---|
| L0 (`75-real;75-virtual`) | local baseline | 355 | 101 | 69.8 |
| L1 | + `FORCE_MMQ` | 355 | 101 | 69.2 |
| L2 | `61-virtual;80-virtual` + `FORCE_MMQ` | 1275 | 95 | 111.1 |
| **L3** | L2 + mmvq patch | 1272 | 95 | **112.1** |
| L4 | L0 + `GGML_NATIVE`, no `CPU_ALL_VARIANTS` | 355 | 101 | 69.0 |
| A1 stock `server-cuda-b10644` | six variables at once | 358 | 101 | 69.4 |
| A3 Vulkan (`GGML_VULKAN`, no CUDA) | the whole backend | 677 | 89 | not served |

The arch list is the whole gain: 3.6x prefill, 1.6x serving aggregate, and 6%
off decode. `FORCE_MMQ` alone and the CPU build flags move nothing, and stock
equals the local baseline. `cuobjdump` confirms the mechanism: L0/L1/L4 carry
257k tensor-core lines for sm_75, L2/L3 carry none and JIT sm_61 PTX. The
serving A/A null on this instrument spreads 15.3%, so L2 vs L3 is not
distinguishable on speed and the 1.6x is. Correctness: L2 and L3 each drift 1
of 257 bench-py cells (0.39pp) from L0, inside the 1.47pp bound every arm
priced on its own null, so the faster build answers the same. The ratios in the
2026-09-01 A/B (1.5–1.8x) were the same size, but that file ran all of one arm
then all of the other and its rows carry no `arm=`; it is superseded, do not
quote it.
→ `records/evidence/2026-09-03-srv1-kernel-arms/{srv1-build-ladder.tsv,srv1-llama-bench.tsv,correctness.json}`
→ `records/evidence/2026-09-02-srv1-kernel-arms/{srv1-lcpp-arms.tsv,srv1-aa-null.tsv,srv1-moe-slots.tsv,RUN-ORDER.md}`
→ `tools/runs/campaigns/srv1-kernel-arms/PLAN.md`

**Vulkan is a real middle path, not a replacement.** The Vulkan backend detects
tensor cores by querying `VK_KHR_cooperative_matrix`, so it needs no arch hack
and gives 1.9x stock prefill — but half of L3's prefill and the lowest decode.
To run it at all the image needs `libX11 libXext libGLdispatch libEGL` (the
NVIDIA ICD links and dlopens them) and the device must be requested through CDI
(`--device nvidia.com/gpu=all`, not `--gpus all`), or ggml registers the CPU
backend alone and benches the CPU under a `vulkan` label. It did that twice
before the bench step learned to refuse a declared backend that did not run.
→ `records/evidence/2026-09-02-srv1-kernel-arms/refusals/A3-vulkan-never-loaded.txt`

Two build notes: a CUDA docker build needs
`-DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-shlib-undefined` or the final link fails
on `libcuda.so.1` (the driver stub is absent in the devel image), and building
on srv2 and shipping the image is faster and safer than building on srv1.

## Arch tags and tokenizer traps

- **`gpt-oss` vs `gptoss`**: only the official MXFP4 conversion loads in b10644;
  ollama's blob and the unsloth Q3_K_M carry the other tag and fail with
  `unknown model architecture`.
- **Qwen2.5-Coder vocab split** blocks 1.5B→7B speculative decoding in vLLM:
  151936 vs 152064. It is padding only, and llama.cpp tolerates it.
- **Post to `/v1/chat/completions`, never a raw completion endpoint.** With no
  chat template Qwen3.6-35B emits a stop token on the first step; that cost 20
  of 60 measured rows, each reporting `otok=1` beside `failed=0/n`.
