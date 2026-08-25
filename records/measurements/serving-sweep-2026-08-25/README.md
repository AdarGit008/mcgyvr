# Serving sweep, 2026-08-25 — Phase A of docs/plans/serving-sweep-2026-08-25

**This is exploration, not a bench manifest.** There is deliberately **no `run.json`**. The
recorder cannot describe this world yet: `serving_build()` (`tools/breadth/measure.py:861`)
probes `/api/version`, llama.cpp has no such route, and the server argv — which is what this
sweep varies — is recorded nowhere. Writing a `run.json` whose `serving_build` is `null` and
whose flags are absent would be `--condition` again (ADR-0027 D4): an identity field that
reached dispatch and never `record_run`. Those two writers are P0.1/P0.2 of the plan and were
deliberately not attempted in this session. Nothing here is comparable to anything in
`records/measurements/` and nothing here scores a model.

**What this is.** 32 serving configurations timed against `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481`
on srv1 and srv2 — model, `--n-cpu-moe`, `-t`, and KV-cache precision — to answer one question:
*what does a sweep cost?* 20 cells returned numbers, 12 refused to load. Per the plan's §0 this
is infrastructure: it sets Phase B's budget and decides nothing about any model's quality.

**The engine was llama.cpp, not ollama.** Ollama was `inactive` on both hosts throughout
(`rig-reality-2026-08-25.md (this directory)`). Cells naming a `/blobs/sha256-…`
path read a file out of ollama's blob store; the process reading it was `llama-server`. This is
the binding CAV-02 requires — an explicit GGUF under llama-server, never an ollama tag.

## Method

Per cell: restart the container with the cell's argv → poll `/health` → **2 warmup requests,
discarded** → 5 × `POST /completion`, `n_predict: 160`, `temperature: 0`, `cache_prompt: false`
→ median `timings.predicted_per_second` = **S1** → one 8-way concurrent burst → 8 requests ÷
wall = **tasks/h @8**. `sweep.py` is the harness as run; `cells/` holds every cell definition.

The prompt is a real corpus task contract (`tools/bench/tasks/py/b002-option-pairs/contract.yaml`)
wrapped in an instruction — **527 tokens (Qwen3.6 tokenizer) / 550 (Qwen2.5)**, near the corpus
median of 688 measured over 23,902 prior dispatches. The arrival baselines quoted in the
evidence file used a 21-token toy prompt and are therefore **not** comparable to S1 here; A1-1
and A1-5 re-anchor on this prompt.

Every ok cell reports `build_info: b10481-25ae3a9b3`, `total_slots: 4`, `n_ctx_per_slot: 4096`.
`--parallel` was never passed; 4 slots is this build's default.

## The two winners

| | srv1 | srv2 |
|---|---|---|
| model | `Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` | same file, byte-identical |
| sha256 | `9c964e657212fea1…` | `9c964e657212fea1…` |
| argv | `-ngl 99 --n-cpu-moe 28 -t 6 -c 4096 -fa on` | `-ngl 99 --n-cpu-moe 4 -t 10 -c 4096 -fa on --no-mmap` |
| S1 | 33.28 tok/s | **67.04 tok/s** |
| TTFT | 5.66 s | **0.67 s** |
| tasks/h @8 | 457 | **2,215** |
| VRAM | 5,554 / 6,144 MiB | 11,882 / 12,288 MiB |
| vs arrival config | +23% | +49% |

Both hosts converged on the same model, which is the model neither was running on arrival, and
both finished within ~500 MiB of their card's ceiling.

## Findings

- **The `--n-cpu-moe` descent is the whole story on srv2.** 20→7,690 MiB/50.55 tok/s, 16→53.97,
  12→57.56, 8→61.89, 6→64.14, **4→67.04**, 2 OOM. About +1 tok/s and +260 MiB per layer moved
  onto the GPU, monotone to the wall. The incumbent `qwen3-coder-30b` cannot play this game: it
  is 5.3 GB larger on disk, sits at 11,326 MiB at ncmoe 20, and OOMs at 18 and 16.
- **A smaller quant of a bigger model beat a bigger quant of a smaller one.** 35B-A3B at
  UD-IQ3_XXS (13.21 GB) reached 67.04 tok/s where 30B-A3B at 18.56 GB capped at 44.84 — +50% on
  5B more parameters, because the disk savings convert directly into layers that fit.
- **KV-cache quantisation is a dead end here.** `-ctk q8_0 -ctv q8_0` at ncmoe 4 freed **36 MiB**
  (11,846 vs 11,882) and cost 1.6 tok/s; ncmoe 2 and 0 OOM'd under it exactly as at f16. At
  `-c 4096` across 4 slots the KV is negligible against the weights. It also changes numerics,
  so it would have needed separate scoring — for nothing.
- **Threads matter in proportion to layers on the CPU.** srv2 (4 layers on CPU): t20 67.04, t16
  65.87, t10 66.18 — flat within noise, so **take `-t 10`** and leave 10 cores for the
  acceptance gate. srv1 (28 layers on CPU): `-t 5`→`-t 6` is +3.9%, and composed with ncmoe 28
  gives 33.28 — **more than the two gains added** (+10.7% against +6.7% expected).
- **srv1's floor is ncmoe 28.** 27 fails: 5,554 MiB at 28 plus ~520 MiB for one more layer
  overruns a 6,144 MiB card.
- **srv1's TTFT never moved.** 5.5–6.0 s across every configuration tried, against srv2's
  0.67 s. On a corpus whose median completion is 178 tokens, srv1 spends more wall clock on
  prefill than on generation. No `--n-cpu-moe` or `-t` setting touched it. This bears on
  ADR-0024 clause 2 ("srv1 is capacity"): the objection to srv1 as a dispatch host is its
  prefill, not its decode.
- **srv2 pulled further ahead under tuning** — 3.4x srv1 at arrival, **4.8x** at the winners.
  Tuning helped the host that had room to be tuned.
- **`gpt-oss-20b` does not load on this build, either host**: `unknown model architecture:
  'gptoss'`. Not VRAM, not flags — b10481 cannot read it. Moving the image to fix it would break
  the same-build comparability the sweep rests on, so it is out until the image moves for
  another reason.
- **The dense control outruns every MoE config and Phase B has to price it.**
  `Qwen2.5-Coder-7B-Instruct-IQ4_XS` (4.22 GB) does **71.76 tok/s and 4,174 tasks/h** on srv2
  against the 35B's 67.04 and 2,215 — 1.9x the sweep throughput at a third of the VRAM. Whether
  35B-A3B's quality is worth halving throughput is exactly what Phase B measures, and it is not
  answered here.

## Two legal cross-host contrasts

`Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` and `Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf` were verified
byte-identical on both hosts (`9c964e657212fea1…`, `f7eff217195ff980…`) and every cell ran
build `b10481-25ae3a9b3`. At matched flags (A1-2/A1-6 and A1-4/A1-8):

| model | srv1 | srv2 | ratio |
|---|---:|---:|---:|
| Qwen3.6-35B-A3B, ncmoe 20/38 | 25.91 | 50.55 | 1.95x |
| Qwen2.5-Coder-7B IQ4_XS, dense | 54.18 | 71.76 | 1.32x |

Same weights, same build; host and flags are the only differences. Whatever ADR-0024 clause 2
decides about comparing rates across hosts, the technical objection it was written against does
not apply to this pair — which makes it the first such pair this project has had.

## Skips

12 of 32 cells never became healthy; each row carries `status: "skipped"`, a reason, and the
last 15 lines of the loader log. Ten are VRAM refusals at the descent's wall (srv1 ncmoe 24/18
on the 35B and 35/32 on the 30B, srv2 ncmoe 2 on the 35B and 18/16 on the 30B, plus ncmoe 2/0
under q8_0 KV) and two are the `gptoss` architecture failure. No cell was dropped silently.

## What this does not establish

No model was scored. No task passed or failed. Phase B — the per-family floor map and pass@<=k
per 1,000 tokens — has not run, and cannot be recorded as a measurement until P0.1 and P0.2
land. Nothing about vLLM was measured in this session on either host.

---

## CORRECTION — 2026-08-25, on rebase onto main

This record was written against `main@f2d9ddb9` and is five commits stale. Rebasing it onto
`main@b8247a75` puts it beside work that measures the same flag on the same two rigs and
**refutes three of its claims**. They are corrected here rather than edited above: the numbers
were really measured, and what they are numbers *about* is narrower than the text says.

**1. Every cell ran at llama.cpp's default `-np 4`, so no `tasks/h @8` figure above is a
property of its configuration.** #366 is a correction issued for this exact defect — "a level of
n=16 was four concurrent sequences and twelve queued." An 8-way burst against 4 slots is four
served and four queued, which is what the 29.0 / 39.1 split in the arrival measurement was
showing. #366 varies `-np` and the figure moves hard: 35B-A3B IQ3_XXS at `--n-cpu-moe 25` and
**32 slots** reaches **254.5 tok/s at n=32**, against this record's best of ~67 tok/s single-stream
at 4 slots. Read every `tasks/h @8` column here as *tasks/h at 8 requests against 4 slots*.

**2. The `--n-cpu-moe` descent walked to the refusal, which #364 names as the wrong search.**
"The curve is not monotone at the edge. n-cpu-moe 37 is slower than 38 while still loading, so a
search that walks to the refusal picks the wrong cell." srv2's ncmoe 4 (406 MiB spare, ncmoe 2
OOM) and srv1's ncmoe 28 (27 OOM) are exactly cells found that way. They are the fastest cells
*measured*; they are not established as the fastest cells.

That defect compounds with the first: tuning ncmoe to the VRAM wall is what left 406 MiB and made
`--parallel` look unreachable. #366's best configuration spends VRAM on slots instead
(`--n-cpu-moe 25`, 32 slots), which this record's search could not reach because it optimised
single-stream throughput first.

**3. The two "legal cross-host contrasts" are confounded by `--no-mmap`.** srv2 carried it in
every cell and srv1 in none. #364 measures that flag at **+63% on a 16 GB host and −12..−18% on a
48 GB one** — precisely srv2 and srv1. The 1.95x and 1.32x ratios fold host, thread count and
`--no-mmap` together. The byte-identity of the weights and the identity of the build hold; the
contrast does not.

**4. The harness beside this file duplicates one that already exists.** `tools/bench/serving/`
(#318) carries `launch.py`, `knobs.py`, `calibrate.py`, its own `sweep.py`, `fingerprint.py`, and
backends for both ollama and vLLM, with the rigs declared in `configs/hosts.json`. A re-run
belongs there. `sweep.py` here is kept only because it is what produced these rows.

**5. Withdrawn: "nothing about vLLM was measured in this session on either host" was written as
though it described the repository.** It describes this session only. `records/evidence/` on main
holds ten vLLM measurement directories, including a 140-cell config sweep
(`2026-08-24-config-sweep/`) in which 36 cells were refusals and one flag was worth 5.02x on srv2.

**What survives.** The rig facts in `rig-reality-2026-08-25.md` (both hosts' RAM against the 32 GB
in ADR-0024 and `capability-table.json`, the byte-identical GGUF digests, `gpt-oss-20b` failing to
load on b10481 as `unknown model architecture: 'gptoss'`), and the single-stream S1 column, which
is a measurement of a named configuration and does not depend on `-np`.
