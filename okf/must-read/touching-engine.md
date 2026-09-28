# touching-engine

Before choosing an engine, a quantisation format, or a kernel flag. Every claim
here is a capability gate read from engine source or from an engine's own
startup log. The floors are the pinned engine's; re-read them from its source
after an engine upgrade.

## Compute-capability gates (vLLM)

Read each card's compute capability off the rig
(`nvidia-smi --query-gpu=compute_cap --format=csv`) and compare it with the
floor.

| feature | floor |
|---|---|
| Marlin W4A16 (AWQ / GPTQ) | 7.5 |
| Exllama (GPTQ) | 6.0 |
| FP8 *weights* via Marlin-FP8 (weight-only, W8A16) | 7.5 |
| native FP8 compute (CUTLASS scaled-mm, W8A8) | 8.9 |
| Machete | 9.0 exactly (Hopper) |
| FlashAttention 2 backend | 8.0 |
| bfloat16 | 8.0 — below it, cast to float16 |
| `--kv-cache-dtype fp8` on the FlashAttention backend | 9.x only, with FlashAttention 3 |

**Marlin's floor is 7.5, so a Turing card is not excluded from AWQ or GPTQ.**
Poor vLLM numbers there are not a kernel-availability problem.

**Machete and native FP8 compute are not available on Ampere or below.** No flag
changes that. FP8
*weights* are a separate thing and load from 7.5 up, keeping the
byte-per-weight saving.

## `--dtype` and `--kv-cache-dtype`

**Below 9.0, Marlin with bfloat16 logs that float16 is the faster path.** Measure
`--dtype float16` against the same cell before adopting it.

**`--kv-cache-dtype fp8` is not free off a 9.x card — it changes the attention
backend.** The FlashAttention backend accepts only the 16-bit dtypes elsewhere, so
the request falls through to a different attention implementation where one
exists, and the launch fails where none does. You get a larger KV pool and a
different kernel in the same change. Do not attribute the result to the pool
alone. → `okf/config/vllm.md` KV sizing

## `--cpu-offload-gb` is not "streaming", it is worse

**vLLM maps offloaded weights as a zero-copy host view and the GPU reads them
across PCIe on every forward pass, with no VRAM caching at any point.** Its own
config docstring says as much.

The bus is far slower than host memory, so every offloaded byte is read at bus
speed per token. `--n-cpu-moe` computes decode on the CPU beside the weights
instead.

**Rule: if the model fits on the card, vLLM. If it does not, llama.cpp with
`--n-cpu-moe`.**

## llama.cpp picks tensor-core kernels on a card with no tensor cores

**A die can report compute capability 7.5 and have no tensor cores, and no CUDA
API exposes that fact.** llama.cpp selects its tensor-core paths from the
capability integer alone, for both matrix multiply and flash attention. So the
stock image runs tensor-core kernels on hardware that emulates them. Check the
die, not the capability, before trusting a stock-image number on a 7.5 card.

**The fix is a build flag, plus a one-function patch for MoE.** Compiling with
`CMAKE_CUDA_ARCHITECTURES` below Turing makes the highest-compiled-arch query
return below Turing, so the tensor-core paths cannot be selected and the
integer-dot kernels run instead. The arch list alone leaves host and device
disagreeing about the MoE batch limit — the host reads the raw capability and
hands Turing batch sizes to a kernel compiled with older launch bounds, which is
a CUDA invalid-argument on every MoE model above the lowest width. The patch
makes that one function read the compiled arch instead.

**Serve such a card on the patched image, and only that card.** The
arch-list-only build crashes every MoE model at width. A card with real tensor
cores keeps the stock image. → `okf/must-read/touching-rigs.md`

**The arch list is the whole gain.** Forcing the
matrix-multiply kernel alone moves nothing and the CPU build flags move nothing.
After any such build, re-run a correctness null: the build is adopted only if it
answers inside the bound each arm priced on its own null.

**Attribute a build gain with a one-variable ladder, the arm recorded on every
row, replicates interleaved across arms.** Blocked order — all of one arm, then
all of the other — confounds the arm with elapsed time and card temperature.

**Vulkan needs no arch hack, and has its own traps.** The Vulkan backend queries
the cooperative-matrix extension rather than the capability integer. To run at
all, the image needs the X and EGL libraries the NVIDIA ICD dlopens, and the
device must be requested through CDI (`--device nvidia.com/gpu=all`) rather than
`--gpus all`. Otherwise ggml registers the CPU backend alone and benches the CPU
under a Vulkan label — refuse any arm whose declared backend is not the one the
log shows loaded.

**Two build notes.** A CUDA docker build needs the linker told to allow
undefined shared-library symbols (`-Wl,--allow-shlib-undefined`), or the final
link fails on the driver stub that is absent from the devel image. And build on
the rig with the most cores and ship the image.

## Arch tags and tokenizer traps

- **`gpt-oss` vs `gptoss`**: llama.cpp loads the `gpt-oss` arch tag; a blob
  converted for another runtime can carry `gptoss` and fails with
  `unknown model architecture`. Read `general.architecture` from the header
  before planning around the file.
- **A vocab-size split blocks speculative decoding in vLLM** between two sizes
  of one model family. It is padding only, and llama.cpp tolerates it.
- **Post to the chat-completions endpoint, never a raw completion endpoint**
  → `okf/must-read/reading-results.md` § Rows that measured nothing.
