complete: an observation reached every cell.

**ling-3-0-tiny-q4-k-m** on http://127.0.0.1:8094 (build unknown), tier `bench-py`, condition `stock`

- scored by: Gate.run [scope, secrets, structured, adapters, acceptance]
- mode: **single-tier** — one model, no escalation, so every figure below is that tier's own and not the ladder's
- round: **`r2-02-09-2026`**, product `2927fdafe59b` — every arm in this round ran against one revision, and an adopted change lands only at the boundary (ADR-0018)
- **the serving build is unknown** — the endpoint did not answer `/api/version`, so this run cannot be laid beside one from a different build (ADR-0024)

greedy (T=0.0): 27/257 pass
sampled draw 0 (T=0.7): 19/257 pass

first-pass index over 257 tasks with all 1 sampled draws recorded (19 with any pass, 238 with none):

| index | tasks | cumulative pass@≤k |
|:-----:|:-----:|:------------------:|
| 0 | 19 | 19/257 |
| none | 238 | — |

wall clock per additional candidate: 11.3s dispatch + 0.0s acceptance (mean over 257 sampled draws)

cost per candidate: 769 prompt + 733 completion tokens (mean over 514 dispatched draws)

514 rows. 459 replies the parser refused, 0 draws lost to dispatch errors.
