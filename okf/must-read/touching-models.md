# touching-models

Choosing, comparing, quantising or deleting a checkpoint on disk.

## The filename is not evidence. Sum the tensor table.

**A GGUF header carries the truth and costs nothing to read.**
`ggufscan.py` reads headers only — never weights — and returns params, layer
count, expert count, top-k, KV head layout, per-ggml-type byte totals and the
expert / non-expert split for every file on a rig in seconds.
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/ggufscan.py`
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/srv{1,2}-gguf-tensor-tables.json`

**Two checkpoints on disk are mislabelled, and both mislabels would have changed
a decision.** Found 2026-09-01 by header scan, not by running anything:

| file | label says | header says |
|---|---|---|
| `nvidia_Nemotron-3-Nano-30B-A3B-IQ2_XXS` | IQ2_XXS, ~2.06 bpw | **4.56 bpw** — `IQ4_NL` 16.07 GiB, with 0.06 GiB of actual IQ2_XXS |
| `Qwen3.8-27B-UD-IQ3_XXS` | read as a MoE from its A3B-adjacent siblings | **dense** — `expert_count` absent, expert bytes **zero** |

The first was scheduled for deletion as "IQ2 quality at 17 GB". The second was
ranked the top MoE offload candidate at a predicted 105 tok/s; `--n-cpu-moe` is
a **no-op** on a dense model and its real ceiling is ~28.

**Bits-per-weight computed from file size over parameter count is a guess.**
Two defensible estimates of one GGUF's expert bytes disagreed by 14% and both
were wrong. Watch the type map in particular: **MXFP4 is ggml type 39**, and a
reader missing it falls back to f32 and calls an 11.28 GiB file 71 GiB.

## Identical geometry is not identical weights

**KAT-Coder-V2.5-Dev and Ornith-1.0-35B agree on every structural field and are
still different models.** Both are `qwen35moe`, 41 layers, 256 experts, top-8,
`n_embd` 2048, 2 KV heads, `full_attention_interval` 4, ctx 262144. Their
`Q2_K-AllGPU` files agree on expert bytes **to the byte** (12,515,803,136),
agree on quant mix to the gigabyte, differ in total size by 256 bytes, and share
a byte-identical 4 MB tail. Everything short of a full hash said "duplicate".

```
6364cc8f0ef01bbb44f935f044038966  KAT-Coder-V2.5-Dev_Q2_K-AllGPU.gguf
59c77a3c3c05eaa30fec8ec9714b6720  Ornith-1.0-35B_Q2_K-AllGPU.gguf
e26b2e67dcd1157878260222b49cea21  KAT-Coder-V2.5-Dev_Q3_K_M_imatrix_MTP.gguf
dd93c6d8f4b2d4d6052a6132003bdf4c  Ornith-1.0-35B_Q3_K_M.gguf
```

**The trap is structural, not specific to these two.** A community fine-tune
inherits its base model's architecture exactly and is usually quantised by the
same pipeline at the same settings, so size, layer count, expert bytes, quant
mix and tail can all match while the weights — the entire point of the
fine-tune — differ. **Never delete a checkpoint as a duplicate on anything less
than a full `sha256sum`.** Matching size is a reason to hash, not a verdict.

Same-size pairs that are genuinely one file duplicated do exist here: on srv2
`Qwen3-Coder-30B-A3B-Instruct-Q4_K_M` and `Qwen2.5-Coder-14B-Instruct-Q4_K_M`
each sit in two directories, 832 bytes apart. Hash those too before deleting.

## Sparsity, not size, sets decode speed

**Bytes read per token is `expert_bytes × top_k / n_experts`, and it is nearly
independent of total parameters.** Qwen3-Next-80B (top-10 of 512, 2.0% active)
reads *fewer* bytes per token than Qwen3-Coder-30B Q4_K_M (top-8 of 128, 6.3%),
despite being 2.6x the file. Ranking checkpoints by size predicts speed
backwards; gpt-oss-20b (top-4 of 32) is among the smallest files and the slowest
to decode.

**KV cost is set by the layers that cache, not by `block_count`.** Measured from
the metadata on disk: `qwen35moe` declares `full_attention_interval = 4`, so 10
of 40 layers cache — 20 KiB/token, against Qwen3-Coder-30B's 96 KiB/token at 48
of 48. `nemotron_h_moe` declares `head_count_kv` as an **array** with only six
non-zero entries: 6 attention layers of 52, ~12 KiB/token, at a 1,048,576
training context. Cheap KV is VRAM you get to spend on experts, so it compounds
with sparsity.

## Renames applied

**2026-09-01:** `nvidia_Nemotron-3-Nano-30B-A3B-IQ2_XXS.gguf` →
`nvidia_Nemotron-3-Nano-30B-A3B-IQ4_NL.gguf` on both rigs. Folder was already
correct (`models/moe/` — it is `nemotron_h_moe`, 128 experts); only the quant in
the name was wrong. No live config referenced the old name; the pre-rename name
survives in `records/evidence/2026-08-27-spec-decoding/store/README.md`, which is
a historical record and was left alone.

A folder audit over both rigs' tensor tables the same day found **zero** misfiled
checkpoints — every file with experts is under `models/moe/`, every file without
is under `models/dense/`. `Qwen3.8-27B-UD-IQ3_XXS` was already correctly under
`dense/`; only the downstream reasoning about it was wrong.
