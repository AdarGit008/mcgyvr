# Responsive fraction, per (model + bar) x stratum — #224 A1

Derived from committed runs only; no model was called. Every row names which of the three observables it is, because they disagree here by an order of magnitude and the disagreement is mostly the bar.

| observable | what it is | what it bounds |
|---|---|---|
| `headroom` | cells passing under either condition of the named contrast | upper bound on m, hence on psi, for THIS contrast's bar only |
| `psi` | the named lever's measured discordance rate | this lever's discordance rate; delta <= psi is hard |
| `psi_draw` | cells whose verdict varies across sampled draws | NOT psi, and not a bound in either direction |

No row is pooled across tiers or across arms: `bench-py` and `bench-ts` are two bars, not a language contrast (ADR-0026, and `resolution.py`'s docstring). Rows marked `ALL — not the bench's resolution` are the arm aggregate and are printed only because a reader would otherwise compute one.

## 1.5B, gate-scored — lever `norule`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's (not recorded in this manifest; the rig that wrote it had no escalation path)
- round: **none recorded** — this run predates #231's product pin, so the revision that produced it is unknown and it cannot be laid beside an arm measured in a round
- `psi` is this lever's, not the bench's. Wall: m >= 6 (ADR-0019).

| tier | bar | stratum | observable | n | k | fraction | scorer | coverage |
|---|---|---|---|---:|---:|---:|---|---|
| 1.5B | bench-py | ALL — not the bench's resolution | headroom | 257 | 26 | 10.1% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | ALL — not the bench's resolution | psi | 257 | 14 | 5.4% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | bug_fix+scaffold | headroom | 59 | 14 | 23.7% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | bug_fix+scaffold | psi | 59 | 6 | 10.2% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | function_implementation | headroom | 164 | 10 | 6.1% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | function_implementation | psi | 164 | 7 | 4.3% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | function_implementation+scaffold | headroom | 34 | 2 | 5.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-py | function_implementation+scaffold | psi | 34 | 1 | 2.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | ALL — not the bench's resolution | headroom | 257 | 35 | 13.6% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | ALL — not the bench's resolution | psi | 257 | 26 | 10.1% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | bug_fix+scaffold | headroom | 59 | 11 | 18.6% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | bug_fix+scaffold | psi | 59 | 3 | 5.1% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | function_implementation | headroom | 164 | 22 | 13.4% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | function_implementation | psi | 164 | 22 | 13.4% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | function_implementation+scaffold | headroom | 34 | 2 | 5.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 1.5B | bench-ts | function_implementation+scaffold | psi | 34 | 1 | 2.9% | Gate.run | lever `norule`; greedy, one draw per condition |

## 7B, gate-scored — lever `norule`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's
- round: **`r1-commissioning`**, product `ed508e612ff8` — every arm in this round ran against one revision, and an adopted change lands only at the boundary (ADR-0018)
- `psi` is this lever's, not the bench's. Wall: m >= 6 (ADR-0019).

| tier | bar | stratum | observable | n | k | fraction | scorer | coverage |
|---|---|---|---|---:|---:|---:|---|---|
| 7B | bench-py | ALL — not the bench's resolution | headroom | 257 | 73 | 28.4% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | ALL — not the bench's resolution | psi | 257 | 15 | 5.8% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | bug_fix+scaffold | headroom | 59 | 36 | 61.0% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | bug_fix+scaffold | psi | 59 | 7 | 11.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | function_implementation | headroom | 164 | 36 | 22.0% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | function_implementation | psi | 164 | 7 | 4.3% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | function_implementation+scaffold | headroom | 34 | 1 | 2.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-py | function_implementation+scaffold | psi | 34 | 1 | 2.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | ALL — not the bench's resolution | headroom | 257 | 58 | 22.6% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | ALL — not the bench's resolution | psi | 257 | 10 | 3.9% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | bug_fix+scaffold | headroom | 59 | 31 | 52.5% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | bug_fix+scaffold | psi | 59 | 2 | 3.4% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | function_implementation | headroom | 164 | 23 | 14.0% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | function_implementation | psi | 164 | 7 | 4.3% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | function_implementation+scaffold | headroom | 34 | 4 | 11.8% | Gate.run | lever `norule`; greedy, one draw per condition |
| 7B | bench-ts | function_implementation+scaffold | psi | 34 | 1 | 2.9% | Gate.run | lever `norule`; greedy, one draw per condition |

## 1.5B, draw-responsive — `f1-responsiveness-15b-2026-08-11`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's (not recorded in this manifest; the rig that wrote it had no escalation path)
- round: **none recorded** — this run predates #231's product pin, so the revision that produced it is unknown and it cannot be laid beside an arm measured in a round
- `psi_draw` is NOT psi, and not a bound in either direction. It is the cheapest available screen for dead cells, and it costs rig time rather than authoring.

| tier | bar | stratum | observable | n | k | fraction | scorer | coverage |
|---|---|---|---|---:|---:|---:|---|---|
| 1.5B | bench-py | ALL — not the bench's resolution | psi_draw | 135 of 257 | 92 | 68.1% | acceptance only | 8 sampled draws + greedy; f1 tranches (b228+) only, so no scaffolded cell is covered; predates Gate.run |
| 1.5B | bench-py | bug_fix+scaffold | psi_draw | 33 of 59 | 23 | 69.7% | acceptance only | 8 sampled draws + greedy; f1 tranches (b228+) only, so no scaffolded cell is covered; predates Gate.run |
| 1.5B | bench-py | function_implementation | psi_draw | 102 of 164 | 69 | 67.6% | acceptance only | 8 sampled draws + greedy; f1 tranches (b228+) only, so no scaffolded cell is covered; predates Gate.run |
| 1.5B | bench-ts | ALL — not the bench's resolution | psi_draw | 135 of 257 | 86 | 63.7% | acceptance only | 8 sampled draws + greedy; f1 tranches (b228+) only, so no scaffolded cell is covered; predates Gate.run |
| 1.5B | bench-ts | bug_fix+scaffold | psi_draw | 33 of 59 | 19 | 57.6% | acceptance only | 8 sampled draws + greedy; f1 tranches (b228+) only, so no scaffolded cell is covered; predates Gate.run |
| 1.5B | bench-ts | function_implementation | psi_draw | 102 of 164 | 67 | 65.7% | acceptance only | 8 sampled draws + greedy; f1 tranches (b228+) only, so no scaffolded cell is covered; predates Gate.run |

## 7B, draw-responsive — `bench-scaffold-ablation-7b-2026-08-11/stock`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's (not recorded in this manifest; the rig that wrote it had no escalation path)
- round: **none recorded** — this run predates #231's product pin, so the revision that produced it is unknown and it cannot be laid beside an arm measured in a round
- `psi_draw` is NOT psi, and not a bound in either direction. It is the cheapest available screen for dead cells, and it costs rig time rather than authoring.

| tier | bar | stratum | observable | n | k | fraction | scorer | coverage |
|---|---|---|---|---:|---:|---:|---|---|
| 7B | bench-py | ALL — not the bench's resolution | psi_draw | 34 of 257 | 15 | 44.1% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run |
| 7B | bench-py | function_implementation+scaffold | psi_draw | 34 | 15 | 44.1% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run |
| 7B | bench-ts | ALL — not the bench's resolution | psi_draw | 34 of 257 | 16 | 47.1% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run |
| 7B | bench-ts | function_implementation+scaffold | psi_draw | 34 | 16 | 47.1% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run |

## 3B, draw-responsive — `bench-scaffold-ablation-3b-2026-08-11/stock`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's (not recorded in this manifest; the rig that wrote it had no escalation path)
- round: **none recorded** — this run predates #231's product pin, so the revision that produced it is unknown and it cannot be laid beside an arm measured in a round
- `psi_draw` is NOT psi, and not a bound in either direction. It is the cheapest available screen for dead cells, and it costs rig time rather than authoring.

| tier | bar | stratum | observable | n | k | fraction | scorer | coverage |
|---|---|---|---|---:|---:|---:|---|---|
| 3B | bench-py | ALL — not the bench's resolution | psi_draw | 34 of 257 | 10 | 29.4% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run; a third tier, not one of #224's two |
| 3B | bench-py | function_implementation+scaffold | psi_draw | 34 | 10 | 29.4% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run; a third tier, not one of #224's two |
| 3B | bench-ts | ALL — not the bench's resolution | psi_draw | 34 of 257 | 7 | 20.6% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run; a third tier, not one of #224's two |
| 3B | bench-ts | function_implementation+scaffold | psi_draw | 34 | 7 | 20.6% | acceptance only | 7 sampled draws + greedy; the 34 scaffold-eligible cells only; predates Gate.run; a third tier, not one of #224's two |

## Why the three disagree — cells that never reached acceptance

Not a fourth responsive fraction. Under `Gate.run` a cell rejected at `lint` or `format` never ran the contract's acceptance command, so its zero contribution to `headroom` is a fact about the bar rather than about the problem. This is an **upper bound** on what a zero-token pre-gate formatting pass could recover (#113 measured +13.7pp for exactly that), not a claim any of these cells would then pass.

| tier | bar | stratum | n | never reached acceptance | share |
|---|---|---|---:|---:|---:|
| 1.5B | bench-py | bug_fix+scaffold | 59 | 18 | 30.5% |
| 1.5B | bench-py | function_implementation | 164 | 127 | 77.4% |
| 1.5B | bench-py | function_implementation+scaffold | 34 | 23 | 67.6% |
| 1.5B | bench-ts | bug_fix+scaffold | 59 | 13 | 22.0% |
| 1.5B | bench-ts | function_implementation | 164 | 126 | 76.8% |
| 1.5B | bench-ts | function_implementation+scaffold | 34 | 13 | 38.2% |
| 7B | bench-py | bug_fix+scaffold | 59 | 13 | 22.0% |
| 7B | bench-py | function_implementation | 164 | 110 | 67.1% |
| 7B | bench-py | function_implementation+scaffold | 34 | 27 | 79.4% |
| 7B | bench-ts | bug_fix+scaffold | 59 | 18 | 30.5% |
| 7B | bench-ts | function_implementation | 164 | 133 | 81.1% |
| 7B | bench-ts | function_implementation+scaffold | 34 | 15 | 44.1% |

## Coverage gaps — what no committed run can answer

6 of the 36 (tier x bar x stratum x observable) cells over #224's two tiers (1.5B, 7B) have no committed run behind them. An absent row is the finding A2 is scoped from, so it is printed rather than left as whitespace.

| tier | bar | stratum | observable |
|---|---|---|---|
| 1.5B | bench-py | function_implementation+scaffold | psi_draw |
| 1.5B | bench-ts | function_implementation+scaffold | psi_draw |
| 7B | bench-py | bug_fix+scaffold | psi_draw |
| 7B | bench-py | function_implementation | psi_draw |
| 7B | bench-ts | bug_fix+scaffold | psi_draw |
| 7B | bench-ts | function_implementation | psi_draw |
