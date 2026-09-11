# Parameters for a runtime fleet shape — evidence only

Every row: symbol, value with units, **kind**, citation. `MEASURED` = read off a
rig. `FIT` = derived here from measured points (the points are named).
`CONSTANT` = a number in the source, with whatever backs it. `PROPOSED` = a
design number nobody measured. `UNMEASURED` = no value; the row says where one
would come from.

Citations are `path` + section, or `src/path.py:LINE`. Nothing below is carried
over from a number that could not be cited.

---

## 1. Rigs

| symbol | value | kind | citation |
|---|---|---|---|
| `hosts` | `{srv1, srv2}`, one GPU each | MEASURED | `~/.local/state/mcgyvr/scans/srv1.json`, `srv2.json` |
| `V_total(srv1)` | 6144 MiB (GTX 1660 SUPER) | MEASURED | `scans/srv1.json` `gpus[0].vram.total_mib` |
| `V_free_idle(srv1)` | 6127 MiB (used 17) | MEASURED | `scans/srv1.json` `gpus[0].vram.free_mib` |
| `V_total(srv2)` | 12288 MiB (RTX 3060) | MEASURED | `scans/srv2.json` `gpus[0].vram.total_mib` |
| `V_free_idle(srv2)` | 11911 MiB, `reserved` 376 MiB | MEASURED, retaken idle 2026-09-09 | `scans/srv2.json`; `records/measurements/ram-headroom-2026-09-09/README.md` § "Hazards this campaign paid for" |
| `V_reserve` | constant within a boot, ±3 MiB between boots | MEASURED | `okf/must-read/touching-rigs.md` § "Card memory" |
| card bucket law | `total = reserved + used + free`; take the term from `free`, never `total − reserve` | MEASURED rule | `okf/must-read/touching-rigs.md` §§ "Card memory", "Spending the card" |
| `M_total(srv1)` | 15.0 GB | MEASURED | `scans/srv1.json` `memory.total_gb` (`/proc/meminfo MemTotal`) |
| `M_avail_idle(srv1)` | 14.2 GB (scan) / 14.19 GiB (re-confirmed idle) | MEASURED | `scans/srv1.json`; `records/measurements/ram-headroom-2026-09-09/README.md` § "Does a model wait on RAM?" |
| `M_total(srv2)` | 46.0 GB | MEASURED | `scans/srv2.json` `memory.total_gb` |
| `M_avail_idle(srv2)` | 44.6 GB (scan) / 44.5 GiB (re-confirmed idle) | MEASURED | `scans/srv2.json`; `ram-headroom-2026-09-09/README.md` § "Does a model wait on RAM?" |
| `swap(h)` | 8 GiB, both rigs | MEASURED | `okf/must-read/touching-rigs.md` § "Host RAM"; `ram-headroom-2026-09-09/README.md` § "`--load-mode none` allocates Shmem" |
| `BW_read(srv1)` | 40.3 GB/s (pure sequential read) | MEASURED 2026-09-01 | `okf/must-read/touching-rigs.md` § "Host memory bandwidth" |
| `BW_read(srv2)` | 27.9 GB/s | MEASURED 2026-09-01 | same |
| `cores(srv1)` | 6c/6t; bandwidth linear at ~6.7 GB/s per core, never saturates | MEASURED | `scans/srv1.json`; `okf/must-read/touching-rigs.md` § "srv1's thread scaling" |
| `cores(srv2)` | 10c/20t; memory term saturates at 10 threads | MEASURED | `scans/srv2.json`; `okf/must-read/touching-rigs.md` § "srv2 saturates at 10 threads" |
| srv1 hard-lock hazard | locks under CPU expert offload; not fixed, not bounded | MEASURED (3 locks 2026-09-01) | `okf/must-read/touching-rigs.md` § "srv1 hard-locks under CPU expert offload" |

---

## 2. Card-side terms (the VRAM law)

| symbol | value | kind | citation |
|---|---|---|---|
| `W_ne(m)` | non-expert weight bytes, from the tensor table | MEASURED per model | `src/mcgyvr/serving/vramfit.py` (`explain`), `geometry["bytes_nonexpert"]` |
| `E(m)` | total expert bytes | MEASURED per model | `geometry["bytes_experts"]` |
| `e_b(m,b)` | per-block expert bytes; **bimodal**, never averaged (Qwen3.6 IQ3_XXS: 262.0 MiB on 37 blocks, 300.0 MiB on 3) | MEASURED | `src/mcgyvr/serving/vramfit.py-40` (module docstring) |
| `E_on(m,n)` | expert bytes on card at `--n-cpu-moe n`; `n` is a **block index**, not a count | MEASURED law | `src/mcgyvr/serving/vramfit.py` |
| `--n-cpu-moe` saturation | saturates at the layer count (ncmoe 99 ≡ ncmoe 40 on a 40-layer model, byte-identical) | MEASURED | `okf/must-read/touching-rigs.md` § "What a context costs" |
| KV offload | **neither engine ever offloads KV** | MEASURED | `okf/must-read/touching-rigs.md` § "What a context costs" |
| `KV(m, ctx, w)` | per layer, over the layers the header declares as caching | MEASURED law | `src/mcgyvr/serving/vramfit.py` (`kv_bytes`) |
| `CACHE_ELEM_BYTES` | f32 4.0, f16/bf16 2.0, q8_0 34/32 B per element | MEASURED (192.00 MiB f16 → 102.00 MiB) | `src/mcgyvr/serving/vramfit.py` |
| Qwen3.6 / KAT cache width | 20.2 KiB/token measured (10 of 40 layers cache, `full_attention_interval = 4`) — **not** the 80 KiB the layer count predicts | MEASURED | `okf/must-read/touching-rigs.md` § "What a context costs" |
| Qwen3-Coder-30B cache width | 96.2 KiB/token measured vs 96.0 predicted | MEASURED | same |
| deepseek2 cache | 4320 MiB at `-c 16384 -np 8` (a 2 KiB/token scalar law says 864) | MEASURED | `okf/must-read/touching-rigs.md` § "What a context costs"; `records/evidence/2026-09-05-context-decomposition/srv2-deepseek-coder-v2-16b/c16384-r1.log` |
| undeclared SWA split | **refused, never guessed** | MEASURED rule (wrong for 2 of 3 split checkpoints) | `src/mcgyvr/serving/vramfit.py` (`kv_bytes` raises) |
| `SWA_PAD` | 256 | MEASURED | `src/mcgyvr/serving/vramfit.py` |
| `ctx_per_slot` padding | llama.cpp pads per-sequence ctx **up** to ×256 and rewrites the total | MEASURED (`-c 8000 -np 8` → 8192; `-c 8200` → 10240) | `src/mcgyvr/serving/vramfit.py` (`context_per_sequence`) |
| `RS(m, w)` | recurrent state: SSM `S` + conv `R`, charged **per sequence** | MEASURED law | `src/mcgyvr/serving/vramfit.py` (`rs_bytes`) |
| Qwen3.6 per-slot state | 30 linear layers × 4096 × 128 × 4 B = 2 MiB each = **60 MiB per `-np` slot** | MEASURED across np 1/4/8 | `okf/must-read/touching-rigs.md` § "The non-caching layers charge per slot" |
| `A` (`SCRATCH_AND_CONTEXT_MIB`) | **768 MiB** — a bound, deliberately generous, only walked down from | CONSTANT bounding a MEASURED range 255–521 MiB at `-ub 256` over 2 rigs × 4 checkpoints | `src/mcgyvr/serving/vramfit.py` |
| `A_measured` | deepseek2 259.5, gptoss 302.1, qwen35moe 302.7, nemotron_h_moe 521.2 MiB | MEASURED | `src/mcgyvr/serving/vramfit.py` (`MEASURED_SCRATCH_MIB`) |
| CUDA primary context (llama.cpp) | 85–147 MiB (**not** 1.0 GB) | MEASURED | `okf/must-read/touching-rigs.md` § "Derive the floor" |
| unnamed device remainder | 144.67 MiB srv2 / 97.69 MiB srv1, net of idle | MEASURED, per rig | `src/mcgyvr/serving/vramfit.py-40` |
| law accuracy | predicted 5347.2 MiB against measured 5306 MiB — **41 MiB** (srv1, 2026-09-06, n=1) | MEASURED | `src/mcgyvr/serving/vramfit.py` (`Placement` docstring) |
| `MAX_WIDTH` | 32 slots (widest anyone measured, #366) | CONSTANT | `src/mcgyvr/serving/__init__.py` |
| `DEFAULT_UBATCH` | 512 (`-ub`/`-b` on the argv, the value the cache law was sized at) | CONSTANT | `src/mcgyvr/serving/__init__.py` |
| `VLLM_DEFAULT_SEQS` | 8 | CONSTANT | `src/mcgyvr/serving/__init__.py` |
| vLLM card sizing | `--gpu-memory-utilization`, per rig, never inherited; the cache law is **not** consulted | CONSTANT rule | `src/mcgyvr/serving/__init__.py-202`; live values `~/.mcgyvr/config/mcgyvr.yaml` `serve_args` |

---

## 3. Host-RAM terms

| symbol | value | kind | citation |
|---|---|---|---|
| `B(m)` | blob bytes (`spec.disk_gb`, from the scan, never the header) | MEASURED per model | `src/mcgyvr/serving/__init__.py` |
| `R_spill(m,n)` | `E(m) − E_on(m,n)` + `RUNTIME_RESIDENT_GB` | MEASURED law | `src/mcgyvr/serving/__init__.py` (`_host_gb`) |
| `RUNTIME_RESIDENT_GB` | **1.53 GiB** — flat (1.52–1.53) across six `--n-cpu-moe` cells, 4 to 20 blocks | MEASURED, so an intercept not a rate | `src/mcgyvr/serving/__init__.py`; `records/measurements/serving-sweep-2026-08-25/` |
| ~~`RAM_HEADROOM_GB`~~ | **SPLIT 2026-09-09.** One constant priced two gates that compare different things and fail differently, so it is now two | — | superseded by the two rows below |
| `MODE_RAM_HEADROOM_GB` | **0.5 GiB** — the mode gate (map, or `--load-mode none`), weighed against the **blob**. Swept flat from +2.0 to +0.5; below zero the cost is a bounded wake (+19% on srv1's Qwen3.6) and decode never moves. 2.0 was ~4× too large for this gate | MEASURED | `src/mcgyvr/serving/__init__.py`; `records/measurements/ram-headroom-2026-09-09/` |
| `REFUSAL_RAM_HEADROOM_GB` | **2.0 GiB** — the refusal gate (launch, or refuse), weighed against the **spilled experts**. Kept, now for measured reasons: flat to +0.55 GiB then a cliff (385 s wake, 2.3 M faults, decode at 32%), the cliff sits in the unmeasured 1.5 GiB below that, and the failure is silent | MEASURED | `src/mcgyvr/serving/__init__.py`; `records/measurements/ram-headroom-2026-09-09/` |
| `h_mode` (this document's symbol for the mode gate, vs the **blob**) | **0.5 GiB**, and no longer a recommendation — it is `MODE_RAM_HEADROOM_GB` above. This row read "2.0 → 0.5 recommended" until the split landed on 2026-09-09 | MEASURED: flat +2.0 → +0.5 on 3 models × 2 rigs | `formulas.md` G-mode; `src/mcgyvr/serving/__init__.py`; `ram-headroom-2026-09-09/README.md` § "What it settles" (1) |
| `h_refuse` (this document's symbol for the refusal gate, vs the **experts**) | **2.0 GiB** — `REFUSAL_RAM_HEADROOM_GB` above. The value did not move; what moved is that 2.0 is now a number about the experts alone, where before it was one number standing for two gates | MEASURED: flat to +0.55, cliff by −0.97 | `formulas.md` G-refuse; `src/mcgyvr/serving/__init__.py`; `ram-headroom-2026-09-09/README.md` § "What it settles" (3) |
| where the cliff is | **UNMEASURED** — somewhere in the 1.5 GiB between +0.55 and −0.97 GiB of clearance vs the experts; no point in between | UNMEASURED | `ram-headroom-2026-09-09/README.md` § "Three reasons the refusal gate keeps 2.0" |
| mapped footprint | blob in page cache, kernel-reclaimable: RAM used 1.6 GiB, avail 13.4 GiB (srv1 Qwen) | MEASURED | `records/measurements/load-mode-2026-09-08/README.md` § "What is not a null" |
| unmapped footprint | anonymous `Shmem`, not reclaimable: RAM used 9.8 GiB, avail 5.2 GiB (same unit) | MEASURED | same |
| unmapped `Shmem` is swappable | 8.09 GiB of `Shmem`, `/dev/shm` at 100K, no tmpfs; both rigs run 8 GiB swap | MEASURED 2026-09-09 | `ram-headroom-2026-09-09/README.md` § "`--load-mode none` allocates Shmem"; `okf/must-read/touching-rigs.md` § "Host RAM" |
| mapped page-cache cost | 35,000–48,000 pages swapped **out** per wake (0 unmapped), 5,651–7,991 back in, at `vm.swappiness=60` | MEASURED | `ram-headroom-2026-09-09/README.md` § 2a |
| RAM release on teardown | a **step, not a curve**: 8.09 GiB back in <1 s at container exit, settled 2 s later | MEASURED (1 s sampling) | `ram-headroom-2026-09-09/README.md` § "Does a model wait on RAM?"; `srv1-release.txt` |
| VRAM release on teardown | srv2 card 11,853 MiB → 1 MiB across two container exits | MEASURED | same; `srv2-release.txt` |
| sum of host RAM across co-resident units | **MODELLED since 2026-09-09, and still unmeasured as a law.** `Fit` carries `ram_gb` — the blob when mapped, the spilled experts when unmapped, zero when nothing spills — and `hold_together` sums the hungriest alternative at each port across the host's ports, applying `REFUSAL_RAM_HEADROOM_GB` **once** to the total against the recorded scan. Nothing on this fleet has ever run two llama.cpp MoE units co-resident, so the law is declared, not measured (G2) | DECLARED law over MEASURED parts | `src/mcgyvr/serving/__init__.py` (`hold_together`) |
| VRAM cost of the loading mode | **UNMEASURED magnitude.** Observed as a hard failure: srv2's 80B crash-loops under `--load-mode none` at ~83 s on `CUDA error: the resource allocation failed`, with `Shmem` at 25.2 GiB and 18 GiB host RAM spare — a *card* failure. `fit` decides the mode from host RAM alone | UNMEASURED (gap) | `ram-headroom-2026-09-09/README.md` § "`--load-mode none` is not available to srv2's 80B at all"; `80b-unmapped-crash.txt`; `src/mcgyvr/serving/__init__.py-508` |
| `MemAvailable` is decision-dependent | reads 13.4 GiB mapped, 5.2 GiB unmapped, for the same unit | MEASURED hazard | `load-mode-2026-09-08/README.md` § "A hazard this turned up" |

---

## 4. The fleet's models

| model | host | `B` blob | `E` experts on host at the live/emitted placement | card figure | kind | citation |
|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-IQ3_XXS | srv1 | 12.30 GiB (`size_bytes` 13,211,155,424) | 9.2 GiB spilled at the live placement; `bytes_experts` 11,108,614,144 (10.35 GiB) total; `bytes_nonexpert` 2,091,551,232 | 40 placeable blocks, 10 caching layers | MEASURED | `~/.mcgyvr/config/Qwen3.6-35B-A3B-UD-IQ3_XXS.geometry.json`; `ram-headroom-2026-09-09/README.md` § "The two gates fail differently" |
| deepseek-coder-v2-16b | srv1 | 8.29 GiB | — | refused at Qwen's window (wants 5854 MiB of 6127 free at 2 slots); fits at 4096/slot | MEASURED | `ram-headroom-2026-09-09/README.md` § "Hazards this campaign paid for"; `deepseek.geometry.json` |
| KAT-Coder-V2.5-Dev Q3_K_M 35.5B/A3B | srv1 | 16.90 GiB — **overflows 15 GB** | 11.8 GiB experts | `--n-cpu-moe 32` | MEASURED | `records/measurements/wake-2026-09-08/README.md`; `ram-headroom-2026-09-09/README.md` § "For every model this fleet actually runs" |
| Qwen3-Next-80B-A3B Q3_K_M | srv2 | 35.67 GiB | 34.31 GiB experts over 48 layers; 26.6 GiB spilled at ncmoe 35 | 11,960 MiB at `--n-cpu-moe 35`; ~11,228 MiB at 36 | MEASURED | `records/measurements/vllm-sleep-2026-09-09/README.md` § "The 551 MiB that decides it`"; `ram-headroom-2026-09-09/README.md` |
| one 80B expert block | srv2 | — | **0.715 GiB** (34.31 GiB / 48) = 732 MiB of card per block | — | MEASURED/derived | `vllm-sleep-2026-09-09/README.md` § "The 551 MiB that decides it" |
| Qwen2.5-Coder-3B-Instruct-AWQ | srv2 | 1.95 GiB declared | — | declared `vram_gb` 3.49; **measured awake 3,810 MiB** | MEASURED | `~/.mcgyvr/config/mcgyvr.yaml` `models:`; `vllm-sleep-2026-09-09/vllm-sleep-results.json` `baseline-both-serving.procs` |
| Qwen2.5-Coder-7B-Instruct-AWQ | srv2 | 4.93 GiB declared | — | declared `vram_gb` 7.12; **measured awake 6,816 MiB** | MEASURED | same |

---

## 5. Cold wake (container down → first HTTP 200)

All timed from the container's own `docker inspect` `StartedAt` (UTC — `time.mktime` adds the local offset and prints a three-hour wake).
→ `ram-headroom-2026-09-09/README.md` § "Hazards this campaign paid for"

| unit / condition | `T_wake` | n | kind | citation |
|---|---|---|---|---|
| srv1 Qwen3.6, mapped, clearance vs blob **+1.93 GiB** | **140.8 s** (141.1 / 141.3 / 140.0) | 3, alternating | MEASURED | `ram-headroom-2026-09-09/README.md` § "The sweep" |
| srv1 Qwen3.6, mapped, **+0.52** | 139.9 s | 1 | MEASURED | same |
| srv1 Qwen3.6, mapped, **−0.98** | **167.9 s** (170.4 / 166.8 / 166.5) | 3, alternating | MEASURED | same |
| srv1 Qwen3.6, **unmapped**, `swappiness=60` | **132.9 s** (134.8 / 132.3 / 131.6) | 3 | MEASURED | `ram-headroom-2026-09-09/README.md` § 2a |
| srv1 Qwen3.6, mapped, same campaign | **139.6 s** (139.5 / 139.9 / 139.4) | 3 | MEASURED | same |
| srv1 deepseek-16b, +1.93 / +0.50 / −0.98 | 85.7 / 94.9 / 116.3 s | 1 each | MEASURED | `ram-headroom-2026-09-09/README.md` § "The sweep" |
| srv2 80B, +2.02 / +0.48 / −0.84 | 102.9 / 103.7 / 108.0 s | 1 each | MEASURED | same |
| srv1 Qwen3.6, `-c 8192` (2 slots × 4096) | 50–80 s | 2 restarts | MEASURED 2026-09-08 | `records/measurements/wake-2026-09-08/README.md` |
| srv1 Qwen3.6, `-c 16384` (the live config) | **128 s** | 1 | MEASURED | same |
| srv1 KAT (blob overflows RAM by ~2.7 GiB) | **203 s** ← fleet worst | 1 | MEASURED | same |
| srv2 7B-AWQ vLLM **alone** on an empty card | **82 s** | 1 | MEASURED | same |
| srv2 80B llama.cpp | **97 s** | 1 | MEASURED | same |
| srv2 80B at ncmoe 36, into a card left by two L2 sleepers | **100 s** | 1 | MEASURED | `vllm-sleep-2026-09-09/README.md` |
| srv2 vLLM **pair** container restart (`depends_on`, sequential) | **168 s** | 3 | MEASURED 2026-09-09 | `vllm-sleep-2026-09-09/README.md` § "Sleep and wake are sub-second" |
| srv2 vLLM pair, first measurement | 110–120 s | 1 | MEASURED 2026-09-08 | `records/plans/sleep-wake.md` §6 |
| srv1 Qwen3.6, **experts** clearance −0.97 GiB (the cliff) | **385.3 s** | 1 | MEASURED | `ram-headroom-2026-09-09/README.md` § "The two gates fail differently" |
| context widening cost | doubling `-c` cost **+48 s** of wake and one expert block (ncmoe 29 → 30) | 1 | MEASURED | `wake-2026-09-08/README.md`; `~/.mcgyvr/config/mcgyvr.yaml` `srv1_llamacpp.context_window` |
| wake predictor | **RAM headroom, not model size, not parameter count, not engine** | MEASURED finding | `okf/must-read/touching-rigs.md` § "Wake time tracks RAM headroom"; `wake-2026-09-08/README.md` |
| `pgmajfault` at wake | ≈9,180 (+1.9) vs ≈12,150 (−1.0), reproducible to within 1% — a better instrument than the clock | MEASURED | `ram-headroom-2026-09-09/README.md` § "The sweep" |
| rig drift | within-arm spread ≤2.3%; rig moved 5% between paired arms | MEASURED | `ram-headroom-2026-09-09/README.md`; `load-mode-2026-09-08/README.md` |
| wake into a partially-occupied card, llama.cpp | **UNMEASURED except one point** (the 80B at ncmoe 36 into 11,409 MiB, 100 s) | UNMEASURED | `vllm-sleep-2026-09-09/README.md` |

---

## 6. vLLM sleep / wake (`--enable-sleep-mode` + `VLLM_SERVER_DEV_MODE=1`)

Not reachable on the live ladder: without those flags `/sleep`, `/wake_up`, `/is_sleeping` are 404.
All rows n=1. → `records/measurements/vllm-sleep-2026-09-09/README.md`, `vllm-sleep-results.json`

| symbol | value | kind | citation |
|---|---|---|---|
| `T_sleep_L1(3B)` / `T_wake_L1(3B)` | 1.39 s / 0.41 s | MEASURED n=1 | `vllm-sleep-results.json` `L1-3B-asleep`, `L1-3B-awake` |
| `T_sleep_L1(7B)` / `T_wake_L1(7B)` | 3.99 s / 0.79 s | MEASURED n=1 | `L1-7B-asleep`, `L1-7B-awake` |
| `T_sleep_L2(3B)` / `T_wake_L2(3B)` | 0.25 s / 0.24 s | MEASURED n=1 | `L2-3B-asleep`, `L2-3B-awake` |
| `T_sleep_L2(7B)` / `T_wake_L2(7B)` | 0.30 s / 0.31 s | MEASURED n=1 | `L2-7B-asleep`, `L2-7B-awake` |
| `V_awake(3B)` | 3,810 MiB | MEASURED (per-process `nvidia-smi`) | `baseline-both-serving.procs` (pid 840372) |
| `V_awake(7B)` | 6,816 MiB | MEASURED | same (pid 838861) |
| `V_resid(3B)` asleep, either level | **228 MiB** (its CUDA context) | MEASURED | `L1-3B-asleep.procs`, `L2-3B-asleep.procs` |
| `V_resid(7B)` asleep, either level | **234 MiB** | MEASURED | `L1-7B-asleep.procs`, `L2-7B-asleep.procs` |
| `V_released(3B)` | 3,810 − 228 = **3,582 MiB** | derived from MEASURED | same |
| `V_released(7B)` | 6,816 − 234 = **6,582 MiB** | derived from MEASURED | same |
| card with **both** L2-asleep | **503 MiB used, 11,409 MiB free** | MEASURED | `L2-both-asleep` |
| `V_resid` release requires process exit | a sleeping vLLM gives back weights and KV pool, **never its CUDA context** | MEASURED | `vllm-sleep-2026-09-09/README.md` § "The 551 MiB that decides it" |
| L1 host-RAM retention | `MemAvailable` 39.18 → 36.06 GiB (3B) and 36.06 → 25.74 (7B); **stays down after the wake**; 13.46 GiB gone with both units awake and serving | MEASURED | `README.md` § "Level 1 never gives the host RAM back"; `L1-*` rows |
| L2 host-RAM cost | **none** (25.72–25.73 GiB throughout) | MEASURED | `L2-*` rows |
| L1 vs L2 verdict | L2 is strictly better here — faster, same VRAM, no RAM cost. **L1 should be refused rather than offered** | MEASURED ruling | `README.md` § "Sleep and wake are sub-second" |
| sleep/wake vs restart | ~**500×** faster than a 168 s container restart of the same pair | derived from MEASURED | same |
| wake into a full card | HTTP 500 in **395 ms**, named CUDA OOM; unit stays asleep, co-resident keeps serving, card never moves | MEASURED n=1 | `README.md` § "Waking into a full card fails well" |
| the health-probe trap | a sleeping unit answers `GET /v1/models` **200** and then **hangs** on `POST /v1/chat/completions` (no response in 60 s). Liveness must consult `/is_sleeping` | MEASURED | `README.md` § "A sleeping unit passes a health check and then hangs" |
| llama.cpp sleep | **no mechanism.** A llama.cpp unit leaves the card only by container exit | MEASURED (absence) | `vllm-sleep-2026-09-09/README.md`; `records/plans/sleep-wake.md` §10 |

---

## 7. Throughput and width

| symbol | value | kind | citation |
|---|---|---|---|
| `λ(3B, w)` per stream | 115.85 / 113.39 / 113.38 / 109.61 / 82.59 tok/s at w = 1/2/4/8/16 | MEASURED 2026-09-06 | `records/measurements/serving-concurrency-2026-09-06/README.md` |
| `Λ(3B, w)` aggregate | 115.80 / 226.29 / 452.28 / 873.59 / 900.67 tok/s | MEASURED | same |
| `λ(7B, w)` per stream | 64.64 / 64.46 / 63.51 / 61.28 / 46.34 tok/s | MEASURED | same |
| `Λ(7B, w)` aggregate | 64.62 / 128.70 / 253.78 / 489.18 / 499.50 tok/s | MEASURED | same |
| `λ(srv1 Qwen3.6, w)` per stream | 27.23 / 13.99 / 7.83 / 5.09 tok/s at w = 1/2/4/8 | MEASURED | same |
| `Λ(srv1 Qwen3.6, w)` aggregate | 27.22 / 27.93 / 31.27 / 40.71 tok/s | MEASURED | same |
| vLLM width scaling | near-linear to `--max-num-seqs`; per-stream cost 5.4% (3B) and 5.2% (7B) at w=8; plateaus past it (queueing, not refusal) | MEASURED | same |
| llama.cpp + CPU offload width scaling | width 8 buys **50% aggregate for a fifth of per-stream**; expert GEMM is memory-bound and concurrent streams activate different experts | MEASURED | same |
| srv1 effective width | **2**, not 8 (width 4 puts a 1024-token reply at 131 s, past the timeout) | MEASURED ruling | same; `~/.mcgyvr/config/mcgyvr.yaml` `local_qwen3.6-35b-a3b.max_parallel` |
| srv1 top-rung live rate | median **17.0 tok/s** over 82 journalled replies, p90/p95 at the cap | MEASURED 2026-09-08 | `~/.mcgyvr/config/mcgyvr.yaml` `output_tokens` comment |
| srv1 cold-stream rate | **1.37 tok/s** cold against 27.2 warm (page cache refilling) | MEASURED n=1 | `serving-concurrency-2026-09-06/README.md` |
| decode under the RAM cliff | **10.78 tok/s vs 33.26 baseline (−68%)**, 2.3 M major faults, 2.2 M pages swapped out | MEASURED n=1 | `ram-headroom-2026-09-09/README.md` § "The two gates fail differently" |
| decode vs mode-gate clearance | **never moved** at any clearance on any of three models (all spreads inside 5% rig drift) | MEASURED, 9 arms | `ram-headroom-2026-09-09/README.md` § "What it settles" (2) |
| `--n-cpu-moe` floor value | correcting an over-high offload is worth ~**2.4×** throughput (srv2, ncmoe 24 → 6: 28.6 → 43.4 tok/s n=1, 34.8 → 69.3 n=4) | MEASURED | `okf/must-read/touching-rigs.md` § "Spending the card" |
| `--n-cpu-moe` semantics | a **semantic** key: ncmoe 0 vs 99 flipped 9 of 257 verdicts against a 0-flip own null. Quote a floor for fit and speed only | MEASURED (ADR-0041, 2026-09-02) | `okf/must-read/touching-rigs.md` § "Spending the card" |
| launch near the memory edge | a **1-in-3 coin flip**; retry any refusal three times | MEASURED rule | `okf/must-read/touching-rigs.md` § "The refusal is the measurement" |
| `q(r)` rung quality gain | rungs are cheapest-first; a lower rung is kept only if ≥ `MIN_QUALITY_GAIN` = **0.03** below the one above; dominance does **not** rank on speed | CONSTANT | `src/mcgyvr/propose.py`, `:40-43`; `src/mcgyvr/config.py-389` |

---

## 8. Pressure and the control loop

| symbol | value | kind | citation |
|---|---|---|---|
| `busy(b)` | locked slot files of bound `b`, **host-wide, cross-process** | MEASURED at runtime | `src/mcgyvr/capacity.py` (`_acquire_slot` sweep); `records/plans/sleep-wake.md` §7.2 |
| `waiting(b)` | threads of **this process** blocked on `b` | design counter, per-process | `records/plans/sleep-wake.md` §7.2 |
| `in_use` / `in_flight` / `load` | per-process only, **not shared** | CONSTANT (code) | `src/mcgyvr/capacity.py`, `:917`, `:936` |
| `limit(b)` | the enforced width of bound `b`; a bound is a source, or a rung that declared its own width | CONSTANT (code) | `src/mcgyvr/capacity.py` (`_bound`) |
| `demand(b)` | `busy(b) + waiting(b)` — a **deliberate lower bound**: `busy` is shared, `waiting` is not | design | `records/plans/sleep-wake.md` §7.2 |
| `pressure(b)` | `demand(b) / limit(b)` | design | same |
| `_POLL_SECONDS` | 0.02 s (the whole penalty of a census race) | CONSTANT | `src/mcgyvr/capacity.py` |
| `WAKE_RATIO` | 2.0 | PROPOSED (N1) | `records/plans/sleep-wake.md` §7.3, §16 |
| `WAKE_SUSTAIN_S` | 45 s — anchored to 3B ~9 s and srv1 ~73 s service times | PROPOSED (N2), anchored to MEASURED rates | same |
| `SLEEP_IDLE_S` | 600 s | PROPOSED (N3) | §7.6, §16 |
| `MIN_UPTIME_S` | 900 s | PROPOSED (N4) | same |
| `COOLDOWN_S` | 600 s, either direction, exempt for the refusal-driven wake | PROPOSED (N5) | same |
| `budgets.wake_timeout_s` | **480.0 s** — validated against the 203 s worst mapped wake (2.4×), above the door's 360 s health budget | CONSTANT, MEASURED-validated (N7) | `records/measurements/wake-2026-09-08/README.md`; `records/plans/sleep-wake.md` §16 |
| `wake_timeout_s` is the wrong shape | one budget spans **0.24 s** (vLLM L2 wake), **0.40 s** (named OOM refusal), **100 s** (80B behind sleepers), **385 s** (squeezed unmapped srv1) | MEASURED (gap) | `vllm-sleep-2026-09-09/README.md` § "What this changes"; `ram-headroom-2026-09-09/README.md` |
| `budgets.request_timeout_s` | 180 s (live), default 120 | CONSTANT | `~/.mcgyvr/config/mcgyvr.yaml` `budgets` |
| `budgets.task_timeout_s` | 900 s (live) | CONSTANT | same |
| `budgets.max_escalations` | 2 | CONSTANT | same |
| `output_tokens` (srv1 rung) | 2048 | MEASURED-argued | same |
| `ladder.fanout` | `idle` (live). A woken card gets no work under `none` until something escalates onto it | CONSTANT | `~/.mcgyvr/config/mcgyvr.yaml`; `src/mcgyvr/config.py-416`; `records/plans/sleep-wake.md` §7.1 |
| clocks | `<host-stem>.wake` (flock; mtime = last transition), `<host-stem>.used` (mtime = last dispatch), `<host-stem>.<n>.slot` | design, in `/tmp/mcgyvr-capacity-<uid>/` | `records/plans/sleep-wake.md` §9; `src/mcgyvr/capacity.py`, `:264` |
| rig lease | `~/.mcgyvr/lease` **on the rig** — the only lock two machines can both see | CONSTANT | `src/mcgyvr/serving/gatelib.py-361`; `records/plans/sleep-wake.md` §9 |
| drain bound | `budgets.request_timeout_s`; eviction takes every slot of the card, then downs it, then releases | design | `records/plans/sleep-wake.md` §10 |
| arrival rate / queue model | **UNMEASURED.** No record holds a work-arrival distribution. Would come from the journal (`~/.local/state/mcgyvr/journal`) once rows carry dispatch timestamps per rung | UNMEASURED | `~/.mcgyvr/config/mcgyvr.yaml` `journal.dir` |
| learning-loop coefficients | **UNMEASURED, all of them.** Nothing in the tree fits `T_wake`, `λ`, or `C` online today | UNMEASURED | — |

---

## 9. Gates as they exist today (what a shape must clear)

> **Superseded, 2026-09-09.** This section, and gaps G11a and G11b below, were
> written before the covering landed on `red/sleep-wake`. Three things in them
> are now false: the discriminator is **card contention**, not the port; a host
> mixing alternatives with co-residents is **emitted as a covering**, not
> refused; and `launch_specs` returns a **covering by anchor-maximal feasible
> sets**, not a partition. The current statements are the `alternate`,
> `launch_specs` and `hold_together` docstrings in `src/mcgyvr/serving/`, which
> are maintained with the code. Read this section for the shape of the argument
> and not for what the code does.


| gate | compares | citation |
|---|---|---|
| geometry required for MoE | a MoE spec with no geometry is refused | `src/mcgyvr/serving/__init__.py` |
| disk | `spec.disk_gb > scan.disk.free_gb` | `src/mcgyvr/serving/__init__.py` |
| card / offload floor | `vramfit.floor` walks blocks off the tensor table; `None` ⇒ the card cannot hold `C` alone | `src/mcgyvr/serving/vramfit.py`; `src/mcgyvr/serving/__init__.py` |
| mode gate | `placed.ram_gb and spec.disk_gb + MODE_RAM_HEADROOM_GB > available_ram` ⇒ `--load-mode none` | `src/mcgyvr/serving/__init__.py` |
| refusal gate | `placed.ram_gb + REFUSAL_RAM_HEADROOM_GB > available_ram` ⇒ refuse | `src/mcgyvr/serving/__init__.py` |
| scalar card gate | `placed.vram_gb + DEFAULT_HEADROOM_GB > free_vram` (non-geometry specs only) | `src/mcgyvr/serving/__init__.py` |
| co-residency, card | the **largest alternative at each port, summed across the host's ports**, against free VRAM, **no headroom on top** (it is inside each figure). Verified srv2 2026-09-05: 7.12 + 3.49 on 11.63 free, 1.0 GiB to spare. Was `sum(unit.fit.vram_gb)` over every unit on the host until `d8c5cf0a`, which priced a contention that cannot happen — srv1's two alternatives at 11.83 GiB against 6.00 free | `src/mcgyvr/serving/__init__.py` (`hold_together`) |
| co-residency, host memory | the **hungriest alternative at each port, summed across the host's ports**, plus `REFUSAL_RAM_HEADROOM_GB` **once on the total**, against the recorded scan's `MemAvailable`. Two maxima and not one: the pairing that fills the card need not be the pairing that fills the memory. Each unit contributes `Fit.ram_gb`, so the sum must run *after* the loading modes are picked. A host the scan has no memory reading for is skipped rather than guessed at. New on 2026-09-09; before it a 15 GB host was emitted a file asking for 26 | `src/mcgyvr/serving/__init__.py` (`hold_together`); owner's ruling, RAM per host and VRAM per card |
| launch-spec cut | a host whose units come up together is one `compose.<host>.yml`; a host whose units take turns on one port is one `compose.<host>.<model>.yml` **each**. A host carrying both is refused by name | `src/mcgyvr/serving/__init__.py` (`launch_specs`); `src/mcgyvr/emit.py` (`_planned`); commit `d8c5cf0a` |
| the card the placement is computed against | **always the idle card.** Funding a unit from sleeping co-residents needs the placement computed against what the sleepers leave — a number only the runtime knows | `vllm-sleep-2026-09-09/README.md` § "The 551 MiB that decides it" |
| `emit --check` | re-emits and diffs; exits 4 on config/rig drift | memory: "emit --check catches config/rig drift" |

---

## 10. Known gaps carried forward, not papered over

| # | gap | citation |
|---|---|---|
| G1 | The loading mode has a **VRAM** cost `fit` does not model; `fit` picks the mode from host RAM alone. srv2's 80B crash-loops unmapped with 18 GiB host RAM spare. Deliberately still unmodelled after the 2026-09-09 split: the evidence is n=1 at an unknown margin, and no honest coefficient comes out of one crash, so the gap is named in `MODE_RAM_HEADROOM_GB`'s own comment rather than papered over with a guess | `src/mcgyvr/serving/__init__.py-508`, `:159`; `ram-headroom-2026-09-09/README.md` |
| ~~G2~~ | **PARTLY RESOLVED 2026-09-09.** `hold_together` now sums host RAM per host beside VRAM per card — hungriest alternative per port, across ports, one headroom on the total, against the recorded scan and never a live read. What remains is not the sum but its law: nothing on this fleet has run two llama.cpp MoE units co-resident, and two geometry-sized MoE units can never reach the RAM sum at all, because `_placement` fills the card and the VRAM sum refuses them first. The case that arrives is a host whose card figures are *declared* — srv2's vLLM pair. The sum is also not symmetric: an unmapped shortfall is the silent decode cliff, a mapped one a bounded wake, and it refuses both | `src/mcgyvr/serving/__init__.py` (`hold_together`), `:353-365` (`Fit.ram_gb`) |
| G3 | `wake_timeout_s` is a **single fleet constant** covering wakes from 0.24 s to 385 s | `vllm-sleep-2026-09-09/README.md`; §5 above |
| G4 | The **refusal-gate cliff location** is unmeasured (between +0.55 and −0.97 GiB vs the experts) | `ram-headroom-2026-09-09/README.md` |
| G5 | A **sleeping co-resident's residual VRAM** is not modelled anywhere in `fit`/`emit` | `vllm-sleep-2026-09-09/README.md` |
| G6 | `MemAvailable` is **decision-dependent** and `emit` reads a *recorded* scan, so a scan taken while a unit serves unmapped would refuse the model that is running | `load-mode-2026-09-08/README.md` |
| G7 | The KAT "cleared bare `MemAvailable` by 0.4 GiB … 203 s" figure that once defended `RAM_HEADROOM_GB` **appears nowhere under `records/`** as a mapping-gate datum — the 0.4 GiB is a refusal-gate number and the 203 s is a mode-gate one. Corrected in the source on this branch, and the comment carrying the correction now sits on `MODE_RAM_HEADROOM_GB`, which is the gate the 203 s actually belongs to; recorded here so the correction is not re-inherited | `ram-headroom-2026-09-09/README.md` § "A claim in the source that the records do not support"; `src/mcgyvr/serving/__init__.py` |
| G8 | The refusal gate **cannot be measured on srv2** with this fleet's models: it governs unmapped units, vLLM has no loading mode, and the 80B will not run in one | `ram-headroom-2026-09-09/README.md` |
| G9 | Two models alternating on one port **cannot share a teardown**; `serve down` names one container | `ram-headroom-2026-09-09/README.md` § "Hazards"; `tests/test_two_models_on_one_url_are_alternatives.py` |
| G10 | srv1's two alternatives **cannot share a window**: `emit` refuses deepseek at Qwen's 8192 (5854 MiB wanted of 6127 free at 2 slots); it fits at 4096 | `ram-headroom-2026-09-09/README.md` § "Hazards" |
| ~~G11~~ | **RESOLVED by `d8c5cf0a`** for the shape it named. `emit` no longer writes one static compose file per host: `serving.launch_specs` cuts a host whose units take turns on a port into one `compose.<host>.<model>.yml` per alternative, so such a host holds exactly the second spec G11 said did not exist, and `hold_together` stopped summing alternatives against a card only one of them is ever on. Nothing on disk moved for a host of co-residents, which is both live rigs | commit `d8c5cf0a`; `src/mcgyvr/serving/__init__.py`; `records/plans/sleep-wake.md` §2, §7.5, §10, §17 |
| G11a *(superseded — see §9)* | **What G11's resolution does not reach: the discriminator is the port, not card contention.** Two units are alternatives here iff they name one host and one port. That is srv1 — deepseek and Qwen3.6 both on `:8080`. It is **not** srv2, whose vLLM pair answers on `:8001`/`:8002` and whose 80B answers on `:8003`: those three alternate because they contend for the **card**, and no port collides, so `launch_specs` reads them as three co-residents and `hold_together` prices a sum the card cannot hold. The limitation is stated in the source rather than left to be rediscovered — "port is a proxy and not the fact" — and card contention is named there as the discriminator this controller will need | `src/mcgyvr/serving/__init__.py` (`alternatives` docstring); `records/measurements/vllm-sleep-2026-09-09/README.md`; `records/plans/sleep-wake.md` §7.7 |
| G11b *(superseded — see §9)* | **A host mixing alternatives with co-residents is refused, not planned.** `launch_specs` raises rather than guess where a unit that must be up beside whichever alternative wins belongs — putting it in both specs writes two files that disagree about what is running. Owner ruling 2026-09-09 withdrew the earlier recommendation to refuse such a mix as policy: under the fluid ladder this document describes, that mix is the normal case, so the refusal is a placeholder for a decision nobody has made | `src/mcgyvr/serving/__init__.py` (`launch_specs`); `records/plans/handoff.md`, owner ruling 5 |
| G12 | A RUN_ID cannot contain `+`; ids must match `[A-Za-z0-9_.-]+` | `ram-headroom-2026-09-09/README.md` § "Hazards" |
