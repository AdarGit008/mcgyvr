# `wake_timeout_s` — derive it per unit, not per fleet shape

**Recommendation.** Budget a wake as a property of the *unit* being woken —
`blob × host×engine rate × clearance penalty` for llama.cpp, a per-unit
constant for a vLLM cold start, a per-unit constant for a vLLM L2 wake — summed
over the units one launch spec sequences, and held under the config's single
`budgets.wake_timeout_s` ceiling as an upper bound rather than replacing it.

**The alternative this argues against.** Keying the budget on the *fleet setup*
— a number per (model × shape) pair, looked up by what else is resident — which
needs a measurement per pair, and under the fluid fleet the owner ruled for on
2026-09-09 (handoff, ruling 6) the number of shapes is not bounded by anything
this repository can measure.

The case is not that the per-unit fit is good. It is not. Section 4 says how bad
it is and what it would take to fix, because that is the part of this argument
that has to survive contact with the next measurement. The case is that the
per-unit form needs **six numbers this fleet can actually take**, where the
shape form needs a matrix whose row count grows with the catalogue.

---

## 1. What is already settled, and is not being put to the owner again

`tests/test_a_wake_is_asked_for_in_the_config_and_bounded_by_its_own_budget.py`
is the config-schema spec for this budget. It is RED — it needs
`src/mcgyvr/wake.py`, which does not exist — but it is approved RED, and eight
tests in it pin decisions that nothing below revisits:

| pinned | by | value |
|---|---|---|
| it is a **config key**, not a flag | `test_a_config_that_asks_for_sleep_and_wake_is_not_refused_as_an_unknown_key`, and the module docstring's first bullet | `budgets.wake_timeout_s`, beside `serving.enable_sleep_wake` (default `False`) and `serving.compose_dir` |
| it is **its own number** | `test_a_wake_budget_is_neither_the_request_nor_the_task_one` | not derived from `request_timeout_s` (default 120.0) or `task_timeout_s` (default 900) — `src/mcgyvr/config.py:619-641` |
| it is **defaulted and filled in**, not absent | `test_a_wake_budget_is_defaulted_and_is_not_a_re_spelling_of_the_other_two` | a `float`, readable off a config that never mentioned it |
| it has a **floor at the door's own health budget** | `test_a_wake_budget_under_the_doors_own_health_budget_is_refused_by_name`, `..._at_or_above_..._is_accepted` | `HEALTH_POLLS × HEALTH_INTERVAL_S` = 120 × 3.0 = **360 s** (`src/mcgyvr/serving/servelib.py:41-42`), and a config below it is refused *naming that number* |
| the **default clears the fleet's worst measured wake twice over** | `test_the_default_wake_budget_clears_the_slowest_wake_ever_measured` | `default >= 2 × 203.0 = 406 s` |

So the owner is not being asked whether there should be a single config
constant. There is one, its floor is 360 s, and its default must be at least
406 s. Everything below is about what happens *underneath* that ceiling: what
number a scheduler should expect a particular wake to take, and where that
number comes from.

---

## 2. The evidence, re-derived

Every figure in this section was recomputed from the measurement READMEs rather
than carried over. Where a re-derivation disagrees with the 2026-09-09 handoff,
the measurement wins and the disagreement is named.

### 2.1 Wake is roughly linear in blob, at a rate that is per host **and per engine**

`records/measurements/ram-headroom-2026-09-09/README.md` § "The sweep" and § 2a,
plus `records/measurements/wake-2026-09-08/README.md`. All wakes timed from the
container's own `StartedAt` in UTC.

| unit | blob | wake | n | s/GiB | GiB/s |
|---|---|---|---|---|---|
| srv1 deepseek-16b, mapped, +1.93 | 8.29 GiB | 85.7 s | 1 | 10.34 | 0.0967 |
| srv1 Qwen3.6, mapped, +1.93, `swappiness=0` | 12.30 | 140.8 s | 3 | 11.45 | 0.0874 |
| srv1 Qwen3.6, mapped, `swappiness=60` | 12.30 | 139.6 s | 3 | 11.35 | 0.0881 |
| srv1 Qwen3.6, unmapped, `swappiness=60` | 12.30 | 132.9 s | 3 | 10.81 | 0.0926 |
| srv2 80B, mapped, +2.02 | 35.67 | 102.9 s | 1 | **2.89** | **0.3466** |

`r(srv1) = 0.0920 GiB/s` is the mean of the deepseek point and the 140.8 s Qwen
point, spread ±5.1% — which is `records/plans/fleet-shape/formulas.md` F3.1
exactly. `r(srv2) = 0.3466 GiB/s`, n=1. The ratio is **3.77×**, and F3.1 records
that memory bandwidth points the other way (srv1 reads 40.3 GB/s, srv2 27.9), so
`r` is a fitted per-host constant with no mechanism behind it.

**Where the handoff's table disagrees with its sources.** The handoff prints
`srv1 Qwen mapped 139.6 s → 11.4 s/GiB`. That is the `swappiness=60` figure
from § 2a. `formulas.md` F3.1 fits `r(srv1)` from the **140.8 s** figure — the
`swappiness=0` sweep arm. Both are real, both are n=3, and they differ by 1.2 s
(0.9%), which is inside the rig's own drift. It does not move `r(srv1)`
materially (0.0920 against 0.0924 if the other figure is substituted), but the
two documents should not be quoting different mapped-Qwen wakes: **`formulas.md`
is the fit of record, so 140.8 s is the number, and the handoff's 139.6 is the
comparison arm for F3.3's mapping term, not the rate point.**

**Where the handoff's claim "engine does not appear" is wrong.** This is the one
substantive correction. What `wake-2026-09-08` settles is that neither engine is
faster *at the whole-unit wall clock* — 82 s for a vLLM unit alone against a
50–128 s llama.cpp band on the same fleet. That is not the same claim as the
rate being engine-free, and `formulas.md` F3.1 already says so in as many words:

> vLLM does not lie on this line: `5.2 GB / 82 s = 0.063 GiB/s` on srv2, where
> llama.cpp reads 0.347.

That is a **5.5× difference in rate on one host**, which is larger than the
3.77× difference between the two hosts. Engine appears, and it appears in the
coefficient the recommendation is built on. `r` must be keyed by (host, engine).

### 2.2 For vLLM the honest form is a constant, not a rate

Two vLLM cold-start points exist, and taken together they refute the
proportional form outright:

| vLLM unit | blob | cold wake | s/GiB |
|---|---|---|---|
| srv2 7B-AWQ, alone, `depends_on` stripped | 4.93 GiB (5.29 GB) | **82 s**, n=1 (`wake-2026-09-08`) | 16.6 |
| srv2 3B-AWQ, implied: pair 168 s − 7B 82 s | 1.95 GiB (2.09 GB) | **86 s**, derived | 44.1 |

A blob 2.5× smaller took 4 s longer. As a proportional law those two points are
**2.65× apart**; as a constant they are 84 s ± 2.4%. The mechanism F3.1 already
names — HF cache read, engine-core init, CUDA graph capture — is a fixed cost,
and a fixed cost is what these two points measure. **A vLLM cold start should be
budgeted as a per-unit constant, and `blob × rate` should not be applied to it
at all.**

Two honesty notes on that 86 s. It is a subtraction, not a measurement: the
168 s pair restart was taken 2026-09-09 (n=3,
`records/measurements/vllm-sleep-2026-09-09/README.md`) and the 82 s single-unit
figure 2026-09-08 (n=1, `wake-2026-09-08`), a day and a campaign apart. And the
handoff's gloss — "the vLLM pair is 168 s because the 3B waits on the 7B, which
then takes **1.0 s**" — has **no source anywhere under `records/`**. Nothing
measures the 3B alone, and no row in `vllm-sleep-results.json` carries a 1.0 s
cold start. The subtraction says 86 s, not 1.0 s. That sentence should not be
repeated.

### 2.3 What the shape contributes: two terms, and only two

**Clearance.** `ram-headroom-2026-09-09` moved the blob against `MemAvailable`
on three models and found the whole cost of a shortfall lands on wake, never on
decode. Re-derived from § "The sweep":

| model | baseline | squeezed | shortfall | ratio | implied `k` |
|---|---|---|---|---|---|
| srv1 Qwen3.6 | 140.8 s (n=3) | 167.9 s (n=3) | 0.98 / 12.30 GiB | 1.1925 | 2.42 |
| srv1 deepseek | 85.7 s | 116.3 s | 0.98 / 8.29 | 1.3571 | 3.02 |
| srv2 80B | 102.9 s | 108.0 s | 0.84 / 35.67 | 1.0496 | **2.10** |

Mean **2.514**, which is F3.2's `k = 2.52`. (F3.2 prints 2.11 for the srv2 row;
the arithmetic gives 2.104. Rounding, not a disagreement.)

**Sequencing.** `depends_on` makes a launch spec's wake the sum of its units'
wakes, serialized: the srv2 vLLM pair is 168 s where the 7B alone is 82 s.
That is F6.1's `sum over u in B\A of T_up(u)`. Section 5 is about what
commit `d8c5cf0a` did to the set that sum runs over.

Nothing else in the shape shows up. A wake into a partially-occupied card has
exactly one point — the 80B at `--n-cpu-moe 36` into the 11,409 MiB two L2
sleepers leave, 100 s against 97 s into an idle card
(`vllm-sleep-2026-09-09`) — and the difference is inside the rig's drift. That
is the strongest evidence there is that the *shape* is not the axis: the one
measurement that varied the shape while holding the unit fixed moved the wake
by 3%.

---

## 3. The formula

```
T_budget(spec) = margin × Σ over u in spec, sequenced by depends_on, of T_wake(u)

T_wake(u) =  T0(u) × ( 1 + k(h) × shortfall(u) / B(m) )     llama.cpp cold
             T0(u) = B(m) / r(h, llama.cpp)                 [F3.1]
             shortfall = max(0, −clearance)                 [F3.2]

          =  T_cold_vllm(u)                                 vLLM cold, a constant
          =  T_wake_L2(u)                                   vLLM L2 wake [F3.5]

margin = 2.4      the ratio the door's own comment already uses ("three of the
                  slowest with room", servelib.py:38-40) and the ratio the
                  current 480 s default has over the fleet's worst emittable
                  wake (480 / 203 = 2.36)
```

**Where this differs from `records/plans/fleet-shape/formulas.md`, and why.**
It does not contradict it; it extends it in three places, and the extensions
should be folded back into F3.1 and F8.5 when whoever owns that directory next
touches it.

1. **`r` is keyed by (host, engine), not host.** F3.1 fits `r(h)` per host and
   then observes in prose that vLLM is off the line by 5.5×. The prose is the
   finding; the symbol should carry it.
2. **A vLLM cold start gets a constant, not `B/r`.** F3.1 leaves the vLLM form
   unstated. §2.2 above gives it one, from the only two points that exist, and
   says they refute the proportional alternative.
3. **The sum runs over a launch spec, not a host.** F6.1 says "serialized by
   `depends_on`", which was the same thing until `d8c5cf0a`. It is not any more
   (§5).

F8.5 already proposes precisely this shape —
`budget(cold llama.cpp wake) = 2.4 * F3.2` beside `~5 s` for an L2 wake and
`~5 s` for a named OOM refusal — so the recommendation here is F8.5's, made
per-unit-summable and given the engine key the evidence demands.

---

## 4. How weak this fit is, stated before it is used

Weak enough that it must never be allowed to *shorten* a budget. Every
coefficient in §3:

| coefficient | value | basis | how it fails |
|---|---|---|---|
| `r(srv1, llama.cpp)` | 0.0920 GiB/s | **n=2 models**, one at n=3 arms and one at n=1, spread ±5.1% | two points define a line; the two-point line *with* an intercept fits at `r = 0.0728, a = −28.2 s`, and a negative intercept is unphysical, which is the only reason the proportional form was chosen |
| `r(srv2, llama.cpp)` | 0.3466 GiB/s | **n=1**, one model, one arm | a single point cannot distinguish a rate from a constant at all |
| `r(srv1, vLLM)` | — | **no measurement exists** | srv1 has never run vLLM |
| `T_cold_vllm(srv2)` | ~84 s | **n=2 units**, one measured and one *subtracted across two campaigns* | the constant form is chosen because the two points are 2.65× apart as a rate; with two points that is a preference, not a fit |
| `k` | 2.52 | **n=3 models, one sub-zero point each**, only one of which is n=3 arms; spread 2.10–3.02 (**1.44×**) | over-predicts KAT by **27%** out of sample (§4.1) and *under*-predicts the refusal cliff by **2.4×** (§4.2) |
| `margin` | 2.4 | not measured at all; the door's comment and the existing default's ratio | an assumption, and the only thing standing between a wrong `k` and an abandoned wake |

### 4.1 The one out-of-sample check fails, high

KAT-Coder on srv1: `B = 16.90 GiB`, `M_avail = 14.19 GiB`, so
`clearance = −2.71 GiB`.

```
T0   = 16.90 / 0.0920                     = 183.7 s
pred = 183.7 × (1 + 2.52 × 2.71 / 16.90)  = 257.9 s
measured                                  = 203.0 s      (wake-2026-09-08)
```

Over by **27%**. The `k` that would land KAT exactly is **0.66**, against the
2.10–3.02 the three in-sample points give. So the penalty term saturates
somewhere between a 0.98 GiB shortfall and a 2.71 GiB one, and where it
saturates is unmeasured. **F3.2 is an upper bound, not a predictor**, and this
document adopts it as one.

### 4.2 And the same coefficient is wrong low, by more, on the other axis

This is worse than the handoff's framing admits and it is worth stating plainly.
`ram-headroom-2026-09-09` § "The two gates fail differently" measures a *second*
shortfall axis — clearance against the **spilled experts** rather than the blob
— and it produces the cliff: 385.3 s against a 132.9 s baseline at −0.97 GiB.
Feeding that shortfall through F3.2 with `k = 2.52`:

```
132.9 × (1 + 2.52 × 0.97 / 12.30) = 159.3 s      against a measured 385.3 s
```

Under by **2.4×**. The `k` that fits it is **24.1**, an order of magnitude off
the blob-axis fit. So `k` is not one coefficient with a spread; it is **two
coefficients on two axes** that F3.2 currently conflates, exactly as
`RAM_HEADROOM_GB` conflates two gates (`h_mode` = 0.5 vs `h_refuse` = 2.0).

The defence is that the cliff is a *refusal*, not a budget case: `G-refuse`
keeps 2.0 GiB precisely to make that configuration unemittable, and the 385.3 s
arm was reached by ballooning deliberately past the gate. But `G4` records that
the cliff's location is unmeasured — somewhere in the 1.5 GiB between +0.55 and
−0.97 — so a config on the wrong side of it can slip through, silently, and the
budget is the only thing that will ever notice. That is the whole argument for
keeping a generous fixed ceiling above the derived number.

### 4.3 What it would take to make each coefficient trustworthy

Every row below is a `sweep.py`-shaped campaign of the kind
`ram-headroom-2026-09-09` already ran, one arm per (model, condition) with a
discarded warm-up and three measured samples.

| to establish | needs | arms |
|---|---|---|
| `r(srv1, llama.cpp)` as a line rather than two points | a third clearing blob on srv1 (KAT does not clear — it overflows), plus deepseek raised from n=1 to n=3 | 3 + 2 = **5** |
| `r(srv2, llama.cpp)` at all | two further srv2 blobs at ample clearance, n=3 each | **6** |
| `T_cold_vllm` as a constant rather than a preference | the 3B alone with `depends_on` stripped n=3; the 7B re-taken n=3; ideally a third vLLM checkpoint | 3 + 3 + 3 = **9** |
| `r(srv1, vLLM)` | any vLLM unit srv1's 6 GiB card can hold, n=3 | **3** |
| `k` on the blob axis, with its saturation | three shortfalls (−0.5, −1.5, −2.7) × two models × n=2 | **12** |
| `k` on the experts axis, separately | three shortfalls × the one model that can carry them (srv1 Qwen unmapped) × n=2 | **6** |
| the cliff's location (G4) | bisect +0.55 → −0.97 against the experts at three points, n=3 | **9** |
| `margin` | nothing; it is a policy number and should stay declared, not fitted | 0 |
| the shape term, to confirm it stays absent | one llama.cpp wake into a card left by sleepers, against the same unit into an idle card, n=3 each | **6** |
| | **total** | **~56 arms** |

At the campaign rate `ram-headroom-2026-09-09` actually achieved — nine arms
plus four repeat passes in a day, with three arms lost to teardown and RUN_ID
hazards — that is on the order of a week of rig time, and it is the honest
price of turning §3 from an upper bound into a fit.

**Against which: the alternative.** Keying the budget on fleet setup needs one
measurement per (model × shape). Today's catalogue is
`{Qwen3.6, deepseek, KAT}` on srv1 and `{3B, 7B, 80B}` on srv2, with three
states each (`awake`, `asleep-L2`, absent) — and under ruling 6 the resident set
is runtime-chosen, so the shape a unit wakes into is not enumerable in advance.
The per-unit form has six coefficients and ~56 arms. The shape form has no
finite arm count, which is not a fit that is weaker; it is not a fit at all.

---

## 5. The sequencing term after `d8c5cf0a`

The sum in §3 runs over the units a **launch spec** holds, and as of commit
`d8c5cf0a` ("GREEN: two models on one URL are alternatives, and each is its own
launch spec") that is no longer the same as the units on a host.

`serving.launch_specs` (`src/mcgyvr/serving/__init__.py:955-1034`) now cuts a
ladder three ways:

* a host whose units **all come up together** stays one `compose.<host>.yml`,
  they share a card, `depends_on` sequences them, and the budget is the sum;
* a host whose units **take turns on a port** becomes one
  `compose.<host>.<model>.yml` **per alternative**, holding exactly one unit, and
  the budget is that unit's alone;
* a host carrying **both** is refused by name, as a `UnitError`.

**For alternatives this makes the budget strictly smaller, and by a lot.**
srv1's two alternatives, at `r(srv1) = 0.0920`:

| launch spec | units | `Σ T0` | × 2.4 |
|---|---|---|---|
| counterfactual: one file holding both | Qwen + deepseek | 223.8 s | **537 s** |
| as `d8c5cf0a` emits it: `compose.srv1.Qwen3.6-35B-A3B.yml` | Qwen alone | 133.7 s | **321 s** |
| as `d8c5cf0a` emits it: `compose.srv1.deepseek-coder-v2-16b.yml` | deepseek alone | 90.1 s | **216 s** |

537 s is over the current 480 s default; 321 s and 216 s are comfortably under
it. The counterfactual is genuinely counterfactual — before `d8c5cf0a`, `_emit`
refused a `base_url` bound to two models outright, so no such file ever
existed — but it is the shape the sum would have taken had alternatives been
folded into a host file, and it is the arithmetic that says the split was the
right call for this budget too, not only for `hold_together`.

For co-residents nothing changes: srv2's vLLM pair is still one file, still
`depends_on`-sequenced, still 168 s measured, and `2.4 × 168 = 403 s` — 77 s
inside the default.

One caveat to carry: the refusal of a mixed host is live in the code *and*
owner ruling 5 of the 2026-09-09 handoff withdraws the recommendation to refuse
that mix, on the grounds that under a fluid ladder it is the normal case. When
that refusal is lifted, the set a budget sums over becomes an owner's decision
about what a launch spec means — and this budget is one of the things that
decision will have to answer for, because a file holding an alternative *and* a
co-resident has two different sums depending on which alternative won.

---

## 6. The default: keep 480.0

Not because it was right when it was chosen — it was priced off the door's 360 s
health budget before anyone had timed a wake (N7) — but because it survives
every measurement taken since.

| it must clear | value | 480 clears it by |
|---|---|---|
| the door's own health budget, or the caller abandons a wake the door is still working on (`servelib.py:41-42`, and the RED test refuses below it *by name*) | 360 s | 120 s |
| `2 × WORST_MEASURED_WAKE_S`, asserted by `test_the_default_wake_budget_clears_the_slowest_wake_ever_measured` | 406 s | 74 s |
| the fleet's worst **emittable** wake — KAT on srv1, 16.90 GiB into 15 GB of RAM, mapped | 203 s | **2.36×** |
| the fleet's worst wake **ever recorded**, squeezed past `h_refuse` into the cliff | 385.3 s | 94.7 s |
| the largest sequenced sum any launch spec on this fleet emits, `2.4 ×` the 168 s vLLM pair | 403 s | 77 s |
| distinctness from its neighbours (`request_timeout_s` 120.0, `task_timeout_s` 900) | — | both |

It must also *not* be raised to satisfy the fit. `2.4 × F3.2`'s KAT prediction
is 619 s, and KAT wakes in 203 s. Moving the ceiling to accommodate an
over-predicting upper bound would be letting the weakest number in this document
set the strongest one.

The two figures the default does **not** need to cover, because they belong to
different mechanisms and F8.5 already says each should get its own budget: a
vLLM L2 wake (0.24–0.31 s) and a named CUDA-OOM refusal (0.395 s). Bounding
those with 480 s is what makes the current constant span a factor of ~1,600 and
is the whole of `G3`.

---

## 7. The open question for the owner

Everything above is either measured, cited as unmeasured, or already pinned by
the RED tests. One thing is none of those, and it is a policy call rather than
an evidence call:

> **May a derived per-unit budget ever be *shorter* than
> `budgets.wake_timeout_s` — that is, may it abort a wake — or does it only ever
> inform scheduling, with the config constant remaining the sole authority that
> gives up?**

The consequence is concrete in both directions. If the derived number may abort,
then a wake that was about to land can be abandoned by a coefficient that is
27% high on the one out-of-sample point it has and 2.4× low on the one axis it
was not fitted for, and the failure is a card left half-up — the one state D2
says the reading cannot name. If it may only inform, then §3 is a planning input
for `J(S|A)` and `T_trans` (F6.1, F8.1) and nothing else, the 480 s ceiling
stays the only thing that gives up, and the price is that a 0.24 s vLLM wake
sits under an eight-minute abort until the per-mechanism budgets of F8.5 are
written.

The rest of this document holds either way. Only the answer to that decides
whether the coefficients in §4 are load-bearing or advisory — and therefore
whether the ~56 arms in §4.3 have to be spent before any of this ships.
