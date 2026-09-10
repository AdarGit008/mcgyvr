# Run mechanics spec — measuring-gaps-2026-09-10

How to author the NEW measurement runners for the measuring-gaps run
(`records/plans/measuring-gaps-2026-09-10.md`). Everything here is reverse-
engineered from the flexibility campaign (`records/measurements/flexibility-2026-09-09/`)
and the serving "door" (`src/mcgyvr/serving/`), so a runner author can write a
correct runner from this spec + the plan alone, without re-reading the
flexibility tree.

**One-line architecture.** A runner is a *standalone* Python script (operator
code, NOT running under the door). It reaches a rig for **read-only** probes with
plain `ssh -o BatchMode=yes <host> <cmd>`, and it starts/stops containers **only**
by shelling out to the door as a subprocess:
`python -m mcgyvr.serving.run serve up|down --host H --compose F --suffix S`.
The door is the only thing allowed to launch/tear down, and under the door
`docker` is a shim that points at the rig daemon.

---

## 0. The flexibility campaign as a template

The flexibility runners (`wake_rate.py`, `vllm_arms.py`) are the model for
every new runner. Read these three first:

1. `records/measurements/flexibility-2026-09-09/rig.py` — shared primitives:
   `rig()`, `gpu()`, `meminfo()`, `sample_start()/sample_stop()`, `door()`,
   `decode_llamacpp()`, `decode_llamacpp_warm()`, `decode_vllm()`.
2. `records/measurements/flexibility-2026-09-09/wake_rate.py` — the llama.cpp
   single-unit A/B runner shape: arms JSON in, `results-*.json` out.
3. `records/measurements/flexibility-2026-09-09/vllm_arms.py` — the vLLM cold
   start runner shape, including `engine_lines` capture.

The new runners go in
`records/measurements/measuring-gaps-2026-09-10/` and import `rig.py` the same
way the flexibility runners do (`import rig` from that directory, or copy the
primitives — the plan says results land in the run's own directory, not in the
session).

---

## 1. End-to-end: bring ONE llama.cpp unit up on a rig and tear it down

### 1a. What `make_config.py` takes and emits

`records/measurements/flexibility-2026-09-09/make_config.py`:

- **Usage:** `uv run --no-sync python make_config.py <host> <blob-stem> [ctx] [slots]`
  (`make_config.py:79-88`). Defaults `ctx=4096`, `slots=2`.
- **Input:** `host` (`srv1`|`srv2`) + `stem` (GGUF blob stem under
  `/home/adaramir/models/moe/<stem>.gguf`).
- **Step 1 — geometry:** `geometry()` (`make_config.py:35-46`) ships
  `src/mcgyvr/serving/ggufscan.py` to the rig on stdin and runs it against the
  blob:
  ```
  ssh -o BatchMode=yes <host> "python3 - /home/adaramir/models/moe/<stem>.gguf" < ggufscan.py
  ```
  and writes the JSON list to `<emit>/<host>-<stem>/<stem>.geometry.json`.
- **Step 2 — config:** `build()` (`make_config.py:49-76`) writes a one-tier
  `mcgyvr.yaml` (sources → models → ladder → verifier disabled → sandbox docker →
  delivery branch) with `image: llamacpp:b10644-L3`, `context_window: ctx`,
  `max_parallel: slots`, then runs `emit`:
  ```
  uv run --no-sync python -m mcgyvr.cli emit --config <cfg> --out <into>
  ```
- **Emit output:** `compose.<host>.yml` (e.g.
  `emit/srv1-deepseek-coder-v2-16b/compose.srv1.yml`). `build()` prints and
  returns that path.

**Note for the new runners:** the plan says kv_q8_ab does NOT re-run make_config;
it *patches the existing srv1 deepseek compose* to add `-ctk q8_0 -ctv q8_0`
(`records/plans/measuring-gaps-2026-09-10.md:128-129`). A hand-written compose
is a plain YAML file in the campaign dir — see the templates below.

### 1b. The exact command(s) that bring a compose up and down

**Not** raw `docker compose` from the runner, and **not** `mcgyvr serve up` as a
library call. The runner invokes the door's **serve run** as a subprocess. The
flexibility helper is `rig.door()` (`rig.py:172-199`):

```python
flock /tmp/claude-1000/mcgyvr-door.lock \
  uv run --no-sync python -m mcgyvr.serving.run \
    serve up --host <host> --compose <compose> --suffix <unique>
```

i.e. the literal commands are:

```bash
# UP
uv run --no-sync python -m mcgyvr.serving.run serve up \
  --host srv1 --compose /home/adaramir/claude/mcgyvr/records/measurements/measuring-gaps-2026-09-10/<compose>.yml \
  --suffix <unique-suffix>

# DOWN
uv run --no-sync python -m mcgyvr.serving.run serve down \
  --host srv1 --compose <same-file> --suffix <unique-suffix>
```

What the door then does inside (`src/mcgyvr/serving/gate-scripts/serve-up.py`,
`serve-down.py`):

- `serve-up.py:88` → `servelib.compose(compose_file, "up", "-d", "--remove-orphans")`.
- `serve-down.py:66` → `servelib.compose(compose_file, "down")`.
- `servelib.compose()` (`servelib.py:97-108`) expands to
  `docker compose -f <file> -p mcgyvr <args>`, and under the door `docker` is the
  shim (`gate-scripts/bin/docker`) that prepends `-H ssh://<host>` — so the
  compose runs **on the rig's daemon**, never the operator's.

The `flock` wrapper serialises gate 1's write to `tools/bench/rounds.json`
(see `rig.py:163-168` for the why); keep it if srv1 and srv2 runners run in
parallel.

**Up is verified by the door, not the runner.** `serve-up.py` polls each unit via
`servelib.wait_for()` (`servelib.py:257-302`): `/v1/models` must list models AND
`/is_sleeping` must not be `true`. On success the door leaves the container
**running** and writes `serve-up.json`.

### 1c. How gate 2 refuses a busy rig, and how a rig is verified empty

`src/mcgyvr/serving/gate-scripts/02-rig.py`:

- It ships `rig-snapshot.sh` to the rig and parses `key=value` back
  (`02-rig.py:120-126`, `snapshot()` at `02-rig.py:50-93`).
- The idle keys are `IDLE_KEYS = ("gpu_procs", "containers")` (`02-rig.py:42`).
  If either reads anything other than `none`, the run is refused
  (`02-rig.py:203-214`):
  ```
  gate 2: <host> is not idle — gpu_procs=..., containers=... — Nothing is
  measured on a card or a daemon something else is using ...
  ```
- The one exception: `serve down` is allowed to open on a busy rig, because its
  job is to stop what is up (`02-rig.py:188-200`).

The runner's own empty-check (before any arm) is the same read via ssh
(`wake_rate.py:33-71`):

```bash
docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true   # expect empty
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits   # expect 17 (srv1) / 1 (srv2)
sudo pkill -f /tmp/balloon.py ; sleep 2 ; true             # no balloon resident
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'       # cold page cache
```

Idle card baselines: **srv1 = 17 MiB used, srv2 = 1 MiB used** (see
`headroom.py:38-39` — `CARD_TOTAL_MIB = {"srv1": 5744, "srv2": 11912}` and the
arm's own `vram_idle_free_mib`).

---

## 2. The results JSON schema

### Who writes it

- `wake_rate.py` (llama.cpp): `OUT = rig.SCR / (MCG_OUT or f"results-{Path(sys.argv[1]).stem}.json")`
  (`wake_rate.py:25-26`); appended per arm in `main()` (`wake_rate.py:138-150`).
- `vllm_arms.py` (vLLM): `OUT = rig.SCR / (MCG_OUT or "results-vllm.json")`
  (`vllm_arms.py:40-41`).
- `headroom.py` (offline recompute): writes `results-q11-headroom.json`
  (`headroom.py:104-151`).

Arms are supplied as a JSON list of specs; each entry is `{host, label, compose,
container, port, blob_gib, repeats}` (+ `units` for vLLM, + `balloon_gib` optional).
The runner appends one result row per repeat, naming the row `"<label>-<index>"`.

### llama.cpp result row fields (exact names + types)

From `wake_rate.py:121-136` (all floats are Python floats, ints are ints, MiB are ints):

| field | type | meaning |
|---|---|---|
| `host` | str | `srv1` / `srv2` |
| `label` | str | `<label>-<index>` |
| `blob_gib` | float | GGUF size in GiB |
| `port` | int | container port |
| `repeats` | int | planned repeats |
| `container` | str | `container_name` from the compose |
| `compose` | str | absolute path to the compose used |
| `balloon` | str | `"none"` or the balloon READY log |
| `idle_avail_gib` | float | MemAvailable before load |
| `avail_before_gib` | float | MemAvailable after cache drop / balloon |
| `clearance_vs_blob_gib` | float | `avail_before - blob_gib` |
| `wake_s` | float | door-done − `StartedAt` (UTC) |
| `gib_per_s` | float | `blob_gib / wake_s` |
| `vram_peak_used_mib` | int | max of the 1 Hz sampler |
| `vram_steady_used_mib` | int | `nvidia-smi memory.used` after settle |
| `vram_idle_free_mib` | int | `nvidia-smi memory.free` before load |
| `shmem_steady_gib` | float | `/proc/meminfo Shmem` after |
| `avail_after_gib` | float | MemAvailable after |
| `decode_tok_s` | float | cold single decode |
| `decode_warm` | {mean, samples[], n} | warm mean over 3 samples after 1 discarded |
| `restart_count` | int | `docker inspect .RestartCount` |
| `pgmajfault_wake` | int | vmstat delta across the wake |
| `pswpout_wake` | int | vmstat delta |
| `samples` | int | 1 Hz sampler row count |

### vLLM result row fields

From `vllm_arms.py:133-156`: `label`, `units`, `repeats`, `compose`, `wake_s`,
`idle_avail_gib`, `avail_after_gib`, `ram_cost_gib`, `idle_vram_used_mib`,
`vram_peak_used_mib`, `vram_steady_used_mib`, `vram_steady_free_mib`,
`per_unit{}`, `samples`. `per_unit[k]` (`vllm_arms.py:106-122`):
`started_offset_s`, `restart_count`, `engine_lines` (str, verbatim grep),
`is_sleeping_http`, `tok_s[]`, `ttft_s[]`, `mean_tok_s`.

### One real record to copy the shape from

`records/measurements/flexibility-2026-09-09/results-q1-srv1.json` (first row):

```json
{
  "host": "srv1",
  "label": "q1-deepseek-1",
  "blob_gib": 8.29,
  "port": 8080,
  "repeats": 2,
  "container": "mcgyvr-srv1-deepseek-coder-v2-16b-8080",
  "compose": ".../emit/srv1-deepseek-coder-v2-16b/compose.srv1.yml",
  "balloon": "none",
  "idle_avail_gib": 14.230873107910156,
  "avail_before_gib": 14.226470947265625,
  "clearance_vs_blob_gib": 5.936470947265626,
  "wake_s": 86.3242392539978,
  "gib_per_s": 0.09603328186429488,
  "vram_peak_used_mib": 5446,
  "vram_steady_used_mib": 5460,
  "vram_idle_free_mib": 5727,
  "shmem_steady_gib": 0.10962295532226562,
  "avail_after_gib": 13.438785552978516,
  "decode_tok_s": 34.72687856032408,
  "decode_warm": {"mean": 34.84201958852203, "samples": [34.83174841575788, 34.854586227835, 34.83972412197321], "n": 3},
  "restart_count": 0,
  "pgmajfault_wake": 5409,
  "pswpout_wake": 0,
  "samples": 103
}
```

---

## 3. How engine log lines are captured from a running container

The three log lines this run needs:

- **llama.cpp KV** — `llama_kv_cache: size = 4320.00 MiB ( 2048 cells, 27 layers, 8/8 seqs), K (f16): 2592.00 MiB, V (f16): 1728.00 MiB`
  (real line: `records/evidence/2026-09-05-context-decomposition/srv2-floorverify/deepseek-coder-v2-16b-c16384/n4-t1.log:1097`).
  Under an SWA checkpoint there are TWO of these (one per cache), prefixed by
  `llama_kv_cache_iswa: creating non-SWA/SWA KV cache`.
- **llama.cpp compute buffer** — `sched_reserve: CUDA0 compute buffer size =   125.39 MiB`
  (same log, line 1127).
- **vLLM pool** — `GPU KV cache size: 22,608 tokens` and
  `Maximum concurrency for <N> tokens per request: <X.xx>x` (real line:
  `results-q9-vllm-srv1.json` `engine_lines`, and `records/evidence/...`).

### Exact extraction command

**Method A (flexibility on-rig inline grep) — `vllm_arms.py:111-116`:**

```bash
docker logs <container> 2>&1 | grep -iE \
 'KV cache size|GPU KV cache|memory profiling|Available KV cache|model weights take|non-torch memory|PyTorch activation peak' | tail -8 || true
```
executed **on the rig** via `rig.rig(host, cmd)` — the command runs on the rig,
so `docker` there talks to the rig's local daemon (no shim needed for read-only).

**Method B (vLLM exact token/concurrency grep) — `tools/runs/drivers/vllm_sweep.py:268-270`:**

```bash
docker logs <container> 2>&1 | grep -oE \
 '(GPU KV cache size: [0-9,]+ tokens|Maximum concurrency for [0-9,]+ tokens per request: [0-9.]+x)' | tail -2
```
parse with `re.search(r"GPU KV cache size: ([\d,]+) tokens", kvlog)` and
`re.search(r"per request: ([\d.]+)x", kvlog)`.

**Method C (llama.cpp buffer names, exact) — `records/evidence/2026-09-05-context-decomposition/parse-logs.py:6-16`:**

```python
PATS = {
 "cuda_model":  r"load_tensors:\s+CUDA0 model buffer size =\s+([\d.]+)",
 "cpu_model":   r"load_tensors:\s+CPU_Mapped model buffer size =\s+([\d.]+)",
 "cuda_kv":     r"llama_kv_cache:\s+CUDA0 KV buffer size =\s+([\d.]+)",
 "cuda_compute":r"sched_reserve:\s+CUDA0 compute buffer size =\s+([\d.]+)",
 "host_compute":r"sched_reserve:\s+CUDA_Host compute buffer size =\s+([\d.]+)",
 "output":      r"llama_context:\s+CUDA_Host\s+output buffer size =\s+([\d.]+)",
 "cuda_rs":     r"llama_memory_recurrent:\s+CUDA0 RS buffer size =\s+([\d.]+)",
}
KVSIZE = re.compile(r"llama_kv_cache: size =\s+([\d.]+) MiB \(\s*(\d+) cells,\s*(\d+) layers,\s*(\d+)/(\d+) seqs\), K \(\w+\):\s*([\d.]+) MiB, V \(\w+\):\s*([\d.]+)")
```

**The one rule that matters** (`ctx-probe.sh` header, and `parse-logs.py:17-30`):
**capture the FULL container log to a file, never `grep … | tail -1` on the
rig.** llama.cpp's loader runs twice (a fit pass then the real one), and an SWA
model prints TWO `CUDA0 KV buffer size` lines — `tail -1` silently kept one and
hid the other in the residue. Split on the LAST `load_tensors: … model buffer
size` occurrence and parse what follows.

For the measuring-gaps runners, the safe recipe is:

```python
log = rig.rig(host, f"docker logs {container} 2>&1 || true")   # full log off-rig
(LOGS / f"{label}.log").write_text(log)
# then parse with parse-logs.py's PATS/KVSIZE off-rig
```

---

## 4. The 1 Hz nvidia-smi sampler and steady-state "net of idle baseline"

The sampler lives in `rig.py:111-160`.

- **Start** (`sample_start`, `rig.py:131-135`): writes `/tmp/mcg-sample.sh` to
  the rig. The loop (`rig.py:111-129`) runs every 1 s:
  ```
  g=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits | tr -d ' ')
  m=$(awk '/^MemAvailable:/{a=$2}/^Shmem:/{s=$2}END{print a","s}' /proc/meminfo)
  echo "$(date -u +%s),$g,$m"
  ```
  launched detached (`setsid … &`), PID stored in `/tmp/mcg-sample.pid`, output
  to `/tmp/mcg-sample.csv`.
- **Stop + read** (`sample_stop`, `rig.py:137-160`): kills by PID file (never
  `pkill -f`, which matches its own ssh command line — see `rig.py:103-110`),
  cats the CSV, parses rows `{t, vram_used_mib, vram_free_mib, avail_kib,
  shmem_kib}`, writes `logs/sample-<name>.json`.
- **Peak** = `max(r["vram_used_mib"])` over rows.

**Steady-state:** after the wake, a single `rig.gpu()` read
(`rig.py:71-77`):
```
nvidia-smi --query-gpu=memory.total,memory.used,memory.reserved,memory.free --format=csv,noheader,nounits
```
`vram_steady_used_mib = after_gpu["used"]`.

**Net of idle baseline** (this is the number `headroom.py` and `c_drift_report`
recompute):

```python
idle_used   = CARD_TOTAL_MIB[host] - row["vram_idle_free_mib"]   # headroom.py:98
measured_net_mib = row["vram_steady_used_mib"] - idle_used        # headroom.py:99
```

Idle used baselines: **srv1 = 17 MiB, srv2 = 1 MiB** (also seen directly as
`idle_vram_used_mib: 17` in `results-q9-vllm-srv1.json`). Do not hardcode
against `memory.used` from the arm — always read `memory.free` before the load
and derive the idle-used figure, exactly as `headroom.py:98` does.

---

## 5. Decode cold + warm sampling

Prompt and instruments (`rig.py:263-304`):

```python
LLAMA_PROMPT = "Write a Python function that merges two sorted lists."
```

- **Cold single sample** — `decode_llamacpp()` (`rig.py:266-279`):
  ```
  curl -s -m 900 http://<host>:<port>/completion \
    -H 'Content-Type: application/json' \
    -d '{"prompt": "<LLAMA_PROMPT>", "n_predict": 160, "temperature": 0, "cache_prompt": false}'
  ```
  returns `json["timings"]["predicted_per_second"]`.
- **Warm mean** — `decode_llamacpp_warm()` (`rig.py:281-304`): one **discarded**
  warm-up call, then `samples=3` more; returns `{mean, samples[], n}`. The mean
  is the figure the run must use for the q8_0 decode delta (a cold single
  sample reads ~2× low — flexibility README §3).
- **vLLM decode** — `decode_vllm()` (`rig.py:306-363`): streams
  `POST /v1/completions` (`stream: true`, `stream_options: {include_usage: true}`),
  computes `ttft_s = first - t0`, `tok_s = (tokens-1)/(last-first)`, plus
  `tokens`, `usage`. Use this for `vllm_fp8_kv.py`.

---

## 6. Map each NEW runner to its closest existing flexibility runner

| new runner | model on | why |
|---|---|---|
| `kv_q8_ab.py` | `wake_rate.py` | llama.cpp single-unit A/B cold start (`host/label/compose/container/port/blob_gib/repeats`); instead of a `--n-cpu-moe` ladder, patch the compose argv with `-ctk q8_0 -ctv q8_0`, and additionally capture the engine KV line (Q3) + card + wake + `decode_warm`. Emit the compose by patching `emit/srv1-deepseek-coder-v2-16b/compose.srv1.yml`; do NOT use `make_config.py` (plan `measuring-gaps-2026-09-10.md:128`). |
| `mla_absorbed_v.py` | `wake_rate.py` | Ling cold start, capture `llama_kv_cache: size = … K (f16): … V (f16): 0.00 MiB` verbatim + steady card; cross-check card vs `vramfit.predict` (plan `:159`). Same arm shape, but the only "measurement" is the KV line + card. |
| `vllm_fp8_kv.py` | `vllm_arms.py` | vLLM cold start A/B with `--kv-cache-dtype` toggled; read `GPU KV cache size: N tokens` + `Maximum concurrency …: Xx` (the `engine_lines` grep in `vllm_arms.py:111-116`) + card + one warm `decode_vllm`. |
| `c_drift_deepseek.py` | `wake_rate.py` (launch half) + `headroom.py` (recompute half) | launches deepseek at `ncmoe 0/13/26`, n=2 each, records `vramfit.predict` vs steady card. |
| `c_drift_report.py` | `headroom.py` | offline: `vramfit.experts_on_card` + `constant_from_probe` per arm, probe = lowest ncmoe, print C spread + residual. Mirror `headroom.py:82-151`. |
| `scratch_curve.py` | `wake_rate.py` (launch half) + `parse-logs.py` / `ctx-probe.sh` (capture half) | one cold start per `(arch, -ub)`, capture `sched_reserve: CUDA0 compute buffer size` verbatim + steady card (net of idle). |
| `scratch_report.py` | `parse-logs.py` | offline: sum `cuda_compute` + residue (card − idle − named buffers) against the `SCRATCH_AND_CONTEXT_MIB = 768` bound. |

The `C`/scratch recompute functions live in
`src/mcgyvr/serving/vramfit.py`: `experts_on_card()` (`:268`),
`constant_from_probe()` (`:296`), `predict()` (`:335`),
`CACHE_ELEM_BYTES` (`:48`), `SCRATCH_AND_CONTEXT_MIB` (`:66`),
`MEASURED_SCRATCH_MIB` (`:88`).

---

## 7. Everything a runner needs to reach a rig

### Env vars

- `MCG_HOST` (vLLM runner) / `HOST` (`wake_rate` reads `spec["host"]` per arm)
  — set to `srv1` or `srv2`.
- `MCG_OUT` — output JSON filename (optional; defaults shown in §2).
- **Do NOT set `MCGYVR_CONFIG`.** With it unset, gate 1 loads
  `~/.mcgyvr/config/mcgyvr.yaml` and the serve run is **profile=live** — which
  is required, because gate 1 refuses a *dev*-profile serve whose compose is
  not inside the live config's `serving.compose_dir`
  (`01-round.py:121-213`). Under live, hand-written composes anywhere are fine.
- `MCGYVR_RUN_ROOT` — optional; defaults to the checkout. Do not set `RUN_*` or
  `DOCKER_*` (the door refuses ambient ones, `run.py:_ambient()`).

### SSH

Read-only probes use **plain ssh** from the runner process (this is allowed —
the runner is operator code outside the door):

```python
subprocess.run(["ssh", "-o", "BatchMode=yes", host, script], ...)   # rig.rig, rig.py:38-41
```
`BatchMode=yes` means key-based auth; hostnames are the short `srv1` / `srv2`
(as declared in `tools/runs/hosts.json`). There is no wrapper for reads.

### compose_dir / door naming of round and lease

- **Round:** gate 1 (`01-round.py`) calls `tools/bench/product.py ensure_open()`
  → exports `RUN_ROUND` (e.g. `r26-09-09-2026`) and `RUN_PRODUCT_SHA256`
  (`01-round.py:255-260`).
- **Lease:** gate 2 (`02-rig.py`) takes the rig lease at `~/.mcgyvr/lease` on
  the rig (`gatelib.py: LEASE_DIR/LEASE_FILE`), exported as `RUN_LEASE`; the
  door releases it on every exit (`lease-release.py`).
- **RUN_ID:** for a serve run it is
  `<date>-live-<host>-serve-up[-<suffix>]` / `...-serve-down[-<suffix>]`
  (campaign is fixed to `live-<host>` by `run.py:_serve`). The envelope is
  `records/evidence/<date>-live-<host>/` and holds `serve-up.json` /
  `serve-down.json`. A unique `--suffix` is **mandatory per arm** because
  `serve-up.json` is a write-once artifact (gate 5) — reusing a suffix on the
  same day is refused.

### Exact serve invocation (copy-paste)

```bash
uv run --no-sync python -m mcgyvr.serving.run serve up \
  --host srv1 \
  --compose /home/adaramir/claude/mcgyvr/records/measurements/measuring-gaps-2026-09-10/compose.srv1-q8kv.yml \
  --suffix "q8-ab-1"
```
(and the same with `serve down`). The flexibility helper that wraps `flock` +
this command is `rig.door()` / `rig.door_or_die()` (`rig.py:172-210`).

### How `docker` is pointed at the rig daemon

Only under the door: `gate-scripts/bin/docker` (`gatelib.shim_docker`,
`gatelib.py:654-680`) prepends `-H ssh://<host>` to every docker invocation, so
`docker compose`/`docker ps` inside the door reach the rig's daemon. The runner
itself must never run a local `docker` that starts containers; for read-only
`docker logs` / `docker inspect` / `docker ps`, it runs the command **on the
rig via ssh** (e.g. `rig.rig(host, "docker logs <container> 2>&1 || true")`),
where docker talks to the rig's local daemon directly.

---

## Compose templates

**llama.cpp, srv1, mapped (base = `emit/srv1-deepseek-coder-v2-16b/compose.srv1.yml`):**

```yaml
services:
  <service>:
    command:
    - --model
    - /home/adaramir/models/moe/<stem>.gguf
    - --n-cpu-moe
    - '19'
    - --parallel
    - '2'
    - --port
    - '8080'
    - -b
    - '512'
    - -c
    - '8192'
    - -fa
    - 'on'
    - -ngl
    - '99'
    - -t
    - '6'
    - -ub
    - '512'
    container_name: mcgyvr-srv1-<stem>-8080
    deploy:
      resources:
        reservations:
          devices:
          - capabilities: [gpu]
            device_ids: ['0']
            driver: nvidia
    environment:
      LLAMA_ARG_HOST: 0.0.0.0
    image: llamacpp:b10644-L3
    network_mode: host
    restart: unless-stopped
    volumes:
    - /home/adaramir/models/moe:/home/adaramir/models/moe:ro
    - /home/adaramir/models/moe:/models:ro
```

For **kv_q8_ab**, append to `command`:
```yaml
    - -ctk
    - q8_0
    - -ctv
    - q8_0
```

**llama.cpp, srv2** uses the same image (`llamacpp:b10644-L3` in the flexibility
srv2 composes) and `-t 10`, `--n-cpu-moe` per arm — see
`compose.srv2.m2-both.yml` / `compose.srv2-qwen36-ncmoe7.yml`. Note the
discrepancy to be aware of: `tools/runs/hosts.json` declares srv2's
`llamacpp_image` as `ghcr.io/ggml-org/llama.cpp:server-cuda-b10644` (that is
the **default-step** image only); the measurement composes on srv2 deliberately
used `llamacpp:b10644-L3`.

**vLLM (base = `compose.srv1-vllm-3b.yml`):**

```yaml
services:
  <service>:
    command:
    - <model-id>
    - --max-model-len
    - '2048'
    - --max-num-seqs
    - '128'
    - --port
    - '8001'
    - --gpu-memory-utilization
    - '0.90'
    - --dtype
    - float16
    container_name: mcgyvr-srv2-<model>-8001
    deploy:
      resources:
        reservations:
          devices:
          - capabilities: [gpu]
            device_ids: ['0']
            driver: nvidia
    environment:
      HF_HUB_OFFLINE: '1'
    image: vllm/vllm-openai@sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52
    ipc: host
    network_mode: host
    restart: unless-stopped
    volumes:
    - /home/adaramir/.cache/huggingface:/root/.cache/huggingface:ro
```
For **vllm_fp8_kv** (srv2 only — srv1's cc 7.5 refuses fp8), append
`--kv-cache-dtype fp8` to `command` and set `--max-model-len 2048
--max-num-seqs 128 --gpu-memory-utilization 0.90` with model
`thewimo/Qwen3-4B-AWQ` (the "q34b" cell), per
`records/plans/measuring-gaps-2026-09-10.md` Q2.

---

## Runner skeleton (copy-paste shape)

```python
#!/usr/bin/env python3
"""One arm = one cold start, capture <what this runner measures>."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
import rig                      # copy from flexibility dir, or same dir

ARMS  = json.loads((rig.SCR / sys.argv[1]).read_text())   # [{host,label,compose,container,port,...}]
OUT   = rig.SCR / (os.environ.get("MCG_OUT") or f"results-{Path(sys.argv[1]).stem}.json")
LOGS  = rig.SCR / "logs"; LOGS.mkdir(exist_ok=True)

def teardown(host):
    running = rig.rig(host, "docker ps --format '{{.Names}}' | grep '^mcgyvr-' || true")
    names = [n for n in running.split() if n]
    if not names:
        return
    index = json.loads((rig.SCR / "teardown-index.json").read_text())
    wanted = []
    remembered = rig.last_up(host)
    if remembered:
        wanted.append(remembered)
    else:
        for name in names:
            c = index.get(name)
            if c is None:
                raise SystemExit(f"{host}: {name} is up and nothing names it")
            if c not in wanted:
                wanted.append(c)
    for c in wanted:
        rig.door_or_die("down", host, c, f"td-{int(time.time())}")

def arm(spec, index):
    host, label = spec["host"], f"{spec['label']}-{index}"
    teardown(host)
    rig.balloon_down(host)
    rig.drop_caches(host)
    idle_gpu = rig.gpu(host)                       # idle used/free BEFORE launch
    rig.sample_start(host)
    proc = rig.door("up", host, spec["compose"], f"{label}-up")
    t1 = time.time()
    if proc.returncode != 0:
        log = rig.rig(host, f"docker logs --tail 40 {spec['container']} 2>&1 || true")
        rig.sample_stop(host, label)
        (LOGS / f"crash-{label}.log").write_text(log)
        raise SystemExit(f"door up rc={proc.returncode}\n{log[-1500:]}")
    rig.note_up(host, spec["compose"])
    wake = rig.wake_from(host, spec["container"], t1)
    time.sleep(2)
    rows = rig.sample_stop(host, label)
    engine_log = rig.rig(host, f"docker logs {spec['container']} 2>&1 || true")
    (LOGS / f"{label}.log").write_text(engine_log)  # FULL log, parse off-rig
    cold = rig.decode_llamacpp(host, spec["port"])
    warm = rig.decode_llamacpp_warm(host, spec["port"])
    after_gpu = rig.gpu(host)
    peak = max((r["vram_used_mib"] for r in rows), default=None)
    return {**spec, "label": label, "wake_s": wake,
            "vram_peak_used_mib": peak, "vram_steady_used_mib": after_gpu["used"],
            "vram_idle_free_mib": idle_gpu["free"],
            "decode_tok_s": cold, "decode_warm": warm, "samples": len(rows)}

def main():
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    for spec in ARMS:
        for i in range(1, spec.get("repeats", 1) + 1):
            try:
                results.append(arm(spec, i))
            except SystemExit as exc:
                results.append({**spec, "label": f"{spec['label']}-{i}", "failed": str(exc)})
            OUT.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {OUT}")

if __name__ == "__main__":
    main()
```

The offline report runners (`c_drift_report.py`, `scratch_report.py`) import
`vramfit` and the geometry JSON exactly as `headroom.py` does
(`headroom.py:68-104`, `sys.path.insert(0, "/home/adaramir/claude/mcgyvr/src")`),
recompute the named buffer/residue per arm, and write a `results-*.json` beside
the arm results.

---

## Constraints, risks, open questions

1. **Write the teardown marker on every path that starts a unit** — `note_up()`
   (`rig.py:212-222`) records `last-up-<host>.txt`, and every new compose must
   be added to `teardown-index.json` (flexibility README "Harness lessons").
   The file that *started* a unit is the file that *stops* it; never infer from
   container name alone.
2. **Unique `--suffix` per arm** — `serve-up.json`/`serve-down.json` are
   write-once; a same-day repeat without a fresh suffix is refused at gate 5.
3. **srv1 must use `llamacpp:b10644-L3`** (the stock image reads ~1.6-3.6× low
   on TU116 — `okf/must-read/touching-rigs.md`). The flexibility srv2 composes
   also used `llamacpp:b10644-L3`, not the `hosts.json` default-step image.
4. **Never `grep | tail -1` a llama.cpp log on the rig** — capture the full log
   and parse off-rig (SWA prints two KV lines; loader runs twice).
5. **srv1 hard-locks under CPU expert offload** in some configs — keep arm
   composes mapped; do not run `--n-cpu-moe` on srv1 beyond the already-measured
   placements without re-checking (`touching-rigs.md`, "srv1 hard-locks").
6. **The 1 Hz sampler is stopped by PID file, never `pkill -f`** (matches its
   own ssh command line — `rig.py:103-110`).
7. **Decode is read on the warm mean**, not the cold single sample (the
   flexibility campaign's cold column is 2× low — README §3).
8. **vLLM fp8 is srv2-only** (srv1 cc 7.5 refuses `Minimum capability: 89`);
   fp8 swaps FLASH_ATTN for FLASHINFER on Ampere, so record the warm decode
   beside the pool line (`touching-engine.md`).
