---
record: session/3
lane: lane/266
agent: adar
started: 2026-08-15T09:00:00Z
---

# Session — lane/266 — 2026-08-15

## Did

#224's A1: measured the **responsive fraction per (model + bar) x stratum**, from
committed runs only. No model was called and no rig was touched.
`tools/bench/responsive.py` derives it by composing the three tools that already
own the pieces — `eligibility.headroom`, `resolution.measure`,
`responsiveness.cells` — rather than copying their arithmetic.
`tests/test_bench_responsive.py` pins every figure;
`records/evidence/responsive-fraction-2026-08-15/` holds the printed table and
the rows as JSON.

**Three observables, and they disagree by up to 15x.** The project's records use
"responsive" for three different things, so every row names which it is:
`headroom` (cells passing under either condition — an upper bound on `m`), `psi`
(a named lever's discordance rate — `delta <= psi`, hard), and `psi_draw` (cells
varying across draws — **not `psi`, and not a bound in either direction**, a
caveat carried verbatim from `responsiveness.py`). Nothing is pooled across
tiers or across arms; both of `resolution.py`'s objections apply unchanged, and
the arm-level rows carry its label.

| tier | bar | stratum | n | headroom | psi (`norule`) | psi_draw (acceptance only) |
|---|---|---|---:|---:|---:|---:|
| 1.5B | bench-py | bug_fix+scaffold | 59 | 23.7% | 10.2% | 69.7% (33 cells) |
| 1.5B | bench-py | function_implementation | 164 | 6.1% | 4.3% | 67.6% (102 cells) |
| 1.5B | bench-py | function_implementation+scaffold | 34 | 5.9% | 2.9% | — |
| 1.5B | bench-ts | bug_fix+scaffold | 59 | 18.6% | 5.1% | 57.6% (33 cells) |
| 1.5B | bench-ts | function_implementation | 164 | 13.4% | 13.4% | 65.7% (102 cells) |
| 1.5B | bench-ts | function_implementation+scaffold | 34 | 5.9% | 2.9% | — |
| 7B | bench-py | bug_fix+scaffold | 59 | 61.0% | 11.9% | — |
| 7B | bench-py | function_implementation | 164 | 22.0% | 4.3% | — |
| 7B | bench-py | function_implementation+scaffold | 34 | 2.9% | 2.9% | 44.1% (34 cells) |
| 7B | bench-ts | bug_fix+scaffold | 59 | 52.5% | 3.4% | — |
| 7B | bench-ts | function_implementation | 164 | 14.0% | 4.3% | — |
| 7B | bench-ts | function_implementation+scaffold | 34 | 11.8% | 2.9% | 47.1% (34 cells) |

**The finding, and it moves #224's centre of gravity.** The gap between
`psi_draw` and `headroom` is almost entirely the **scorer**, not the material.
On the same 135 cells at the 1.5B on `bench-py`, the acceptance proxy passes 55
greedy where `Gate.run` passes 18. Per stratum, counting cells whose acceptance
command never ran under *either* condition because a pre-acceptance rung
rejected first: `function_implementation` loses **127/164, 126/164, 110/164 and
133/164** across the four tier x bar cells — 67% to 81% of the bench's largest
stratum, frozen before the problem is attempted. That is an upper bound on what
a zero-token formatting pass could recover (#113 measured +13.7pp for exactly
that), not a claim the cells would pass. But it means **the authoring yield of
responsive problems cannot be separated from the yield of lint-clean ones until
the bar is priced.** Pricing the bar now sits ahead of pricing the corpus in the
chain.

**Keep-or-retire.** `bug_fix+scaffold` keep — 61.0%/52.5% headroom at the 7B and
the lowest pre-acceptance loss, and still the stratum `matrix.json` rules the
capacity levers out of. `function_implementation` keep, but author nothing more
until the bar is priced: it holds the bench's only live cell (1.5B `bench-ts`,
psi 0.134, m=22, 8.5pp) and 64% of the corpus, and today buys 19-33% of nominal
`n`. `function_implementation+scaffold` retire **as a lever-bearing stratum**,
not as material — ceiling 1/2/2/4 against a wall of 6 is undecidable at any
effect size (#266), but `psi_draw` 44-47% at the 7B says the contracts are
reachable and the deadness is the bar plus the eligibility rule.

**Two figures already quoted that do not re-derive as stated**, in this
project's #243 tradition of saying so loudly:

1. **"88% of cells never pass under any condition"** (#224's 2026-08-14
   amendment) is the **1.5B only**, and is itself pooled across the two bars —
   what the same amendment forbids two paragraphs earlier. Per cell: 1.5B py
   89.9%, ts 86.4%; 7B py **71.6%**, ts **77.4%**. It overstates the 7B by
   11-16pp.
2. **"2.9% pass at the 7B"** on `function_implementation+scaffold` is the
   **`bench-py`** arm; `bench-ts` reads 8.8% stock and 11.8% headroom. `n=34`
   and `psi=0.029` are right on both.

Everything else in the 2026-08-14 resolution table re-derived exactly — all
twelve `psi`, all four arm rows, the 1-of-6 and 0-of-6 counts.

The proposed #224 amendment text is at
`records/evidence/responsive-fraction-2026-08-15/proposed-224-amendment.md`.
It is **not posted**.

## Left open

- **Hole 1: every `psi_draw` above is on the wrong bar.** All three committed
  multi-draw runs predate `Gate.run`; their rows carry no `rejected_by`. #224's
  acceptance requires the gate. This is **closable offline at zero token cost** —
  the candidate trees are on disk — but `tools/bench/regrade.py` re-runs
  acceptance only, by design, so a `Gate.run` regrade path has to be built.
  2,430 gate invocations for `f1-responsiveness-15b-2026-08-11`, 544 per
  scaffold-ablation condition directory. This should be A2's first item.
- **Hole 2: six of the twelve (tier x bar x stratum) cells have no multi-draw
  run.** S1 — the 1.5B, both arms, all 257, 8 draws + greedy: 4,626 dispatches,
  ~2.4 h at the measured 1.70/1.95 s. S2 — the 7B, same shape: 4,626 dispatches,
  ~4 h at this round's 3.24/4.33 s and up to ~9 h at the scaffold-ablation's
  6.5-7.2 s. Both must run in round `r1-commissioning` and be gate-scored, or
  hole 1 recurs in the new material.
- **The authoring yield is still unmeasured**, and now has a prerequisite: it
  cannot be told apart from the lint-clean yield until hole 1 closes.
- The `psi_draw` rows for the 1.5B come from the `f1` tranches (b228+) only, so
  they describe the newest authoring campaign rather than a random subset of
  each stratum. Named in the tool's output, not corrected — there is no other
  material.

next: A2 — build the `Gate.run` regrade path and re-score the three committed
multi-draw runs before spending any rig time
