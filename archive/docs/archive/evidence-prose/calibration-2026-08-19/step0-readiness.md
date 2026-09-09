# Step 0.2 — readiness, both rigs

Two agents, one per rig, 2026-08-19. Both rigs are **ready**; every roster model
exists, loads, answers and unloads; both cards were left at their idle baseline of
**1 MiB**. No FAILs on either host.

## What was provisioned

| job | host | result |
|---|---|---|
| `llama3.2:3b` | srv2 | `ollama pull`, 41 s. Digest **byte-identical to srv1's copy** (`a80c4f17…b8b72`), so the mutable-tag risk the pin exists for did not fire. srv2 now holds 13 models. |
| `Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ` | srv2 | 1.6 GB into `~/.cache/huggingface`, 31 s. **B2 closed** — the subsequent vLLM launch loaded with no download. |

`~/.cache/huggingface/hub` on srv2 is **root-owned**, so the `hf download` route as
`adaramir` would have failed; the pre-warm went through the vLLM image itself with
the cache bind-mounted, which is how the existing checkpoints got their ownership
and exactly how vLLM reads it. No permissions were changed.

## The roster, verified

Every model: present with its digest, loaded from an idle card, answered a
completion, placement recorded, explicitly unloaded, card back to 1 MiB.

**srv1, 5 of 5.** Cold loads 2.30 / 3.87 / 4.18 / 5.39 / **7.77 s** (1.5b→7b).
Placement 1.0000 on four; `qwen2.5-coder:7b` at **0.9080**.

**srv2, 10 of 10.** Cold loads 2.58 s → **25.32 s** (worst: `gpt-oss:20b`).
Placement 1.0000 on eight; `gpt-oss:20b` **0.7945**, `qwen3-coder:30b` **0.5806**.

All 15 cells: `pgrep -af '[l]lama-server'` non-empty, `--port <N>` **space
separated** (so `ollama.py:399` holds), the child's `/props` 200 with `total_slots`.
`fingerprint.classify` was replayed offline against all five real srv1 `/props`
captures: **no `UnclassifiedError`, 5 of 5, both digests computed** — step 0.1's
deferred assertion 4 passes.

## Six findings

### R1 — `total_slots` is not uniform within a host

`nemotron-3-nano:4b` reports **`total_slots = 1`** on srv1 while the other four
report **2**. Its child launches `-c 4096 -np 1 -b 512 -ub 512` against the others'
`-c 8192 -np 2`: the engine **overrides** `OLLAMA_NUM_PARALLEL=2` for this
architecture (`nemotron_h`, hybrid/Mamba). Since `total_slots` is the only observed
source of `declared_slots`, it is read per model. Any per-host constant would be
wrong for exactly one entry — the hardest kind to notice. On srv2 all ten read 1,
consistent with `OLLAMA_NUM_PARALLEL` being unset there.

### R2 — the `/metrics` trap now has a positive disproof

Step 0.1 could only show that `kv_cache_max_concurrency` **coincided** with the flag
at 16. srv1 produced the counterexample: on a server launched **`--max-num-seqs 8`**,
`/metrics` reported `kv_cache_max_concurrency="16.00390625"`
(`kv_cache_size_tokens=131104` ÷ `max_model_len=8192`). `/server_info` at depth 0:
`max_num_seqs` **0 hits**, `num_seqs` **0 hits**. E5 is not the cautious reading, it
is the only correct one.

### R3 — sleep, both arms measured

| arm | card before | after | freed | `/sleep` | `/is_sleeping` |
|---|---|---|---|---|---|
| **without** `--enable-sleep-mode` (srv1) | 4958 MiB | 4936 MiB | **22 MiB** | **200** | **`true`** |
| **without** `--enable-sleep-mode` (srv2) | 9903 MiB | 9883 MiB | **20 MiB** | **200** | **`true`** |
| **with** `--enable-sleep-mode` (srv2) | 10869 MiB | 231 MiB | **10 638 MiB** | 200 | `true` |

Both arms return 200 and both report `is_sleeping: true`. **Only the card
distinguishes them.** E3 is not a precaution, it is the measurement. The flag also
raises steady-state VRAM (10869 vs 9903 MiB), and `/wake_up` restored 10851 MiB.

### R4 — two reasoning models on the roster, not one

`nemotron-3-nano:4b` returns a hidden `thinking` field and spent **54 tokens on a
17-token visible reply (~69% hidden)**; on the same prompt `gpt-oss:20b` spent 61
(**~72%**, heavier than the ~52% on record). Step 0.1 named only `gpt-oss:20b`.
Both models' `completion_tokens` counts reasoning tokens, so `RAMP_TOKENS = 475`
buys materially less visible output for them. Their throughput is real throughput;
the quantity is simply not comparable with a non-reasoning model's, and both are
labelled in the campaign config.

### R5 — `/api/ps` reports a phantom resident model after a kill

After a successful `sudo -n pkill`, with the card reading 1 MiB and no child
process, `/api/ps` **kept listing the model with its full `size_vram` and original
`expires_at` for the entire 60 s polled** — it survives to the keep-alive. So
residency can assert a model is on the card at fraction **1.0** when the card holds
nothing. E9 (making the kill actually work) is what opens this window; the service
restart that follows closes it. **Decision E11** makes `claim` read the card after
the load and refuse on `residency_contradicts_card`, so the guarantee no longer
depends on step ordering. An explicit `keep_alive:0` clears `/api/ps` at once, and
is already `release`'s first step.

### R6 — three corrections to the step 0.1 gotcha list

- **`num_ctx` defaults to 4096 here, not 2048.** All 15 children launched `-c 4096`
  and `/props` reports `n_ctx: 4096` on ollama 0.32.5. The advice is unchanged (set
  it explicitly); the silent-truncation threshold is twice what the record said.
- **`qwen2.5-coder:14b` and `deepseek-coder-v2:16b` do not spill.** Both read
  **1.0000** at 4096 context. `deepseek-coder-v2:16b` is a MoE and is *fully*
  resident, which sharpens D4 rather than softening it: architecture alone does not
  predict placement, so a placement gate was never an architecture check.
- **VRAM release was instant** — 1–2 s to baseline on both rigs, against the 30–60 s
  local-ai's swap script polls for. The polling stays; it did not fire here.

Also: a **third** off-roster near-miss tag exists that 0.1 did not name —
`nemotron-3-nano:30b-a3b-iq2` (18 GB, IQ2_XXS), beside the roster's
`nemotron-3-nano:4b`. With `qwen3:30b-a3b` (F16) and `qwen3-coder-next-ud:q3_K_XL`,
srv2 carries three tags that shorten to a roster name. None was loaded. Every
campaign entry is pinned by digest.

## The timing budget, measured

| | srv1 | srv2 |
|---|---|---|
| vLLM cold launch → health (200 **and** card > 500 MiB) | **33 s** | **109 s** |
| ollama cold load, worst model | 7.77 s (`7b`) | **25.32 s** (`gpt-oss:20b`) |
| margin on `START_TIMEOUT_S = 900` | 27x | 8.3x |
| margin on `LOAD_TIMEOUT_S = 2400` | ~309x | 95x |

Both budgets are adequate with very large margin, and the two MoE models the budget
was written for are not the problem. Caveats stated so the margins are not
over-read: the blobs were warm in page cache, and srv2's store is 130 GB against
~27 GB of cache, so a campaign cycling all ten will re-read the big blobs from NVMe
— minutes, not the 40 the budget allows. Step 0.1's risk 7 is unchanged:
`LOAD_TIMEOUT_S = 2400` is still shorter than the `curl -m 3600` it wraps.

## Closing state

Both rigs idle. srv1: no compute apps, `memory.used = 1 MiB`, `/api/ps` empty, no
`llama-server`, no vLLM, nothing on 8000, ollama active. srv2: identical, plus the
readiness container removed and the four pre-existing exited containers untouched.
The leftover vLLM that step 0.1 deliberately kept alive (E1) is gone. Nothing was
deleted or reconfigured on either host; no systemd unit or environment was changed.
