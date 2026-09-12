# The fleet identity measurements — planned 2026-09-11

**The question.** The fleet identity design approves a fleet only after arithmetic that no
rig has measured yet:

- warm decode is judged against a no-NVMe baseline, within tolerances that are still
  provisional survey values;
- a unit's room plus the rig's headroom must fit the card;
- vLLM units pin their KV cache;
- a rig's identity leaves out the card reserve.

This run measures what that arithmetic reads.

**The authority is the test, not this file.**
`tests/test_the_numbers_the_fleet_identity_design_waits_on_are_measured.py` names:

- every unit × rig in scope;
- every record the run must write;
- every criterion.

This file says how each record is taken. Where the two disagree, the test is right.

**Frozen at the first measurement** (`okf/must-read/always.md`). The arms, the
instruments and the derivation rules below can only change before the first arm runs.
Any change after that is a new run.

Results land in `records/measurements/fleet-identity-2026-09-11/`, with a README, the
raw `results-*.json` and the scripts that took them, as the earlier campaigns did.

---

## Scope: the live fleet's units, plus one unit per missing class

The units are the ones the live fleet (`~/.mcgyvr/config/mcgyvr.yaml`) runs today. Each
compose is copied byte for byte into the run directory.

| rig | unit | engine | decode class | as-run launch |
|---|---|---|---|---|
| srv1 | `Qwen3.6-35B-A3B-UD-IQ3_XXS` | llama.cpp `b10644-L3` | CPU experts | `compose.srv1.yml`: `--n-cpu-moe 30`, mapped, `-c 16384 --parallel 2` |
| srv1 | `Ling-3.0-tiny-Q4_K_M` | llama.cpp `b10644-L3` | llama.cpp, all on card | `--n-cpu-moe 0`, mapped, `-c 8192 --parallel 2` |
| srv2 | `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ` | vLLM v0.26.0 | vLLM | `compose.srv2.yml`, the pair: util 0.26 |
| srv2 | `Qwen/Qwen2.5-Coder-7B-Instruct-AWQ` | vLLM v0.26.0 | vLLM | `compose.srv2.yml`, the pair: util 0.72 |
| srv1 | `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ` | vLLM v0.26.0 | host RAM only | `flexibility-2026-09-09/compose.srv1-vllm-3b.yml`: util 0.60 |

Why the extra units:

- **Ling is here because the live fleet has no llama.cpp unit that runs all on card**,
  and the −5% class needs one. It is the card-only llama.cpp unit measured most often
  on srv1 (`measuring-gaps-2026-09-10` Q5).
- **The srv1 3B is here only because "vLLM host RAM per rig" needs a vLLM unit on srv1.**

---

## How every arm is run

- **Through the door.** `python -m mcgyvr.serving.run serve up|down --host H --compose F
  --suffix S`, run with this checkout's interpreter. This is the same argv the Waker
  spawns (`src/mcgyvr/wake.py` `door_argv`).
- **Rig reads use plain `ssh -o BatchMode=yes`.** They are all read-only, except four
  deliberate host actions, each undone in the same arm:
  - `drop_caches`;
  - `swapoff -a` / `swapon -a`;
  - `sudo kill -9` of one engine process, so that docker's `restart: unless-stopped`
    restarts it;
  - reboots, which need the owner's yes first and are listed under M8.
- **Every arm starts cold.**
  - No `mcgyvr-*` container is up, which gate 2 enforces.
  - The page cache is dropped immediately before `serve up`.
  - Swap state is read, not assumed.
- **Every row carries:**
  - the rig's `uptime_since`;
  - `RestartCount` for every container;
  - `SwapTotal`;
  - `pswpout` and `pgmajfault` deltas over its decode window;
  - the full container log, saved under `logs/` and parsed off the rig.

### Decode instrument (M1, M5)

- **Request.** `POST /v1/chat/completions` with one fixed system and user message,
  `max_tokens 256`, `ignore_eos: true` and `temperature 0`.
  - Every sample therefore decodes exactly 256 tokens.
  - A sample that does not is refused, not recorded.
- **llama.cpp** reads the server's own `timings.predicted_per_second`.
- **vLLM** streams with `include_usage`, and the rate is `(completion_tokens − 1) /
  (last chunk − first chunk)`.
- **Per cold start:** one discarded warm-up, then **5 samples**, one stream at a time.
  Any neighbouring unit is idle.
- **Arm size:** 3 cold starts.

### Wake clocks (M2)

Every cold start records three clocks:

| clock | starts | stops |
|---|---|---|
| `door_process_s`, the Waker's clock | just before the door subprocess is spawned, after the local door lock is taken | the door exits. This is the span `src/mcgyvr/wake.py` `_run_door` times with `time.monotonic()` |
| `door_unit_s` | `docker compose up -d` returns | the unit answers healthy, polled every 3.0 s (`servelib.HEALTH_INTERVAL_S`). This is `serve-up.json` `units[].seconds` |
| `started_at_to_ready_s` | the container's `State.StartedAt` | this runner's own 0.5 s poll of that unit's `/v1/models` first answers 200. The rig's clock offset is measured in the same arm and corrected |

Differences between the clocks:

- On srv1's live unit, the Waker's clock reads **18.6–19.2 s** over the door's
  (`records/measurements/flexibility-2026-09-09/README.md`, "`mcgyvr`'s own clock runs
  19 s past the door's", n=3). No srv2 unit has a Waker-clock wake on record.
- **For a pair, the door's unit clock is not per unit.** It polls units in turn, so the
  second unit reads "how much longer after the first". `started_at_to_ready_s` is the
  per-unit clock.

---

## M1. Warm decode: no-NVMe baseline vs as-run, per unit × rig

**What it establishes.** Two things, per unit × rig:

- the warm decode rate with everything held in RAM and VRAM;
- the warm decode rate as the unit really runs.

It also establishes the three class tolerances that replace the survey's provisional
−3% (vLLM), −5% (llama.cpp) and −15% (CPU experts). Those values are in commit
`42f4967c`'s message; `records/evidence/2026-09-10-tolerance-survey/` holds no
derivation of them.

**Arms per unit** (3 cold starts each):

| unit | `baseline` (no NVMe) | `as_run` |
|---|---|---|
| srv1 Qwen3.6 | `--load-mode none` (experts in RAM, nothing read from the GGUF while serving) + `swapoff -a` | the live compose, mapped, swap as found |
| srv1 Ling | `--load-mode none` + `swapoff -a` | mapped, swap as found |
| srv2 3B, 7B | the live pair compose + `swapoff -a` | the live pair compose, swap as found |

**No baseline.** A llama.cpp baseline is launched only if the unmapped host-RAM need
clears `MemAvailable` by the refusal gate's 2.0 GiB (`REFUSAL_RAM_HEADROOM_GB`). That
need is:

- the spilled experts from the tensor table (`vramfit.experts_on_card`);
- plus `RUNTIME_RESIDENT_GB`.

A unit that does not clear is recorded as `no_baseline: "NVMe required"`, with both
figures, and is not launched with swap off: with no swap, an unmapped unit that does not
fit is killed, not paged, and srv1 has hard-locked under CPU expert offload before
(`okf/must-read/touching-rigs.md`, "srv1 hard-locks under CPU expert offload"). Predicted
today:

- Qwen3.6 at `--n-cpu-moe 30` needs 7.68 + 1.53 = 9.21 GiB against 14.19 − 2.0, so it
  clears;
- Ling clears.

**The tolerance rule, fixed before any arm:**

- For unit `u` and arm `a`, `x` is every warm sample (3 starts × 5), and `m = median(x)`.
- `shortfall(u, a) = max over x of (m − x) / m`.
- `tolerance(class)` is `max` of `shortfall` over the class's units and both arms, in
  percent. It is rounded **up** to the next whole percent, with a floor of 1%.
- `gap(u) = (median(baseline) − median(as_run)) / median(baseline)`.
- NVMe is allowed for `u` iff `gap(u) ≤ tolerance(class(u))`.
- The approved value is `median(as_run)`.

**Limit, UNVERIFIED.** The live judge reads decode rates off journal rows, which come from
real prompts at real widths. This instrument measures a fixed prompt at width 1. The
tolerance is therefore the dev instrument's own spread, and whether live traffic fits
inside it is not measured here.

**Record.**

- `results-decode.json`: one row per cold start, with its samples.
- `tolerances.json`: the rule's outputs.

The test recomputes both from the rows.

---

## M2. Cold wake per unit × rig, on named clocks

**What it establishes.** For every decode unit in scope, the cold wake measured on all
three clocks, n ≥ 3, with 0 restarts.

**Arms.**

- srv1 units: their M1 `as_run` starts.
- srv2 units: **each unit alone** (a one-service compose with the live argv), 3 cold
  starts each. The live pair orders its units `service_started`, and that crash-restarts
  the 3B on a cold start (`records/measurements/fleet-gaps-2026-09-09/README.md`, M5),
  so a pair start cannot give a restart-free per-unit wake.
- The M1 pair starts still record their restarts.

**Record.**

- `results-wake.json`: one row per cold start.
- `wake.json`: per unit × rig, the median on each clock, and the clock the design reads.
  That is `door_process_s`, because the Waker is what wakes a unit live.

---

## M3. vLLM host RAM per rig

**What it establishes.** Per rig, what one vLLM unit costs in host RAM. It replaces the
survey bounds of 2.60 GiB (srv1) and 2.96 GiB (srv2)
(`tests/test_a_bound_is_small_verified_and_scoped.py`).

**Arms.**

- srv2: the M2 single-unit starts of the 3B and 7B.
- srv1: the srv1 3B, 3 cold starts.

**Instrument.** `MemAvailable` after `drop_caches` on an idle rig, minus `MemAvailable`
after `drop_caches` with the unit healthy and warmed. Cross-checked against the summed
`RssAnon + RssShmem` of the container's processes (`/proc/<pid>/status`).

**Record.**

- `results-host-ram.json`: one row per cold start.
- The per-rig figure is the maximum over that rig's rows.

---

## M4. Unmapped Shmem, as a per-model residual

**What it establishes.** For each llama.cpp model in scope, run unmapped, how far `Shmem`
exceeds what the tensor table predicts, and whether that residual is one number per model.

- The survey read 0.414–0.418 GiB for Qwen3.6 across two placements.
- It proposes +0.60 GiB for any model not measured.

**Residual.**

```
residual = (Shmem with the unit up − Shmem idle) − (bytes_experts − vramfit.experts_on_card(geometry, n_cpu_moe))
```

This is the survey's own definition, `records/evidence/2026-09-10-tolerance-survey/extract.py`
`spilled_gib`. The geometry is `ggufscan.py` run over the blob on the rig.

**Arms** (swap off, so no `Shmem` page is on swap):

- the M1 `baseline` starts;
- plus a second placement per model, 2 cold starts each:
  - Qwen3.6 at `--n-cpu-moe 32`;
  - Ling at `--n-cpu-moe 4`.

**Criterion.** Every row carries a residual. A model's residual across starts and
placements spreads by ≤ 16 MiB.

**Record.** `results-shmem.json`.

---

## M5. fp8 KV cache on the RTX 3060 (sm_86)

**What it establishes.** For the live 7B alone on srv2, at `--kv-cache-dtype auto`
against `fp8`:

- the attention backend vLLM selects;
- card memory;
- KV tokens;
- warm decode;
- whether answers change.

**Why.** vLLM v0.26.0's code takes FlashAttention first and accepts fp8 there only with
FA3 on sm_90, so sm_86 falls to FlashInfer or Triton (`okf/must-read/touching-engine.md`).
`measuring-gaps-2026-09-10` Q2 measured the pool (2.000×) and decode (−3.5%) on another
model, but named no backend and checked no answers.

**Arms.**

- `auto`: the M2 7B single-unit starts.
- `fp8`: the same compose plus `--kv-cache-dtype fp8`, 3 cold starts.

Each start reads:

- the log line `Using <BACKEND> attention backend out of potential backends`;
- `GPU KV cache size: N tokens`;
- `nvidia-smi` steady `memory.used`;
- the M1 decode instrument.

**Quality.**

- **Runs.** `tools/breadth/measure.py --tier bench-py --draws 0` (greedy, 257 cells),
  twice on each dtype: `auto-a`, `auto-b`, `fp8-a`, `fp8-b`. Each dtype runs in its own
  unit lifetime.
- **Flips.** A cell flips when `passed` differs between two runs.
- **Bound.** The 95% Wilson upper limit on flips over cells (`tools/bench/responsiveness.py`
  `wilson`), on each dtype's own a/b null.
- **Verdict.** fp8 is `within null` iff flips(`auto-a`, `fp8-a`) / 257 ≤ the larger of
  the two null bounds. This is the house method of
  `records/evidence/2026-09-03-srv1-kernel-arms/correctness.json`.

**Record.**

- `results-fp8.json`;
- `fp8-quality.json`;
- the four bench run directories under `bench-7b-{auto,fp8}-{a,b}/`.

---

## M6. `--kv-cache-memory-bytes` on a rig

**What vLLM v0.26.0's code says** (read at tag `v0.26.0`):

- **The start gate is unconditional.** `v1/worker/gpu_worker.py:388-389` takes the init
  snapshot and calls `request_memory`. That raises `ValueError` when free memory is below
  `ceil(total × util)` (`v1/worker/utils.py:425-445`).
- **A pinned size skips memory profiling but not the profile run.** In
  `gpu_worker.py:462-480` it still calls `profile_run()`, then logs "Initial free memory X
  GiB, reserved K GiB … This does not respect the gpu_memory_utilization config".

**What it establishes, on srv2 with the 3B and 7B pinned:**

1. **Same size on every start.** The logged KV size is identical:
   - on a first start;
   - on a restart (`sudo kill -9` of the engine process, so docker restarts it with its
     writable layer kept);
   - and when the unit starts while its neighbour is serving a saturating load.
2. **An oversized value**, twice:
   - `K` above the unit's share but below the card's free memory: predicted to run past
     its room, silently;
   - `K` above the card's free memory: predicted to fail at allocation, not to shrink.
3. **The start gate still runs.** With the 3B up, the 7B starts pinned at util 0.90,
   whose `ceil(T × 0.90)` exceeds what is free. Predicted: the `request_memory` refusal
   text.

**Record.** `results-pinned-kv.json`, one row per case, with the log lines that decide it.

---

## M7. Headroom per rig, and resized srv2 shares

**What it establishes.**

- **Per rig:** `headroom = reserve + Σ contexts`.
  - `reserve` is `nvidia-smi memory.reserved`, read idle.
  - A vLLM unit's context is `T − initial free memory`, from its own start alone, where
    `T` is the total memory vLLM reads.
    - It is taken from the `DEBUG` init snapshot, in bytes (`gpu_worker.py:390`).
    - The arms run with `VLLM_LOGGING_LEVEL=DEBUG` for that reason, and are not the M1 arms.
  - The llama.cpp unit's context is its card net of idle, less its named device buffers.
    This is the `measuring-gaps-2026-09-10` Q3 residue, from 2 `--verbose` starts.
- **For srv2:** shares for the 3B and 7B, with pinned KV bytes, that satisfy
  `Σ ceil(share × T) + Σ contexts ≤ T`. Both start orders must pass.

**Sizing rule, fixed before any arm:**

1. **Measure each unit's non-KV peak.** Each unit alone, pinned at today's first-start
   KV (3B 12,352 tokens × 36,864 B; 7B 8,592 tokens × 57,344 B), serves 8 concurrent
   requests of about 3,000 prompt tokens and 1,000 output tokens (`ignore_eos`), so
   every sequence reaches its window. Its peak process memory
   (`nvidia-smi --query-compute-apps`, 1 Hz) minus its context minus `K` is its non-KV
   peak `P`. 2 cold starts each; the larger `P` is kept.
2. **Size KV to equal token capacity.** Pick the largest block-aligned `K3` and `K7`
   that give both units the same number of KV tokens, capped at `8 × 4096` each, such
   that `(P3 + K3) + (P7 + K7) + Σ contexts + 2 × 64 MiB ≤ T`.
3. **Round up to a share.** `share = ceil((P + K + 64 MiB) / T)`, to 0.01.

**Both orders.** The pair is started 3B-first and 7B-first, 2 cold starts each, ordered
by `depends_on: service_healthy`.

**Criterion.** On every start:

- both units are healthy;
- `RestartCount` is 0;
- the logged KV size equals `K`;
- each unit's peak process memory under the saturating load is ≤ `ceil(share × T)` plus
  its context.

**Record.**

- `results-headroom.json`: contexts, reserves, the proposal and the order rows.

---

## M8. `gpu_reserve_mib` across boots

**What it establishes.** The card reserve of each rig, read idle on at least two boots,
each named by its `uptime_since` (`/proc/stat` btime), with the same card and driver.

**Why it matters now.**

- Gate 2 compares `gpu_reserve_mib` with `tools/runs/hosts.json` **literally**
  (`src/mcgyvr/serving/gate-scripts/02-rig.py`).
- A srv1 boot on 2026-08-31 read 399 against the declared 401
  (`records/evidence/2026-08-31-inventory/srv1-scan.txt`).
- A reboot that moves the reserve therefore makes gate 2 refuse every door run on that
  rig until `hosts.json` changes.
- **The records hold no btime-stamped reading from any boot but today's**, so none
  counts toward this.

**Arms.** Read the reserve now, on the boot of 2026-09-01. Then, **only with the owner's
yes**, reboot the rig once and read it again, idle, before any unit starts.

**Record.** `results-reserve.json`.

---

## Order of work

1. **srv1**, in this order:
   - M1 Qwen3.6 as-run, then baseline;
   - M4 Qwen3.6 at 32;
   - M1 Ling as-run, then baseline;
   - M4 Ling at 4;
   - M3 srv1 3B;
   - M7 llama.cpp contexts.
2. **srv2**, in parallel, in this order:
   - M1 pair as-run, then baseline;
   - M2/M3/M5 7B and 3B alone;
   - M5 fp8;
   - M5 quality;
   - M7 solo pinned;
   - M7 orders;
   - M6.
3. **M8**, last, after asking the owner.
4. **Both rigs are left as found:** no `mcgyvr-*` container up, swap on.
