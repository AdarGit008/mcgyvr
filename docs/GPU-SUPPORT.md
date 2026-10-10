# GPU & engine support

Which inference engine runs on which GPU, and what to do when your card is
below the floor. mcgyvr binds local OpenAI-compatible servers (llama.cpp,
vLLM) or API models; this page is the support contract for the local engines.

## Read your GPU first

```bash
nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv
```

`compute_cap` is the **compute capability** (`cc`), e.g. `8.6` for an RTX 3060.
Match it against the floor for the engine you want. Floors are **per-image** —
re-read the arch list after an engine upgrade, never trust a number read once.

## Floors at a glance

| Engine | Min cc (CUDA 12.x) | Min cc (CUDA 13.x) | Floor |
| --- | --- | --- | --- |
| llama.cpp (upstream) | 6.1 | — (out of blast radius) | **sm_61** |
| ik_llama.cpp | 6.1 | 7.5 (sm_61 dropped) | **sm_61** |
| vLLM | 7.5 | — (ships own PyTorch) | **sm_75** |
| Mesh-LLM | 6.1 | 7.5 build, pkg ✗ (NCCL) | **sm_61** |
| DS4 | 6.1 (build); 8.6 loads, serve ✗ | 7.5 build | **sm_61** (build) |
| Strata | — (RTX 20+ only) | ships CUDA 13.0 | **RTX 20 (cc 7.5 + tensor cores), 12 GiB** |
| FreeToken | — | 8.6 (RTX 30/40/50) | **CUDA 13.x** |

## The matrix (engine × compute capability)

`✓` works · `✗` blocked · `—` not applicable. The three cc columns are on a
CUDA 12.x toolchain; the CUDA 13.x column is the FreeToken-bump blast radius
and Strata's shipped container.

| Engine | cc 6.1 (12.x) | cc 7.5 (12.x) | cc 8.6 (12.x) | CUDA 13.x |
| --- | --- | --- | --- | --- |
| vLLM | ✗ refused (no kernel image) | ✓ loads | ✓ loads + serves | — (ships own PyTorch) |
| llama.cpp (upstream) | ✓ runs | ✓ runs | ✓ runs (split) | — (out of blast radius) |
| ik_llama.cpp | ✓ builds + serves | ✓ builds + serves | ✓ builds + serves | sm_61 dropped; 75/86 build ✓ |
| Mesh-LLM | ✓ serves | ✓ serves | ✓ serves | sm_61 dropped; 75/86 pkg ✗ (NCCL) |
| DS4 | ✓ builds + runs | ✓ builds + runs | ✓ loads; ✗ serve (prefill) | sm_61 dropped; 75/86 build ✓ |
| Strata | ✗ (VRAM < 12 GiB) | ✗ (VRAM / GTX-16 gate) | ✓ loads + serves (Q2_0 LOW_RAM) | ships CUDA 13.0 |
| FreeToken | ✗ (CUDA 13 drops sm_61) | — (RTX 30/40/50 only) | ✗ by default (nvcc 12.4 vs cu130) | required |

## The CUDA-version floor and the cc floor are coupled

A **CUDA 13.x toolkit cannot compile for sm_61** — Pascal is evicted from the
toolchain. Upgrading the toolkit to satisfy one engine (FreeToken needs
CUDA 13.x) removes sm_61 support for every engine that still compiles CUDA
kernels on that toolkit. Decide the toolkit once against the oldest card you
plan to keep, not per-engine.

## Older / odd hardware — what to do (the extra use case)

- **Pascal (cc 6.1, e.g. GTX 1080 Ti).** Fine on CUDA 12.x: llama.cpp, ik_llama.cpp,
  Mesh-LLM and DS4 all build and run. vLLM refuses (needs sm_75). Strata is out
  (needs 12 GiB+ VRAM). FreeToken is impossible (drops sm_61). On CUDA 13.x,
  everything that compiles CUDA kernels loses sm_61.
- **GTX-16 (cc 7.5, no tensor cores, e.g. 1660 SUPER).** Same story as Pascal for
  llama.cpp / ik / Mesh-LLM / DS4, and it clears vLLM's sm_75 gate. Strata is
  still out: it wants the RTX-20 line's tensor cores, not raw cc 7.5.
- **Ampere (cc 8.6, e.g. RTX 3060).** Everything loads. Exception: **DS4 loads but
  does not serve** — its SSD-streaming CUDA backend fails the first prefill on
  Ampere (`CUDA SSD cache cannot stage 6 experts`); it is aimed at DGX Spark /
  Ada Lovelace, so use another engine on Ampere.
- **Strata on anything older than RTX 20.** Only path is the **experimental
  CUDA-12 engine** (`-DSTRATA_EXPERIMENTAL_SM60=ON`, CUDA 12.9 toolkit), which
  lowers the floor to sm_60 but is compile-checked upstream, not validated on
  the maintainers' own hardware. Treat it as experimental.
- **Mesh-LLM split (two machines).** `--split` needs a **layer package**
  (`model-package.json` + per-layer GGUF fragments), not a raw `.gguf`. Produce
  one with `skippy-model-package write-package` (or the HF splitter) before
  serving with `--split`.

## How to read this page

Floors are **capability facts** read from engine source and the measured
evidence in `records/evidence/2026-10-09-pp-latency-2b-support-matrix/`; a
value measured on one fleet is a data point, not a rule. Before offering an
engine to a user, read the user's card cc and check it against the floor —
and re-read the arch list after any engine upgrade, because floors are
per-image.
