# The flexibility campaign — measured 2026-09-09/10

The plan is `records/plans/flexibility-campaign.md`; the question it exists to
answer is not "how fast is the fleet" but **what shapes can it hold and what
does each one cost**. 70 arms were budgeted and **68 landed**, over two days. The two short are the
second pair arm of Q7 — stopped when the first showed the pair paging, and
accepted at n=1 by the owner — and of Q17, whose runner took each unit alone
instead. Every question in the plan has its answer here.

Every arm ran against the frozen tree — `product_sha256 ec531573f5402b84…`,
round `r26-09-09-2026` — and the hash did not move once during the campaign.

---

## The five things this campaign settled

### 1. The intercept is real, and it is architecture — not the window

M4 reported a positive intercept of ~22.5 s on srv1 and named it the reason to
abandon the proportional form. The suspicion was that it rested on one blob, or
on Qwen3.6 being the only checkpoint running `-c 16384` while every other ran
`-c 8192`. **Both suspicions are wrong.**

Q1's arms 10–11 put Qwen3.6 on `-c 8192`, so all four mapped srv1 checkpoints
now sit on one window:

| checkpoint                    | GiB   | wake (n=2) |
| ----------------------------- | ----- | ---------- |
| Ling-3.0-tiny Q4_K_M          | 4.58  | 71.22 s    |
| deepseek-coder-v2-16b         | 8.29  | 86.38 s    |
| gemma-4-26B-A4B IQ3_XXS       | 10.63 | 126.22 s   |
| Qwen3.6-35B IQ3_XXS `-c 8192` | 12.30 | 141.07 s   |

`wake = 21.89 + 9.423·GiB`, R² 0.9221 — **the intercept survives the window
control almost exactly where M4 left it.** It was never Qwen's window.

And the Ling quant ladder — one architecture, one layer count, one expert
structure, one window, blob bytes varying 3×:

| blob                   | GiB  | `--n-cpu-moe` | wake (n=2) |
| ---------------------- | ---- | ------------- | ---------- |
| `Ling-3.0-tiny-IQ2_M`  | 2.63 | —             | 61.63 s    |
| `Ling-3.0-tiny-Q3_K_M` | 3.53 | —             | 68.50 s    |
| `Ling-3.0-tiny-Q4_K_M` | 4.58 | —             | 71.22 s    |
| `Ling-3.0-tiny-Q6_K`   | 6.37 | 6             | 83.93 s    |
| `Ling-3.0-tiny-Q8_0`   | 7.83 | 10            | 92.35 s    |

`wake = 46.39 + 5.842·GiB`, R² 0.9866, over ten arms.

**The ladder is not offload-free, as the plan assumed.** The two largest quants
overflow srv1's card and `emit` placed them at `--n-cpu-moe` 6 and 10. The
intercept does not rest on them: the three rungs with no offload term fit
`49.72 + 4.859·GiB` (R² 0.8947, six arms) on their own, and the two offloaded
rungs sit **+2.7 to +5.3 s above that line**. §2 and Q4 both say offload is
close to free — srv1's Qwen3.6 is flat to 1.3 s from ncmoe 28 to 32 — which
leaves curvature in the bytes term or the K-quant type mix. Five points cannot
separate those.

**The two fits disagree, and that is the result.** 46.4 s and 5.84 s/GiB within
one architecture against 21.9 s and 9.42 s/GiB across four. A cross-model "rate"
is not a rate: it is a blend of per-architecture intercepts and per-architecture
slopes, and fitting one line through four checkpoints recovers neither. **Q3 is
answered — those five rows were never one measurement**, and putting them on one
window did not make them one.

### 2. `--n-cpu-moe` costs no wake at all, on either rig

This was the "bytes uploaded to the card" explanation for `r(srv2)`'s negative
R². It does not survive.

| ladder                          | span          | wake change         |
| ------------------------------- | ------------- | ------------------- |
| Q13, srv2 Qwen3.6, ncmoe 7 → 40 | **33 blocks** | **−3.01 s (−3.6%)** |
| Q10, srv2 80B, ncmoe 35 → 41    | 6 blocks      | −1.75 s (−1.6%)     |
| Q4, srv1 Qwen3.6, ncmoe 28 → 32 | 4 blocks      | −1.29 s (−0.9%)     |

All three are small and all three are **negative** — deeper offload is marginally
*faster*. Whatever `r(srv2)` is measuring, it is not the cost of moving expert
weight onto the card.

### 3. The card law is exact, and the decode contradiction was the instrument

Q10 was two questions on one ladder. Both resolve.

**The card.** Five placements of the 80B, n=2, byte-identical composes apart
from `--n-cpu-moe`:

| ncmoe | card used  |
| ----- | ---------- |
| 35    | 11,895 MiB |
| 36    | 11,167 MiB |
| 38    | 9,711 MiB  |
| 40    | 8,255 MiB  |
| 41    | 7,527 MiB  |

**728.0 MiB per offloaded block across all four intervals, zero deviation**, and
the two arms at each rung agree to the MiB. This confirms `F4.3`'s corrected
marginal-block figure exactly, on the card side. Extrapolated to full offload
the residual is **2,431 MiB**, which is `C`.

**The decode.** The plan asked whether one extra offloaded block can cost 56%.
It cannot, and it did not: **every Q10 arm carries both instruments**, and the
gap is between them, not between the rungs.

|                  | cold, one sample  | warm, 3 samples after a discarded warm-up |
| ---------------- | ----------------- | ----------------------------------------- |
| 80B, ncmoe 35–41 | 12.5 – 13.4 tok/s | **25.0 – 29.3 tok/s**                     |

`ram-headroom`'s 29.71 / 29.51 / 29.19 was right; the campaign's 13.02 / 13.46 /
12.30 / 12.81 was a cold first request. **The 2026-09-09 campaign's whole decode
column needs the asterisk**, as its plan pre-authorised. Q13 shows the same
split (cold 13.5–17.7, warm 30.0–62.7), so this is a property of the
instrument, not of one model.

### 4. Q11 — the headroom constant is +38 MiB, and it is a drift, not an offset

No arm recorded a prediction and none had to: `vramfit.predict` is arithmetic on
the GGUF header plus one measured constant, so every prediction was recomputed
offline from composes and geometry already on disk (`headroom.py`,
`results-q11-headroom.json`). What the arms contributed is the measured side.

The claim under test is the one `vramfit` rests on: **`C` — everything on the
card that is not expert weight — does not move with `--n-cpu-moe`.** `emit`
probes it once and predicts every other placement from it.

| group         | placements         | span          | `C` spread    | worst residual |
| ------------- | ------------------ | ------------- | ------------- | -------------- |
| 80B, srv2     | 35, 36, 38, 40, 41 | 6 blocks      | **0.00 MiB**  | **+0.00**      |
| Qwen3.6, srv1 | 28, 29, 32         | 4 blocks      | **0.00 MiB**  | **+0.00**      |
| Qwen3.6, srv2 | 7, 20, 40          | **33 blocks** | **38.00 MiB** | **+38.00**     |

Sixteen arms predict to the last MiB. Six do not, and they are the six spanning
33 blocks: `C` is 2,254 MiB at ncmoe 7, +2 MiB by ncmoe 20 and +38 MiB by
ncmoe 40, reproducing exactly across both arms at every rung.

**So the headroom G1 asks for is +38 MiB, and it is a lower bound.** The two
groups that showed no drift span 4 and 6 blocks; the one that spans a real
placement range drifts. A campaign that had only run narrow ladders would have
concluded `C` is invariant and been wrong in the dangerous direction — the
residual is **positive**, meaning the card holds *more* than the law predicts.

**This is a different term from M1's 63 MiB and both are real.** M1 measured
`emit`'s *stored* `C` being 63 MiB too high — a probe-transfer error, `C`
measured under one condition and used under another. Q11 measures `C` drifting
with the placement, which `vramfit`'s own docstring says does not happen. A
headroom on the geometry path has to cover both.

### 5. The sleep-mode pair is faster, and it was never the crashes

M5 found the plain vLLM pair crash-restarting the 3B 1–2× per cold start, hidden
by `restart: unless-stopped`, because `depends_on: service_started` released the
3B before the 7B had taken its card — and concluded the sleep-mode pair's 36 s
advantage was "crashing against clean", not the flag.

The freeze's `condition: service_healthy` fixed the plain pair. It did not close
the gap; it widened it.

|                                    | wake (StartedAt) | 3B restarts          | card steady         |
| ---------------------------------- | ---------------- | -------------------- | ------------------- |
| plain pair, `service_healthy`, n=2 | **192.98 s**     | **0, both arms**     | 10,587 MiB          |
| sleep-mode pair, n=4               | **141.94 s**     | **1, all four arms** | 10,753 – 11,369 MiB |

**The sleep-mode pair is ~51 s faster while still crash-restarting the 3B once
every time**, and the plain pair is slower with a clean start. The 36 s figure
was, if anything, an under-statement of the flag. Two things follow:

* `service_healthy` reached the plain compose and **not** the sleep-mode one —
  the 3B's `Available KV cache memory: -4.98 GiB` is on record in all four arms.
  That is a compose to fix, not a finding.
* the sleep-mode pair's card cost still varies by **616 MiB between arms of the
  same config** (10,753 / 11,369 / 11,369 / 11,257), all of it invisible to the
  declared 3.49 / 7.12 GiB figures. Q15's cycles, below, find the mechanism: the 7B's KV cache, sized during a start the crashing 3B intrudes on.

---

## The rest, in brief

**Q5 — no experts cliff in the bracket.** Three balloon points (5.53 / 5.68 /
5.83 GiB, targeting −0.50 / −0.65 / −0.80 GiB against the spilled experts),
n=2, unmapped. Warm decode holds at **33.4 – 33.7 tok/s at every point** while
major faults climb 12k → 53k and swap-outs 83k → 196k. The machine is under
rising pressure and the rate does not notice. M3's 190% step at −0.97 is
therefore **between −0.80 and −0.97**, narrowing G4's cliff from 0.63 GiB to
~0.17 — which is what `REFUSAL_RAM_HEADROOM_GB = 2.0` should be re-argued
against. *(The arms record clearance against the blob; the experts-axis
clearance is inferred from the balloon target and should be reconciled against
the 9.2 GiB experts figure before this is quoted as final.)*

**Q6 — M3's 5× decode collapse was the cold sample.** Warm, n=3, mapped:
**31.8 – 33.5 tok/s** at −2.44 and −2.99 GiB of blob clearance, against the
5.09 tok/s single cold sample at −3.03 that the claim rested on. The blob axis
does not collapse. It saturates, as `ram-headroom` said.

**Q4 — srv1's geometry path predicts exactly.** ncmoe 28 / 29 / 32, n=2 each,
zero residual at every rung. Folded into Q11.

**Q12 — `Λ(80B, w)` exists now.** `ncmoe 36`, `--parallel 4`:

| width | per-stream | aggregate | p50 latency |
| ----- | ---------- | --------- | ----------- |
| 1     | 6.63 tok/s | 6.63      | 38.59 s     |
| 2     | 14.56      | 29.08     | 17.58 s     |
| 4     | 8.96       | 35.80     | 28.56 s     |

Aggregate rises to width 4; per-stream peaks at 2. The width-1 figure is a cold
first request on the campaign's own showing (see §3) and should not be read as
the serial rate.

**Q17 — M2's co-residency law holds, and its four `emit` verdicts reproduce.**
Live: `Shmem` 7.4683838 + 10.7577934 = **18.2261772 GiB against a measured
18.2261810 — additive to 4 KiB**; card 5,711 MiB used against a 5,712 MiB sum. Decode unmoved by co-residency
(24.5 vs 25.3, 14.56 vs 14.57). The campaign README flagged M2's `emit` verdicts
irreproducible because another agent was moving `src/` during them; **re-taken
against the frozen tree, all five are unchanged** (`logs/q17-emit-retake.log`):

| config                   | verdict                    | re-take                 |
| ------------------------ | -------------------------- | ----------------------- |
| `A-geometry-pair`        | two files, alternatives    | unchanged, exit 0       |
| `B-declared-fits`        | one file, co-residents     | unchanged               |
| `C-declared-ram-refused` | one file                   | unchanged               |
| `D-each-alone-passes`    | accepted                   | unchanged               |
| `E-blob-sum-refused`     | refused, 48.00 vs 44.60 GB | unchanged, same figures |

B/C/D report a `--check` mismatch, and the diff is **exclusively the freeze's
healthcheck block and `service_started` → `service_healthy`**. No co-residency
verdict moved. The irreproducibility flag can be lifted.

**Q8 (partial) — the door's clock, on 60 arms instead of 3.** `collect_door.py`
harvests every `up after` the door printed, so two of Q8's three clocks now
exist for every arm in the campaign rather than for three purpose-built ones
(`door-up-after.json`). The pair arms show the O8 defect exactly as
described: Q14 reads `8001:88.2s  8002:2.1s` against a 193 s `StartedAt` wake —
**the door's second figure is "how much longer after the first", 2.1 s for a
unit that took 97.** The third clock, `mcgyvr`'s own, is measured on day two, below.

---

## Day two, 2026-09-10 — the arms that were left

### Q9 — `r(srv1, vLLM)` exists now, and the host figure is per rig

Qwen2.5-Coder-3B-AWQ alone on srv1 — the first vLLM deployment on the lock-prone
rig — `--dtype float16` (TU116 has no bfloat16), `--gpu-memory-utilization
0.60`, n=3 (`q9b-1`, `q9c-1`, `q9c-2`: gate 5 is write-once per RUN_ID, and each
attempt spends its own):

|                     | arm 1       | arm 2     | arm 3     |
| ------------------- | ----------- | --------- | --------- |
| wake (StartedAt)    | 109.3 s     | 110.9 s   | 111.1 s   |
| card, peak = steady | 3,112 MiB   | 3,112 MiB | 3,112 MiB |
| host RAM            | 2.57 GiB    | 2.57 GiB  | 2.60 GiB  |
| decode              | 22.86 tok/s | 22.95     | 22.95     |
| restarts            | 0           | 0         | 0         |

TTFT 0.243–0.249 s; `/is_sleeping` 404, as launched. **A vLLM unit costs srv1
2.57–2.60 GiB of host RAM against srv2's 2.92–2.95** (M2) — about 0.35 GiB less,
so the per-unit constant is per rig, not universal. It is **18% of srv1's
14.19 GiB**, which is what `Fit.ram_gb = 0.0` hides on the host where it would
matter most.

No lock in three cold starts, and the 3B had already sat up on srv1 for seven
hours overnight.

### Q15's cycles — nothing grows, and the 616 MiB spread has a mechanism

Four fresh cold starts of the same sleep-mode compose, each followed by three
level-2 sleep/wake cycles of both units, **card read per process** (pids mapped
to containers through `/proc/<pid>/cgroup` on the rig, never guessed from size):

|                         | 3B                    | 7B                            |
| ----------------------- | --------------------- | ----------------------------- |
| cold, serving           | **3,810** every arm   | 6,816 / 6,928 / 7,432 / 7,544 |
| asleep                  | **228** every cycle   | **234** every cycle           |
| serving after each wake | **3,790** every cycle | cold − 20, every cycle        |
| released per sleep      | **3,562** every cycle | 6,562 / 6,674 / 7,178 / 7,290 |
| `/sleep`                | 0.238–0.300 s         | 0.289–0.351 s                 |
| `/wake_up`              | 0.239–0.252 s         | 0.296–0.322 s                 |
| decode, all 16 readings | 127.3–129.6 tok/s     | 68.67–68.97 tok/s             |

Wake half, n=4 more: 141.9 / 143.1 / 143.1 / 142.6 s; the 3B restarts once in
every arm, 89 s after the 7B, as in Q15.

* **The residual does not grow with cycling.** 228 and 234 MiB after the first
  sleep and after the twelfth. 477 MiB (card total asleep) is the figure; 503 was
  not reproduced.
* **M6's 20 MiB disagreement is a cold-start overhead, exactly.** Every unit
  comes back from a wake 20 MiB lighter than it cold-started. A release derived
  from a cold `V_awake` reads 3,810 − 228 = **3,582**, which is M6's derived
  figure; the measured release is **3,562**, which is M6's measured one. The 7B
  in the arm that cold-started at M6's 6,816 reproduces 6,582 and 6,562 the same
  way.
* **The 616 MiB spread is all the 7B, set at cold start, fixed for the life of
  the process** — and it has a mechanism. vLLM sizes its KV cache after
  subtracting the "non-torch memory" it sees while profiling, and in this
  compose the 3B's crashing first attempt is on the card during the 7B's
  profile, by a different amount each time. From Q15's wake arms' own engine
  lines:

  |                                              | 7B non-torch memory | 7B KV cache | card, both serving |
  | -------------------------------------------- | ------------------- | ----------- | ------------------ |
  | sleep-mode arm 1                             | 0.89 GiB            | 1.15 GiB    | 10,753 MiB         |
  | sleep-mode arms 2, 3                         | 0.30                | 1.74        | 11,369             |
  | sleep-mode arm 4                             | 0.45                | 1.59        | 11,257             |
  | **plain pair, `service_healthy`, both arms** | **0.05**            | **1.99**    | **10,587**         |

  `service_healthy` removes the race: both Q14 arms size identically. **It has a
  cost nobody has priced:** the healthy pair's 3B, starting after the 7B has
  taken its card, gets **12,352 KV tokens** against the sleep-mode pair's
  **42,608** — 71% fewer — while the 7B gains (37,248 against 21,456–32,496).

### Q7 — two llama.cpp units on srv1: the sum holds where it binds, and binding is swap

**Owner's pick:** gemma-4-26B at `--n-cpu-moe 28` and Ling-3.0-tiny Q6_K at 21,
both `--load-mode none`, `-c 8192`. Each alone once, as M2 did, then the pair.

| arm             | `Shmem`    | geometry said | card (vramfit)    | answering on every port | swap used       | pages out    | warm decode   |
| --------------- | ---------- | ------------- | ----------------- | ----------------------- | --------------- | ------------ | ------------- |
| gemma alone     | 8.555 GiB  | 7.96 (+0.60)  | 3,814 MiB (3,813) | 129.1 s                 | 0.36 → 0.41     | +69,196      | 25.57 tok/s   |
| Ling Q6_K alone | 5.004      | 4.80 (+0.20)  | 1,854 (1,856)     | 86.7 s                  | 0.41 → 0.17     | +0           | 60.20         |
| **the pair**    | **13.559** | 12.76 (+0.80) | 5,648 (5,652)     | **184.4 s**             | **0.17 → 1.32** | **+565,534** | 23.26 / 60.25 |

* **`Shmem` is additive to 0.2 MiB** — 8.5551 + 5.0039 = 13.5590 GiB against
  13.5588 — on the rig where the sum binds, under pressure. M2's law holds on
  srv1. The card is additive to 3 MiB and `vramfit` is within ±4 MiB on all
  three arms.
* **The geometry under-predicts an unmapped unit's `Shmem` by 4–8%**, +0.20 to
  +0.60 GiB per unit. The pair was picked at +1.43 GiB of clearance on that
  prediction; it really had +0.65 before any process overhead, and
  `MemAvailable` floored at **0.13 GiB**. Swap took the rest: 1.15 GiB more of
  it used, 565k pages out (2.16 GiB), 188k major faults.
* **`MemAvailable` stops being additive once it floors** (9.19 + 5.77 = 14.95
  against 14.08). The difference is what swap absorbed.
* **What binding cost was time, not failure.** Both ports answered after 184.4 s
  against 129.1 s and 86.7 s alone; gemma's warm decode fell 9%, Ling's did not
  move, and nothing locked.
* **`emit` refused it and was right to** — by the mapped arithmetic (17.00 GB),
  not the machine's (13.56 GB of `Shmem` plus 2.0 held back against 14.21).
* **The second pair arm was stopped before it finished loading.** The premise
  the pair was approved on — +1.43 GiB clear, no swap — was falsified by the
  first arm, and a second would have repeated a paging state on the lock-prone
  rig. srv1 was cleared through the door to 14.9 GiB available and `Shmem` 0
  (`logs/q7-both-1-pressure.txt` is the machine at the moment of the halt).

### Q8 — `mcgyvr`'s own clock runs 19 s past the door's

Three wakes of srv1's live ladder through `mcgyvr serve wake --host srv1` itself —
on `q8/mcgyvr.yaml`, for the reason under Defects — with all three clocks read
off each one:

| wake          | clock 1, `StartedAt` → answering | clock 2, the door's `up after` | clock 3, `Wake.seconds` | 3 − 2  | 1 − 2 |
| ------------- | -------------------------------- | ------------------------------ | ----------------------- | ------ | ----- |
| `q8b-clock-1` | 141.4 s                          | 134.8 s                        | 153.4 s                 | 18.6 s | 6.6 s |
| `q8c-clock-1` | 140.2                            | 133.9                          | 153.1                   | 19.2   | 6.3   |
| `q8c-clock-2` | 140.2                            | 133.5                          | 152.3                   | 18.8   | 6.7   |

No restarts on any of them.

* **The door costs about 19 s of its own** — gates 1–8, the rig lease and ssh —
  on top of the load. Nothing priced that before, and `DEVIATION_RATIO = 1.5` is
  applied to clock 3.
* **Clock 1 runs 6.3–6.7 s past clock 2**, which is `METHOD.md`'s "~7 s clean".
  Clean is the only case measured: nothing restarted.
* **The window costs this wake nothing.** The live ladder — `-c 16384`,
  `--n-cpu-moe 30` — answers 140.6 s after `StartedAt`, n=3; Q1's `-c 8192`,
  `ncmoe 29` arms read 141.1 s, n=2, on the same clock. The +48 s the plan carried
  from `wake-2026-09-08` for the window does not reproduce, which is the other
  half of §1: the intercept was never the window.

### Q16 — a sleeper, an awake unit and the 80B on one card, placed to within 7 MiB

**Off the door, by owner ruling**: gate 2 refuses `serve up` onto a busy rig, and
that is the experiment. `three_way_offdoor.py` says what that forfeits and how
the leftover check was done in its place. The pair came up and went down through
the door every arm; only the 80B went around it, under its own compose project.

| asleep | awake | card free beside the sleeper | `vramfit` floor | predicted | the 80B added  | its own process | all three             | 80B wake       | 80B warm decode     | the awake unit        |
| ------ | ----- | ---------------------------- | --------------- | --------- | -------------- | --------------- | --------------------- | -------------- | ------------------- | --------------------- |
| 7B     | 3B    | 7,853 MiB                    | `ncmoe 41`      | 7,526 MiB | **7,521 (−5)** | 7,516           | 11,580 used, 332 free | 98.2 / 99.8 s  | 28.42 / 28.18 tok/s | 127.86 / 128.52 tok/s |
| 3B     | 7B    | 4,125                        | `ncmoe 46`      | 3,886     | **3,879 (−7)** | 3,874           | 11,666 used, 246 free | 100.3 / 99.4 s | 25.33 / 24.56       | 68.71 / 68.73         |

n=2 per placement, the two arms identical to the MiB. No restarts; peak equals
steady.

* **Can it load X+Y and sleep Z — yes, and `vramfit` sizes the third unit against
  what the sleeper actually left to within 7 MiB, on the safe side.** The
  per-process figures add: 234 + 3,810 + 7,516 = 11,560 against 11,580 on the
  card, and 7,544 + 228 + 3,874 = 11,646 against 11,666 — 20 MiB of
  unattributed context both times.
* **Nothing co-resident noticed.** The awake 3B decodes at 128 tok/s and the 7B
  at 68.7, Q15's figures without an 80B beside them; the sleeper stayed asleep
  through every load; the 80B woke in 98–100 s, inside Q10's 101.6–106.8 on an
  idle card.
* **The plan's free-card figure was one cold start stale.** It expected 4,853 MiB
  free with the 3B asleep. All four arms cold-started the 7B at 7,544 MiB —
  Q15's high-KV state — which left 4,125 and moved the floor to `ncmoe 46`.
  Which state a pair lands in is the race Q15 found, so a placement into a
  sleeper's space has to be sized from a reading, never from a declared figure.
  `vramfit.floor` against a live `nvidia-smi` is what did it here.
* The level-1 ban fired before any transport, all four arms.

### Defects the campaign found — recorded, not fixed

The tree is frozen for the campaign; each of these is the owner's.

* **`mcgyvr serve sleep` crashes on srv1.** `Capacity.drain` sorts the bounds
  of the named sources, and `_bounds` keys a source's own pool as
  `(source, None)` and a width-declaring rung as `(source, rung_name)`. The live
  srv1 rung `local_qwen3.6-35b-a3b` declares `max_parallel: 2`, so `sorted()`
  compares `None` with a `str` and raises `TypeError` (`q8b-clock-1`, traceback
  in `results-q8-clocks.json`). Any source with a width-declaring rung is hit;
  srv2's rungs declare no width, so by the code it would not fire there — not
  exercised. A sort key fixes it.
* **The live config cannot `serve wake` at all.** It holds no
  `serving.compose_dir`: "this config holds no launch spec for that card"
  (`q8-clock-*`). The Waker is unwired on production.
* **The Waker cannot wake one card twice in a day.** `door_argv` mints a unique
  suffix so "every wake gets an envelope of its own", and the RUN_ID is unique —
  but `serve-up.json` is a fixed artifact name, and gate 5 refused `q8b-clock-1`'s
  first attempt because the day's `serve-up.json` already existed. A dispatch-time
  waker that works once per campaign-day is not a waker.
* **The Waker has no memory on this machine, and says nothing about it.**
  `/tmp/mcgyvr-wake-1000` is group-writable (`drwxrwxr-x`) and holds
  `{"host": "rig", "seconds": 0.0}`, both dated 2026-09-09 17:57:07 — before
  `cabc5a26` committed `wake.py` and its tests, so something uncommitted made
  it. `_ours()` refuses a directory anyone else can write, correctly, so
  `predicted_wake_s` returns `None` and `_remember` writes nothing, on every
  wake: none of Q8's three wakes left a record. The owner's ruling that every
  wake records predicted against actual, and warns both ways, is inert here
  until the directory goes, and nothing tells an operator so. The committed
  tests isolate the directory (the `clock` fixture); what created this one is
  not on record.
* **The CLI's own error sends an operator to the wrong place.** "read its
  envelope under `records/evidence/live-<host>/`"; envelopes are under
  `records/evidence/<date>-live-<host>/`.
* **srv2's live compose is not what the tree emits.** `mcgyvr emit --check --out
  ~/.mcgyvr/config` fails on `compose.srv2.yml` alone, and the difference is the
  freeze's healthcheck and `service_healthy`: production srv2 still runs the
  `service_started` ordering M5 found crash-restarting. srv1's file matches
  (`logs/q8-live-emit-check.log`). Q14 is the healthcheck's validation — 0
  restarts, both arms — which the plan asked for before any live re-emit; the
  re-emit, and the 3B's KV cost above, are the owner's call.
* **`emit` sums a declared-figure unit as mapped whatever the rig will do.** On
  Q7's pair it refused on 17.00 GB of blob (`logs/q7-emit.log`); the rig runs both
  unmapped at a predicted 12.76 GB of `Shmem`. The verdict is right here; the
  arithmetic behind it is not the machine's.

### Harness lessons, paid for today

* **Write the teardown marker on every path that starts a unit.** Q9's first
  attempt left the 3B up without updating `last-up-srv1.txt`, so all three arms
  tore down with the Qwen compose and gate 7 refused each on the 3B it had not
  named. Pointing the marker at the file that was really up was the whole fix.
* **Name the evidence directory for the day the door runs.** `rig.door` wrote
  `2026-09-09` out; at midnight the door moved to `2026-09-10` and the move-aside
  kept clearing yesterday's, so gate 5 took two of Q9's arms. Fixed in `rig.py`.
* **A waiter that `pgrep -f`s for a script name matches itself.** Its own
  command line contains the pattern, so the loop never ends. Two Q16 waiters
  hung that way; Q16 was started directly.
* **Kill a runner by the interpreter's PID, never by `pgrep -f` alone.** Halting
  Q7, `pgrep` returned the chain's shell *and* the python, the newline between
  them made `kill` a no-op, and the runner went on to start the arm it was being
  stopped to prevent. The filter that worked matches the interpreter in
  `ps -eo pid,args`.
* **Parallel shell calls share one working directory.** A background chain
  launched beside a `cd` ran from the repo root and did nothing. Every chain now
  opens with an absolute `cd … || exit`.

## What the campaign leaves open

Nothing here needs rig time to decide. Each is a ruling or a change to `src/`,
and each is the owner's:

* **Re-emit srv2 onto `service_healthy`.** The healthcheck is validated (Q14, no
  restarts), it removes the race that varies the 7B's card by 616 MiB — and it
  costs the 3B 71% of its KV tokens (Q15). The trade is the decision.
* **`REFUSAL_RAM_HEADROOM_GB = 2.0`.** Q5 puts the experts cliff between −0.80 and
  −0.97 GiB; Q7 shows the gate refusing a pair that ran by paging 1.15 GiB, at
  +0.65 GiB of real clearance. Both say 2.0 is not loose. *(Q5's clearances are
  inferred from balloon targets and should be reconciled against the 9.2 GiB
  experts figure before either is quoted as final.)*
* **G1's headroom on the geometry path.** Two terms, both measured: `C` drifting
  +38 MiB over a wide placement range (§4) and a stored `C` 63 MiB high (M1).
* **`Fit.ram_gb = 0.0` for declared-figure vLLM units.** A unit costs 2.57–2.60 GiB
  on srv1 (Q9) and 2.92–2.95 on srv2 (M2).
* **The geometry under-predicts an unmapped unit's `Shmem` by 4–8%** (Q7), which
  is the figure a host-RAM sum over unmapped units would add.
* **A per-architecture wake law** in place of `r(srv1)` and `r(srv2)` (§1, §2,
  and Q8's window).
* **The seven defects above** — five in `src/`, two in the live config.

## Records this campaign makes false

Deliberate corrections, not cleanup — each is a measurement record and the
owner's to sign off:

* `fleet-gaps-2026-09-09/README.md` — **the decode column throughout**. Every
  figure in it is a cold single sample; the warm figure is 2× larger and is the
  one `ram-headroom` reported. M1's own table (`13.02` / `13.46` / `12.30` /
  `12.81`) is the clearest case.
* the same file, **M3's "5.09 tok/s at −3.03 GiB"** — a 5× collapse from one
  cold sample, measured warm at 31.8–33.5.
* the same file, **M2's `emit` verdicts flagged irreproducible** — re-taken and
  unchanged, above.
* `plans/wake-timeout.md` and `plans/fleet-shape/formulas.md` carry `r(srv1)` and `r(srv2)` as single
  rates. §1 and §2 above say a single rate is the wrong shape.
* `fleet-gaps-2026-09-09/README.md`, **M5's reading of the sleep-mode pair** —
  "crashing against clean". With the crashes gone from the plain pair the
  sleep-mode pair is 51 s *faster* (§5), and the crash it still has is what
  varies its card by 616 MiB (Q15).
* **The +48 s the plan carries for srv1's window**, from `wake-2026-09-08` — Q8.
* **`vramfit`'s module docstring**, that `C` "does not move with
  `--n-cpu-moe`" — true across 4 and 6 blocks, 38 MiB false across 33 (§4). It
  is in `src/`, so it waits with the defects.

## Files

|                                                                                   |                                                                                          |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `results-q1-srv1.json`                                                            | Q1, 9 arms — srv1 wake law, first card readings                                          |
| `results-q2-ling.json`                                                            | Q2, 10 arms — the Ling quant ladder                                                      |
| `results-q4q5q6-srv1.json`                                                        | Q4/Q5/Q6, 14 arms                                                                        |
| `results-arms-q10-80b.json`                                                       | Q10, 10 arms — the 80B ladder, both decode instruments                                   |
| `results-q11-headroom.json`                                                       | Q11, computed — the headroom constant                                                    |
| `results-q12-lambda.json`                                                         | Q12 — `Λ(80B, w)` at widths 1/2/4                                                        |
| `results-q13-srv2.json`                                                           | Q13, 6 arms                                                                              |
| `results-q14-pair-healthy.json`                                                   | Q14, 2 arms — the plain pair, healthy                                                    |
| `results-q15-sleepmode.json`                                                      | Q15, 4 arms — the wake half                                                              |
| `results-q16-threeway.json`                                                       | Q16 through the door — gate 2's refusal, as designed                                     |
| `results-q9-vllm-srv1.json`                                                       | Q9 — the first attempt's three teardown failures, then the three arms                    |
| `m2-coresidency.json`                                                             | Q17, 3 arms                                                                              |
| `headroom.py`                                                                     | Q11, offline: recomputes every prediction from header + probe                            |
| `collect_door.py`                                                                 | the door's own clock, harvested from `logs/`                                             |
| `rig.py`                                                                          | the primitives every arm shares                                                          |
| `wake_rate.py`, `vllm_arms.py`, `three_way.py`, `coresidency.py`, `balloon.py`    | day one's runners                                                                        |
| `door_clock.py`, `sleep_cycles.py`, `coresidency_srv1.py`, `three_way_offdoor.py` | day two's runners                                                                        |
| `logs/q17-emit-retake.log`                                                        | the four M2 verdicts, re-taken against the frozen tree                                   |
| `results-q7-coresidency.json`                                                     | Q7 — each unit alone, then the pair                                                      |
| `results-q8-clocks.json`                                                          | Q8 — three wakes, three clocks each; the six failures before them are two of the defects |
| `results-q15-cycles.json`                                                         | Q15's cycles — 4 cold starts × 3 sleep/wake cycles, per process                          |
| `results-q16b-offdoor.json`                                                       | Q16 off the door, 4 arms                                                                 |
| `door-up-after.json`                                                              | the door's own clock, every day-one arm                                                  |
| `q7/`                                                                             | Q7's composes, and the declared-figure config `emit` refused                             |
| `q8/`                                                                             | Q8's config: the live one plus `serving.compose_dir`, and its geometry                   |
| `logs/q7-emit.log`, `logs/q8-live-emit-check.log`                                 | `emit`'s Q7 verdict; the live ladder checked against the tree                            |
| `logs/q7-both-1-pressure.txt`                                                     | srv1 at the moment Q7 was halted                                                         |
