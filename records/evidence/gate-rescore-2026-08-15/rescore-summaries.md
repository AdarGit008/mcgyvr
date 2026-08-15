# Gate re-score, per measurement directory — #224 A2 hole 1

Produced by `tools/bench/gate_rescore.py`. Every row of every run below was
re-scored offline under `Gate.run`; no model was called and no rig was touched.
The source `results.jsonl` files are unchanged — each re-score sits beside its
run as `gate-rescore.jsonl` with a `gate-rescore.json` summary carrying the
digests it was produced under.

- round: **`r1-commissioning`**, product `ed508e612ff8`
- rungs: scope, secrets, structured, adapters, acceptance; semantic off by decision (ADR-0011)
- scorer: `tools/bench/score.py:score — mcgyvr.gate.runner.Gate.run`
- previously: acceptance command only (predates #113)

| run | condition | arm | rows | scored | passed before | passed after | lint | format | syntax | structure | acceptance | env issues |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bench-scaffold-ablation-3b-2026-08-11 | noscaffold | bench-py | 272 | 272 | 14 | 0 | 235 | 7 | 3 | 21 | 6 | none |
| bench-scaffold-ablation-3b-2026-08-11 | noscaffold | bench-ts | 272 | 272 | 6 | 0 | 117 | 136 | 5 | 0 | 14 | none |
| bench-scaffold-ablation-3b-2026-08-11 | planonly | bench-py | 272 | 272 | 14 | 1 | 241 | 7 | 6 | 15 | 2 | none |
| bench-scaffold-ablation-3b-2026-08-11 | planonly | bench-ts | 272 | 272 | 12 | 0 | 125 | 134 | 4 | 1 | 8 | none |
| bench-scaffold-ablation-3b-2026-08-11 | stock | bench-py | 272 | 272 | 25 | 1 | 224 | 8 | 2 | 8 | 29 | none |
| bench-scaffold-ablation-3b-2026-08-11 | stock | bench-ts | 272 | 272 | 28 | 13 | 81 | 123 | 7 | 0 | 48 | none |
| bench-scaffold-ablation-7b-2026-08-11 | noscaffold | bench-py | 272 | 272 | 41 | 9 | 201 | 34 | 3 | 1 | 24 | none |
| bench-scaffold-ablation-7b-2026-08-11 | noscaffold | bench-ts | 272 | 272 | 43 | 2 | 81 | 181 | 4 | 0 | 4 | none |
| bench-scaffold-ablation-7b-2026-08-11 | planonly | bench-py | 272 | 272 | 53 | 7 | 201 | 33 | 6 | 0 | 25 | none |
| bench-scaffold-ablation-7b-2026-08-11 | planonly | bench-ts | 272 | 272 | 44 | 0 | 85 | 180 | 6 | 0 | 1 | none |
| bench-scaffold-ablation-7b-2026-08-11 | stock | bench-py | 272 | 272 | 76 | 15 | 174 | 29 | 2 | 0 | 52 | none |
| bench-scaffold-ablation-7b-2026-08-11 | stock | bench-ts | 272 | 272 | 70 | 30 | 60 | 104 | 5 | 0 | 73 | none |
| f1-responsiveness-15b-2026-08-11 | stock | bench-py | 1215 | 1212 | 399 | 135 | 665 | 135 | 4 | 60 | 213 | none |
| f1-responsiveness-15b-2026-08-11 | stock | bench-ts | 1215 | 1215 | 361 | 150 | 217 | 613 | 5 | 0 | 230 | none |

**The `scope` rung rejected nothing, anywhere, and structurally cannot.**
`mcgyvr.contract` refuses a contract whose target lies outside its own
`scope.allow`, and the bench writes exactly one file — that target. So of the
five declared rungs, four can fire on bench material. The declaration is
accurate about what runs and must not be read as five working checks.
