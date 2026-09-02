# What the serving hosts will say about themselves — measured, 2026-08-18

Every number here was read off a running server on 2026-08-18. Nothing in this
document comes from documentation except where it is labelled as such, and in
the two places where documentation and measurement disagreed the measurement is
recorded as the finding.

Raised by **#286** (the `observed` block, ADR-0027 D7), which needs four fields —
`quantization`, `context_length`, `concurrency`, `seed` — that only a server can
answer. The lane started by asking ollama's two documented endpoints. It ended
by finding that ollama runs `llama-server` underneath and that *that* process
answers all four.

## The rigs, as they were

| | srv1 | srv2 |
|---|---|---|
| GPU | GTX 1660 SUPER, 6 GB | RTX 3060, 12 GB |
| ollama | 0.32.4 | 0.32.5 |
| `OLLAMA_NUM_PARALLEL` | **2** (systemd) | **unset** |
| `OLLAMA_KEEP_ALIVE` | 5m | unset |
| vLLM | 0.26.0, pip | 0.26.0, `vllm/vllm-openai` container |
| vLLM launch | `--max-model-len 8192 --max-num-seqs 8 --enforce-eager` | `--max-model-len 16384 --max-num-seqs 16 --enable-prefix-caching --enable-sleep-mode` |
| ollama models held | 5 | 12 |

## The four fields, per surface

| field | ollama public API | ollama's `llama-server` | vLLM, dev mode ON | vLLM, dev mode OFF |
|---|---|---|---|---|
| `quantization` | `Q4_K_M` (`/api/show`) | `Q4_K - Medium` | `auto_awq` | — |
| `context_length` | `4096` (`/api/ps`) | `4096` | `8192` / `16384` | `8192` / `16384` |
| `concurrency` | — | **`total_slots` 2 / 1** | — | — |
| `seed` | — | **`4294967295`** | `0` | — |

Four of the eight cells are answered on a surface nobody in this tree was
reading, and two of those four are answered *only* there.

## Finding 1 — the served window is not the advertised window

`/api/tags` and `/api/show` both report **32768** for `qwen2.5-coder:1.5b`. That
is the window the model was *trained* with. The loaded instance is being served
with **4096**, and only `/api/ps` says so.

`/api/ps`'s `context_length` field **is not in ollama's API documentation**
(fetched 2026-08-18); it is in the running builds on both rigs. Documentation
lagging the implementation is the reason this was found by probing rather than
by reading.

The mechanism is on the `llama-server` command line: srv1 runs `-c 8192 -np 2`,
so the total KV context is divided across slots and each request gets
`8192 / 2 = 4096`. srv2 runs `-c 4096 -np 1` — a different route to the same
per-request 4096. Recording the 32768 would have put a window on disk that no
run has ever had.

## Finding 2 — the two rigs serve at different concurrency, and nothing recorded it

srv1 serves **2** concurrent slots; srv2 serves **1**. Confirmed four
independent ways on srv1:

1. `OLLAMA_NUM_PARALLEL=2` in the systemd unit
2. `-np 2` on the `llama-server` process command line
3. `total_slots: 2` from `llama-server`'s `/props`
4. **Measured**: a concurrency ramp

The ramp is the one that does not depend on trusting a config. Aggregate
throughput against offered concurrency, 128 tokens per request, each level run
twice and the better kept:

| n | tok/s | speedup | mean latency |
|---|---|---|---|
| 1 | 98.9 | 1.00 | 1.29 s |
| 2 | 147.6 | **1.49** | 1.73 s |
| 3 | 140.9 | 1.42 | 2.07 s |
| 4 | 160.1 | 1.62 | 2.47 s |
| 6 | 165.0 | 1.67 | 3.21 s |
| 8 | 166.4 | 1.68 | 3.99 s |
| 12 | 168.8 | 1.71 | 5.51 s |
| 16 | 168.3 | 1.70 | 7.10 s |
| 24 | 168.4 | 1.70 | 10.29 s |

Throughput rises to n=2 and then flats; past the knee, mean latency grows as
`n/2`. The knee recovers the configured value, which is what earns the method
its other readings.

**A first method was tried and discarded**, and it is recorded because the way
it failed is instructive. It read the *clustering* of completion times — `n`
requests served `k`-at-a-time should finish in clusters of `k` — and on a cold
server it recovered srv1's 2 as twelve clean pairs. Warm, the structure vanished
entirely: the probe prompt hit EOS at different lengths per request, and unequal
work destroys the clustering. A method that only works on a cold cache has
measured nothing. The ramp depends on totals rather than on when any individual
request landed, so unequal replies cannot corrupt it.

## Finding 2b — the slot count is per MODEL, not per host

An earlier version of this document assumed ollama's serving parameters were a
host setting, and used that to justify loading one model per host rather than
all of them. **Measured false on srv1**, which is configured
`OLLAMA_NUM_PARALLEL=2`. Each model loaded alone, GPU verified back to 1 MiB
between every one:

| model | served ctx | slots | llama.cpp `-c` / `-np` | VRAM |
|---|---|---|---|---|
| `qwen2.5-coder:1.5b` | 4096 | 2 | 8192 / 2 | 1.35 GB |
| `qwen2.5-coder:3b` | 4096 | 2 | 8192 / 2 | 2.39 GB |
| `llama3.2:3b` | 4096 | 2 | 8192 / 2 | 3.10 GB |
| **`nemotron-3-nano:4b`** | 4096 | **1** | **4096 / 1** | 2.81 GB |
| `qwen2.5-coder:7b` | 4096 | 2 | 8192 / 2 | 4.86 GB |

Ollama sizes the context and the slot count per model against the memory it has,
so `OLLAMA_NUM_PARALLEL` is a ceiling rather than a setting. A one-model sample
would have recorded 2 slots for a model that gets 1. `build_info` is
`b1-b4d6c7d8f` for all five, so the llama.cpp build is per install.

The served window is 4096 for every one of them, against trained windows of
32768 (qwen2.5-coder), 131072 (llama3.2) and **262144** (nemotron) — a 64× gap on
the last, and the strongest case for why the trained window must never be written
into `context_length`.

## Finding 2c — a model placed on the CPU stays there

Stopping the competing engine is **not** the same as freeing the card. On srv2,
the 1.5B was loaded while vLLM held 10.8 GB of the 12 GB card at
`--gpu-memory-utilization 0.90`; ollama placed it on the CPU, reporting
`size_vram` **0.08 GB**. Stopping the vLLM container afterwards did not migrate
it — the GPU sat at 205 MiB and the model kept running on CPU for the life of
that `llama-server` process. Only restarting ollama with the card already free
put it on the GPU: `size_vram` **1.17 GB**, GPU 1247 MiB, 60% utilisation.

Placement is decided at load time and is sticky. A throughput measurement taken
in the first state measures contention, not the server — and the first srv2
ollama ramp attempted here did exactly that and was discarded. Every ramp now
records the GPU state it ran under, so a contaminated reading is visible in its
own file rather than depending on whoever ran it having remembered.

## Finding 3 — the seed is observable, and the two engines differ absolutely

`llama-server`'s `/slots` reports `params.seed = 4294967295` on both rigs. That
is `0xFFFFFFFF`, llama.cpp's "draw a fresh random seed per request". vLLM's
`/server_info` reports `seed=0` on both rigs — vLLM 0.26.0 *defaults* to a seed
rather than to none.

So on the sampled arm (temperature 0.7), **ollama's draws are irreproducible by
construction and vLLM's are reproducible by default**. Neither fact was on
disk. "Observed, never set" turns out to be a statement about what this tree
dispatches, and not a statement about the server.

## Finding 4 — dev mode is 18 routes, and it is measured now, not assumed

Same server, same model, same flags, `VLLM_SERVER_DEV_MODE` the only difference:

| | dev ON | dev OFF |
|---|---|---|
| routes in `/openapi.json` | **43** | **25** |
| `/server_info` | 200 | **404** |
| probe-set fields answered | **3 of 4** | **1 of 4** |

Exactly 18 routes are gated, every one of them 404 when the flag is unset:
`/abort_requests`, `/collective_rpc`, `/finish_weight_update`, `/get_world_size`,
`/init_weight_transfer_engine`, `/is_paused`, `/is_sleeping`, `/pause`,
`/reset_encoder_cache`, `/reset_mm_cache`, `/reset_prefix_cache`, `/resume`,
`/server_info`, `/sleep`, `/start_draft_weight_update`, `/start_weight_update`,
`/update_weights`, `/wake_up`.

srv1 and srv2 declare **identical** 43-route tables with the flag on, so this is
a property of the version and not of the deployment. `/tokenizer_info`, which
vLLM's current documentation lists, is **404 on 0.26.0** — the second place the
docs and the running build disagree.

Routes answering GET in both modes: `/health`, `/load`, `/metrics`,
`/openapi.json`, `/ping`, `/v1/models`, `/version`.

## Finding 5 — exposure

| | srv1 | srv2 |
|---|---|---|
| ufw | **active** | **inactive** |
| ollama 11434 | `ALLOW 100.64.0.0/10` — tailnet only | open, all interfaces |
| vLLM 8000 | no rule → not admitted | open, all interfaces |

Verified by reaching srv2 **from srv1 over the LAN** (192.168.1.132, not the
tailnet): `/v1/models` 200, `/api/tags` 200, `/server_info` 200 — all
unauthenticated. Internet reachability depends on the router at 192.168.1.1,
which was not inspected, and is therefore not claimed either way.

vLLM's own security documentation (fetched 2026-08-18) states that the server has
no authentication by default; that `--api-key` covers only the `/v1`, `/v2` and
`/inference` prefixes and is bypassable through `/invocations`,
`/generative_scoring`, `/pooling` and `/score`; and — verbatim — "Never set
`VLLM_SERVER_DEV_MODE=1` in production environments."

On srv2 the flag is set, the port is open on every interface, and there is no
host firewall. The dev routes include `/collective_rpc`, which executes a method
inside the engine process.

## Finding 6 — ollama is llama.cpp, and the build that does the arithmetic is not recorded

`serving_build` records ollama's version (`0.32.4` / `0.32.5`). The process that
actually runs the model is `/usr/local/lib/ollama/llama-server`, and it reports
`build_info: b1-b4d6c7d8f` — the same on both rigs, and a different identifier
from either ollama version. ADR-0024's argument ("a serving build nothing
recorded has already moved results twice") applies to the inner build at least as
much as to the outer one.

The command line also carries serving settings that reach no HTTP endpoint:
`--flash-attn auto`, `-b 1024 -ub 1024`, `--context-shift --keep 4`,
`--no-jinja --chat-template chatml`. `/props`'s
`default_generation_settings.params` carries 39 more, including every sampler
parameter.

## Finding 7 — vLLM's batch width is unaskable, not unknowable

`max_num_seqs` is on **no endpoint** of vLLM 0.26.0: not `/server_info`'s full
engine config, not any of the 122 `/metrics` series, not `/v1/models`. Searched
across every parameterless GET in each server's own route table, on both rigs.

`vllm:cache_config_info` carries `kv_cache_max_concurrency`, which looks like the
answer and is KV-cache capacity: srv1 ran `--max-num-seqs 8` and reported
**16.004**; srv2 ran **16** and reported **5.314**. It moves opposite to the
quantity it resembles, so a capture that took it would record a number that
shrinks as concurrency grows.

**The ramp recovers it anyway.** srv1 vLLM, launched `--max-num-seqs 8`:

| n | tok/s | mean latency |
|---|---|---|
| 1 | 42.6 | 3.00 s |
| 2 | 27.6 | 9.28 s |
| 3 | 40.8 | 9.38 s |
| 4 | 54.4 | 9.40 s |
| 6 | 80.5 | 9.53 s |
| **8** | **106.5** | **9.60 s** |
| 12 | 80.9 | 12.74 s |
| 16 | 106.8 | 14.42 s |
| 24 | 107.3 | 19.13 s |

Two signatures, both at 8. Throughput climbs to 106.5 and then plateaus (106.8,
107.3). And mean latency is **flat at 9.28–9.60 s for every n from 2 to 8** —
every request is in one batch and they finish together — then jumps at n=12 when
the ninth request has to wait. The knee is the flag.

**Replicated within 1% at every level** (42.4 / 28.0 / 40.9 / 54.4 / 80.8 /
**106.8** / 81.2 / 106.9 / 107.3). The two dips reproduce as well, which makes
them deterministic scheduler behaviour rather than noise — and a third
independent reading of the same 8. n=12 is one full batch of eight plus a
two-thirds-empty batch of four, so it pays two batch-times for one and a half
batches of work and drops to ~81; n=16 is two full batches and recovers to 106.9.

The two runs also overlapped different work on the *other* rig — the first with
srv2's ollama ramp, the second with srv2's census sweep — and agree to 1%. So
driving two machines from one client does not corrupt the client-side timing,
which had been a stated risk and is now a measured non-issue.

So the method has now recovered a configured value it could not read on both
engines: `OLLAMA_NUM_PARALLEL=2` on ollama, `--max-num-seqs 8` on vLLM.

`/collective_rpc` exists under the dev flag and would very likely reach the
scheduler config directly. It was not called: it executes a method inside the
running engine, which is not the endpoint describing itself.

## What this means for the per-run capture

`observed.json` is written immediately before a sweep's first draw, so it must
not run the ramp — measuring concurrency means creating concurrency, which fills
the KV cache and warms the prefix cache of the server about to be measured. The
split is therefore not a compromise:

- **`observed.py`** records what the endpoint *says*, passively, per run.
- **`census.py`** records what the machine *is*, with host access and with
  experiments, once per configuration — because concurrency is a property of
  `(host, engine, config)` and does not change between sweeps.

Both `concurrency` and `seed` on ollama are refusals of **reach**, not of
existence, and the refusal text says so and names where the answer lives.

## Files

- `routes.json` — declared route tables and per-route GET status for srv1 dev-on,
  srv1 dev-off and srv2 dev-on
- `concurrency.json` — the ramps, per host and engine, with the token counts each
  server reported
- `census.json` — every model on both rigs, with what each endpoint said about it


---

## Correction, 2026-08-19 — the concurrency method, twice

Finding 2's method statement and Finding 7's numbers were both revised after two
further vLLM configurations were measured. The corrections are recorded rather
than edited in, because what was wrong is the useful part.

**The first rule read the throughput plateau alone.** It returned **6 for both
ollama hosts** — one configured `-np 2` and one `-np 1` — so it could not
distinguish the two configurations it was meant to measure. Any claim that "the
ramp recovers `OLLAMA_NUM_PARALLEL`" rests on reading the curve by eye, which is
how it was originally reported here, and is withdrawn.

**The second rule required the latency plateau to agree.** It fixed ollama and
then threw away a correct answer: a vLLM launched `--max-num-seqs 16` reports a
throughput plateau at 16 and a latency plateau at 8, because latency does not
stay flat until queueing begins — a larger batch is slower per request even when
every request fits. At n=12 of 16 slots, latency had risen 25% with no queueing.

**What holds, measured 2026-08-19 on srv1:**

| server | throughput plateau | max speedup | configured | reported |
|---|---|---|---|---|
| vLLM `--max-num-seqs 8` | 8 | 2.52 | 8 | **8** |
| vLLM `--max-num-seqs 16` | 16 | 3.94 | 16 | **16** |
| ollama `-np 2` | 6 | 1.69 | 2 | **none** |
| ollama `-np 1` | 6 | — | 1 | **none** |

The plateau is the batch width on a server that batches, and two different
configured values were recovered on the same engine. Ollama's curve barely rises
(1.69x), so the point at which it flattens is unrelated to its slot count — which
is consistent with an independent throughput study finding that this engine's
parallelism setting behaves as queue depth rather than as a batch.

`BATCHING_SPEEDUP = 2.0` separates those groups and is a **judgement calibrated
on four measurements**, not a derived constant. A fifth configuration could move
it.

## Correction — the exclusion gate, reproduced on hardware

A review predicted from the source that the orchestrator's exclusion gate read
*total* card usage rather than each backend's own footprint, so a backend holding
nothing would report failure whenever another engine held the card. The first
end-to-end survey reproduced it exactly:

```
q15-vllm-s16 REFUSED: ['ollama'] would not give up the card: ollama=4916 MiB
family qwen2.5-coder-1.5b: … [2 of 3]
```

The 4,916 MiB was vLLM's own allocation. After the fix, the same survey measured
all three entries and the family reported `[3 of 3]`. The unit tests passed
throughout, because the stub backends always report a successful release.

## Correction, 2026-08-19 — two cited files were never written, and the survey that would have filled them

The `## Files` section above names `concurrency.json` and `census.json`. **Neither
exists, and neither ever did** — `git log --diff-filter=A` over this directory
returns one commit, adding `README.md` and `routes.json` only. A record citing
evidence that was never written is worse than one citing none, so the citation is
withdrawn here rather than deleted above.

Where that material actually survives:

| named file | what survives | where |
|---|---|---|
| `concurrency.json` | the four ramps and the rule they falsified | the concurrency correction above; every level of every later ramp in `../calibration-2026-08-19/samples.jsonl` |
| `census.json` | served window, slot count and placement per model | Findings 1, 2b and 2c above; per-model load time and VRAM fraction in the calibration samples |

What is genuinely lost is the raw per-endpoint capture per model — the bytes each
server returned. Re-running the census is the only way back to it.

### The end-to-end survey, recorded here because its result file is gone

`run.py --config configs/srv-full.json --hosts srv1` ran twice on 2026-08-18. Both
runs wrote their result JSON to a transient path that no longer exists, so this is
the only record of them. The first run is the one quoted in the exclusion-gate
correction above. The second, against the fixed gate, measured all three entries:

```
q15-ollama-srv1   knee None   (no expectation; the stale expect: 2 was removed)
q15-vllm-s8       knee 8      configured --max-num-seqs 8
q15-vllm-s16      knee 16     configured --max-num-seqs 16
family qwen2.5-coder-1.5b: REFUTED as identical [3 of 3]
  digests are not the same KIND (['checkpoint-tensor digest', 'manifest digest'])
  quantizations (['Q4_K_M', 'auto_awq']) make these different instruments
```

Three things that only a full orchestrator run could establish, and which no unit
test could: release-then-claim frees a shared 6 GB card across an engine switch;
the ramp recovers the batch width through the whole pipeline rather than only in
isolation; and a refused entry does not lose the run — the entries measured before
it were written.

The family verdict is the intended behaviour rather than a failure: `family` is a
**declared** claim that two entries are the same model, and the measurement is
allowed to disagree with it in writing. Here it did, on two independent grounds,
with its denominator attached.

### A trap for the next digest

`/v1/models` is **not byte-stable**. Its model card carries a `created` timestamp
that changes per request — two calls one second apart differ, and the difference
is not client-versus-host. Nothing digests it today (`fingerprint.py` reads
`/server_info`), and nothing should without stripping that field first.
