# touching-engine

Before choosing an engine, a quantisation format, or a kernel flag. Every claim
here is a capability gate read from engine source or from a rig's own startup
log — none of it is rig-conditional, so it survives the next hardware swap.

## Compute-capability gates

srv1's card is Turing, compute capability 7.5; srv2's is Ampere, 8.6.

| feature | 7.5 | 8.6 |
|---|---|---|
| Marlin W4A16 (AWQ / GPTQ) | yes | yes |
| Marlin W4A8-INT8 | yes | yes |
| Marlin W4A8-FP8 | no | no |
| Machete | no | no |
| CUTLASS native FP8 GEMM | no | no |
| FP8 *weights* via Marlin-FP8 | yes | yes |
| FlashAttention 2 | no | yes |
| bfloat16 | auto-cast to fp16 | yes |
| `--kv-cache-dtype fp8` | no | yes |

**Marlin's floor sits below Turing, so srv1 is not excluded from AWQ or GPTQ.**
Its poor vLLM numbers are not a kernel-availability problem — see the Turing
entry below for what they actually are.

**Machete and native FP8 GEMM are Hopper-and-later.** Neither rig reaches them
and no flag changes that. FP8 *weights* are a separate thing and do work on
both, keeping the byte-per-weight saving.

## Two free flags nothing in this repo sets

**`--dtype float16` on every vLLM cell.** Marlin logs its own complaint on
pre-Hopper hardware and recommends fp16 over bf16 for performance. Both rigs are
pre-Hopper. No config in the tree passes it. Untested, free.

**`--kv-cache-dtype fp8` is not free on Ampere — it changes the attention
backend.** The default backend accepts only the 16-bit dtypes; fp8 additionally
requires a newer FlashAttention *and* a Hopper card, so the request falls
through to a different attention implementation. You get a larger KV pool and a
different kernel in the same change. Do not attribute the result to the pool
alone.

## `--cpu-offload-gb` is not "streaming", it is worse

**vLLM maps offloaded weights as a zero-copy host view and the GPU reads them
across PCIe on every forward pass, with no VRAM caching at any point.** Its own
config docstring says as much.

Two penalties compound: the bus is far slower than host memory, and vLLM cannot
load the 3-bit GGUF-class quants, so the same model costs materially more bytes
per token as AWQ-INT4 or FP8.

**Rule: if the model fits on the card, vLLM, and the margin grows with
concurrency. If it does not, llama.cpp, and it is not close.**

## llama.cpp picks tensor-core kernels on a card with no tensor cores

**The TU116 die is Turing with the RT cores and the tensor cores removed — and
it still reports compute capability 7.5.** NVIDIA substituted plain FP16 ALUs,
so FP16 runs at twice FP32, but there is no tensor core and **no CUDA API
exposes that fact.**

llama.cpp tests only the capability integer, and it does so *before* any
integer-dot fallback is considered, for both matrix multiply and flash
attention. So the stock image runs tensor-core kernels on hardware that emulates
them. Upstream calls the result correct but abysmal. **The measured cost is a
roofline deficit of more than twofold on cards a few percent apart in
bandwidth.**

**The fix is a build flag, plus a one-function patch for MoE.** Compiling for a
virtual architecture below Turing makes the highest-compiled-arch query return
below Turing, so the tensor-core paths cannot be selected and the integer-dot
kernels run instead. The arch list alone leaves host and device disagreeing
about the MoE batch limit — the host reads the raw capability and hands Turing
batch sizes to a kernel compiled with older launch bounds, which is a CUDA
invalid-argument on every MoE model above the lowest width. The patch makes that
one function read the compiled arch instead.

**Serve srv1 on the patched image.** The arch-list-only build is retired: it
crashes every MoE model at width. The patch changes nothing on srv2, whose card
has real tensor cores and should keep the stock image.
→ `okf/must-read/touching-rigs.md`

**The arch list is the whole gain** — a large multiple on prefill, a substantial
one on serving aggregate, and a few percent off decode. Forcing the
matrix-multiply kernel alone moves nothing, the CPU build flags move nothing,
and stock equals the local baseline. Disassembly confirms the mechanism: the
slow builds carry tensor-core instructions for the real architecture and the
fast ones carry none. Correctness holds — the faster build answers the same,
inside the bound each arm priced on its own null.

**Attribute a build gain with a one-variable ladder.** The earlier comparison
that ran all of one arm and then all of the other, with no arm recorded on the
row, is superseded and is not quoted.

**Vulkan is a real middle path, not a replacement.** The Vulkan backend queries
the cooperative-matrix extension rather than the capability integer, so it needs
no arch hack and beats stock prefill — but it is well short of the patched
build's prefill and has the lowest decode of anything tested. To run at all, the
image needs the X and EGL libraries the NVIDIA ICD dlopens, and the device must
be requested through CDI rather than the plain GPU flag. Otherwise ggml
registers the CPU backend alone and benches the CPU under a Vulkan label — it
did exactly that twice, before the bench step learned to refuse a declared
backend that did not run.

**Two build notes.** A CUDA docker build needs the linker told to allow
undefined shared-library symbols, or the final link fails on the driver stub
that is absent from the devel image. And building on srv2 and shipping the image
is faster and safer than building on srv1.

## Arch tags and tokenizer traps

- **`gpt-oss` vs `gptoss`**: only the official MXFP4 conversion loads; blobs
  carrying the other arch tag fail with `unknown model architecture`.
- **A vocab-size split blocks speculative decoding in vLLM** between two sizes
  of one model family. It is padding only, and llama.cpp tolerates it.
- **Post to the chat-completions endpoint, never a raw completion endpoint.**
  With no chat template some models emit a stop token on the first step, and the
  cell records a whole ladder of nothing while reporting no failures.
