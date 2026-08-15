# Proposed amendment for #224 — 2026-08-15 (lane/266, A1)

**Not posted.** This is the text A1 proposes for #224's body. It is derived
entirely from committed runs — no model was called, no rig touched — by
`tools/bench/responsive.py`, pinned by `tests/test_bench_responsive.py`, and
printed in full at
`records/evidence/responsive-fraction-2026-08-15/per-stratum.md`.

---

## Amendment — 2026-08-15 (lane/266): the responsive fraction, measured

The amendment of 2026-08-14 added *"the responsive fraction is reported per
(model+bar) x stratum, never pooled, with the tool that derives it"*. It is
measured below. **No figure here is pooled across tiers or across arms** —
`bench-py` and `bench-ts` are two bars, not a language contrast (ADR-0026, and
`tools/bench/resolution.py`'s docstring).

### Three observables, and they are not the same number

The word "responsive" has carried three meanings in this project's records. They
disagree here by an order of magnitude, so every figure names which it is.

| observable | what it is | what it bounds |
|---|---|---|
| `headroom` | cells passing under **either** condition of a named contrast | upper bound on `m`, hence on `psi` — **for that contrast's bar only** |
| `psi` | a **named lever's** measured discordance rate | `delta <= psi`, hard. A property of (instrument, lever), never of "the bench" |
| `psi_draw` | cells whose verdict varies across sampled draws | **nothing. It is not `psi` and is not a bound in either direction** (`tools/bench/responsiveness.py`) |

### The table — per (model + bar) x stratum

`headroom` and `psi` are gate-scored, off the committed `norule` contrasts.
`psi_draw` is **acceptance-scored** and partial; its cell shows covered-of-total.

| tier | bar | stratum | n | `headroom` | `psi` (`norule`) | `psi_draw` (acceptance only) |
|---|---|---|---:|---:|---:|---:|
| 1.5B | bench-py | `bug_fix+scaffold` | 59 | 23.7% (14) | 10.2% (m=6) | 69.7% (23 of 33 cells) |
| 1.5B | bench-py | `function_implementation` | 164 | 6.1% (10) | 4.3% (m=7) | 67.6% (69 of 102 cells) |
| 1.5B | bench-py | `function_implementation+scaffold` | 34 | 5.9% (2) | 2.9% (m=1) | — no run |
| 1.5B | bench-ts | `bug_fix+scaffold` | 59 | 18.6% (11) | 5.1% (m=3) | 57.6% (19 of 33 cells) |
| 1.5B | bench-ts | `function_implementation` | 164 | 13.4% (22) | 13.4% (m=22) | 65.7% (67 of 102 cells) |
| 1.5B | bench-ts | `function_implementation+scaffold` | 34 | 5.9% (2) | 2.9% (m=1) | — no run |
| 7B | bench-py | `bug_fix+scaffold` | 59 | 61.0% (36) | 11.9% (m=7) | — no run |
| 7B | bench-py | `function_implementation` | 164 | 22.0% (36) | 4.3% (m=7) | — no run |
| 7B | bench-py | `function_implementation+scaffold` | 34 | 2.9% (1) | 2.9% (m=1) | 44.1% (15 of 34 cells) |
| 7B | bench-ts | `bug_fix+scaffold` | 59 | 52.5% (31) | 3.4% (m=2) | — no run |
| 7B | bench-ts | `function_implementation` | 164 | 14.0% (23) | 4.3% (m=7) | — no run |
| 7B | bench-ts | `function_implementation+scaffold` | 34 | 11.8% (4) | 2.9% (m=1) | 47.1% (16 of 34 cells) |

Context, not one of #224's two tiers: on the same 34 scaffolded cells the 3B
reads `psi_draw` 29.4% (py) and 20.6% (ts) — below the 7B on both bars, from
the same rig and the same seven draws.

### The finding: most of the dead fraction is the bar, not the material

`psi_draw` runs 2.9x to 15.2x `headroom` at the same tier on the same stratum
(lowest: 1.5B `bench-py` `bug_fix+scaffold`; highest: 7B `bench-py`
`function_implementation+scaffold`). That gap is almost entirely the **scorer**,
not the problems. On the same 135 cells at the 1.5B on `bench-py`, the
acceptance proxy passes **55** greedy where `Gate.run` passes **18**.

The mechanism is measurable per stratum. Counting cells whose acceptance command
never ran under *either* condition, because a pre-acceptance rung — `lint`,
`format`, `syntax`, `structure` — rejected first:

| tier | bar | `bug_fix+scaffold` | `function_implementation` | `function_implementation+scaffold` |
|---|---|---:|---:|---:|
| 1.5B | bench-py | 18 of 59 (30.5%) | **127 of 164 (77.4%)** | 23 of 34 (67.6%) |
| 1.5B | bench-ts | 13 of 59 (22.0%) | **126 of 164 (76.8%)** | 13 of 34 (38.2%) |
| 7B | bench-py | 13 of 59 (22.0%) | **110 of 164 (67.1%)** | 27 of 34 (79.4%) |
| 7B | bench-ts | 18 of 59 (30.5%) | **133 of 164 (81.1%)** | 15 of 34 (44.1%) |

This is an **upper bound** on what a zero-token pre-gate formatting pass could
recover — #113 already measured +13.7pp for exactly that — and not a claim that
any of these cells would then pass acceptance. But it settles the direction: on
the largest stratum, two thirds to four fifths of cells are frozen before the
problem is attempted. **The authoring yield of responsive problems cannot be
measured, and no keep-or-retire verdict can be taken, until that term is
separated from the material's difficulty.** That reorders the chain: pricing the
bar comes before pricing the corpus.

### Keep-or-retire, per stratum

| stratum | verdict | why |
|---|---|---|
| `bug_fix+scaffold` (59) | **keep** | the only stratum with real gate-scored headroom — 61.0% / 52.5% at the 7B, an order of magnitude above the scaffolded implementations — and the lowest pre-acceptance loss (22–31%). It is also the one stratum the capacity levers are ruled ineligible for (`matrix.json`), so the material constraint and the eligibility rule still point in opposite directions (#266) |
| `function_implementation` (164) | **keep, but author nothing more until the bar is priced** | it holds the bench's only live cell (1.5B `bench-ts`, `psi`=0.134, m=22, 8.5pp) and 64% of the corpus, and 67–81% of it never reaches acceptance. Authoring at today's bar buys 19–33% of nominal `n` |
| `function_implementation+scaffold` (34) | **retire as a lever-bearing stratum; do not delete the material** | ceiling of 1, 2, 2, 4 against ADR-0019's wall of 6 — undecidable at any effect size, on every tier x bar cell (#266). But `psi_draw` reads 44.1% / 47.1% at the 7B, so the *problems* are reachable and the deadness is the bar plus the levers' eligibility rule, not the contracts. Retiring it from the capacity-lever arms costs nothing; deleting 34 contracts would destroy the only stratum with a complete multi-draw run |

The standing candidate named on 2026-08-14 is confirmed on the arithmetic, with
one correction — see below.

### Three figures already quoted that do not re-derive as stated

1. **"88% of cells never pass under any condition, and that — not sample size —
   is what bounds every arm."** This re-derives as the **1.5B only**, and is
   itself pooled across the two bars — the thing the same amendment forbids two
   paragraphs earlier. Per cell: 1.5B `bench-py` 89.9%, `bench-ts` 86.4% (mean
   88.1%); 7B `bench-py` **71.6%**, `bench-ts` **77.4%**. The claim overstates
   the 7B by 11–16pp. Proposed replacement: *"between 72% and 90% of cells never
   pass under either condition, depending on tier and bar; it is 88% at the floor
   unit."*
2. **"`function_implementation` +scaffold (n=34, psi=0.029, 2.9% pass at the
   7B)."** `n` and `psi` are right on both arms. The **2.9% pass is `bench-py`
   only**; `bench-ts` reads 8.8% stock (3 of 34) and 11.8% headroom (4 of 34).
   A tier-level pass rate on this stratum does not exist — there are two bars.
3. Everything else in the 2026-08-14 resolution table re-derives **exactly**:
   all twelve `psi` values, all four arm-level rows, and the 1-of-6 / 0-of-6
   counts. `tests/test_bench_responsive.py` now pins them.

### What A2 needs, exactly

Two holes. Neither is a reason to withhold the table; both are named so they are
closed rather than forgotten.

**Hole 1 — every `psi_draw` figure is on the wrong bar.** All three committed
multi-draw runs predate the `Gate.run` scorer; their rows carry no
`rejected_by`. #224's own acceptance requires every band figure to be scored
through `Gate.run`.

> **This one costs no rig time and no tokens.** The candidate trees are on disk
> (`<run>/bench-<arm>/candidates/`). What is missing is a *gate* regrade path:
> `tools/bench/regrade.py` re-runs the acceptance command only, by design. A
> `Gate.run` regrade over saved candidates would close hole 1 for all three runs
> — 2,430 gate invocations for `f1-responsiveness-15b-2026-08-11`, and 544 per
> scaffold-ablation condition directory — offline, at zero token cost. **This should be A2's first item**,
> because until it lands every `psi_draw` above is measured against a proxy that
> passes three times as many cells.

**Hole 2 — six of the twelve (tier x bar x stratum) cells have no multi-draw run
at all.** These are the sweeps, and both must run in round `r1-commissioning`
with the product pinned, gate-scored, so their `psi_draw` lands on the bench's
bar and hole 1 does not recur:

| # | sweep | cells missing | dispatches | measured wall-clock |
|---|---|---|---:|---|
| S1 | **1.5B, both arms, all 257, 8 sampled draws + greedy** | 1.5B x {py, ts} x `function_implementation+scaffold` | 4,626 | ~2.4 h at the measured 1.70 s (py) / 1.95 s (ts) per dispatch |
| S2 | **7B, both arms, all 257, 8 sampled draws + greedy** | 7B x {py, ts} x `bug_fix+scaffold`, `function_implementation` | 4,626 | ~4 h at this run's 3.24 s / 4.33 s; up to ~9 h at the 7B scaffold-ablation's measured 6.5–7.2 s |

S1 could be cut to the 34 scaffold-eligible tasks (612 dispatches, ~20 min), but
the full run also replaces the 135-task `f1` subset with a complete,
gate-scored, round-pinned one at the floor unit, which is the tier every other
figure is quoted against. S2 has no cheap version: the 7B has never had a
multi-draw run outside the 34 scaffolded cells.

Neither sweep measures the **authoring yield** of responsive problems. That term
is still unmeasured, and after this table it has a prerequisite: the yield of
*responsive* problems cannot be told apart from the yield of *lint-clean* ones
until hole 1 is closed.
