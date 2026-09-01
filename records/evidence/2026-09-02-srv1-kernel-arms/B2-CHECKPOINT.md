# B2's checkpoint, and what `--linear-backend` actually is in v0.26.0

Off-rig research, 2026-09-01. Resolves the first two `Blockers` in
`lcp-vllm-3-arm-run.md:132-139`. Nothing here was measured on srv1; every claim
cites a URL or a repo path, and what could not be checked is marked
**UNVERIFIED**.

---

## Headline

1. `--linear-backend` **exists** in `vllm/vllm-openai:v0.26.0`, and `exllama` is
   one of its 20 accepted values. The August refusal was not the flag failing to
   parse — it was the kernel refusing the *quant type* of an AWQ checkpoint.
2. The doc's proposed fallback, `--quantization gptq` vs `--quantization
   gptq_marlin`, **does not name two kernels in v0.26.0**. Both strings resolve
   to the same config class. That contrast is invalid here.
3. So B2 keeps `--linear-backend exllama`, and B1 becomes `--linear-backend
   marlin` on the same checkpoint — one flag, one variable, one artifact.
4. The checkpoint should be **`Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4`**.

---

## (B) `--linear-backend` in v0.26.0

### The flag exists, and `exllama` is a legal value

Already captured in this repo, from the image itself:
`records/evidence/2026-08-24-knob-surface/declared-vllm-ffb2d59b1c05.json`,
flag index 255 (`vllm/vllm-openai@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52`):

```
--linear-backend   shape=choice   default=auto
choices = [aiter, auto, conch, cutlass, deep_gemm, emulation, exllama, fbgemm,
           flashinfer_b12x, flashinfer_cudnn, flashinfer_cutedsl,
           flashinfer_cutlass, flashinfer_trtllm, humming, machete, marlin,
           torch, triton, xpu, xpu_woq]
```

Every startup log in `records/` also prints the resolved value, e.g.
`records/evidence/2026-08-24-resolved-config/srv2-startup.log:16` —
`kernel_config=KernelConfig(..., moe_backend='auto', linear_backend='auto')`.

### How the flag is honoured

`vllm/model_executor/kernels/linear/__init__.py` @ `v0.26.0`:

- `_get_linear_backend()` reads `config.kernel_config.linear_backend` (default
  `"auto"`).
- `_LINEAR_BACKEND_KERNEL_MAP` maps `"exllama" -> {ExllamaLinearKernel}`. The
  comment is explicit: *"When a user sets `--linear-backend <name>`, only kernels
  in the corresponding set are considered candidates. If none can implement the
  layer config, an error is raised to respect the user's explicit intent."*
- `_POSSIBLE_KERNELS[PlatformEnum.CUDA]`, in priority order, is
  `[CutlassW4A8, Machete, AllSpark, Marlin, Conch, Exllama, TritonW4A16,
  Humming]`. So under `auto` on sm75 the winner is **Marlin** — B1's premise is
  correct — and `exllama` is only ever reached by naming it.
- The chooser raises `ValueError("Failed to find a kernel that can implement the
  WNA16 linear layer. Reasons: \n" + ...)`. That is verbatim the string srv1
  recorded on 2026-08-24.

### Why srv1's August refusal happened, and why it does not recur on GPTQ

`vllm/model_executor/kernels/linear/mixed_precision/exllama.py` @ `v0.26.0`:

```python
class ExllamaLinearKernel(MPLinearKernel):
    SUPPORTED_QUANT_TYPES = [scalar_types.uint4b8, scalar_types.uint8b128]

    @classmethod
    def get_min_capability(cls) -> int:
        return 60
```

and in `can_implement`, verbatim:

```
f"Quant type ({c.weight_type}) not supported by Exllama, supported types are: ..."
```

`records/evidence/2026-08-24-knob-surface/surface.md:81` (and
`surface.json:1598`) recorded exactly that, with `(uint4)`. **`uint4` is the AWQ
scalar type** (unsigned + runtime zero-point);
`vllm/model_executor/layers/quantization/utils/marlin_utils.py:80-87` labels the
two families in-source — `uint4` = "AWQ style, unsigned + runtime zero-point",
`uint4b8` = "GPTQ style, unsigned + symmetric bias".

`vllm/model_executor/layers/quantization/auto_gptq.py:100-104`:

```python
# (num_bits, is_sym) -> quant_type
TYPE_MAP = {
    (4, True): scalar_types.uint4b8,
    (8, True): scalar_types.uint8b128,
}
```

So the requirement chain is exact and complete:

| requirement | source | why B2's checkpoint must satisfy it |
|---|---|---|
| `bits=4`, `sym=true` | `auto_gptq.py:100-104` | anything else is not `uint4b8`; `sym=false` is not in `TYPE_MAP` at all and raises `Unsupported quantization config` (`auto_gptq.py:157-159`) |
| `group_size > 0` and divides in-features | `exllama.py can_implement` | `group_size=128` with hidden/intermediate both multiples of 128 |
| out-features % 8 == 0 | `exllama.py can_implement` (`32 // size_bits`) | all Qwen2 projections satisfy this |
| activations fp16 | `exllama.py can_implement` — *"Exllama only supports float16 activations"* | Qwen GPTQ-Int4 repos declare `"torch_dtype": "float16"` |
| compute capability ≥ 60 | `exllama.py get_min_capability` | srv1 is 7.5 |
| dense, not MoE | `_POSSIBLE_KERNELS` holds *linear* kernels only; MoE routes to `AutoGPTQMoEMethod` / `select_wna16_moe_backend` (`auto_gptq.py:467,489`) and is filtered by `--moe-backend`, a different flag | on a MoE checkpoint `--linear-backend exllama` would bind only the attention/dense projections, so the arm would not isolate the kernel even if it launched |

`desc_act` is **not** a hard gate at TP=1 — `exllama.py` only rejects act-reorder
when input features are partitioned across devices. `desc_act=false` is still the
right choice: it sets `has_g_idx=False` (`auto_gptq.py:351`), which keeps the
weight-permute path out of the arm entirely.

### The engine names the kernel that ran — test #12's `kernel_observed`

`vllm/model_executor/layers/quantization/auto_gptq.py:354-358`:

```python
kernel_type = choose_mp_linear_kernel(mp_linear_kernel_config)
if kernel_type.__name__ not in self._kernel_backends_being_used:
    logger.info("Using %s for AutoGPTQLinearMethod", kernel_type.__name__)
```

So B1 must log `Using MarlinLinearKernel for AutoGPTQLinearMethod` and B2
`Using ExllamaLinearKernel for AutoGPTQLinearMethod`. This is the same line
shape srv2 already emitted for AWQ —
`records/evidence/2026-08-24-resolved-config/srv2-startup.log:21`,
`auto_awq.py:473 Using MarlinLinearKernel for AutoAWQMarlinLinearMethod` — so the
field is known to be harvestable from the container log.

### The proposed fallback contrast is INVALID in v0.26.0

`vllm/model_executor/layers/quantization/__init__.py` @ `v0.26.0`, lines 152-154:

```python
"auto_gptq": AutoGPTQConfig,
"gptq":      AutoGPTQConfig,
"gptq_marlin": AutoGPTQConfig,
```

All three names resolve to **one class**. v0.26.0 merged the old `gptq.py` and
`gptq_marlin.py` into a single `auto_gptq.py` (the tree at tag `v0.26.0` contains
`vllm/model_executor/layers/quantization/auto_gptq.py` and **no** `gptq.py` or
`gptq_marlin.py`). `AutoGPTQConfig.override_quantization_method`
(`auto_gptq.py:220-238`) treats `gptq`, `gptq_marlin`, `auto_gptq` and `marlin`
as one interchangeable set of user strings and returns `cls.get_name()` for all
of them.

Consequence: **`--quantization gptq` vs `--quantization gptq_marlin` moves
nothing.** Both give the same config object, the same
`choose_mp_linear_kernel()` call, and therefore the same kernel. A B1/B2 pair
built on that contrast would print two different flags and run one kernel twice
— the exact failure mode `test_the_engine_log_names_the_kernel_that_actually_ran`
exists to catch (cf. `--cpu-offload-params experts`).

The doc's `Blockers` bullet at `lcp-vllm-3-arm-run.md:136-139` should be struck
and replaced by:

```
B1  --linear-backend marlin    -> MarlinLinearKernel   (mma.sync PTX on sm75)
B2  --linear-backend exllama   -> ExllamaLinearKernel  (__hfma2, no mma.sync)
```

one flag, one variable, same checkpoint. `marlin` is named explicitly rather than
left to `auto` so that the CONFIG row records a flag rather than a default, and
so `_LINEAR_BACKEND_KERNEL_MAP` filtering is on in both arms symmetrically.

Marlin is reachable on sm75, so B1's premise holds:
`kernels/linear/mixed_precision/marlin.py` `get_min_capability() -> 75`, and
`marlin_utils.py:64-65` gates only `device_capability < 75`.

**Residual risk (UNVERIFIED, on-rig).** `AutoGPTQLinearMethod.__init__`
(`auto_gptq.py:320-324`) calls `verify_marlin_supported(quant_type, group_size)`
*unconditionally*, before the chooser runs. For `uint4b8`/`g128` on sm75 the
source says this passes, but it has not been executed on srv1. If B2 dies with a
Marlin message rather than an Exllama one, that assert is the cause and it is a
finding, not a setup error — record it as a REFUSED row with the reason.

---

## (A) A dense GPTQ 4-bit checkpoint for a 6144 MiB card

### First, a correction to the blocker's premise

`lcp-vllm-3-arm-run.md:132` says srv1's only GPTQ is
`Qwen1.5-MoE-A2.7B-Chat-GPTQ-Int4`. That string appears **nowhere** in this repo
outside that sentence. The 2026-08-31 inventory
(`records/evidence/2026-08-31-inventory/srv1-scan.txt:51-122`) lists srv1's
`~/models` tree and both HF caches, and contains **no GPTQ checkpoint at all** —
only GGUF, three Qwen2.5-Coder AWQ repos, `thewimo/Qwen3-4B-AWQ`,
`nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8`, and the safetensors dirs under
`~/models/{dense,moe}`. So the blocker understates the problem: B2 has no GPTQ
checkpoint of *any* shape, and one must be fetched regardless. Marked
**UNVERIFIED** rather than refuted — the inventory is a week old and the file may
exist unrecorded.

### The budget

srv1 is `6144 MiB` total, `5745 MiB` free at idle with 399 MiB reserved
(`records/evidence/2026-08-31-inventory/srv1-scan.txt:43`). Under
`--gpu-memory-utilization` the KV pool is whatever survives the weights, and
`test_two_backends_on_one_checkpoint_is_the_only_pair.py` requires the pool to be
comparable across the two arms — so the checkpoint must leave *slack*, not just
fit. Guideline 8 of the run doc prices a launch near the memory edge at a
1-in-3 coin flip. Target: weights ≤ 2 GiB, leaving ≳3 GiB of KV at util 0.85.

Per-token fp16 KV, from each config's own `num_hidden_layers`,
`num_key_value_heads` and `hidden_size/num_attention_heads`:

| model | layers | kv heads | head dim | B/token | tokens per GiB |
|---|---|---|---|---|---|
| 1.5B | 28 | 2 | 128 | 28,672 | ~37,400 |
| 3B | 36 | 2 | 128 | 36,864 | ~29,100 |
| 7B | 28 | 4 | 128 | 57,344 | ~18,700 |

### A trap worth recording

**None of the Qwen GPTQ-Int4 repos ships a `quantize_config.json`.** All four
`https://huggingface.co/<repo>/resolve/main/quantize_config.json` fetches return
**HTTP 404**. The quantisation parameters live in `config.json` under
`quantization_config`, which is where vLLM reads them from
(`AutoGPTQConfig.from_config`, `auto_gptq.py:201-211`, via
`get_from_keys(config, ["desc_act"])` / `["sym"]`). Any fetch script that checks
only `quantize_config.json` will report "missing config" for exactly the right
checkpoints and "present" for the older TheBloke-style ones.

### Candidates

#### 1. `Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4` — RECOMMENDED

- Parameters: **1,543,714,304** total in the quantised file (1,310,195,712 I32 +
  233,518,592 F16); base model is Qwen2.5-Coder-1.5B, dense `Qwen2ForCausalLM`,
  28 layers, hidden 1536, intermediate 8960, GQA 12/2.
- On disk: single `model.safetensors`, **1,149,862,960 B = 1.071 GiB**; whole
  repo ≈ 1.161 GiB with tokenizer/vocab/merges.
  (`https://huggingface.co/api/models/Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4?blobs=true`)
- `quantize_config.json`: **absent (HTTP 404)**. From
  `https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4/resolve/main/config.json`,
  `quantization_config` verbatim:

```json
{"batch_size": 1, "bits": 4, "block_name_to_quantize": null,
 "cache_block_outputs": true, "damp_percent": 0.01, "dataset": null,
 "desc_act": false, "exllama_config": {"version": 1}, "group_size": 128,
 "max_input_length": null, "model_seqlen": null,
 "module_name_preceding_first_block": null, "modules_in_block_to_quantize": null,
 "pad_token_id": null, "quant_method": "gptq", "sym": true, "tokenizer": null,
 "true_sequential": true, "use_cuda_fp16": false, "use_exllama": true}
```

  `bits=4` ✓ `sym=true` ✓ `group_size=128` ✓ `desc_act=false` ✓ — and the
  checkpoint literally ships `"use_exllama": true` with an `exllama_config`.
  `"torch_dtype": "float16"` ✓ satisfies exllama's activation gate.
  1536 % 128 == 0 and 8960 % 128 == 0, so the group size divides every
  in-features ✓.
- Budget: 1.07 GiB of weights leaves roughly 4.1 GiB at util 0.85 ≈ **150k KV
  tokens** at fp16 — vastly more than the run's `levels 1,4,8` need, so the two
  arms' pools cannot diverge for lack of room.
- **The decisive argument:** its AWQ sibling
  `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` is already the standing vLLM model on
  both rigs — `records/headers/2026-08-22-coresidency-feasibility.json:8`,
  `records/headers/2026-08-24-ramp-tokens.json:7`,
  `records/evidence/2026-08-24-resolved-config/srv2-startup.log:4`, and the only
  vLLM entry in `tools/bench/serving/configs/srv-full.json`
  (`records/headers/2026-08-22-cpu-offload.json:33`). Same architecture, same
  tokenizer, same shapes, same launch geometry — the vLLM pair lands on a model
  the campaign's drivers and null already know how to price. This is not a
  cross-engine comparison; it just removes one class of surprise.

#### 2. `Qwen/Qwen2.5-Coder-3B-Instruct-GPTQ-Int4` — ACCEPTED, second choice

- Parameters: **3,085,938,688** (2,774,532,096 I32 + 311,406,592 F16); dense
  `Qwen2ForCausalLM`, 36 layers, hidden 2048, intermediate 11008, GQA 16/2.
- On disk: single `model.safetensors`, **2,067,756,448 B = 1.926 GiB**; repo
  ≈ 2.016 GiB.
- `quantize_config.json`: **absent (HTTP 404)**. `config.json` →
  `quantization_config` is byte-identical in every field that matters:
  `"bits": 4, "group_size": 128, "desc_act": false, "sym": true,
  "quant_method": "gptq", "use_exllama": true, "exllama_config": {"version": 1}`,
  `damp_percent 0.01`, `true_sequential true`, `use_cuda_fp16 false`.
  `"torch_dtype": "float16"` ✓. 2048 % 128 == 0, 11008 % 128 == 0 ✓.
- Budget: 1.93 GiB of weights leaves ≈3.2 GiB at util 0.85 ≈ **93k KV tokens**.
  Comfortable. Its AWQ sibling is also on both rigs
  (`records/evidence/2026-08-31-inventory/srv1-scan.txt:100`), so the same
  familiarity argument applies one notch weaker.
- Use this if the 1.5B turns out too small to make a kernel difference visible
  above the null.

#### 3. `Qwen/Qwen2.5-1.5B-Instruct-GPTQ-Int4` — ACCEPTED, fallback only

- Parameters: **1,543,714,304**; dense `Qwen2ForCausalLM`, 28 layers, hidden
  1536, intermediate 8960.
- On disk: `model.safetensors` **1,149,862,960 B = 1.071 GiB** (byte-identical
  size to candidate 1 — same architecture, different fine-tune).
- `quantize_config.json`: **absent (HTTP 404)**. `config.json` →
  `quantization_config` matches on all four required fields: `"bits": 4,
  "group_size": 128, "desc_act": false, "sym": true`. `"torch_dtype": "float16"`.
- Rank 3 only because it is not the Coder line, so it shares nothing with the
  workload the rest of the campaign runs. Config-wise it is as good as #1.

### Rejected

#### `Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4` — REJECTED on budget, not config

- Config is **fine**: `"bits": 4, "group_size": 128, "desc_act": false, "sym":
  true, "quant_method": "gptq"`, `torch_dtype float16`, hidden 3584 (28×128),
  intermediate 18944 (148×128). `quantize_config.json` also 404s.
- Rejected because of size: `model-00001-of-00002.safetensors` 3,999,234,216 B +
  `model-00002-of-00002.safetensors` 1,576,146,928 B = **5,575,381,144 B =
  5.193 GiB** of weights on a **6.000 GiB** card. After the ~0.39 GiB the driver
  already reserves at idle there is essentially nothing left for a KV pool, and
  at 56 KiB/token even 200 MiB buys under 4k tokens. srv1 has recorded launches
  at this edge failing as a 1-in-3 coin flip (run doc, guideline 8), which is
  precisely the noise that would make B1 and B2 incomparable.

#### `TheBloke/TinyLlama-1.1B-Chat-v1.0-GPTQ` — REJECTED on config

- This repo *does* ship
  `https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GPTQ/resolve/main/quantize_config.json`,
  verbatim:

```json
{"bits": 4, "group_size": 128, "damp_percent": 0.1, "desc_act": true,
 "static_groups": false, "sym": true, "true_sequential": true,
 "model_name_or_path": null, "model_file_base_name": "model"}
```

- **`desc_act` is `true` on `main`.** Rejected on the stated criterion. It would
  in fact still run at TP=1 (exllama only refuses act-reorder when input features
  are sharded), but it drags `has_g_idx=True` and the `torch.argsort` weight
  permute into the arm, adding a variable the pair is supposed to hold fixed.
  TheBloke repos carry alternate branches; a `desc_act=false` branch was **not**
  checked — **UNVERIFIED**.

### Ranking for the 6 GiB budget

| rank | repo | weights | KV headroom @ util 0.85 | verdict |
|---|---|---|---|---|
| 1 | `Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4` | 1.071 GiB | ~4.1 GiB / ~150k tok | **use this** |
| 2 | `Qwen/Qwen2.5-Coder-3B-Instruct-GPTQ-Int4` | 1.926 GiB | ~3.2 GiB / ~93k tok | good |
| 3 | `Qwen/Qwen2.5-1.5B-Instruct-GPTQ-Int4` | 1.071 GiB | ~4.1 GiB / ~150k tok | fine, off-workload |
| — | `Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4` | 5.193 GiB | ~0 | rejected, budget |
| — | `TheBloke/TinyLlama-1.1B-Chat-v1.0-GPTQ` | 0.72 GiB | ample | rejected, `desc_act=true` |

The KV-headroom column is arithmetic on the config dimensions, not a measurement.
vLLM's own `# GPU blocks:` line prices the real pool and must be recorded per arm
— **UNVERIFIED** until then.

---

## The "two checkpoints on disk are already mislabelled" claim

`lcp-vllm-3-arm-run.md:134-135` asserts this without a citation, and **no note
saying so exists anywhere in `records/` or `archive/`** — searched for
`mislabel*`, `misnamed`, `not actually`, `despite the name`. The claim as
written is **UNVERIFIED**. What *is* verifiable is a set of name-vs-content
mismatches on the shared store, any two of which the sentence may be pointing at:

1. **`~/models/moe/nemotron-30b-awq/` is not AWQ.** vLLM resolves it as
   `quantization=compressed-tensors` — twice, on srv1:
   `records/evidence/2026-08-31-inventory/srv1-vllm-nemotronh-moe-loadtest.log:20`
   and `srv1-vllm-nemotronh-offload12-mml1024.log:21`. The directory name says
   AWQ; the engine says compressed-tensors. This one is a real, logged
   contradiction, and it is already causing damage —
   `archive/docs/board-findings-2026-08-31.md:131` records the offload gate as
   right "for the Qwen2/AWQ cells" while compressed-tensors/NemotronH is
   **unmeasured**.
2. **`~/models/dense/nvidia_OpenCodeReasoning-Nemotron-7B-Q4_K_{M,S}.gguf` are
   Qwen2, not Nemotron.** `records/evidence/2026-08-27-spec-decoding/store/README.md`
   annotates both as "qwen2 arch, vocab 152064". Two files, one model family
   misnamed — arguably the "two checkpoints" the sentence means.
3. **`~/models/moe/4b-Q4_K_M.gguf` names no model at all** and is filed under
   `moe/`; the store README has to gloss it as "(gpt-oss-4b draft)".
4. **`~/models/moe/Ornith-1.0-35B_Q3_K_M.gguf` (18,134,220,000 B) and
   `KAT-Coder-V2.5-Dev_Q3_K_M_imatrix_MTP.gguf` (18,134,220,160 B)** sit 160
   bytes apart on srv1 (`srv1-scan.txt:70,79`), and the store README lists the
   KAT file but not the Ornith one. Suspicious, **UNVERIFIED** — needs a GGUF
   header read, which is on-rig.

**The operational consequence is the same whichever two were meant, and it is the
one that matters for B2: a checkpoint's directory or file name is not evidence of
its quantisation format.** Read `config.json` → `quantization_config` (or
`quantize_config.json` where one exists) and record `bits`/`sym`/`group_size`/
`desc_act` into the CONFIG row, so
`test_a_refusal_is_recorded_as_the_result_it_is`'s `checkpoint_quant` field
carries a value that was read rather than inferred from a path.

---

## What B2 should run

```
B1  --model Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4 --linear-backend marlin
B2  --model Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4 --linear-backend exllama
```

Everything else held: `--dtype float16` (exllama refuses anything else), and
`model`, `weights_sha256`, `img`, `util`, `len`, `seqs`, `kv` identical across
the pair per `HELD` in
`tests/test_two_backends_on_one_checkpoint_is_the_only_pair.py`.

`kernel_observed` comes from the engine log line
`Using {Marlin,Exllama}LinearKernel for AutoGPTQLinearMethod`
(`auto_gptq.py:357`), not from the flag.

Do **not** write the pair as `--quantization gptq` vs `gptq_marlin`: in v0.26.0
those are the same class and would produce two rows and one kernel.

---

## Sources

- `records/evidence/2026-08-24-knob-surface/declared-vllm-ffb2d59b1c05.json`
  (flag 255) — the flag list read out of the pinned image digest.
- `records/evidence/2026-08-24-knob-surface/surface.md:81`,
  `surface.json:1598` — the August exllama refusal and its full reason string.
- `records/evidence/2026-08-31-inventory/srv1-scan.txt` — rig state and model
  inventory.
- `records/evidence/2026-08-31-inventory/srv1-vllm-nemotronh-moe-loadtest.log:20`
  — `nemotron-30b-awq` resolving as compressed-tensors.
- `records/evidence/2026-08-24-resolved-config/srv2-startup.log:16,21` — the
  `linear_backend=` echo and the `Using ...LinearKernel for ...` log shape.
- `records/evidence/2026-08-27-spec-decoding/store/README.md` — the shared store
  and its arch annotations.
- vLLM `v0.26.0` source, via
  `https://github.com/vllm-project/vllm/tree/v0.26.0`:
  - `vllm/model_executor/kernels/linear/__init__.py`
    (`_get_linear_backend`, `_LINEAR_BACKEND_KERNEL_MAP`, `_POSSIBLE_KERNELS`,
    the `WNA16` `ValueError`)
  - `vllm/model_executor/kernels/linear/mixed_precision/exllama.py`
  - `vllm/model_executor/kernels/linear/mixed_precision/marlin.py`
  - `vllm/model_executor/layers/quantization/__init__.py` (lines 152-154)
  - `vllm/model_executor/layers/quantization/auto_gptq.py`
  - `vllm/model_executor/layers/quantization/utils/marlin_utils.py`
- HuggingFace, fetched 2026-09-01:
  - `https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GPTQ-Int4/resolve/main/config.json`
  - `https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GPTQ-Int4/resolve/main/config.json`
  - `https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GPTQ-Int4/resolve/main/config.json`
  - `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GPTQ-Int4/resolve/main/config.json`
  - `https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GPTQ/resolve/main/quantize_config.json`
  - `https://huggingface.co/api/models/<repo>?blobs=true` for every size and
    parameter count above.
