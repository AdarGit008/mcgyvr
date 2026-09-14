# SRV2 fleet-stamping report — a-solo, b-small, b-big (srv2 half)

Scope: **srv2 only** (RTX 3060 12 GiB sm_86, 48 GB RAM). Parallel run; the
coordinator merges this with the srv1 half. I did not touch srv1, did not edit
`fleet.yaml`/`policy.yaml`, did not run `mcgyvr fleet lock`, and wrote nothing
under `records/fleet/`. The rig is idle at the end (card `used=1 MiB`, no
`mcgyvr-*` container).

`validated_at` for every combination: `2026-09-13T21:44:00Z`.

---

## 0. Deliverables

- `fleet-setup/digests-srv2.json` — srv2 `rig_id` + the 4 srv2 `unit_id`s, with
  the exact fields hashed (reproducible via `mcgyvr.fleet.ids.digest`).
- `fleet-setup/evidence-srv2.json` — the lock's evidence shape: `rigs.srv2.card_mib`,
  3 combinations, 2 moves.
- `fleet-setup/REPORT-srv2.md` — this file.
- Raw outputs: `records/measurements/fleet-setup-2026-09-13/srv2/`.

A dry-run of `mcgyvr.fleet.lock.write` against these digests + recommended
rooms + evidence **passes** (writes the 3 fleet locks and 3 `cmb-` records in a
temp dir).

---

## 1. Image check (task 1)

`llamacpp-lidenburg:e85e4d9` is present on srv2 and was already running a
healthy server (container `mcgyvr-lidenburg`, up 37 min, `RestartCount 0`).
No rebuild. Resolved image Id:
`sha256:9a61823266917162c9611f110df1ea24f116909d10cb3804641db184fcd95b63`.

The fork's io_uring disk tier logs
`[expert cache] io_uring_queue_init failed: Operation not permitted` under
docker's default seccomp and falls back to the RAM tier (`disk=0` in the steady
state). The RAM tier (cache 120/256) is what this unit runs; the io_uring
failure is non-fatal and matches the plan ("our RAM tier does not exercise it").

---

## 2. a-solo/srv2 — `[[srv2_35b_256k, awake]]` (task 2)

Lidenburg `llama-server`, `-c 262144` width 1, cache 120/256 env.

| field | value | source |
|---|---|---|
| warm_decode_tok_s | **48.2** (5 samples: 43.68, 47.19, 48.20, 48.76, 48.98; median 48.20) | `srv2/a-solo-running.json` |
| prefill_tok_s | **629.8** (3 samples: 623.5, 629.8, 635.0; median 629.8) | same |
| card_steady_mib | **10597** | `nvidia-smi` after requests |
| card_peak_mib | **10597** (peak sampler across 3 concurrent long requests: no growth) | `srv2/a-solo-context.json` |
| overhead_mib | **490** = CUDA primary context 113 MiB + driver reserve 377 MiB | see below |
| restarts | **0** | `docker inspect` |

- **CUDA primary context 113 MiB**: from the `--verbose` load log
  `CUDA0 : NVIDIA GeForce RTX 3060 (11911 MiB, 11798 MiB free)` → 11911−11798,
  before any model load.
- **Driver reserve 377 MiB**: idle card reads `used=1, free=11911, total=12288`
  → `12288−11911 = 377` (never handed to any process). Matches
  `tools/runs/hosts.json` `gpu_reserve_mib: 377`.
- **Named buffers** (Lidenburg fork, second `--verbose` pass): `CPU_Mapped model
  12189.97 MiB`, `CUDA0 model 1596.81 MiB`, `CUDA0 KV 2720.00 MiB`, `CUDA0 RS
  62.81 MiB`, `CUDA0 compute 891.00 MiB`, `CUDA_Host compute 264.28 MiB`. The
  Lidenburg expert cache keeps the expert weights in the mmap, so `CUDA0 model`
  is only the non-expert resident part; the card's 10597 MiB "used" is the full
  process footprint (weights + KV + compute + RS + context + expert cache).
- **Pin**: `room_mib = 10597` (the measured peak; the draft's 10475 is below the
  measured peak and would fail B85). `window = 262144` (`-c 256k`).

---

## 3. b-small/srv2 — `[[srv2_3b, awake], [srv2_7b, awake]]` (task 3)

vLLM pair, `service_healthy` gated (3B first), pinned KV. Compose
`compose.srv2-pinned-3b-first.yml` (from
`records/measurements/fleet-identity-2026-09-11/`), byte-for-byte the M7 pair.

| field | srv2_3b | srv2_7b | source |
|---|---|---|---|
| warm_decode_tok_s | **126.7** (126.5–126.9) | **68.3** (68.2–68.3) | `srv2/b-small-3b.json`, `-7b.json` |
| prefill_tok_s | **11500** | **12059** | `records/measurements/fleet-identity-prefill-2026-09-12/README.md` (median tok/s) |
| attention_backend | **FLASH_ATTN** | **FLASH_ATTN** | vLLM log: "Using FLASH_ATTN attention backend" |
| kv_cache_memory_bytes | **1207959552** (32768 tok) | **1879048192** (32768 tok) | vLLM log "GPU KV cache size: 32,768 tokens" |
| gpu_memory_utilization | **0.30** | **0.68** | run log (non-default args) |
| room_mib | **3573** (= 0.30 × 11911) | **8099** (= 0.68 × 11911) | M7 proposal (`fleet-identity-2026-09-11/README.md` §M7) |
| overhead_mib (pair) | **610.5** | | M7: reserve 377 + contexts 116.8 × 2 |
| restarts | **0** | **0** | `docker inspect` (both) |

- **Per-process card** (nvidia-smi compute apps): 3B `VLLM::EngineCore` 3574 MiB,
  7B 7858 MiB; card total used 11447 MiB.
- **`Σ room + overhead ≤ card`**: `3573 + 8099 + 610.5 = 12282.5 ≤ 12288` ✓ (M7's
  exact arithmetic).
- **Corrections to the draft `fleet.yaml`** (the draft is stale — it carries the
  pre-measurement 0.26/0.72 shares that §8 of `fleet-identity.md` flagged as too
  thin):
  - `srv2_3b`: `gpu_memory_utilization 0.26 → 0.30`, `room_mib 3810 → 3573`,
    `kv_cache_memory_bytes 0 → 1207959552`.
  - `srv2_7b`: `gpu_memory_utilization 0.72 → 0.68`, `room_mib 7544 → 8099`,
    `kv_cache_memory_bytes 0 → 1879048192`.
- Both units reported `FLASH_ATTN`, matching the pinned `attention_backend`, and
  0 restarts (the pinned KV + `service_healthy` gating removes the live pair's
  known crash-restart).

---

## 4. b-big/srv2 — `[[srv2_80b, awake]]` (task 4)

Qwen3-Next-80B-A3B Q3_K_M, `--n-cpu-moe 36 --parallel 4`, `-c 16384`.

| field | value | source |
|---|---|---|
| warm_decode_tok_s | **28.4** (25.78, 28.35, 28.40, 28.42, 28.41; median 28.40) | `srv2/b-big-80b.json` |
| prefill_tok_s | **280.9** (265.8, 280.9, 281.7; median 280.9) | same |
| card_steady_mib | **11523** | `nvidia-smi` after requests |
| card_peak_mib | **11523** (peak sampler across 4 concurrent requests: no growth) | same |
| overhead_mib | **524** = CUDA context 146.69 MiB + driver reserve 377 MiB | see below |
| restarts | **0** | `docker inspect` |

- **CUDA context 146.69 MiB**: `records/evidence/2026-09-04-srv1-ncmoe-floor/srv2-buffer-probe.tsv:5`
  (srv2 RTX 3060, mainline `llamacpp:b10644-L3`), cited per §8 of the plan.
- **`--verbose` context probe** (`measure_context.py`) read: `CUDA0 model
  9992.39 MiB`, `CUDA0 KV 384.00 MiB`, `CUDA0 compute 664.00 MiB`, steady
  11507 MiB → unnamed `465.61 MiB`. That unnamed lump = CUDA context (~147) +
  the recurrent-state buffer (~319) the probe does not parse, consistent with
  the 146.69 primary-context figure.
- **Pin**: `room_mib = 11523` (measured peak; draft's 11167 is Q10's `-c 8192`
  figure and is below the `-c 16384` width-4 peak). `window = 16384` (the width-4
  compose runs `-c 16384`, not the draft's 8192).
- `pswpout 0` (no swap-out); `pgmajfault 110307` (mmap of the 38.3 GB blob).

---

## 5. Switch moves (task 5)

Timed on srv2 with `measure_switches.py` (`srv2/switches.json`).

| move | downtime_s | wake_s |
|---|---|---|
| b-small→b-big (`[[3b,awake],[7b,awake]]` → `[[80b,awake]]`) | **70.33** | `{srv2_80b: 70.33}` |
| b-big→b-small (`[[80b,awake]]` → `[[3b,awake],[7b,awake]]`) | **179.57** | `{srv2_3b: 91.55, srv2_7b: 179.57}` |

- b-small→b-big: stop pair took 1.55 s, then 80B came up (70.33 s).
- b-big→b-small: stop 80B took 0.4 s; the gated pair's 3B healthy at 91.55 s,
  7B healthy at 179.57 s (7B waits on 3B `service_healthy`, so it inherits the
  3B's start latency).
- **Caveat — warm page cache.** These were taken minutes after the same models
  had been resident, so the 38 GB 80B and the AWQ weights were still in page
  cache. Cold references for the coordinator's validated values: 80B cold wake
  **98.2 / 99.8 s** (`flexibility-2026-09-09` Q16); 3B/7B cold wake **96.0 /
  96.4 s** door clock (`fleet-identity-2026-09-11` M2). A cold-cache switch is
  ~99 s (b-small→b-big) and ~180 s (b-big→b-small, gated).

---

## 6. Identity digests (task 6)

Computed via `mcgyvr.fleet.ids.digest`; exact hashed fields in
`fleet-setup/digests-srv2.json`.

- **rig_id** = `rig-cbe770b55841d616363165e38553a1c7c3768250df01ead1a255f0cbdef98455`
  over `{host: srv2, hardware: {cpu_model, cpu_max_mhz, ram_mt_s, pl1_uw,
  pl2_uw, gpu_name, gpu_vram_mib, gpu_cc}, system: {os_machine_id, kernel,
  driver, docker}}` — `gpu_reserve_mib` dropped per §12.
- unit_ids:
  - `srv2_35b_256k` = `unt-87384c127bc1554097e40bad7f3c0174c292dbb7b254026817915d1dbb3252b3`
  - `srv2_3b` = `unt-507267b8eaf983cf530b2841f824d4bd0856ac6d1ee576d9d666c961b41aeba4`
  - `srv2_7b` = `unt-17f274caba402438930c0d11795adb57cfe8611ce6c23a7a42473f9bb9d20a48`
  - `srv2_80b` = `unt-1dde4df84e0bc1a1e3b693b89c02f83783a56c2398e18359eb8ce227ec5834f7`

Field sets follow `fleet-identity.md` §1: `unt- = H{ engine, image id
(sha256:…), weights sha256, argv, env, gpu_cc }`. Weights: GGUF sha256 for the
two llama.cpp units; for the vLLM units, sha256 of the resolved HF snapshot's
safetensors (3B single file; 7B the two shards concatenated in filename order).

---

## 7. Rig / driver drift flags (for the coordinator)

- **srv2 driver drift.** `tools/runs/hosts.json` declares `driver: 595.84`
  (read_on 2026-09-03); live `nvidia-smi` reports **595.91.07**. This is a
  driver bump → a new rig id, and gate 2 will refuse srv2 against the stale
  `hosts.json` until it is re-declared. The rig_id above uses the live
  595.91.07. (srv1's re-declaration precedent is
  `fleet-identity-prefill-2026-09-12/README.md`.)
- **Draft addresses.** The draft `fleet.yaml` says `srv2_35b_256k` at
  `http://srv2:8090` and `srv2_80b` at `http://srv2:8081`; the as-run servers
  were on **8080** (Lidenburg default) and **8003** (the Q12 width-4 compose),
  respectively. `srv2_3b`/`srv2_7b` at 8001/8002 match the draft.

---

## 8. Evidence paths

| artifact | path |
|---|---|
| a-solo decode/prefill/card/restarts | `records/measurements/fleet-setup-2026-09-13/srv2/a-solo-running.json` |
| a-solo buffer/context decomposition | `records/measurements/fleet-setup-2026-09-13/srv2/a-solo-context.json` |
| b-small 3B / 7B | `records/measurements/fleet-setup-2026-09-13/srv2/b-small-3b.json`, `-7b.json` |
| b-big 80B + context probe | `records/measurements/fleet-setup-2026-09-13/srv2/b-big-80b.json` |
| switches | `records/measurements/fleet-setup-2026-09-13/srv2/switches.json` |
| harness scripts | `records/measurements/fleet-setup-2026-09-13/srv2/*.py` (also `scripts/`) |
| digests | `fleet-setup/digests-srv2.json` |
| evidence | `fleet-setup/evidence-srv2.json` |

Prior art harvested (cited, not re-measured): warm decode / prefill / overhead /
KV pinning from `records/measurements/fleet-identity-2026-09-11/README.md`
(M1, M6, M7), `records/measurements/fleet-identity-prefill-2026-09-12/README.md`,
and `records/measurements/flexibility-2026-09-09/README.md` (Q10/Q12/Q15/Q16).

---

## 9. Teardown

Every `mcgyvr-*` container was removed after each run. Final state: card
`used=1 MiB, free=11911 MiB`, no `mcgyvr-*` container, `docker ps` empty of our
units. The rig is idle.
