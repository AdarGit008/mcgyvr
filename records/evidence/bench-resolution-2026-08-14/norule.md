## Resolution — 1.5B, lever `norule`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's (not recorded in this manifest; the rig that wrote it had no escalation path)
- round: **none recorded** — this run predates #231's product pin, so the revision that produced it is unknown and it cannot be laid beside an arm measured in a round
- psi is this lever's, not the bench's: a contrast of a different lever resolves differently. Wall: m >= 6 (ADR-0019).

| tier | arm | stratum | n | psi | m | detectable at 80% |
|---|---|---|---:|---:|---:|---:|
| 1.5B | bench-py | bug_fix+scaffold | 59 | 0.102 | 6 | **not reachable** |
| 1.5B | bench-py | function_implementation | 164 | 0.043 | 7 | **not reachable** |
| 1.5B | bench-py | function_implementation+scaffold | 34 | 0.029 | 1 | **not reachable** |
| 1.5B | bench-py | ALL — not the bench's resolution | 257 | 0.054 | 14 | 4.3pp |
| 1.5B | bench-ts | bug_fix+scaffold | 59 | 0.051 | 3 | **not reachable** |
| 1.5B | bench-ts | function_implementation | 164 | 0.134 | 22 | 8.5pp |
| 1.5B | bench-ts | function_implementation+scaffold | 34 | 0.029 | 1 | **not reachable** |
| 1.5B | bench-ts | ALL — not the bench's resolution | 257 | 0.101 | 26 | 5.8pp |

**1 of 6 strata can resolve anything at all.** psi spreads 4.6x across strata, which is why no pooled figure is printed (ADR-0026).

## Resolution — 7B, lever `norule`

- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's
- round: **`r1-commissioning`**, product `ed508e612ff8` — every arm in this round ran against one revision, and an adopted change lands only at the boundary (ADR-0018)
- psi is this lever's, not the bench's: a contrast of a different lever resolves differently. Wall: m >= 6 (ADR-0019).

| tier | arm | stratum | n | psi | m | detectable at 80% |
|---|---|---|---:|---:|---:|---:|
| 7B | bench-py | bug_fix+scaffold | 59 | 0.119 | 7 | **not reachable** |
| 7B | bench-py | function_implementation | 164 | 0.043 | 7 | **not reachable** |
| 7B | bench-py | function_implementation+scaffold | 34 | 0.029 | 1 | **not reachable** |
| 7B | bench-py | ALL — not the bench's resolution | 257 | 0.058 | 15 | 4.7pp |
| 7B | bench-ts | bug_fix+scaffold | 59 | 0.034 | 2 | **not reachable** |
| 7B | bench-ts | function_implementation | 164 | 0.043 | 7 | **not reachable** |
| 7B | bench-ts | function_implementation+scaffold | 34 | 0.029 | 1 | **not reachable** |
| 7B | bench-ts | ALL — not the bench's resolution | 257 | 0.039 | 10 | 3.5pp |

**0 of 6 strata can resolve anything at all.** psi spreads 4.0x across strata, which is why no pooled figure is printed (ADR-0026).
