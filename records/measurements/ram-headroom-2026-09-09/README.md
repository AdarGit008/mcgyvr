# What the 2 GiB of RAM headroom is worth — priced on both rigs, with the fleet's own models

Taken 2026-09-09 to settle the threshold `records/measurements/load-mode-2026-09-08/`
left open. That measurement showed `--load-mode none` bought nothing on srv1 and
argued the trigger should be the blob genuinely not fitting. It could not say how
much headroom is *enough*, because it never varied the headroom. This does.

**Result: `RAM_HEADROOM_GB = 2.0` is far too large for the mapping decision, and
what it is protecting is not what the code says it protects.** Nothing measurable
degrades between +2.0 and +0.5 GiB of clearance. Below zero the cost is real,
reproducible, and lands entirely on **wake** — decode throughput never moved at
any clearance on any of the three models.

## What ran

One arm = one (model, clearance) pair, where

    clearance = idle MemAvailable - blob

is set by holding host RAM in a locked balloon (`balloon.py`: anonymous, touched,
`mlockall`'d — so neither reclaimable as page cache nor swappable, which is what
an unmapped co-resident's experts are; `oom_score_adj` pinned at 1000 so the
kernel would take the balloon and not the model). Every model is served
**mapped**; the window, the offload and the card figures are whatever `emit`
chose and are identical across that model's arms. The page cache is dropped
before every wake, so each wake is genuinely cold. `vm.swappiness` was 0 for the
campaign and is restored to 60.

Each arm: `serve down` through the door, balloon, drop caches, `serve up`, wake
timed from the container's own `StartedAt`, one discarded warm-up and three
measured samples (160 tokens, `temperature 0`, `cache_prompt false`, identical
prompt), with `/proc/vmstat` read either side.

## The sweep

| rig / model | blob | clearance | wake | majfault @ wake | majfault @ decode | decode |
|---|---|---|---|---|---|---|
| srv1 Qwen3.6-35B-A3B IQ3_XXS | 12.30 GiB | +1.93 | **140.8 s** (n=3) | ~9,180 | 5–14 | 32.7–33.4 tok/s |
| | | +0.52 | 139.9 s | 10,265 | 111 | 33.03 tok/s |
| | | −0.98 | **167.9 s** (n=3) | ~12,150 | 15–110 | 31.4–33.1 tok/s |
| srv1 deepseek-coder-v2-16b | 8.29 GiB | +1.93 | 85.7 s | 5,938 | 25 | 34.67 tok/s |
| | | +0.50 | 94.9 s | 9,044 | 47 | 34.56 tok/s |
| | | −0.98 | 116.3 s | 10,487 | 106 | 33.16 tok/s |
| srv2 Qwen3-Next-80B-A3B Q3_K_M | 35.67 GiB | +2.02 | 102.9 s | 5,372 | 0 | 29.71 tok/s |
| | | +0.48 | 103.7 s | 145,596 | 519 | 29.51 tok/s |
| | | −0.84 | 108.0 s | 35,511 | 23 | 29.19 tok/s |

The srv1 Qwen rows at +1.9 and −1.0 are means of three arms run **alternating**
(+1.9, −1.0, +1.9, −1.0), because the rig's own drift is what a single pair
cannot separate from the effect:

| arm | +1.9 | −1.0 |
|---|---|---|
| first pass | 141.1 s | 170.4 s |
| repeat r1/r2 | 141.3 s | 166.8 s |
| repeat r3/r4 | 140.0 s | 166.5 s |
| **mean** | **140.8 s** | **167.9 s** |

Within-arm spread is ≤2.3%; the step between them is **+27.1 s, +19.3%** — about
eight times the noise. The wake fault counts are near-deterministic and reproduce
to within 1% (≈9,180 against ≈12,150, +33%), which makes `pgmajfault` at load the
better instrument of the two.

## What it settles

**1. Nothing degrades between +2.0 and +0.5 GiB.** Qwen: 140.8 → 139.9 s. The
80B: 102.9 → 103.7 s. Both nil. The 2 GiB margin is buying no measured thing in
the range it is asserted over. This is the whole case against it: it is not that
headroom is worthless, it is that *this* headroom is priced an order of magnitude
above where anything happens.

**2. The cost is real below zero, and it is a wake cost, not a serving cost.**
+19% (Qwen, n=3), +36% (deepseek), +5% (the 80B). And across all nine arms
**decode throughput never degraded** — 32.7–33.4 for Qwen against 31.4–33.1
squeezed, 34.7 → 33.2 for deepseek, 29.7 → 29.2 for the 80B. Every one of those
spreads is inside the rig's own 5% drift. Whatever a mapping headroom protects,
it is not tok/s.

That matters for what the flag trades. Going unmapped on srv1 gives up **8.4 GiB
of reclaimable memory permanently** to save, at most, a one-off ~27 s of wake on
a rung that then stays up. For a served ladder that is a bad trade; for a rig
that sleeps and wakes constantly it is a different question, and §17 of the
sleep/wake design is where that one belongs.

**2a. Mapped costs 6.7 s of wake against unmapped, not 24 — settled the same
day.** A single restore arm had unmapped waking in 116.4 s against 140.8 s
mapped, which would have made the mapping trade a real one. Three alternating
pairs at production `vm.swappiness=60`, cold cache, say otherwise:

| | wake |
|---|---|
| unmapped | 134.8 / 132.3 / 131.6 → **132.9 s** |
| mapped | 139.5 / 139.9 / 139.4 → **139.6 s** |

**6.7 s, 4.8%**, and the mapped arm reproduces to within 0.5 s across three
repeats. The 116.4 s was one draw. So the trade on srv1 is 8.4 GiB of
reclaimable memory against under seven seconds of one-off wake on a rung that
stays up — **mapped wins**, and by more than the earlier reading suggested.

What mapped does cost, visible only at production swappiness: **35,000–48,000
pages swapped *out* per wake** (against 0 unmapped), and 5,651–7,991 swapped back
in. That is the page cache evicting anonymous memory to fit a 12.30 GiB blob on a
15 GiB host. It buys the 6.7 s and nothing measurable afterwards — decode is
33.0/33.2/33.2 mapped against 31.7/33.2/33.2 unmapped, which is the same null
`records/measurements/load-mode-2026-09-08/` found, now with the cache dropped
between arms.

**3. The two gates fail differently, and the refusal gate keeps its 2.0.** The
sweep above moves the *blob* against `MemAvailable`. Moving the **spilled
experts** — 9.2 GiB for this unit, the figure the refusal gate actually compares
— is a different curve and a much worse failure:

| clearance vs experts | wake | majfault @ wake | swap-out @ wake | decode |
|---|---|---|---|---|
| +5.0 (n=3, no balloon) | 132.9 s | ~6,700 | 0 | 33.2 tok/s |
| +2.09 | 127.6 s | 11,360 | 0 | 33.12 tok/s |
| **+0.55** | **131.5 s** | 6,427 | **0** | **33.26 tok/s** |
| **−0.97** | **385.3 s** | **2,327,837** | **2,228,826** | **10.78 tok/s** |

**A cliff, not a slope.** Flat to +0.55 on every axis, then 2.9× the wake, 347×
the faults, 5.5 million pages moved through swap, and **decode at 32% of
baseline**. Across all nine mode-gate arms decode never moved at all; one GiB
past the experts it loses two thirds.

This is the failure `okf/must-read/touching-rigs.md` describes and it is worth
being precise about why it is the dangerous one: **nothing errors.** The unit
comes up, gate 7 is green, `/v1/models` answers 200, and every request is served
— at a third of the rate, off swap. A run that hit this would report a disk
benchmark as a decode rate.

So the recommendation splits, and the two gates get different numbers for
reasons that are now measured rather than inherited:

| gate | compares | value | why |
|---|---|---|---|
| mode | the blob | **2.0 → 0.5** | flat to +0.5; failure is a bounded ~20% wake cost |
| refusal | the experts | **2.0, unchanged** | cliff below +0.55; failure is silent and −68% |

Three reasons the refusal gate keeps 2.0 despite +0.55 measuring clean:

* **the cliff's location is unmeasured** — it is somewhere in the 1.5 GiB
  between +0.55 and −0.97, and there is no point in between;
* **the failure is silent**, so being wrong is not self-announcing the way a
  slow wake is;
* **the margin is free on this fleet** — at 2.0, srv1 still admits Qwen's
  9.2 GiB of experts and KAT's 11.8 (11.8 + 2.0 = 13.8 against 14.2). It refuses
  nothing that would have worked.

It also settles what `--load-mode none` does *not* buy. The −0.97 arm swapped
**2.2 million pages out** during its wake: the experts were evicted. Anonymous
shared memory is swappable, and the flag does not protect it.

**3. The penalty is proportional, not constant** — which is the argument against
any single-number headroom. One GiB of shortfall costs +19% on srv1's 12.30 GiB
blob and +5% on srv2's 35.67 GiB blob, because it is 8% of one and 2.8% of the
other. A figure that means two different things on two rigs is the wrong shape
for a constant.

**4. Some headroom is real, and it is nearer 0.5 GiB than 2.0.** deepseek is the
one model that paid *above* the line: +10.7% at +0.5 GiB clearance (n=1, so
weaker than the rest of this). The likely reason is that clearance measured
against the blob understates the pressure — the process needs RAM the blob does
not account for: llama.cpp's own allocations, CUDA host-side buffers, container
overhead. That is exactly what a headroom constant is for. So this measurement
does **not** vindicate a bare-blob rule outright; it says the constant is real
and roughly a quarter of its current size.

**For every model this fleet actually runs, bare-blob and a 0.5 GiB margin give
the same answer, and both differ from 2.0 GiB in exactly the live case:**

| model | blob | available | `blob > avail` | `blob + 0.5 > avail` | `blob + 2.0 > avail` |
|---|---|---|---|---|---|
| srv1 Qwen3.6 | 12.30 | 14.19 | mapped | mapped | **unmapped** ← live, and wrong |
| srv1 deepseek | 8.29 | 14.19 | mapped | mapped | mapped |
| srv2 80B | 35.67 | 44.50 | mapped | mapped | mapped |
| srv1 KAT (2026-09-08) | 16.90 | 14.19 | unmapped | unmapped | unmapped |

## A claim in the source that the records do not support

`src/mcgyvr/serving/__init__.py:112` defends the 2.0 with:

> KAT-Coder cleared bare `MemAvailable` by 0.4 GiB on srv1 and then took 203 s to
> wake behind a thrashing cache

That figure appears nowhere under `records/`. The record that exists —
`records/measurements/wake-2026-09-08/README.md` — has KAT at a **16.9 GB blob
into 15 GB of RAM**, which does not clear `MemAvailable`, it overflows it by
about 1.9 GB. The 0.4 GiB matches KAT's *expert* figure against the refusal gate
(11.8 + 2.0 = 13.8 against 14.2), not its blob against the mapping gate.

The comment reads a refusal-gate datum as a mapping-gate datum, and it is the
only thing in the tree arguing for the 2.0 on the mapping decision. Correct it
with whatever the threshold becomes.

## The two gates are about two different things

`fit` nests them (`__init__.py:420-421`) and prices both with the same constant:

```python
if placed.ram_gb and spec.disk_gb + RAM_HEADROOM_GB > available_ram:   # mode
    if placed.ram_gb + RAM_HEADROOM_GB > available_ram:                # refusal
```

This sweep separates them:

* **the mode gate compares `spec.disk_gb`, the blob** — and the blob is what is
  read in full at load, which is why it predicts *wake*. That is the figure this
  measurement moved, and the one whose margin is too big.
* **the refusal gate compares `placed.ram_gb`, the spilled experts** — the set
  that stays resident while serving, which is why it predicts *decode*. Nothing
  here touched it. KAT's 0.4 GiB clearance and 203 s wake is evidence about this
  gate, and it stands.

Keeping a margin on the refusal and shrinking it on the mode is therefore not a
compromise between two readings of one number; it is two numbers that were never
the same one.

## `--load-mode none` is not available to srv2's 80B at all

The same two campaigns were aimed at srv2 and could not run, for a reason worth
more than the arms it cost. `--load-mode none` on
`Qwen3-Next-80B-A3B-Instruct-Q3_K_M` **crash-loops**, reproducibly, about 83 s
into the load (`80b-unmapped-crash.txt`):

```
/src/ggml/src/ggml-cuda/ggml-cuda.cu:107: CUDA error
CUDA error: the resource allocation failed
```

It is a *card* failure, not a host-RAM one: `Shmem` had climbed to 25.2 GiB —
matching the 26.6 GiB of experts `fit` predicts — with 18 GiB still available,
so the host side was fine. Mapped, the same unit loads in 103 s. `restart:
unless-stopped` turned the crash into a loop, which is why the door reported
`NOT ANSWERING after 539.9s` rather than a failure to start.

**`fit` decides the loading mode from host RAM alone, and the mode has a VRAM
cost it does not model.** The 80B asks for 11.68 GiB of a card the idle scan
reads as 11.63 GiB free; mapped fits anyway because `fit` slightly over-estimates,
and unmapped's extra CUDA allocations do not. Nothing in `fit` knows that. If
srv2's RAM were tighter, `fit` would emit exactly this configuration today and
the rung would crash-loop.

Two consequences:

* **the refusal gate cannot be measured on srv2 with the models this fleet
  runs** — it governs unmapped units, the vLLM pair has no loading mode, and the
  80B will not run in one;
* **`budgets.wake_timeout_s = 480` was validated only against mapped wakes.**
  N7's evidence for this model is 97 s, mapped. Worth re-checking against any
  unmapped rung that does work — srv1's own unmapped Qwen woke in 385 s once
  squeezed, which is inside 480 by 95 s.

## Hazards this campaign paid for

* **`docker inspect`'s `StartedAt` is UTC.** Reading it with `time.mktime` adds
  the local offset — 10,800 s here — and prints a three-hour wake. The first srv1
  and srv2 passes carry that offset in their raw JSON and are corrected by
  subtracting it; `sweep.py` uses `calendar.timegm` and the later passes are
  already right. The door's own `up after` figure cross-checked it (133.5 s
  against 141.1 s from `StartedAt`; the gap is compose-up before the container
  starts, and `StartedAt` is the honest one).
* **Two models alternating on one port cannot share a teardown.** `serve down`
  names one container; the other is left up and gate 7 refuses the run —
  correctly. Three arms were lost to this before the arm table carried an
  explicit `down_compose`. This is the same shape the alternatives work is about
  (`tests/test_two_models_on_one_url_are_alternatives.py`).
* **`emit` refuses deepseek on srv1 at Qwen's window** — a card refusal, not a
  RAM one: the non-expert weights, cache, state and scratch alone want 5854 MiB
  of the 6127 free at 2 slots. It fits at 4096 per slot. srv1's two alternatives
  cannot share a window, which is a thing the alternatives design should know.
* **srv2's recorded scan measured the wrong directory — retaken.** `disk.path`
  was `/home/adaramir/models` while the blobs live in `moe/`, so `emit` wrote a
  `--model` path that does not exist on the rig. `_weights_path` was behaving as
  documented; the scan was stale. Retaken idle on 2026-09-09 during this
  campaign's srv2 window (`srv2-scan-2026-09-09-idle.json`, installed; the
  2026-09-05 one is kept as `srv2.json.bak-2026-09-05`). It also corrected a
  second field nobody had noticed: the old scan recorded **12,287 MiB of free
  VRAM with no card reserve at all**, where the idle retake reads 11,911 free
  and 376 reserved. `emit --check` is clean on both hosts either way, because
  srv2's vLLM units declare `vram_gb` in the config rather than deriving it.
* **A RUN_ID cannot contain `+`.** Arm labels of the shape `B-refusal-+20` are
  refused at gate 5 — the id prefixes container names and must be
  `[A-Za-z0-9_.-]+`. Two arms were lost to this and re-run as `p20`/`p05`.
* **`actual_clearance_gib` in the raw JSON is always measured against the
  blob**, including on the arms whose axis is the experts. The refusal-gate rows
  read `-4.07` where the clearance against the 9.2 GiB experts is `-0.97`. The
  tables above use the experts figure; recompute as
  `avail_before_gib - 9.2` rather than trusting the field.

## `--load-mode none` allocates Shmem, and Shmem swaps

Measured while taking srv1 down (`srv1-release.txt`): the unmapped unit was
holding **8.09 GiB of `Shmem`** with `/dev/shm` at 100K used and no tmpfs to
account for it. `okf/must-read/touching-rigs.md` says of the flag that "only the
CPU-side expert tensors are allocated, as anon memory, and **nothing pages**."
Shared anonymous memory is swappable, and both rigs run 8 GiB of swap — srv2 was
2.2 GiB into it when this began. The experts can be paged out. The flag does not
buy what the note claims.

## Does a model wait on RAM?

**Only on the sleeper's process exit, and that costs about a second.** Release is
a step, not a curve (`srv1-release.txt`, one sample per second):

```
t+13   MemAvailable  5.26 GiB   Shmem 8.08 GiB   ← container alive
t+14   MemAvailable 13.45 GiB   Shmem 0.01 GiB   ← container exits
t+16   MemAvailable 14.17 GiB   Shmem 0.00 GiB   ← settled
```

Nothing is handed back incrementally: 8.09 GiB appears in under one second when
the process dies, and settles two seconds later. srv2 behaves the same on the
vLLM pair, its card going 11,853 MiB → 1 MiB across two container exits
(`srv2-release.txt`).

So sleep→wake is hard-serialized at teardown — a waking alternative cannot have
the sleeper's RAM until the sleeper's container is gone — but the serialization
itself is not a cost worth designing around. The wake is: 86–168 s on srv1,
103–108 s on srv2, and that is where `budgets.wake_timeout_s` is spent.

Idle `MemAvailable` settles at **14.19 GiB** on srv1 and **44.5 GiB** on srv2,
which confirms the 2026-09-05 recorded scans (14.2 and 44.5) are still true.

## The files

| | |
|---|---|
| `sweep.py` | the runner; one arm per (model, clearance) |
| `balloon.py` | the instrument — locked, unswappable, first OOM victim |
| `arms.json`, `arms-srv2.json`, `arms-deepseek.json`, `arms-repeat.json` | the four passes |
| `sweep-results*.json` | every arm's raw figures, including the failed ones |
| `sweep-*.log` | the transcripts |
| `compose.srv1-qwen-mapped.yml`, `compose.srv1-deepseek.yml`, `compose.srv2-80b.yml` | what `emit` wrote, and what was run |
| `srv1-release.txt`, `srv2-release.txt` | the teardown memory traces |
| `deepseek.geometry.json`, `qwen80b.geometry.json` | read by `src/mcgyvr/serving/ggufscan.py` |

Raw wake figures in `sweep-results.json` and `sweep-results-arms-srv2.json` need
−10800 s; `sweep-results-arms-deepseek.json` and `sweep-results-arms-repeat.json`
do not. The tables above are corrected.
