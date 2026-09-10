# The flexibility campaign — full coverage, planned 2026-09-09

**The question this round exists to answer.** Not "how fast is the fleet" but
**what shapes can it hold, and what does each one cost**: can it load X, can it
load X+Y, can it load X and sleep Y, can it load X+Y and sleep Z, can it load
X+Y and sleep Z+W. The 2026-09-09 campaign measured seven carried gaps and
overturned four beliefs. This round is what those overturnings made necessary,
plus every coverage hole the capability envelope showed.

Two audits were run over the corpus before this was written — one across every
measurement record of the last three weeks, one across the capability envelope
and the code that implements it. Both are folded in; neither is quoted at
length, because a plan that restates its sources is a plan nobody reads twice.

**Owner ruling, 2026-09-09: no bench-only exclusion.** An earlier draft cut
every experiment that measures a capability `src/` cannot yet reach — which was
most of the sleep envelope and the highest-yield experiment on the list. That
cut is withdrawn. **A capability is measured before it is built, not after**;
knowing the envelope is what tells us which shapes are worth writing code for.

**70 arms.** At the last campaign's observed 4–5 minutes an arm that is roughly
**five hours of rig time**, and more with the long loads — KAT is 203 s a start,
the 80B 100–120 s, and the srv2 pair 130–170 s. This is a full day. It is
budgeted as one because the alternative is another round of single-sample
figures that the next campaign has to overturn.

## Before any arm runs

**The tree must be frozen first.** The last campaign flagged one measurement
irreproducible because another agent was moving `src/` while arms ran: the door
opens a new round by itself and the product hash under each arm moved with it.
Everything in this section lands, the suite goes green, and only then does an
arm run.

### Three `src/` changes

**Status: the freeze is done.** All three `src/` changes and all four
corrections have landed; what follows describes each as built.

1. **The wrong-weights check** — done. `Completion.served_model` compared
   against `is_model`, which moved out of `availability` into `mcgyvr/weights.py`
   so that the runner below the seam and availability above it read one
   spelling. Closes the hole `cli._climb` documents.
2. **`condition: service_healthy` for the vLLM pair** — done. Q14 cannot be
   asked without it, and it is the fix for the crash-restarts that hid inside
   the 168 s pair figure for weeks. `service_started` releases the waiter as
   soon as the process ahead *exists*, about a second, and always long before
   that process has sized its cache off what is free.

   Two things came with it. `service_healthy` against a service that declares
   no healthcheck never releases, so `_sequence_on_one_card` now writes a
   `/v1/models` healthcheck — **only on a service something waits for**, so no
   single-unit rig's compose file moves and srv1 is untouched. And the check is
   `CMD-SHELL` with a `wget` fallback, because the two engines ship different
   base images and neither promises `curl`: a check whose binary is absent is a
   container that is unhealthy forever and a waiter that never starts.

   **Validate the healthcheck on srv2 before any live re-emit.** Q14's first
   arm is where it would show, and it is a bench compose, so the blast radius
   is one arm rather than the live pair.
3. **`servelib.sleep(host, port, level)`, refusing level 1** — done. This is
   O9, and
   under full coverage it stops being speculative: **this campaign issues
   sleeps** (Q8, Q9, Q10), and today the only code that can is
   `tools/bench/serving/calibrate.py`. Giving the ban a home and giving the
   campaign its instrument are the same commit. The refusal carries the measured
   reason: 13.46 GiB of host RAM surrendered permanently to free a card that
   level 2 frees for nothing, 4–12× faster.

### Four corrections that cost no rig time, and must not be paid for with any

* **`F4.3` averages a bimodal table** — corrected. The real table is
  **792.0 MiB at blocks 0, 1 and 2 and 728.0 MiB at the other 45**, 34.3125 GiB
  over 48, whose mean is the 732 that was quoted. Two consequences, both now in
  `formulas.md`: the **marginal** block past the third is 728 MiB, so a deficit
  is bought back slightly more slowly than 732 implied; and the three expensive
  blocks are the **first** three, which is the end `--n-cpu-moe N` offloads
  first, so `ncmoe 3` buys 2,376 MiB against the 2,196 an average predicts.
* **`WORST_MEASURED_WAKE_S = 203.0` is not the worst** — corrected, and it
  **opened an owner call**. 385.3 s is the worst, in `ram-headroom-2026-09-09`
  § "The two gates fail differently", and checking it changed the fix: 385.3 is
  a wake that **landed**, on srv1 ballooned to −0.97 GiB against its experts —
  2.9× the baseline, 2.3 million major faults, decode at 32%, gate 7 green and
  nothing erroring.

  So the two facts are recorded rather than averaged. `WORST_MEASURED_WAKE_S`
  keeps 203.0 and now says what it is — the worst among placements the refusal
  gate **permits** — and a second constant carries 385.3 with its own, thinner
  assertion.

  **The call: 480 s clears 385.3 by 1.25×, not by 2×.** The test's own rule is
  that the fix for a margin this fails is a re-measurement and a new default,
  never a wider assertion. It is not failing, so nothing was changed — but the
  gate keeping placements out of that state is `REFUSAL_RAM_HEADROOM_GB = 2.0`,
  whose cliff is bracketed only to 0.63 GiB on single samples. **Q5 is what
  informs this decision**, and the decision is the owner's.
* **`fleet-shape/evidence_and_params.md` §9 and gaps G11a/G11b describe the
  pre-campaign world** — port as discriminator, mixed host refused, partition
  rather than covering. Mark them superseded by the `alternate`, `launch_specs`
  and `hold_together` docstrings, which are current. Every `src/…:LINE` citation
  in that file is stale on this branch; strip them rather than renumber.
* **The campaign README's remaining contradiction** — corrected to 140.75 s in
  all three places (137.7 + 141.5 + 142.7 + 141.1 = 563.0, over 4). The
  10.32/10.23 pair was already done.
* **`evidence_and_params.md` §9 and G11a/G11b** — corrected. §9 carries a
  superseded banner naming the three statements that are now false, both gaps
  are marked, and **all 52 stale `src/…:LINE` citations in that file were
  stripped** rather than renumbered: a file plus the symbol named beside it
  resolves, and a line number does not.

### Q2 was rewritten by the scan, and it is now a better experiment

The scan of 2026-09-09 killed Q2 as drafted and replaced it with something
stronger.

**What the scan found.** srv1 holds exactly two MoE blobs under 8 GiB. One is
Ling-3.0-tiny Q4_K_M at 4.58 GiB, already a fit point. The other is
`4b-Q4_K_M.gguf` at 3.01 GiB, and `ggufscan` confirms what the last campaign
recorded: `arch: gpt-oss`, `sliding_window: 128`,
`sliding_window_pattern_declared: false`. `emit` refuses it because the cache
cannot be sized and nothing is placed from an invented split — a principled
refusal that is not to be worked around during a freeze. The three candidates
this plan first named are not on the fleet at those quants: srv1 has
North-Mini-Code Q4_K_M (17.46), Nemotron IQ4_NL (16.77) and Ornith Q3_K_M
(16.89), all far above 8 GiB, and srv2 holds no MoE blobs at all.

**So there was no second small blob to find, and looking for one was the wrong
question.** Two arbitrary new models would have added two more points to a fit
that already confounds architecture with bytes — the defect Q3 names.

**Ling-3.0-tiny is published at every quant from 2.63 to 7.83 GiB.** One
architecture, one layer count, one expert structure, blob bytes varying by 3x,
across exactly the small end where the proportional form fails worst — it
predicts Ling at 49.7 s against 72.6 measured. And Ling runs with **no
`--n-cpu-moe` at all**, so the offload term is not merely matched across the
ladder, it is absent.

Four quants are being fetched to srv1 (2.3 TiB free); Q4_K_M is already there:

| blob | GiB |
|---|---|
| `Ling-3.0-tiny-IQ2_M` | 2.63 |
| `Ling-3.0-tiny-Q3_K_M` | 3.53 |
| `Ling-3.0-tiny-Q4_K_M` | 4.58 *(on disk)* |
| `Ling-3.0-tiny-Q6_K` | 6.37 |
| `Ling-3.0-tiny-Q8_0` | 7.83 |

**No arm may run while a download is in flight.** A 20 GiB fetch moves the page
cache, and every mapped-blob figure in this campaign is a page-cache
measurement.

**A quant ladder is not a free lunch and the analysis must say so.** Quants
differ in more than size: type mix changes, and IQ quants dequantise differently
from K quants, so a load rate across them is bytes *plus* whatever the type
costs. That is still a far smaller confound than five models at three windows,
and it is testable inside the ladder — IQ2_M against Q3_K_M is a type change at
almost the same size, and Q6_K against Q8_0 is nearly pure bytes.

---

# srv1 — 41 arms

## Q1. The srv1 wake law, and four card figures nobody has ever read *(11 arms)*

Every srv1 checkpoint has a wake time and **no card reading at all**. The 1 Hz
sampler has never been attached to one. These arms cost no new compose, no new
engine and no new risk, and they close four UNKNOWN cells while raising three
single-sample wakes to n=2 or better.

| arms | what |
|---|---|
| 1–2 | Ling-3.0-tiny Q4_K_M alone, `-c 8192`, mapped, cold, 1 Hz sampler, n=2 |
| 3–4 | deepseek-coder-v2-16b, `-c 8192 ncmoe 19`, mapped, sampler, n=2 *(was n=1)* |
| 5–6 | gemma-4-26B-A4B IQ3_XXS, `-c 8192 ncmoe 22`, mapped, sampler, n=2 |
| 7–9 | KAT-Coder alone, forced unmapped (16.90 GiB overflows 14.19), sampler, **n=3** |
| 10–11 | Qwen3.6-35B `-c 8192` (2 × 4096), `ncmoe 30`, mapped, ample clearance, n=2 |

Arms 7–9 settle the worst-wake constant. Arms 10–11 are the window control:
today Qwen alone runs `-c 16384` while every other srv1 blob runs `-c 8192`, and
`wake-2026-09-08` prices the window alone at **+48 s** — more than twice the
intercept the fit is claiming.

## Q2. Is the intercept real? — the Ling quant ladder *(8 arms)*

M4 reported a positive intercept of ~22.5 s and named that the reason to abandon
the proportional form. **Refit the same five rows without Ling and the intercept
returns to −24.3 s with a better R²** (0.979 against 0.929). The sign flip rests
entirely on one blob, and the 3.01 GiB point that would have discriminated is
the gpt-oss `emit` refuses.

Arms 12–19: Ling-3.0-tiny at **IQ2_M (2.63), Q3_K_M (3.53), Q6_K (6.37) and
Q8_0 (7.83)**, n=2 each, mapped, ample clearance, `-c 8192`. With Q1's arms 1-2
at Q4_K_M that is **five points on one architecture** spanning 2.63 to 7.83 GiB,
with no offload term anywhere in the ladder.

An intercept that survives this is real: no blob-identity, window or offload
confound can produce it, because none of the three varies. An intercept that
does not survive it was Qwen's window all along.

## Q3. Are those five rows one measurement at all? *(0 new arms)*

They are not. Window and offload depth both vary monotonically with blob size —
Ling `-c 8192` with no `--n-cpu-moe` at all, gemma `ncmoe 22`, deepseek
`ncmoe 19`, Qwen `-c 16384 ncmoe 30`. Q1's arms 10–11 and Q2's arms put every
srv1 point on one window, which is what makes a fit across them a fit rather
than four different experiments plotted together.

## Q4. The geometry-path headroom, srv1 half *(4 arms)*

Arms 16–19: Qwen3.6 mapped at `ncmoe 28` and `ncmoe 32`, n=2 each, recording
`vramfit`'s prediction against the sampler's steady state. `ncmoe 30` is already
n=4. See Q11 for what the two halves produce together.

## Q5. Where exactly is the experts cliff? *(6 arms)*

`REFUSAL_RAM_HEADROOM_GB = 2.0` guards a failure now bracketed to **0.63 GiB** —
between −0.34 and −0.97 GiB of clearance against the spilled experts. Every
point bracketing it is n=1, the step is a **33× change in slope**, and the
failure it guards is silent: a rig serving off swap at 32% of rate with gate 7
green.

Arms 20–25: Qwen3.6 unmapped, ballooned to −0.50 / −0.65 / −0.80 against the
9.2 GiB of experts, n=2 each. Locates the step to ~0.15 GiB.

## Q6. Does decode collapse at deep blob clearance, or was that one cold sample? *(4 arms)*

`ram-headroom` says decode never degrades on the blob axis. The campaign says
**5.09 tok/s at −3.03 GiB against 22.1 at −2.03** — a 5× collapse from one cold
sample with no warm-up, against an earlier sweep that only ever covered a range
stopping at −0.98. Both sides of a 5× claim are n=1.

Arms 26–29: Qwen3.6 mapped, ballooned to −3.03 and −2.50, discarded warm-up,
3 measured samples per arm, n=2 each.

## Q7. Two llama.cpp units co-resident on srv1 *(2 arms)*

The only place `hold_together`'s host-RAM sum can be made to **bind**. srv2's
44.5 GiB makes the sum invisible; srv1's 14.19 GiB does not. Two geometry-sized
units never co-reside — each fills the card independently, which is why
`alternate` cuts them — so this needs declared figures and a hand-written
compose, as the mixed-host test fixtures already do at 8 + 8 + 3 on 12.

Arms 30–31. Carries srv1's hard-lock hazard.

## Q8. What does `mcgyvr`'s own clock measure? *(3 arms)*

`wake.py` records wall clock around `spawn_door` — a third instrument that
includes gates 1–7, the rig lease and ssh — while every figure in the corpus is
`StartedAt` or the door's own "up after" clock. `METHOD.md` shows those two
differ by ~7 s clean and by **−80 s when a container restarts**, and
`DEVIATION_RATIO = 1.5` is fitted to nothing.

Arms 32–34: `serve up` on srv1 through `mcgyvr` itself, all three clocks
recorded on the same arm, n=3. Also prices the door's own overhead, which
nothing currently does.

## Q9. `r(srv1, vLLM)` and the `ram_gb = 0.0` hole *(3 arms — LAST, ALONE)*

Two open items collapse into one experiment. `Fit.ram_gb` is **0.0** for both
live vLLM units while the pair measurably costs 5.49 GiB, so `hold_together`'s
host-RAM sum is a no-op on the only co-resident set this fleet runs. The
per-unit constant (2.92–2.95 GiB) is measured only on srv2, where 45 GiB makes
it invisible; on srv1's 14.19 GiB it is **20% of the host**. And
`r(srv1, vLLM)` is the one coefficient in `wake-timeout.md` with no measurement
behind it at all.

Arms 35–37: Qwen2.5-Coder-3B-AWQ alone on srv1, `--dtype float16` (TU116 has no
bfloat16), `--gpu-memory-utilization 0.60`, n=3, reading `MemAvailable` and
`Shmem` either side. First vLLM deployment on the lock-prone rig, needs a
compose nothing in the tree writes. **Run it last and alone.**

---

# srv2 — 29 arms

## Q10. The geometry-path headroom, srv2 half — and the 80B decode contradiction *(10 arms)*

Two questions, one ladder, because they want the same arms.

**The headroom.** `vramfit` over-predicts by 63 MiB, and a geometry-sized
placement's only card allowance is `SCRATCH_AND_CONTEXT_MIB` (768 MiB, a
generous bound over a measured 255–521 MiB range) folded *inside* the
prediction — `DEFAULT_HEADROOM_GB` (2.0 GiB) applies only to scalar specs. That
is how `--n-cpu-moe 35` mapped came to clear srv1's card by ~16 MiB. Only two
accuracy points exist, both n=1, different models, different hosts.

**The decode.** `ram-headroom` reads 29.71 / 29.51 / 29.19 tok/s (n=3, warm,
`ncmoe 35`). The campaign reads 13.02 / 13.46 / 12.30 / 12.81 (one cold sample
each, `ncmoe 36` and `40`). The composes are byte-identical apart from
`--n-cpu-moe`. **One extra offloaded block cannot cost 56%** — one of the two
instruments is wrong about the rung the ladder most wants to add, by 2.3×.

Arms 38–47: 80B mapped at `ncmoe 35 / 36 / 38 / 40 / 41`, n=2 each. Every arm
records `vramfit`'s prediction against sampler steady state **and** decode on
`ram-headroom`'s instrument exactly — discarded warm-up, 3 measured samples,
160 tokens, `temperature 0`, `cache_prompt false`. If the instrument is the
difference, this says so and the campaign's whole decode column needs an
asterisk.

## Q11. The headroom constant *(0 arms)*

Q4 and Q10 together produce it: **the worst signed residual across every
geometry placement this fleet has ever run**, srv1 and srv2, mapped and
unmapped. That number is the deliverable G1's redefinition asked for, and
nothing implements it today.

## Q12. `Λ(80B, w)` has never been measured at any width *(1 arm, three windows)*

`F6.2` and `F8.1` price waking the 80B as `Λ(80B) × 100 s` of foregone tokens —
the objective that picks `fleet.next` — and `Λ(80B, w)` does not exist at any
width. `serving-concurrency-2026-09-06` covers the 3B, the 7B, srv1's Qwen and
srv2 CPU-only, and no 80B.

Arm 48: `tools/serving/concurrency_sweep.py` against the 80B at `ncmoe 36`,
widths 1 / 2 / 4. The compose runs `--parallel 2` today and must be widened.

## Q13. `r(srv2)` is worse than no fit at all *(6 arms)*

The proportional fit has **negative R²** across three points — worse than a
horizontal line — and predicts deepseek 53% low. The affine alternative fits no
better. And the campaign's own arms half-refute the "bytes uploaded"
explanation: srv2's Qwen3.6 wakes in 79.9 s at `ncmoe 7` and 84.8 s at
`ncmoe 40`, a 33-block swing worth 6%.

Arms 49–54: srv2, Qwen3.6 at `ncmoe 7 / 20 / 40`, mapped, matched window, n=2
each. Decouples offload depth from blob size without needing checkpoints the
fleet does not have.

## Q14. Is sleep-mode's 36 s advantage the flag, or the absence of crashes? *(2 arms)*

M5 found the plain pair crash-restarts the 3B one to two times per cold start,
hidden by `restart: unless-stopped`, because `depends_on: service_started`
releases the 3B before the 7B has taken its card. The sleep-mode pair starts
36 s faster with 0 restarts. **So the comparison was never flag-against-no-flag;
it was crashing-against-clean.** It matters because the flag costs **+1.0 to
+1.8 GiB of a 12 GiB card**.

Arms 55–56: the plain pair, no sleep flag, `condition: service_healthy` in
place, cold, `RestartCount` recorded on both containers, n=2.

## Q15. What does the sleep-mode pair actually cost, and why does it vary? *(4 arms)*

The live config declares `vram_gb` 3.49 / 7.12 against a measured 3,810 and
6,816 MiB — the 3B is **under-declared by 236 MiB**. And the sleep-mode pair
moved by +1.0–1.8 GiB with a **616 MiB unexplained spread between two arms of
the same config**, all of it invisible to the declared figure.

Arms 57–60: the sleep-mode pair alone on srv2, same compose, cold each time,
n=4, per-process `nvidia-smi --query-compute-apps` at steady state. **Each arm
then runs a sleep/wake cycle at level 2 on both units**, reading per-process
card at both-serving and at both-asleep — which folds in the separate question
of whether `V_awake` and the derived releases (3,582 / 6,582) match M6's
directly measured ones (3,562 / 6,562), a 20 MiB disagreement of the same size
as the margin Q11 is about. **Three cycles per arm**, to answer whether the
residual CUDA context grows with cycling: 477 MiB and 503 MiB are both on
record, n=1 each, with no mechanism.

## Q16. The three-way matrix — a sleeper *and* a live co-resident on one card *(4 arms)*

**The highest cells-per-arm experiment available, and the one the earlier draft
cut.** It is the only state that exercises `V_avail(h,S)` with a sleeper and an
awake unit on the card simultaneously — which is exactly the "can it load X+Y
and sleep Z" question this campaign is named for. Never run.

Arms 61–64: 80B at `ncmoe 41` with the 7B asleep (7,873 MiB free), and at
`ncmoe ≥ 45` with the 3B asleep (4,853 MiB free), n=2 each, 1 Hz sampler
throughout. Both placements are `vramfit` predictions less M1's 63 MiB
over-prediction, so **Q10 must land first** — its residual sets whether these
placements are feasible as written.

## Q17. Re-take M2's co-residency verdicts against the current tree *(2 arms)*

M2 measured the first two-MoE co-residency ever run here — `Shmem` 7.47 + 10.76
= **18.23 GiB exactly**, card 5,711 of 5,712 MiB. The law held. But the campaign
README flags M2's four `emit` verdicts irreproducible: another agent was moving
`src/` throughout, and if `hold_together` or `alternate` moved during those
probes the verdicts need re-taking. They have since moved — the covering, the
card-contention discriminator and the retired mixed-host refusal all landed on
this branch.

Arms 65–66: deepseek-coder-v2-16b `ncmoe 26` + Qwen3.6-35B `ncmoe 40`, both
llama.cpp, both `--load-mode none`, from the hand-written compose, n=2 — with
`emit`'s verdicts re-taken against the frozen tree.

---

## How the four carried items map

| carried item | answered by |
|---|---|
| card headroom on the geometry path | **Q4 + Q10 → Q11** |
| real `ram_gb` for declared-figure units | **Q9**, and Q15 for the declared-vs-measured gap |
| `r(srv1, vLLM)` | **Q9** — the same three arms |
| steady-state decode at `−3.03` | **Q6** |

## Order of execution

Ordered to minimise model swaps, and to put every hazard last.

1. **Freeze**: three `src/` changes, four zero-cost corrections, blob selection
   for Q2, full suite green.
2. **srv2, 80B block** — Q10 (10), Q12 (1). One model resident throughout.
3. **srv2, Qwen block** — Q13 (6). One swap.
4. **srv2, pair block** — Q14 (2), Q15 (4). One swap.
5. **srv2, three-way** — Q16 (4). Needs Q10's residual in hand.
6. **srv2, co-residency** — Q17 (2).
7. **srv1, mapped block** — Q1 (11), Q2 (8), Q4 (4).
8. **srv1, ballooned block** — Q5 (6), Q6 (4).
9. **srv1, door block** — Q8 (3).
10. **srv1, hazards last** — Q7 (2), then **Q9 (3), alone**.

**Report when every arm is done and both rigs are idle, not before.** Context
stays lean throughout: arm results land in the run's own records, not in the
session.
