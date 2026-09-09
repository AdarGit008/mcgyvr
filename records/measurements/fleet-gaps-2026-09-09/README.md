# Seven gaps the fleet-shape work left open, priced on the live rigs

Taken 2026-09-09 on srv1 and srv2, with the owner's authorisation to re-emit
and restart srv1. `METHOD.md` describes the instrument once; this is the
findings. **39 recorded arms, plus a sleep/wake matrix of 23 steps. 3 arms
failed**, and all three are named at the bottom with what they cost.

Two of the seven items are **decisions rather than measurements** and are
labelled as such. Four headline results:

* **The wake law has an intercept.** Two new blobs on srv1 and two on srv2 turn
  a two-point line into a five-point and a three-point one, and both hosts fit
  a **large positive constant** — 22.5 s on srv1, 48.3 s on srv2 — where
  `wake-timeout.md` §4 chose a proportional form on the grounds that the
  two-point intercept was negative and therefore unphysical.
* **The loading mode costs the card 16–58 MiB, not gigabytes.** The 80B that
  crash-looped under `--load-mode none` on 2026-09-09 **loads and serves** one
  expert block lighter. G1 is not a mode with a hidden VRAM appetite; it is a
  placement sitting 50 MiB from the card's edge.
* **Host RAM is additive across co-resident llama.cpp MoE units, exactly.**
  7.47 + 10.76 = 18.23 GiB of `Shmem`, measured. The law `hold_together`
  declares is now measured — and separately, it is **unreachable on this fleet**
  in the shape the code takes.
* **srv2's production vLLM pair does not come up cleanly.** It crash-restarts
  the 3B one to two times on every cold start, with
  `ValueError: No available memory for the cache blocks`, and
  `restart: unless-stopped` hides it. That is where the "168 s pair restart"
  goes: the two units alone take 100.8 s and 104.4 s.

---

## Step 0 — srv1 is mapped, and that is the production change

`6a2e80d4` dropped the mode gate from 2.0 to 0.5 GiB, so `emit` now places
srv1's Qwen3.6 mapped, and `mcgyvr emit --check --out ~/.mcgyvr/config` exited
4 on one hunk: `--load-mode none` removed, nothing else. `--n-cpu-moe 30`, the
window, the slot count and the image are unchanged, which is what makes the
restart a matched pair for M1.

| | as found (unmapped) | as left (mapped) |
|---|---|---|
| card used / free | 5,126 / 618 MiB | 5,124 / 620 MiB |
| `Shmem` | **8.09 GiB** | **0.03 GiB** |
| `MemAvailable` | **5.29 GiB** | **13.58 GiB** |
| decode (n=3, warm) | 33.30 tok/s | 33.33 tok/s |
| wake | — | 141.5 s |

Healthy on the first attempt; `emit --check` clean on both hosts afterwards.
The trade the 2026-09-09 headroom sweep predicted is what happened: **8.3 GiB
of host RAM returned, decode unmoved to 0.1%, the card unmoved to 2 MiB.**

The old compose is kept as `compose.srv1.unmapped-as-found.yml`; the live file
was backed up to `~/.mcgyvr/config/compose.srv1.yml.bak-20260909-*` before
`emit` overwrote it.

---

## M1 (G1) — the loading mode's cost to the card: **52–58 MiB, and it explains the crash**

**What was unmeasured.** `fit` picks map vs `--load-mode none` from host RAM
alone. srv2's 80B crash-looped under `--load-mode none` on a CUDA allocation
with 18 GiB of host RAM to spare, and loaded mapped in 103 s — so the mode has
a *card* cost nothing models. Evidence: **n=1, at an unknown margin.**

### The margin, measured, at two matched placements on the model that failed

Same model, same `--n-cpu-moe`, same window, two loading modes. Card figures
are the peak of a 1 Hz sampler across the load and the steady state after it.

| host / unit | `--n-cpu-moe` | mapped peak / steady | unmapped peak / steady | **mode's card cost** |
|---|---|---|---|---|
| srv1 Qwen3.6-35B | 30 | 5,110 / 5,124 MiB | 5,126 / 5,140 MiB | **+16 MiB** |
| srv2 Qwen3-Next-80B | 36 | 11,165 / 11,167 | 11,217 / 11,219 | **+52 MiB** |
| srv2 Qwen3-Next-80B | 40 | 8,253 / 8,255 | 8,311 / 8,313 | **+58 MiB** |

n=2 on srv1 per mode (and four further mapped arms agree to 0 MiB), n=1 per
cell on srv2.

**No llama.cpp arm in this campaign spiked.** Across all 23 sampled llama.cpp
arms the peak reads 2–26 MiB *below* the steady state — the last allocation
landing just after the door returned — so there is no transient to model and
the mode's cost is the steady-state difference, present the whole way through.

Four **vLLM** arms did spike, and the largest is a finding rather than noise:
`v-pair-plainB-1` peaked at 10,271 MiB against a 9,445 MiB steady state,
**+826 MiB**, and that arm is the one whose 3B crashed twice (M4). A dying
engine holds the card until its process exits. The two 3B-alone arms peaked
+34 MiB over steady, which is the profiling pass vLLM runs before it sizes its
KV pool.

### The 80B under `--load-mode none` does not crash. It serves.

| arm | wake (StartedAt) | wake (door) | card steady | `Shmem` | decode |
|---|---|---|---|---|---|
| mapped `ncmoe 36` | 105.5 s | 98.7 s | 11,167 MiB | 0.02 GiB | 13.02 tok/s |
| **unmapped `ncmoe 36`** | **117.3 s** | 110.7 s | 11,219 MiB | **25.93 GiB** | **13.46 tok/s** |
| mapped `ncmoe 40` | 104.2 s | 98.0 s | 8,255 MiB | 0.02 GiB | 12.30 tok/s |
| **unmapped `ncmoe 40`** | **118.4 s** | 111.2 s | 8,313 MiB | **28.77 GiB** | 12.81 tok/s |

So `--load-mode none` on this model costs **+13 s of wake** and **+52–58 MiB of
card**, and buys 26–29 GiB of host RAM being allocated rather than cached.

### Which settles G1, and reads the 2026-09-09 crash correctly

`vramfit` predicts 11,958 MiB at `ncmoe 35` and 11,230 at `ncmoe 36`, against
11,911 MiB free on an idle card. Measured, `ncmoe 36` actually uses 11,167 —
`vramfit` **over-predicts by 63 MiB**. Carry that correction to `ncmoe 35` and
the mapped unit really wants about 11,895 MiB, which clears 11,911 by **16
MiB**. Add the mode's 52 MiB and the unmapped unit wants ~11,947 — **36 MiB
past the card**.

**The mode does not have a large VRAM cost. `--n-cpu-moe 35` has almost no
margin, and 52 MiB is enough to decide it.** The failure was correctly
attributed to the mode and incorrectly sized: an `emit` that modelled a 52 MiB
mode cost would still emit `ncmoe 35` mapped and still be 16 MiB from the edge.
What the layout actually needs is a *card* headroom on the geometry path — the
`DEFAULT_HEADROOM_GB` that `fit` applies only when `spec.geometry is None`
(`serving/__init__.py:545`) — not a mode term.

**Still unmeasured:** whether the 52 MiB is constant or scales (two placements
on one model, 6 MiB apart, is not a scaling law); and the mode's card cost on
any engine but llama.cpp.

---

## M2 (G2) — the host-RAM co-residency law

**What was unmeasured.** `hold_together` sums host RAM per host as of
`6a2e80d4`; its docstring says "it is not measured: nothing on this fleet has
run two llama.cpp MoE units co-resident on one host".

### They have now, and the sum is exact

deepseek-coder-v2-16b on `:8080` and Qwen3.6-35B on `:8081`, both
`--load-mode none` with every expert block off the card, so both *allocate*
host memory rather than asking the kernel to cache a blob. Page cache dropped
before each arm; `Shmem` starts at 0.00 GiB every time.

| arm | `Shmem` after | `MemAvailable` drop | card used | wake (StartedAt) |
|---|---|---|---|---|
| deepseek alone (`ncmoe 26`) | 7.47 GiB | 8.31 GiB | 3,413 MiB | 52.0 s |
| Qwen3.6 alone (`ncmoe 40`) | 10.76 GiB | 11.85 GiB | 2,299 MiB | 84.8 s |
| **both together** | **18.23 GiB** | **20.05 GiB** | **5,711 MiB** | 89.9 s |
| *the sum of the two alone* | *18.23* | *20.16* | *5,712* | |

**`Shmem` is additive to 0.00 GiB and the card to 1 MiB.** `MemAvailable` is
additive to 0.11 GiB, 0.5%, and the residual is in the right direction — a
second process shares page cache the first already warmed. Decode was unmoved
by co-residency: 23.17 → 23.58 tok/s for deepseek and 14.60 → 14.41 for
Qwen3.6 (one cold sample each; the difference is inside the instrument).

**The law is right. Sum host RAM per host.** This is the first co-residency of
two llama.cpp MoE units this fleet has run, and it says the arithmetic
`hold_together` performs is the arithmetic the machine performs.

### And on this fleet the sum is a no-op, in both directions

Four `emit` probes with hand-written configs, no rig time (`m2/*.yaml`, each
with its `emit.log`):

| config | declares | `emit` says |
|---|---|---|
| `A-geometry-pair` | the two blobs above, geometry-sized, **two ports** | **two files** — alternatives, not co-residents |
| `B-declared-fits` | two units, card figures declared 4.0 GiB each | one file — co-residents |
| `D-each-alone-passes` | the same, `ram_gb` 30.0 each vs 44.5 GiB available | **accepted** |
| `E-blob-sum-refused` | the same, `disk_gb` 24.0 each | **refused**: "48.00 GB summed with 2.0 GB held back, against 44.60 GB available" |

1. **Two geometry-sized MoE units on one host are never co-residents**, whatever
   ports they take. `alternate()` discriminates on card contention and
   `_placement` fills the card for each unit independently, so their card
   figures cannot sum and they are split into one launch spec per model. The
   arms above had to be run from **hand-written composes** for exactly this
   reason: `emit` will not write that file.
2. **A declared `ram_gb` is not what the sum adds.** `Fit.ram_gb` is
   `placed.ram_gb` only for an unmapped unit; a mapped unit contributes
   `spec.disk_gb`, and a unit with nothing to spill contributes zero
   (`serving/__init__.py:578-583`). `D` declares 60 GiB against 44.5 and passes,
   because what the sum saw was `8.29 + 12.29`.
3. **The one co-resident set this fleet runs contributes zero.** For the live
   config, `Fit.ram_gb` is `0.0` for both vLLM units. srv2's host-RAM sum is
   `0.0` — while the pair measurably costs **5.49 GiB** (below).

So `hold_together`'s RAM arm fires only for a unit that is card-declared *and*
mapped *and* carries a `disk_gb`. Nothing on this fleet is all three.

**A number the sum would want:** a vLLM unit costs **2.92–2.95 GiB of host RAM
regardless of model size** — the 3B (1.95 GiB of weights) and the 7B (4.93 GiB)
are within 0.03 GiB of each other over five arms. It is process, CUDA host-side
and runtime, not weights; the weights are on the card. A per-vLLM-unit constant
is the shape that fits it, and `0.0` is not that constant.

The pair costs **5.49 GiB** against **5.85** for the two summed — 6%
sub-additive, and in the direction two processes on one host should be (shared
libraries, shared CUDA host allocations). Unlike the llama.cpp pair, whose
`Shmem` added to the digit, this one is additive only to about half a
gigabyte, and a sum used as a refusal gate would be conservative by that much.

---

## M3 — `k` is not two coefficients. One axis saturates and the other is a step

**What was unmeasured.** `wake-timeout.md` §5: `k ≈ 2.52` over-predicts KAT by
27% on the blob axis and under-predicts by 2.4× on the experts axis (159.3 s
predicted against 385.3 s measured), which reads like the same conflation
`RAM_HEADROOM_GB` had before it was split.

### The blob axis saturates at about +21% and then stops

srv1 Qwen3.6, mapped, `--n-cpu-moe 30`, balloon set to the clearance. Baseline
is this campaign's four ample mapped arms, **140.75 s** (137.7 / 141.5 / 142.7 /
141.1), which reproduces the 2026-09-09 figure of 140.8 s to 0.1 s.

| clearance vs **blob** | wake | n | vs baseline | implied `k` |
|---|---|---|---|---|
| +1.9 | 140.75 s | 4 | — | — |
| +0.52 *(2026-09-09)* | 139.9 s | 1 | −0.7% | — |
| −0.98 *(2026-09-09)* | 167.9 s | 3 | +19.2% | **2.42** |
| **−2.03** | 169.2, 171.3 → **170.3 s** | 2 | +20.9% | **1.27** |
| **−3.03** | **169.8 s** | 1 | +20.5% | **0.84** |

**The penalty is a plateau, not a slope.** It rises to about +21% by −1 GiB and
does not move again through −3 GiB, where a proportional `k = 2.52` would
predict 228 s against 170 measured — **34% high**. KAT's out-of-sample `k` of
0.66 at −2.71 GiB, the one point §4.1 could not explain, is exactly what a
plateau predicts.

So the blob-axis term should be **bounded, not linear**: something of the shape
`T0 × min(1 + k·s/B, 1.21)` with `k ≈ 2.4` for the first gigabyte, or simply
`T0 × 1.21` for any shortfall at all. Either is an upper bound that stops being
wrong by 33% at three gigabytes.

**One thing the plateau does not cover.** At −3.03 GiB the *decode* fell to
**5.09 tok/s** against 22.1–22.2 at −2.03 and ~25 at ample clearance, on the
same one-cold-sample instrument. `records/measurements/ram-headroom-2026-09-09/`
says "across all nine mode-gate arms decode never degraded" — true over the
range it swept, which stopped at −0.98. **Between −2 and −3 GiB against the
blob, a mapped unit loses its decode too.** This is one cold sample with no
warm-up and the steady-state figure is unmeasured; it is reported because a
5× drop is not an instrument artefact even if its size is uncertain.

### The experts axis is a step, and the cliff is now bracketed to 0.63 GiB

srv1 Qwen3.6, `--load-mode none`, same unit. Baseline is this campaign's two
ample unmapped arms, **133.0 s** (132.3 / 133.7), against 132.9 s on
2026-09-09. Clearance is `MemAvailable − 9.2 GiB` of spilled experts.

**The decode column mixes two instruments** and is here only to show which
arms collapsed: the 2026-09-09 rows are a mean of three warm samples, this
campaign's two are one cold sample each (which reads 3–5 tok/s low on this
unit even at ample clearance). The wake column is the same instrument
throughout.

| clearance vs **experts** | wake | n | vs baseline | decode |
|---|---|---|---|---|
| +5.0 *(2026-09-09)* | 132.9 s | 3 | — | 33.2 |
| +0.55 *(2026-09-09)* | 131.5 s | 1 | −1.1% | 33.26 |
| **+0.17** | **134.0 s** | 1 | +0.8% | 28.50 |
| **−0.34** | **135.7 s** | 1 | +2.0% | 26.82 |
| −0.97 *(2026-09-09)* | **385.3 s** | 1 | **+190%** | **10.78** |

`k` implied at −0.34 is **0.73**; at −0.97 it is **24.1**. Those are not one
coefficient with a spread and they are not two coefficients either: **the
experts axis is a step function**, flat until it falls off, and no linear term
can represent a 33× change in slope across 0.63 GiB.

**G4 moves.** The cliff was "somewhere in the 1.5 GiB between +0.55 and −0.97".
It is now **somewhere in the 0.63 GiB between −0.34 and −0.97**, and −0.34 is
clean on every axis the earlier campaign measured. That does **not** argue for
lowering `REFUSAL_RAM_HEADROOM_GB`: the three reasons it keeps 2.0 — a silent
failure, an unlocated edge, and a margin that refuses nothing this fleet runs —
all still hold, and the edge is merely less unlocated than it was.

### What splitting `k` properly would take, bounded

`wake-timeout.md` §4.3 budgets 12 arms for the blob axis and 6 for the experts
axis. On this evidence that is the wrong shape of spend, because neither axis
is a coefficient:

* **blob axis: 4 more arms.** The plateau needs its knee located between +0.52
  (clean) and −0.98 (+19%) — three clearances at n=1 — plus one repeat of the
  −3.03 arm with a proper warm-up and three decode samples, to settle whether
  the decode collapse is steady state.
* **experts axis: 6 arms.** Bisect −0.34 → −0.97 at three points, n=2. That
  locates the step to about 0.15 GiB, which is as fine as a refusal gate ever
  needs.
* **the rest of §4.3's 18 arms buys nothing**, because it is fitting a slope to
  a plateau and a slope to a step.

---

## M4 — wake rate coefficients: the intercept the two-point fit could not see

**What was unmeasured.** `r(srv1)` was n=2 models, `r(srv2)` n=1,
`r(srv1, vLLM)` did not exist, and `T_cold_vllm` rested on one measurement plus
one cross-campaign subtraction.

### `r(srv1, llama.cpp)`: four blobs, and the constant is real

New blobs are emitted by `fit` at 4096 per slot over 2 slots, cold cache,
production `swappiness=60`, mapped, ample clearance.

| blob | GiB | wake | n | s/GiB |
|---|---|---|---|---|
| **Ling-3.0-tiny Q4_K_M** | **4.57** | 71.1, 74.1 → **72.6 s** | 2 | 15.9 |
| deepseek-coder-v2-16b *(2026-09-09)* | 8.29 | 85.7 s | 1 | 10.3 |
| **gemma-4-26B-A4B IQ3_XXS** | **10.62** | 125.1, 125.3 → **125.2 s** | 2 | 11.8 |
| Qwen3.6-35B IQ3_XXS *(re-taken)* | 12.30 | 137.7, 141.5, 142.7, 141.1 → **140.75 s** | 4 | 11.4 |
| Qwen3.6-35B *(2026-09-09, `swappiness=0`)* | 12.30 | 140.8 s | 3 | 11.4 |

```
affine        wake = 22.5 s + 9.41 s/GiB    (r = 0.106 GiB/s)   R² = 0.929
proportional  wake =           11.55 s/GiB  (r = 0.087 GiB/s)   R² = 0.876
```

**The intercept is positive and about 22 seconds.** §4 of `wake-timeout.md`
chose the proportional form for one stated reason — the two-point affine fit
gives `a = −28.2 s`, unphysical. With four blobs the sign flips and the
constant is physical: container create, CUDA context, header parse, warm-up.

The proportional form's error is worst exactly where a fluid ladder will live.
At Ling's 4.57 GiB it predicts 49.7 s against **72.6 s measured — 32% low**,
and a budget that is 32% low is a budget that abandons a wake about to land.

### `r(srv2, llama.cpp)`: three blobs, a bigger intercept, and a worse fit

| blob | GiB | wake | n | s/GiB |
|---|---|---|---|---|
| **deepseek-coder-v2-16b** | **8.29** | 51.9, 50.1 → **51.0 s** | 2 | 6.2 |
| **Qwen3.6-35B IQ3_XXS** | **12.29** | 80.4, 79.5 → **79.9 s** | 2 | 6.5 |
| Qwen3-Next-80B Q3_K_M *(2026-09-09)* | 35.67 | 102.9 s | 1 | 2.9 |

```
affine        wake = 48.3 s + 1.58 s/GiB   (r = 0.633 GiB/s)   R² = 0.807
proportional  wake =           3.40 s/GiB  (r = 0.294 GiB/s)   R² = −0.710
```

**The proportional fit is worse than a horizontal line** (a negative R² means
exactly that). `r(srv2) = 0.3466 GiB/s` — the single-point figure `formulas.md`
F3.1 carries — predicts deepseek at 23.9 s against **51.0 s measured, 53% low**.

**But the affine fit is not good either, and the R² flatters it.** The three
points are strongly non-linear and the 80B has all the leverage. Fit a line to
the two *new* blobs alone — 7.22 s/GiB, intercept −8.9 s — and extrapolating it
to 35.67 GiB predicts the 80B at **249 s**; it wakes in **102.9**. Read the
other way, the whole-set affine fit misses both small blobs (61.4 s predicted
against 51.0, 67.7 against 79.9).

**No line fits srv2's three points, in either form.** The most that can be said
is that the two blobs under 13 GiB wake at about 6.2–6.5 s/GiB and the 80B at
2.9, so the relationship is concave, and `r(srv2) = 0.3466 GiB/s` is a figure
taken at the concave end and applied at the steep one.

**A hypothesis these arms name and then refuse.** Under mmap the load touches
what it uploads to the card and the CPU-side experts are faulted in later, so
wake might track *bytes uploaded* rather than blob. The three srv2 units are
card-resident to 10.50, 10.74 and about 11.6 GiB and wake in 51.0, 79.9 and
102.9 s — 4.9, 7.4 and 8.9 s per card-GiB. That is no more constant than the
blob rate, in the opposite direction. **Neither predictor survives three
points**, and settling it needs a fourth and fifth srv2 blob chosen to break
the correlation between blob size and offload depth, which none of the
available checkpoints does.

### `T_cold_vllm`: measured rather than subtracted, and 17% higher

`depends_on` stripped, `restart: no`, one unit per compose, page cache dropped.

| unit | blob | wake (StartedAt) | wake (door) | n | card | host RAM |
|---|---|---|---|---|---|---|
| **3B-AWQ alone** | 1.95 GiB | 99.8, 101.7 → **100.8 s** | 93.7, 94.5 | 2 | 2,795 MiB | 2.93 GiB |
| **7B-AWQ alone** | 4.93 GiB | 104.9, 104.2, 104.1 → **104.4 s** | 98.3, 97.7, 97.4 | 3 | 7,795 MiB | 2.92 GiB |

**The constant form is confirmed and the constant is wrong.** §2.2 has 82 s for
the 7B (n=1, 2026-09-08) and a derived 86 s for the 3B; measured, they are
**104.4 s and 100.8 s** — 3.5% apart across a 2.5× blob difference, which is as
clean a constant as this fleet produces, and 17–27% above the figures in the
plan. `T_cold_vllm(srv2) = 103 s ± 2` is the number.

**And the subtraction that produced 86 s was invalid**, for a reason the arms
below make visible: the pair does not serialize, and it does not come up clean.

### The pair is 172 s because it crashes, not because it queues

| arm | door clock | `StartedAt` clock | 3B restarts | 7B restarts |
|---|---|---|---|---|
| production pair, arm 1 | 171.7 s | 89.8 s | *(not recorded)* | *(not recorded)* |
| production pair, arm 2 | 172.1 s | 91.7 s | **2** | **1** |
| sleep-mode pair, arm 1 | 133.7 s | 141.4 s | 0 | 0 |
| sleep-mode pair, arm 2 | 135.8 s | 142.9 s | 0 | 0 |

On every clean arm in this campaign the two clocks differ by a constant +7 s —
the compose-up before the container starts. Where they differ by −80 s, a
container has restarted and reset its own `StartedAt`. The container watcher
caught it and snapshotted the log:

```
(EngineCore) File ".../vllm/v1/core/kv_cache_utils.py", line 758,
             in _check_enough_kv_cache_memory
(EngineCore) ValueError: No available memory for the cache blocks. Try
             increasing `gpu_memory_utilization` ...
(APIServer)  RuntimeError: Engine core initialization failed.
```

The 3B is started by `depends_on: service_started` as soon as the 7B's
container is *running* — not when it has finished taking its 0.72 of the card —
so the 3B profiles memory against a card the 7B is still growing into, finds
nothing for its KV blocks, and dies. `restart: unless-stopped` retries until
the 7B has settled. **Three container deaths per cold start of the live
ladder, on the arm that recorded them.**

Consequences, all of which matter to a wake budget:

* **`depends_on` does not sequence loading.** F6.1's "the sum over sequenced
  units" describes something this fleet does not do: the units load
  concurrently and contend. 100.8 + 104.4 = 205 s; the pair takes 172 s.
* **The 168 s pair figure is not a wake, it is a wake plus two retries.** No
  budget should be derived from it, and the 86 s subtraction built on it should
  be withdrawn.
* **`condition: service_healthy`, or a start-period, would probably remove
  it** — untested, and a `src/` change, so it is reported rather than made.

### `r(srv1, vLLM)` — still does not exist, and here is what it would take

srv1 **has** `vllm/vllm-openai:v0.26.0` and
`models--Qwen--Qwen2.5-Coder-3B-Instruct-AWQ` in its HF cache, so the arm is
reachable: the 3B at `--gpu-memory-utilization 0.60` would ask about 3.4 GiB of
srv1's 5.7 GiB free card, and `--dtype float16` would be needed because TU116
has no bfloat16. It was not run: it is a first deployment of a new engine on a
rig that hard-locks under load, it needs a compose nothing in the tree writes,
and the arms already queued were worth more. **Three arms, and one of them
carries a real risk of a lock.**

---

## M5 (O12) — what `--enable-sleep-mode` costs

**What was unmeasured.** srv2's vLLM units launch without
`--enable-sleep-mode` and without `VLLM_SERVER_DEV_MODE=1`, so `/sleep` is 404
and sleep cannot fund a wake on the live ladder. Nobody had priced the flag.

Two arms of each, alternating, cold cache, the same pair otherwise unchanged:

| | production pair | `--enable-sleep-mode` pair |
|---|---|---|
| cold start (door clock) | 171.7, 172.1 s | **133.7, 135.8 s** |
| container restarts | 1–2 per unit | **0** |
| card, both serving | 9,613 / 9,445 MiB | **10,641 / 11,257 MiB** |
| host RAM | 5.49, 5.49 GiB | 5.58, 5.55 GiB |
| 7B decode (n=3) | 68.83, 68.87 tok/s | 68.89, 68.87 tok/s |
| 3B decode (n=3) | 127.81, 128.21 tok/s | 127.81, 127.91 tok/s |
| 7B / 3B TTFT | 0.167–0.192 s | 0.168–0.195 s |
| `/is_sleeping` | **404** | **200** |

**The flag costs decode nothing and TTFT nothing** — under 0.2% on both units
over n=3 samples each in four arms, far inside the instrument. It costs **host
RAM 0.06–0.09 GiB**, which is noise on a 45 GiB host.

**It costs the card 1.0–1.8 GiB**, and that is the real price: 9,445–9,613 MiB
without, 10,641–11,257 MiB with, at identical `--gpu-memory-utilization`. The
sleep allocator (`CuMemAllocator`) reserves the declared fraction up front
instead of profiling into it. Both arms are within the card, but on a 12 GiB
card that is a gigabyte and a half of headroom spent on a capability.

**And it is 36 s *faster* to start, because it does not crash.** Reserving the
card up front is presumably also what stops the 3B racing the 7B for KV blocks.
That is a benefit the flag was not being considered for, and on this evidence
it is the larger one: it turns a three-crash cold start into a clean one.

**Not measured:** the flag's effect under concurrent load (all decode figures
here are single-stream), and whether the card cost is proportional or fixed
(two units, 1.0 and 1.8 GiB apart across arms — the spread within the
sleep-mode arms is itself 616 MiB, which is unexplained).

---

## M6 (O13) — what a sleeping co-resident actually leaves

**What was unmeasured.** `emit` sizes a placement against an *idle* card, and
the only figure anyone had for a card with sleepers on it was one point.

The full level-2 matrix, on the sleep-mode pair (`gpu-memory-utilization` 0.26
and 0.72), 12,288 MiB total, 377 MiB reserved:

| state | card used | **card free** | 3B releases | 7B releases | sleep | wake |
|---|---|---|---|---|---|---|
| both serving | 10,601–10,641 | 1,271–1,311 | — | — | — | — |
| **3B asleep** | 7,059 | **4,853** | 3,562 MiB | — | 0.27 s | 0.25 s |
| **7B asleep** | 4,039 | **7,873** | — | 6,562 MiB | 0.32 s | 0.32 s |
| **both asleep** | **477** | **11,435** | 3,562 | 6,562 | 0.24 / 0.29 s | 0.25 / 0.31 s |

The 2026-09-09 figure was 503 used / 11,409 free; this reads 477 / 11,435, a
26 MiB difference and the same finding. **The residual is two live CUDA
contexts** — a sleeping vLLM process gives back its weights and its KV pool,
never its context.

With the corrected `vramfit` figures (which over-predict by 63 MiB, M1):

| what fits the card the sleepers leave | `emit` asks | measured free | verdict |
|---|---|---|---|
| 80B `ncmoe 35`, both asleep | 11,958 MiB | 11,435 | **short by 523** |
| 80B `ncmoe 36`, both asleep | 11,230 (11,167 real) | 11,435 | **fits, 268 MiB spare** |
| 80B `ncmoe 40`, 7B asleep only | 8,318 (8,255 real) | 7,873 | **short by 382** |
| 80B `ncmoe 41`, 7B asleep only | 7,590 (7,527 real) | 7,873 | fits, 346 MiB spare *(not run)* |
| 80B, 3B asleep only | — | 4,853 | needs `ncmoe ≥ 45` *(4,615 real)* |

**So a sleeping co-resident is worth a *specific* number of expert blocks, and
the number depends on which co-resident sleeps:** two blocks lighter if only
the 7B sleeps, nine if only the 3B does, and `emit`'s own placement if both do.
The release itself is exactly additive — the 3B hands back 3,562 MiB and the 7B
6,562, and both asleep hands back 10,124, which is those two to the digit. That
is the table `emit` would need to size against a runtime card, and it is now
measured for all four states of this pair.

**The health-probe trap reproduces.** Both units asleep at level 2 answer
`GET /v1/models` with **200**, and both report `{"is_sleeping":true}`. The door
was taught to ask the second question on 2026-09-09 (`b4e9ea8e`); this confirms
the first question is still not enough.

**Not measured:** a card left by a sleeper *and* a live co-resident at once
(three-way), and whether the residual context grows with the number of sleep
cycles — it read 477 MiB before any level-1 sleep and 503 MiB after, which is a
26 MiB difference with n=1 and no mechanism.

---

## M7 (O14) — level 1 is a decision, and here is what a ban needs

**This is a decision, not a measurement.** The finding was already taken on
2026-09-09; the campaign's job was to confirm it reproduces on the current
build and to gather what a ban has to be written against. It reproduces
exactly.

| step | `MemAvailable` | card used | sleep | wake |
|---|---|---|---|---|
| before | 39.06 GiB | 10,601 | — | — |
| 3B asleep L1 | 35.94 | 7,045 | 1.37 s | — |
| 3B awake | **35.92** | 10,607 | — | 0.42 s |
| 7B asleep L1 | 25.57 | 4,065 | 3.78 s | — |
| 7B awake | **25.60** | 10,627 | — | 0.79 s |

**3.14 GiB kept by the 3B, 10.32 GiB by the 7B, 13.46 GiB in total**, with both
units awake and serving. The 2026-09-09 figure was 13.46 GiB. Identical.

Three further things a ban should be written against, each measured here:

1. **A level-2 sleep does not release it.** After the level-1 cycles, sleeping
   both units at level 2 left `MemAvailable` at 25.58–25.59 GiB, and it was
   still 25.64 GiB after sixty seconds idle. The card went all the way back to
   503 MiB used; the host RAM did not move at all.
2. **It is bounded, not a leak.** A second level-1 cycle on each unit cost
   nothing further: 25.62 GiB after, against 25.63 before. The buffer is
   allocated once and reused, and it is permanent for the process's lifetime.
   **Only a container restart recovers it** — the restore at the end of this
   campaign put srv2 back to 39.23 GiB.
3. **It is slower and buys nothing.** Level 1 sleeps in 1.37/3.78 s against
   level 2's 0.24–0.32 s, wakes in 0.42/0.79 s against 0.25–0.32 s, and
   **releases the same card** (7,045 vs 7,059 MiB for the 3B; 4,065 vs 4,039
   for the 7B — 14 and 26 MiB apart). Its only distinguishing property on this
   fleet is the host RAM it never returns.

The exchange rate is the sentence a ban wants: **10.32 GiB of host RAM
surrendered permanently to free 6.5 GiB of card that level 2 frees for
nothing.** The endpoint to refuse is `POST /sleep?level=1`; the safe one is
`POST /sleep?level=2`; and the ban belongs wherever the runtime chooses a sleep
level, not in `emit`, because nothing `emit` writes can reach it.

---

## Arms that failed, and what they cost

| arm | why | cost |
|---|---|---|
| `v-pair-plain-1` (2nd) and `v-pair-sleep-1` (2nd) | **my own label collision.** The arm table listed each label twice at `repeats: 1`, so both instances got index 1 and minted the same RUN_ID. Gate 5 refused the re-use by name — it is write-once and it said so. Re-run as `v-pair-plainB` / `v-pair-sleepB`. | **2 arms, ~10 min** |
| `v-3b-alone-1` | a transient ssh timeout to srv2 (`connect to host 100.69.72.51 port 22: Connection timed out`). Gate 2 refused to enter a rig whose lease it could not read. The rig answered 40 s later. | **1 arm, ~4 min** |
| `srv1 4b-Q4_K_M` — never launched | `emit` refused it: gpt-oss declares `sliding_window 128` and no per-layer pattern, so "the cache cannot be sized, and nothing is placed from an invented split". `okf/must-read/touching-rigs.md` documents this exactly. A 3.00 GiB blob — the most discriminating point for the srv1 intercept — was therefore unavailable. | **0 rig time** |
| `m1-srv1-mapped-1`'s sampler | the 1 Hz sampler collected **0 rows across a 141 s load**: its `pkill -f mcg-sample.sh` matched the ssh command line that contained those characters and killed the invoking shell. Fixed with a pid file; every later arm has 78–351 samples. The peak figure for that one arm is missing and was re-taken by four later mapped arms. | **0 arms, 1 lost instrument reading** |

**One measurement is irreproducible from the tree as it stands.** Another agent
was editing `src/` throughout; the door opened rounds `r11` through `r25` by
itself and the product hash under which each arm ran is in that arm's
`door-*.log`. No arm's *result* depends on the hash — none of them exercise
`src/` beyond `emit` and the door — but the M2 `emit` probes (`m2/*/emit.log`)
were taken against whatever `serving/__init__.py` was at the time, and if
`hold_together` or `alternate` moved during the campaign the four verdicts in
that table would need re-taking. `emit --check` was clean at the start and at
the end.

---

## The final live state

Verified after the last arm:

| | srv1 | srv2 |
|---|---|---|
| serving | Qwen3.6-35B-A3B, `--n-cpu-moe 30`, 2 × 8192, **mapped** | the 3B + 7B vLLM pair, `--max-model-len 4096` |
| endpoint | `:8080/v1/models` → **200** | `:8001` → **200**, `:8002` → **200** |
| card | 5,124 used / 620 free MiB | 9,613 used / 2,299 free MiB |
| `MemAvailable` | 13.51 GiB | 39.23 GiB |
| `vm.swappiness` | **60** | **60** |
| balloons | none | none |
| `/is_sleeping` | n/a | **404** — sleep mode is off again, as found |
| `emit --check --out ~/.mcgyvr/config` | **clean** | **clean** |

The one deliberate difference from how the day began is that **srv1 is mapped**,
which was the owner-approved production change. Every measurement compose,
container watcher and sampler was removed from both rigs.

---

## The files

| | |
|---|---|
| `METHOD.md` | the instrument, described once |
| `rig.py` | the primitives: door, 1 Hz sampler, balloon, meminfo, decode |
| `wake_rate.py` + `arms-srv1-*.json`, `arms-srv2-*.json` | one arm = one cold llama.cpp wake |
| `vllm_arms.py` + `arms-vllm*.json` | vLLM cold starts, with and without the sleep flag |
| `sleep_matrix.py` | M6 and M7: every level × every combination |
| `coresidency.py` | M2's live half: two llama.cpp MoE units on one host |
| `make_config.py`, `emit/` | the throwaway configs `emit` sized the new blobs from |
| `m2/` | the four `emit` probes of `hold_together`, each with its `emit.log` |
| `step0_srv1_mapped.py` | the re-emit and restart |
| `analysis.py`, `collect_door.py` | every table above, recomputed from the raw files |
| `results-*.json`, `m1-*.json`, `m2-*.json`, `m6-m7-*.json` | every arm's raw figures, failures included |
| `door-up-after.json` | the door's own clock for every arm |
| `logs/` | door transcripts, the 1 Hz samples, the captured container crash logs |
| `compose.srv1.unmapped-as-found.yml`, `compose.srv2.pair-as-found.yml` | the live ladder as the campaign found it |
| `compose.srv2-80b-{mapped,unmapped}-ncmoe{35,36,38,40}.yml` | M1's matched pairs |
| `compose.srv2.m2-*.yml` | M2's co-residency, which `emit` will not write |
