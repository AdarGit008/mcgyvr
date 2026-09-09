# Formulas for one verdict: what shape should the fleet be right now

Every symbol is defined in [`evidence_and_params.md`](evidence_and_params.md).
Each formula names its **kind** — MEASURED law, FIT (with the points), or
ASSUMPTION. Units are stated. Nothing here introduces a number that is not
cited there.

Notation: a **unit** `u = (host h, model m, engine, port, offload n, width w,
window c, load mode)`. A **shape** `S(h)` is the set of units resident on `h`,
each in state `awake`, `asleep-L2`, or `asleep-L1`. `fleet = (S(srv1), S(srv2))`.

---

## Q1 — How much VRAM does a unit need?

**F1.1 — card need of a llama.cpp unit** (MEASURED law; accurate to 41 MiB on
the one placement checked against `nvidia-smi`, srv1 2026-09-06, n=1)

```
V_need(u)  =  W_ne(m)                       non-expert weights, tensor table
            + KV(m, c·w, w)                 cache, summed over caching layers only
            + RS(m, w)                      recurrent state, per slot
            + E_on(m, n)                    expert blocks with index >= n
            + A(m)                          scratch allowance
                                                                        [bytes]
A(m) = MEASURED_SCRATCH_MIB[arch(m)]  if probed,  else 768 MiB
```

`KV` never appears on the host: **neither engine offloads KV, ever.** So no
term of `V_need` may be traded against host RAM except `E_on`.

**F1.2 — the offload floor** (MEASURED law)

```
n*(u) = min { n in [0, n_blocks] : C(w) + E_on(m, n) <= V_avail(h, S) }
C(w)  = W_ne + KV(m, c·w, w) + RS(m, w) + A(m)
```

Walked block by block off the tensor table, most-on-card first. `n*` = ∅ means
the **card** is too small, not that the config is wrong. Per-block expert bytes
are bimodal (Qwen3.6 IQ3_XXS: 262.0 MiB × 37, 300.0 MiB × 3), so a per-block
average puts the floor three steps high.

`--n-cpu-moe` saturates at the layer count: `n >= n_layers` is a no-op.

**F1.3 — width from the card** (MEASURED law, when nobody wrote a width)

```
w(u) = max { w in [1, MAX_WIDTH] : n*(w) == n*(1) }
```

The largest width that does not cost an expert block. `MAX_WIDTH = 32`.

**F1.4 — vLLM units** (MEASURED, per unit)

```
V_need(u) = the unit's measured footprint            [MiB]
```

The cache law is **not** consulted: vLLM sizes from `--gpu-memory-utilization`
and prices a request against `--max-model-len`. Measured, not declared:
`V_awake(3B) = 3,810 MiB` against a declared 3.49 GiB; `V_awake(7B) = 6,816 MiB`
against a declared 7.12 GiB (n=1 each).

---

## Q2 — How much host RAM does a unit need?

**F2.1 — the two arms** (MEASURED law; the split is `fit`'s, the numbers are
the 2026-09-09 sweep's)

```
R_need(u) =  B(m)                                    if mapped   (default)
          =  (E(m) - E_on(m, n)) / 2^30  +  1.53     if --load-mode none
                                                                        [GiB]
```

Mapped, the whole GGUF is paged through the page cache and the kernel may evict
it, so the **blob** is what has to fit. Unmapped, only the spilled experts are
resident — as `Shmem`, which **is swappable** (8.09 GiB measured on srv1 with
`/dev/shm` at 100K and no tmpfs; both rigs run 8 GiB of swap). `1.53 GiB` is
`RUNTIME_RESIDENT_GB`: flat at 1.52–1.53 across six offload cells from 4 to 20
blocks, which is what makes it an intercept and not a rate.

A unit with nothing to spill takes neither arm: host RAM does not constrain it.

**F2.2 — a shape's host RAM** (ASSUMPTION — **G2: nothing sums this today**)

```
R_shape(h, S) =  sum over u in S, awake      of R_need(u)
              +  sum over u in S, asleep-L1  of R_retained_L1(u)
              +  sum over u in S, asleep-L2  of 0
```

`hold_together` sums card figures only. Summing the RAM arm is proposed here and
is unvalidated: no measurement on this fleet has two llama.cpp MoE units
co-resident on one host.

**F2.3 — L1 retention** (MEASURED n=1)

```
R_retained_L1(3B) = 3.12 GiB     (MemAvailable 39.18 -> 36.06)
R_retained_L1(7B) = 10.32 GiB    (36.06 -> 25.74)
```

Retained **for the process's lifetime, awake or not** — 13.46 GiB gone with both
units awake and serving after one L1 cycle each. Consequence: **level 1 is
refused, not offered.** F2.2's L1 row exists only to say why.

---

## Q3 — How long will a unit take to wake?

**F3.1 — cold wake, llama.cpp, ample clearance** (FIT, 2 points on srv1 and 1 on
srv2)

```
T0(u) = B(m) / r(h)                                                       [s]

r(srv1) = 0.0920 GiB/s     from 12.30/140.8 = 0.0874 and 8.29/85.7 = 0.0967
                           n=2 models, spread +/-5.1%
r(srv2) = 0.3466 GiB/s     from 35.67/102.9,  n=1
```

A two-point line with an intercept fits srv1 at `r = 0.0728 GiB/s, a = −28.2 s`
— a negative intercept, which is unphysical, so the proportional form is used
and the 5% spread is carried instead.

`r(srv2)/r(srv1) = 3.77`. This is **not** explained by memory bandwidth, which
points the other way (srv1 reads 40.3 GB/s, srv2 27.9). Treat `r` as a
per-host fitted constant with no mechanism, and re-fit it, never extrapolate it.

vLLM does not lie on this line: `5.2 GB / 82 s = 0.063 GiB/s` on srv2, where
llama.cpp reads 0.347. Different mechanism (HF cache read, engine-core init,
CUDA graph capture). **Neither engine is measurably faster to wake** at the
whole-unit level (82 s vLLM against a 50–128 s llama.cpp band on the same fleet).

**F3.2 — the RAM-clearance penalty** (FIT, n=3 models, one sub-zero point each)

```
clearance(u, h, S) = M_avail(h) - R_shape(h, S \ {u}) - R_need(u)         [GiB]
shortfall          = max(0, -clearance)

T_wake(u) = T0(u) * ( 1 + k * shortfall / B(m) )                          [s]

k = 2.52     from  srv1 Qwen  +19.3% at 0.98/12.30 -> k=2.42   (n=3 arms)
                   srv1 deepseek +35.7% at 0.98/8.29 -> k=3.02 (n=1)
                   srv2 80B    +5.0% at 0.84/35.67 -> k=2.11   (n=1)
             spread 2.11-3.02
```

The penalty is **proportional, not constant** — one GiB of shortfall is 8% of a
12.30 GiB blob and 2.8% of a 35.67 GiB one — which is the argument against any
single-number headroom on this gate.

**Out-of-sample check, and it fails high.** KAT on srv1: `B = 16.90`,
clearance `14.19 − 16.90 = −2.71`, so `T0 = 183.7 s` and F3.2 predicts
**257.9 s** against a **measured 203 s** — over by 27%. Read F3.2 as an upper
bound whose penalty term saturates somewhere unmeasured, not as a predictor.

**F3.3 — the mapping term** (MEASURED, n=3 alternating pairs)

```
T_wake(mapped) = T_wake(unmapped) + 6.7 s      (139.6 vs 132.9 on srv1 Qwen, 4.8%)
```

A single earlier draw read 24 s and was one draw. Mapped also costs 35,000–48,000
pages swapped out per wake at `swappiness=60` (0 unmapped) and buys nothing
measurable afterwards — decode is identical.

**Trade, stated once:** on srv1, unmapped gives up **8.4 GiB of reclaimable
memory permanently** to save **under 7 s** of one-off wake. Mapped wins for a
rung that stays up. For a rig that sleeps and wakes constantly the sign can flip
and the crossover is **UNMEASURED**.

**F3.4 — the window term** (n=1, confounded)

```
doubling c on srv1 Qwen:  80 s -> 128 s   (+48 s), and --n-cpu-moe 29 -> 30
```

Not separable into a window cost and an offload cost with one point.

**F3.5 — vLLM sleep/wake** (MEASURED, n=1 each)

```
T_sleep_L2 = 0.25 s (3B), 0.30 s (7B)
T_wake_L2  = 0.24 s (3B), 0.31 s (7B)
T_sleep_L1 = 1.39 s (3B), 3.99 s (7B)
T_wake_L1  = 0.41 s (3B), 0.79 s (7B)
```

≈ **500× faster** than the 168 s container restart of the same pair. It is a
different mechanism, not a faster one: the process, its CUDA context and its
Python runtime never die.

**F3.6 — a wake that cannot fit** (MEASURED, n=1)

```
if V_need(u) > V_avail(h, S):   HTTP 500 in 0.395 s, named CUDA OOM,
                                unit stays asleep, co-residents keep serving
```

The one loud, fast, safe failure in the record. It is also the argument that the
scheduler must read live GPU and RAM state before choosing: the engine refuses
correctly, but only after the decision was made.

**F3.7 — the cliff** (MEASURED, n=1, and its location is UNMEASURED)

```
if  M_avail(h) - R_spill(u) < 0 :   T_wake x 2.9   (385.3 s vs ~132 s)
                                    pgmajfault x 347  (2,327,837)
                                    decode x 0.32     (10.78 vs 33.26 tok/s)
```

Flat on every axis to `+0.55 GiB`; the transition is somewhere in the unmeasured
1.5 GiB below that. **Nothing errors** in this state: the unit comes up, gate 7
is green, `/v1/models` answers 200, every request is served — off swap. This is
why `h_refuse` keeps 2.0 while `h_mode` drops to 0.5.

---

## Q4 — What does a sleeping co-resident still hold?

**F4.1 — residual** (MEASURED, n=1)

```
V_resid(u) = the unit's live CUDA context, released only on process exit
           = 228 MiB (3B), 234 MiB (7B);  503 MiB card-wide with both asleep
V_released(u) = V_awake(u) - V_resid(u) = 3,582 MiB (3B), 6,582 MiB (7B)
R_resid_L2(u) = 0
R_resid_L1(u) = F2.3    (permanent from the first sleep onward)
```

**F4.2 — what a shape leaves for a newcomer** (MEASURED law; the number that
decided the 2026-09-09 case)

```
V_avail(h, S) = V_free_idle(h)
              - sum over u in S, awake  of V_need(u)
              - sum over u in S, asleep of V_resid(u)
```

Worked, on srv2: `11,911 − 228 − 234 = 11,449` predicted against **11,409 MiB
measured**. `emit` writes the 80B at `--n-cpu-moe 35`, wanting **11,960 MiB** —
551 MiB more than the sleepers leave, and it fails at 28 s with
`failed to create_context` then crash-loops. One block lighter, `--n-cpu-moe 36`
wants ~11,228 MiB and **serves after 100 s**.

**F4.3 — buying the deficit back in blocks** (MEASURED)

```
blocks_needed = ceil( (V_need(u) - V_avail(h,S)) / e_blk(m) )
e_blk(80B) = 34.31 GiB / 48 = 0.715 GiB = 732 MiB per block

worked: ceil(551 / 732) = 1 block, and 1 block buys 732 > 551.
```

Each block moved costs host RAM `e_blk` and costs throughput at an unmeasured
rate for this model (measured elsewhere: correcting an over-high offload was
worth ~2.4× on srv2's 35B).

**Gap G5, restated as the reason this section exists:** `fit` computes every
placement against an **idle** card. `V_avail(h,S)` is a runtime number and
nothing in `emit` can express it.

---

## Q5 — When is a shape feasible at all?

A shape `S(h)` is feasible iff **all** of:

```
G-card     sum_{awake} V_need(u) + sum_{asleep} V_resid(u)  <=  V_free_idle(h)
                                        no headroom on top: it is inside V_need

G-floor    n*(u) exists for every awake u in S           (F1.2)

G-mode     mapped(u)  iff  B(m) + h_mode  <=  M_avail(h) - R_shape(h, S\{u})
           h_mode = 0.5 GiB      [measured: flat +2.0 -> +0.5 on 3 models, 2 rigs]

G-refuse   R_shape(h, S) + h_refuse  <=  M_avail(h)
           h_refuse = 2.0 GiB    [measured: cliff below +0.55, silent, -68%]

G-disk     B(m) <= disk_free(h)

G-mode-vram   UNMEASURED.  --load-mode none has a card cost fit does not model.
              Until it is measured, treat "unmapped" as a refusal for any unit
              whose V_need is within an unmeasured margin of V_avail.
              srv2's 80B is the one datum: crash-loops unmapped, loads mapped,
              with 18 GiB of host RAM to spare.

G-window   two units on one host serving one card may not need one window:
           emit refuses deepseek on srv1 at Qwen's 8192 (5854 MiB of 6127 free
           at 2 slots) and admits it at 4096.

G-launch   a launch within an unmeasured margin of the card edge is a
           1-in-3 coin flip.  Retry any refusal three times before believing it.
```

`G-card` uses `V_free_idle` read from **`free`**, never `total − reserve`: the
two agree only on an idle card. The reserve is constant within a boot and varies
±3 MiB across boots.

---

## Q6 — What does a transition cost?

**F6.1 — wall clock** (composed from MEASURED parts; the composition is an
ASSUMPTION)

```
T_trans(A -> B, h) =  T_drain
                    + sum_{u in A\B}  T_release(u)      serialized on the card
                    + sum_{u in B\A}  T_up(u)           serialized by depends_on

T_drain    <= budgets.request_timeout_s   (180 s live)  -- in-flight work finishes
                                                          or the transport gives up
T_release(container down)   ~ 1 s to appear, 3 s to settle   [MEASURED, 1 Hz sampling]
T_release(vLLM L2 sleep)    = 0.24-0.30 s                    [MEASURED n=1]
T_up(vLLM L2 wake)          = 0.24-0.31 s                    [MEASURED n=1]
T_up(cold)                  = F3.2                           [FIT]
```

The serialization is real but cheap: **a waking unit cannot have a sleeper's RAM
until the sleeper's container is gone**, and that hand-back is a step, not a
curve — 8.09 GiB appears in under one second at process exit. So sleep→wake is
hard-serialized and the serialization is not worth designing around; the wake is.

**F6.2 — lost capacity** (ASSUMPTION over MEASURED rates)

```
Lost(A -> B, h) = sum_{u in A\B} Lambda(u, w_u) * (T_drain + T_release(u))
                + sum_{u in B\A} Lambda(u, w_u) * T_up(u)              [tokens]
```

`Λ` from the 2026-09-06 concurrency sweep. Worked, srv2 pair → 80B via L2 sleep:
`Lost ≈ (873.6 + 489.2) tok/s × ~0.6 s + Λ(80B) × 100 s`. Via container restart
instead: `(873.6 + 489.2) × 168 s ≈ 229,000 tokens`. **The sleep path is ~280×
cheaper on this transition**, which is the whole case for it.

**F6.3 — the same cost expressed as a rate** (for Q8)

```
c_trans(A -> B) = Lost(A -> B) / T_trans(A -> B)        [tokens/s foregone]
```

---

## Q7 — How is rung pressure turned into a demand signal?

**F7.1 — pressure** (design; `busy` is MEASURED cross-process, `waiting` is not)

```
demand(b)   = busy(b) + waiting(b)
pressure(b) = demand(b) / limit(b)
```

`busy(b)` = locked slot files of bound `b`, host-wide, by the same
`LOCK_EX | LOCK_NB` sweep `_acquire_slot` already performs, counting instead of
returning. `waiting(b)` = threads of **this** process blocked on `b`.

`demand` is a **deliberate lower bound**: `busy` is shared and `waiting` is not,
so another process's queue is invisible. The loop therefore reads low, trips
late, and never trips on pressure that is not there. Census cost: one
`_POLL_SECONDS` (0.02 s) re-sweep for a racing acquirer, paid once per
evaluation.

**F7.2 — backlog in tokens** (ASSUMPTION; `output_tokens` is per rung and MEASURED-argued)

```
Backlog(r) = demand(r) * output_tokens(r)                              [tokens]
```

**F7.3 — drain time under a shape** (MEASURED rates, ASSUMPTION composition)

```
T_drain_queue(r, S) = Backlog(r) / Lambda(r, S)     if some u in S serves r
                    = infinity                       otherwise
```

`Λ(r, S)` is the aggregate curve, not the per-stream one, and the two engines
answer it in opposite directions: vLLM multiplies aggregate 7.5–7.6× to width 8
for a 5% per-stream cost; llama.cpp with 32 of 40 expert layers on the CPU gives
up 81% of per-stream to buy 50% aggregate. **The width that is right for one is
wrong for the other**, and this term is where that lives.

**F7.4 — the trip** (PROPOSED, N1/N2)

```
wake when   pressure(b) >= WAKE_RATIO (2.0)  held for WAKE_SUSTAIN_S (45 s)
```

`2.0` = every slot busy and as much again queued; `1.0` is merely "full", which
is what a correctly-sized rig looks like under load. `45 s` sits above the 3B's
~9 s service time at width 8 and below srv1's ~73 s at width 2.

---

## Q8 — What picks `fleet.next`?

**F8.1 — the objective** (ASSUMPTION; every input is cited above)

Minimize the time to clear the work that exists, charged for the transition:

```
J(S | A) = T_trans(A -> S)  +  max over rungs r of  T_drain_queue(r, S)        [s]

fleet.next = argmin over feasible S of J(S | A)
```

Ties broken toward the higher `q(r)` — rungs are ordered cheapest-first and a
rung is only a rung if it is `MIN_QUALITY_GAIN = 0.03` better than the one below.

**F8.2 — the switch condition** (hysteresis; PROPOSED)

```
switch to S  only if   J(A|A) - J(S|A)  >=  Delta_min

Delta_min = max( beta * T_trans(A -> S),  WAKE_SUSTAIN_S )
beta = 1.0     ASSUMPTION: the transition must pay for itself once over
```

**F8.3 — the clocks that gate it** (PROPOSED, N3/N4/N5; read from files in the
rendezvous directory, never from process memory)

```
sleep(c) requires ALL of:
   busy(b) == 0 for every bound b of every rung on c        (shared census)
   now - mtime(<host>.used)  >= SLEEP_IDLE_S  (600 s)
   now - mtime(<host>.wake)  >= MIN_UPTIME_S  (900 s)
   no transition of c within COOLDOWN_S       (600 s)

wake(c) requires:
   F7.4 tripped, and no transition within COOLDOWN_S
   -- EXCEPT a refusal-driven wake (a dispatch aimed at the card and refused
      by the port), which is exempt, or the damper becomes an outage.
```

`MIN_UPTIME_S = 900` bounds a pathological oscillation at ~14% boot time for a
card that costs up to 130 s to wake.

**F8.4 — the liveness predicate** (MEASURED, and it is new)

```
serving(u)  =  GET /v1/models == 200   AND   GET /is_sleeping == {"is_sleeping": false}
```

`/v1/models` alone is **wrong**: a sleeping unit answers 200 and then hangs on
`POST /v1/chat/completions` with no response in 60 s. The door polls
`/v1/models`, so it would call a sleeping rig healthy and gate 7 would call the
run green; a contract dispatched there does not fail, it hangs until
`request_timeout_s`.

**F8.5 — timeouts, one per mechanism** (G3: today there is one, `wake_timeout_s = 480`)

```
budget(vLLM L2 wake)        ~ 5 s        against a measured 0.24-0.31 s
budget(named OOM refusal)   ~ 5 s        against a measured 0.395 s
budget(cold llama.cpp wake) = 2.4 * F3.2 against the fleet worst of 203 s
budget(vLLM pair restart)   = 2.4 * 168 s
```

One constant cannot mean 0.24 s and 385 s at once. The 480 was priced against
the door's 360 s health budget and validated only against **mapped** wakes;
srv1's unmapped Qwen woke in 385 s once squeezed, inside 480 by 95 s.

---

## The control algorithm — a sketch, deliberately half-baked

The owner asked for a thought-direction, not a feasibility study. This is that.

### What is polled, and how often

Two triggers, no daemon. Every evaluation happens at a moment mcgyvr is already
awake and running.

1. **On queue diff.** `runner.dispatch` already enters `Capacity.hold`. Enter it
   with `timeout = WAKE_SUSTAIN_S` in a loop instead of the whole
   `task_timeout_s`; on each `SlotUnavailableError` take the census (F7.1),
   evaluate, and re-enter with the remaining budget. The slices sum to the same
   ceiling, `hold` is untouched, and the exception must never escape — only the
   final budget-exhausted one is a `DECLINED`.
2. **On a tick.** A cheap `min(WAKE_SUSTAIN_S, 30 s)` tick while any waiter
   exists, plus once at the end of a run before the result file is written.

A card that goes idle because *everything* stopped is slept by the last run that
used it, or not at all. Anything else is a daemon and this does not build one.

### How a candidate shape is generated

**Enumerate; do not search.** The catalogue per host is single digits, so the
feasible set is small enough to score exhaustively.

```
catalogue(srv1) = { Qwen3.6-35B, deepseek-16b, KAT }            (window-constrained, G10)
catalogue(srv2) = { 3B, 7B, 80B }
candidates(h)   = { S subset of catalogue(h), with a state per member }
                  filtered by Q5
```

≤ 2^3 × states per host, and Q5 kills most of them. Score all survivors. Add the
current shape `A` unchanged as a candidate so "do nothing" competes on the same
axis.

Two shape-level rules that fall out of the evidence:

* a vLLM unit already resident and asleep is a **different candidate** from the
  same model not resident: its wake is 0.24 s and its residual 228 MiB;
* a llama.cpp unit has no sleep state at all — resident or gone.

### How it is scored

`J(S|A)` (F8.1): transition seconds plus the worst rung's drain time under `S`,
with `Λ` from the measured concurrency curves and backlog from the shared
census. Feasibility (Q5) is a filter, not a penalty — an infeasible shape does
not get a bad score, it is not a candidate.

### Hysteresis and damping

Four dampers, in the order they fire:

1. **The shared census** gates every sleep. Not a tunable — it is the
   correctness condition that stops process *n* sleeping a card process *n+1* is
   dispatching to.
2. **`Delta_min`** (F8.2): the transition must pay for itself once over. This is
   what stops a shape flapping between two nearly-equal scores.
3. **The clocks** (F8.3): `SLEEP_IDLE_S`, `MIN_UPTIME_S`, `COOLDOWN_S`, read from
   files so twenty processes share one memory.
4. **One card per trip.** Re-read the pressure after a transition lands; a second
   card moves only if the pressure is still there. Cheapest possible damping and
   it costs nothing to state.

And the drain (Q6) before any teardown: the census decides *whether* to act, the
drain is what makes acting safe. `docker compose down` kills containers, and a
request from a second machine or from something that is not mcgyvr is neither
drained nor asked — the rig lease is what makes that a recorded decision rather
than an accident.

### What the learning loop actually updates

Every transition is a free measurement of a parameter this document had to fit.
Keep an EWMA per key, persisted beside the journal, and read it in preference to
the constant:

| parameter | keyed by | observed from | today's basis |
|---|---|---|---|
| `r(h)` load rate | host, engine | `StartedAt` → first 200, over `B(m)` | FIT, n=2 (srv1), n=1 (srv2) |
| `k` shortfall penalty | host | wakes at known clearance | FIT, n=3, over-predicts KAT by 27% |
| `T0(u)` | unit | every cold wake | replaces the fit once n≥3 per unit |
| `V_resid(u)` | unit | `nvidia-smi --query-compute-apps` after a sleep | MEASURED n=1 |
| `V_need(u)` / `C(m,cfg)` | (model, serve config) | `constant_from_probe` on any launch — **C does not move with `--n-cpu-moe`**, so one probe fixes every placement | MEASURED law |
| `Λ(r, w)` | (rung, width) | completed dispatches: tokens / wall clock | MEASURED 2026-09-06 |
| `output_tokens(r)` | rung | journalled reply lengths (p90/p95 vs the cap) | MEASURED, 82 replies |
| the cliff location | host | any wake whose `pgmajfault` jumps an order of magnitude | **UNMEASURED** — this is the loop's most valuable output |
| arrival rate | rung | journal dispatch timestamps | **UNMEASURED** — nothing records them yet |
| `α` (EWMA rate) | — | — | **UNMEASURED assumption** |

Two instruments the loop should prefer over the clock, because both are
near-deterministic where wall time drifts 5%:

* **`pgmajfault` at load** reproduces to within 1% (≈9,180 vs ≈12,150 across the
  headroom step) and is the better detector of the mode gate;
* **pages swapped out during a wake** is 0 on the safe side of the refusal cliff
  and 2.2 million past it. A wake that swaps is a wake that will decode at a
  third of rate, silently. **That is the one reading that must feed back as a
  refusal and not as a coefficient.**

### What the loop must never learn

The offload `--n-cpu-moe` is a **semantic** key, not just a speed knob (ncmoe 0
vs 99 flipped 9 of 257 verdicts against a 0-flip own null). A loop that trades
blocks for card space is changing what the rung answers, not only how fast. Any
shape change that moves `n` must be recorded on the result file the way a rung
change is — otherwise two runs share a config digest and not a behaviour.
