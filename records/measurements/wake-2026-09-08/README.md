# How long a cold rig takes to answer — the wake measurement

Taken 2026-09-08, to settle **N7** in
[the sleep/wake design](../../plans/sleep-wake.md) (`budgets.wake_timeout_s`),
which §6 of that document flagged as the one number priced from no measurement
at all.

**The result inverts the assumption the design was carrying.** Wake time does
not track model size. It tracks how close the model comes to filling its host's
RAM. srv2 brought up a **35.7 GB** 80B-A3B in **97 s**; srv1 took **203 s** for
a **16.9 GB** model — 2.1× fewer bytes on the slower path. llama.cpp mmaps its
weights and pages them in lazily, so what a wake pays for is memory pressure,
not bytes: KAT's 16.9 GB into srv1's 15 GB of RAM thrashes, and the 80B's
35.7 GB into srv2's 45 GB does not.

The ceiling of this fleet is not "the biggest model". It is "the model closest
to overflowing its host's RAM", and on this fleet that is srv1.

## What ran

Each leg takes the rig down, recreates one service with
`docker compose up -d --force-recreate` through `DOCKER_HOST=ssh://<rig>`, and
polls `http://<rig>:<port>/v1/models` until it returns 200. `measure.sh` timed
from the moment `compose up` returned; `measure2.sh` timed from the container's
own `docker inspect -f '{{.State.StartedAt}}'`, which is the more honest start
and the one the KAT figure was salvaged from after that leg's shell was killed.

| what | rig | engine | size | RAM on host | wake |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B UD-IQ3_XXS, `-c 8192`, `--n-cpu-moe 29` | srv1 | llama.cpp | 12.3 GB | 15 GB | **50–80 s** |
| Qwen3.6-35B-A3B UD-IQ3_XXS, `-c 16384`, `--n-cpu-moe 30` | srv1 | llama.cpp | 12.3 GB | 15 GB | **128 s** |
| KAT-Coder-V2.5-Dev Q3_K_M, 35.5B/A3B, `--n-cpu-moe 32` — srv1's ceiling | srv1 | llama.cpp | 16.9 GB | 15 GB | **203 s** ← worst |
| Qwen2.5-Coder-7B-Instruct-AWQ, **alone on the card** | srv2 | vLLM | 5.2 GB | 45 GB | **82 s** |
| Qwen3-Next-80B-A3B-Instruct Q3_K_M, 79.7B/A3B, `--n-cpu-moe 35` — srv2's ceiling | srv2 | llama.cpp | 35.7 GB | 45 GB | **97 s** |

The 50–80 s row is the design's own §6 figure, taken the same day across two
restarts, and it is the only row not re-taken here.

**Doubling srv1's context cost 48 s of wake** (80 → 128 s) and one expert block
(`--n-cpu-moe` 29 → 30). The window a request gets is `-c` divided by slots, so
`-c 16384` across 2 slots is 8192 per request; that widening was made for the
cohort's 1039-token prompts and it is now the live config.

## What it settles

**N7: `wake_timeout_s = 480.0` is comfortable, not tight.** The measured worst
case on this fleet is 203 s. 480 leaves 2.4× headroom over it and stays above
the door's own 360 s health budget, which is the floor the schema refuses to go
under. The proposed number was right; what it lacked was evidence, and this is
the evidence.

**The design's vLLM figure was inflated, and §6 said so before this ran.**
110–120 s was two units booting sequentially under `depends_on`. A single vLLM
unit alone on an empty card is **82 s** — inside llama.cpp's own 50–128 s band
for the same rig class, not distinguishable from it. Neither engine is
measurably faster to wake, in either direction. The premise usually offered for
scoping sleep/wake to vLLM has no support here.

**N10 has a candidate now, and the vLLM scope excludes it.** §7.7 found the
pressure-driven wake with nothing to wake: srv1's rung is the top of the ladder
and it is scoped out for being llama.cpp. srv2 can serve an **80B-A3B in 97 s**
— a genuine rung above srv1's 35B-A3B, on the rig that is *already* in scope —
but only under llama.cpp. There is no vLLM upgrade path on srv2 at all:
mcgyvr's own fit refuses the 14B AWQ (11.6 GB + 2.0 GB headroom against 12.0 GB
free). So the engine scope, as ruled, excludes the only ladder upgrade this
fleet can offer.

## The files

| | |
|---|---|
| `measure.sh` | legs 1–3: both rigs down, then each rig's ceiling model, then srv2's 7B alone |
| `measure2.sh` | the re-run that produced the 82 s and 97 s figures, timing from `StartedAt` |
| `ladder-moe-ceiling.yaml` | the ceiling spec `mcgyvr emit` was run against — not a working ladder |
| `compose.srv1-kat.yml`, `compose.srv2-80b.yml` | what `emit` wrote from it, and what was run |
| `compose.srv1-16384.yml` | srv1's live model at the widened window (the 128 s row) |
| `compose.srv2-7b-only.yml` | srv2's live 7B with `depends_on` stripped — the per-unit vLLM baseline |
| `kat.geometry.json`, `qwen80b.geometry.json` | read by `src/mcgyvr/serving/ggufscan.py`; the sizes and expert counts above come from these |

Both rigs were restored afterwards: srv1 to Qwen3.6-35B-A3B at 2 slots × 8192,
srv2 to its 3B + 7B vLLM pair.
