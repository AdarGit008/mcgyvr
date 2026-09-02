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

**The fix is a build flag and costs nothing.** Compiling for
`-DCMAKE_CUDA_ARCHITECTURES="61-virtual;80-virtual" -DGGML_CUDA_FORCE_MMQ=ON`
makes `ggml_cuda_highest_compiled_arch(75)` return 61 — below Turing — so the
MMA paths cannot be selected and the Pascal DP4A kernels run instead. Built
2026-09-01 as `llamacpp:b10644-nomma-dp4a` from commit `d7a207411`.

**Measured 2026-09-01: it is worth ~1.7x on srv1, for free.** Same rig, same
hour, same driver, position-matched prompt draws (`ptok` 574/598/672 identical
on both arms), and **identical VRAM** in every cell — so this is kernel speed,
not placement:

| cell | n | stock b10644 | no-MMA DP4A | gain |
|---|---|---|---|---|
| d3b (Qwen2.5-Coder-3B Q4_K_M) | 1 / 4 / 8 | 43.8 / 69.4 / 74.4 | **68.6 / 121.7 / 127.2** | 1.57 / 1.75 / **1.71x** |
| d7b (Qwen2.5-Coder-7B IQ4_XS) | 1 / 4 / 8 | 21.5 / 33.6 / 35.5 | **36.8 / 58.9 / 65.4** | 1.71 / 1.75 / **1.84x** |
| mling (Ling-3.0-tiny Q4_K_M) | 1 / 4 | 53.6 / 88.8 | **82.2 / 131.5** | 1.53 / **1.48x** |

**Two corrections to this entry, 2026-09-01, found by re-deriving it.** The
sentence that stood here quoted `prefill=` as corroboration and the archive
ladder as a control. Both were wrong, and neither changes the ratios above,
which are position-matched *within* the file.

- `prefill=` is not an independent measurement — see `reading-results.md`. The
  "249 → 390" figures it quoted are `agg` multiplied by `ptok/otok`.
- The archived `s1-d3b np=8 = 74.2` is **not** a control for this file's 74.4.
  The two rows drew different work: `ptok` 664 / `otok` 208 against 672 / 214,
  because the ladder ran levels `1,2,4,8,16,32` and this file ran `1,4,8` — the
  extra `n=2` rung consumed two UIDs and desynced every later draw. Agreement to
  0.3% across two different draws is coincidence, and the measured spread
  between nominally-identical stock cells reaches **6.2%** at n≥4.

What does hold: both arms here ran the same cell list in the same order, one
cell per process invocation, so `ptok` is identical arm-to-arm at every position
(574 / 598 / 672). That, and not the archive, is why the ratios are readable.

**Caveat: `mling n=8` returned `ERR` on the no-MMA arm** and is unexplained — one
cell of nine. Re-run it before quoting a Ling number at n=8.

**Use this image for every llama.cpp cell on srv1.** It changes nothing on srv2,
whose Ampere card has real tensor cores and should keep the stock image.
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/srv1-nomma-dp4a-ab.tsv`
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/Dockerfile.nomma-dp4a`

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
