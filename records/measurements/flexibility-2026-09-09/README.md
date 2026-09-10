# The flexibility campaign — measured 2026-09-09/10

The plan is `records/plans/flexibility-campaign.md`; the question it exists to
answer is not "how fast is the fleet" but **what shapes can it hold and what
does each one cost**. 70 arms were budgeted. **59 have landed.** This file
records what they say. The eleven still outstanding are named at the bottom,
with why each one is not here yet.

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

| checkpoint | GiB | wake (n=2) |
|---|---|---|
| Ling-3.0-tiny Q4_K_M | 4.58 | 71.22 s |
| deepseek-coder-v2-16b | 8.29 | 86.38 s |
| gemma-4-26B-A4B IQ3_XXS | 10.63 | 126.22 s |
| Qwen3.6-35B IQ3_XXS `-c 8192` | 12.30 | 141.07 s |

`wake = 21.89 + 9.423·GiB`, R² 0.9221 — **the intercept survives the window
control almost exactly where M4 left it.** It was never Qwen's window.

And the Ling quant ladder, one architecture, one layer count, one expert
structure, no `--n-cpu-moe` anywhere in it, blob bytes varying 3×:

| blob | GiB | wake (n=2) |
|---|---|---|
| `Ling-3.0-tiny-IQ2_M` | 2.63 | 61.63 s |
| `Ling-3.0-tiny-Q3_K_M` | 3.53 | 68.50 s |
| `Ling-3.0-tiny-Q4_K_M` | 4.58 | 71.22 s |
| `Ling-3.0-tiny-Q6_K` | 6.37 | 83.93 s |
| `Ling-3.0-tiny-Q8_0` | 7.83 | 92.35 s |

`wake = 46.39 + 5.842·GiB`, R² 0.9866, over ten arms with no blob-identity,
window or offload confound available to produce it.

**The two fits disagree, and that is the result.** 46.4 s and 5.84 s/GiB within
one architecture against 21.9 s and 9.42 s/GiB across four. A cross-model "rate"
is not a rate: it is a blend of per-architecture intercepts and per-architecture
slopes, and fitting one line through four checkpoints recovers neither. **Q3 is
answered — those five rows were never one measurement**, and putting them on one
window did not make them one.

### 2. `--n-cpu-moe` costs no wake at all, on either rig

This was the "bytes uploaded to the card" explanation for `r(srv2)`'s negative
R². It does not survive.

| ladder | span | wake change |
|---|---|---|
| Q13, srv2 Qwen3.6, ncmoe 7 → 40 | **33 blocks** | **−3.01 s (−3.6%)** |
| Q10, srv2 80B, ncmoe 35 → 41 | 6 blocks | −1.75 s (−1.6%) |

Both are small and both are **negative** — deeper offload is marginally
*faster*. Whatever `r(srv2)` is measuring, it is not the cost of moving expert
weight onto the card.

### 3. The card law is exact, and the decode contradiction was the instrument

Q10 was two questions on one ladder. Both resolve.

**The card.** Five placements of the 80B, n=2, byte-identical composes apart
from `--n-cpu-moe`:

| ncmoe | card used |
|---|---|
| 35 | 11,895 MiB |
| 36 | 11,167 MiB |
| 38 | 9,711 MiB |
| 40 | 8,255 MiB |
| 41 | 7,527 MiB |

**728.0 MiB per offloaded block across all four intervals, zero deviation**, and
the two arms at each rung agree to the MiB. This confirms `F4.3`'s corrected
marginal-block figure exactly, on the card side. Extrapolated to full offload
the residual is **2,431 MiB**, which is `C`.

**The decode.** The plan asked whether one extra offloaded block can cost 56%.
It cannot, and it did not: **every Q10 arm carries both instruments**, and the
gap is between them, not between the rungs.

| | cold, one sample | warm, 3 samples after a discarded warm-up |
|---|---|---|
| 80B, ncmoe 35–41 | 12.5 – 13.4 tok/s | **25.0 – 29.3 tok/s** |

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

| group | placements | span | `C` spread | worst residual |
|---|---|---|---|---|
| 80B, srv2 | 35, 36, 38, 40, 41 | 6 blocks | **0.00 MiB** | **+0.00** |
| Qwen3.6, srv1 | 28, 29, 32 | 4 blocks | **0.00 MiB** | **+0.00** |
| Qwen3.6, srv2 | 7, 20, 40 | **33 blocks** | **38.00 MiB** | **+38.00** |

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

| | wake (StartedAt) | 3B restarts | card steady |
|---|---|---|---|
| plain pair, `service_healthy`, n=2 | **192.98 s** | **0, both arms** | 10,587 MiB |
| sleep-mode pair, n=4 | **141.94 s** | **1, all four arms** | 10,753 – 11,369 MiB |

**The sleep-mode pair is ~51 s faster while still crash-restarting the 3B once
every time**, and the plain pair is slower with a clean start. The 36 s figure
was, if anything, an under-statement of the flag. Two things follow and neither
is closed here:

* `service_healthy` reached the plain compose and **not** the sleep-mode one —
  the 3B's `Available KV cache memory: -4.98 GiB` is on record in all four arms.
  That is a compose to fix, not a finding.
* the sleep-mode pair's card cost still varies by **616 MiB between arms of the
  same config** (10,753 / 11,369 / 11,369 / 11,257), all of it invisible to the
  declared 3.49 / 7.12 GiB figures. The mechanism is unexplained.

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
|---|---|---|---|
| 1 | 6.63 tok/s | 6.63 | 38.59 s |
| 2 | 14.56 | 29.08 | 17.58 s |
| 4 | 8.96 | 35.80 | 28.56 s |

Aggregate rises to width 4; per-stream peaks at 2. The width-1 figure is a cold
first request on the campaign's own showing (see §3) and should not be read as
the serial rate.

**Q17 — M2's co-residency law holds, and its four `emit` verdicts reproduce.**
Live: `Shmem` 7.4683838 + 10.7577934 = **18.2261772 GiB against a measured
18.2261810 — additive to 4 KiB**; card 5,711 MiB used against a 5,712 MiB sum. Decode unmoved by co-residency
(24.5 vs 25.3, 14.56 vs 14.57). The campaign README flagged M2's `emit` verdicts
irreproducible because another agent was moving `src/` during them; **re-taken
against the frozen tree, all five are unchanged** (`logs/q17-emit-retake.log`):

| config | verdict | re-take |
|---|---|---|
| `A-geometry-pair` | two files, alternatives | unchanged, exit 0 |
| `B-declared-fits` | one file, co-residents | unchanged |
| `C-declared-ram-refused` | one file | unchanged |
| `D-each-alone-passes` | accepted | unchanged |
| `E-blob-sum-refused` | refused, 48.00 vs 44.60 GB | unchanged, same figures |

B/C/D report a `--check` mismatch, and the diff is **exclusively the freeze's
healthcheck block and `service_started` → `service_healthy`**. No co-residency
verdict moved. The irreproducibility flag can be lifted.

**Q8 (partial) — the door's clock, on 60 arms instead of 3.** `collect_door.py`
harvests every `up after` the door printed, so two of Q8's three clocks now
exist for every arm in the campaign rather than for three purpose-built ones
(`door-up-after.json`). The pair arms show the O8 defect exactly as
described: Q14 reads `8001:88.2s  8002:2.1s` against a 193 s `StartedAt` wake —
**the door's second figure is "how much longer after the first", 2.1 s for a
unit that took 97.** The third clock, `mcgyvr`'s own wall clock around
`spawn_door`, still needs its three arms.

---

## Still to run — 11 arms

| Q | arms | why not yet |
|---|---|---|
| Q7, two llama.cpp on srv1 | 2 | never reached; needs its hand-written compose authored |
| Q8, `mcgyvr`'s own clock | 3 | never reached |
| Q9, `r(srv1, vLLM)` | 3 | **ran, lost to a stale teardown marker** — see below |
| Q15, sleep/wake cycles | (4 arms' second half) | never reached |
| Q16, the three-way matrix | 4 | **gate 2 forbids it** — see below |

**Q9 was not a rig failure.** `logs/last-up-srv1.txt` still named the Qwen
compose, so `vllm_arms.teardown()` ran `serve down` with a file whose container
was not up, and gate 7 refused on the vLLM 3B it had not named. All three arms
died at the head-of-arm teardown, before `rig.note_up` was ever reached. The 3B
from the first attempt is **still up on srv1**, which is Q9's configuration: the
marker is the whole fix.

**Q16 cannot run through the door as designed.**
`serving/gate-scripts/02-rig.py` refuses `serve up` onto a busy rig, with
`RUN_SERVE == "down"` the only exemption, and Q16's premise is placing a third
unit onto a card that already holds two. The two "gate 5 RUN_ID collision"
failures on record are the retry after that refusal, not the cause.
**Owner ruling, 2026-09-10: run Q16 off-door** — ssh and `docker compose up -d`,
recorded into this directory rather than the evidence envelope. It forfeits
gates 5/7/8 and keeps the freeze intact, which is the trade the plan's own
doctrine asks for: a capability is measured before it is built.

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

## Files

| | |
|---|---|
| `results-q1-srv1.json` | Q1, 9 arms — srv1 wake law, first card readings |
| `results-q2-ling.json` | Q2, 10 arms — the Ling quant ladder |
| `results-q4q5q6-srv1.json` | Q4/Q5/Q6, 14 arms |
| `results-arms-q10-80b.json` | Q10, 10 arms — the 80B ladder, both decode instruments |
| `results-q11-headroom.json` | Q11, computed — the headroom constant |
| `results-q12-lambda.json` | Q12 — `Λ(80B, w)` at widths 1/2/4 |
| `results-q13-srv2.json` | Q13, 6 arms |
| `results-q14-pair-healthy.json` | Q14, 2 arms — the plain pair, healthy |
| `results-q15-sleepmode.json` | Q15, 4 arms — wake half only |
| `results-q16-threeway.json` | Q16 — three refusals, no data |
| `results-q9-vllm-srv1.json` | Q9 — three teardown failures, no data |
| `m2-coresidency.json` | Q17, 3 arms |
| `headroom.py` | Q11, offline: recomputes every prediction from header + probe |
| `collect_door.py` | the door's own clock, harvested from `logs/` |
| `rig.py` | the primitives every arm shares |
| `wake_rate.py`, `vllm_arms.py`, `three_way.py`, `coresidency.py`, `balloon.py` | the runners |
| `logs/q17-emit-retake.log` | the four M2 verdicts, re-taken against the frozen tree |
