---
record: session/4
lane: lane/266
agent: adar
started: 2026-08-15T09:00:00Z
---

# Session — lane/266 — 2026-08-15

## Did

#224's **A2, hole 1**: re-scored every saved worker candidate this project holds
under `Gate.run`, offline, at zero token cost. 5,694 candidates across 14
measurement directories — `f1-responsiveness-15b-2026-08-11` (both arms, 1,215
rows each) and the 3B and 7B scaffold ablations (six condition directories each
at 272 rows). No model was called and no rig was touched.

**The tool is new and purpose-built.** `tools/bench/gate_rescore.py`, beside
`tools/bench/regrade.py` rather than inside it. The two hold opposite
invariants: `regrade` holds the *scorer* fixed at acceptance and re-runs it
after a **checker** is corrected; this holds the *candidate* fixed and changes
the scorer from acceptance-only to the five rungs the product ships. Those
cannot live behind one flag. Everything shareable is composed — `checker_digests`
is imported from `regrade`, and `score.score` is called rather than
reimplemented, because a re-score that scored differently from a sweep would
answer nothing.

Two things it must do that `regrade` does not. It stages each task's base from
`breadth.ablate(contract, condition)`, because `Gate.run`'s scope rung judges a
**diff** and an ablated cell must be diffed against the tree the worker was
actually shown — get that wrong and every `noscaffold` cell is rejected at
`scope` and reads as a finding. And it refuses to start unless `score.preflight`
confirms every declared rung can *reject*, not merely that its tool is
installed: the gate records a missing tool as an environment issue and still
reaches a verdict, so a degraded run would read as evidence that the bar is
kinder than it is. Zero environment issues were recorded across all 14 runs.

`regrade`'s doctrine is kept whole: `results.jsonl` is never rewritten, the
re-score lands beside it as `gate-rescore.jsonl`, rows that never reached a
checker are carried forward and marked, and the candidate is re-parsed rather
than trusted. Three rows were skipped, all pre-existing parse errors. No
candidate that parsed on the day failed to parse now.

`tests/test_bench_gate_rescore.py` is thirteen hand-built cases whose expected
verdicts were derived from the rung order in `mcgyvr.gate.runner` **before** the
tool was run — a clean pass, lint-only, format-only, both (which must resolve to
`lint`, because `_run_adapter` appends lint first), a wrong-but-clean answer
rejected at `acceptance`, a scope violation on code that would have passed, and
the three rows a re-score must refuse to grade.

## The answer

| tier | bar | stratum | n | `psi_draw` acceptance | `psi_draw` `Gate.run` | share of gap | `headroom` | gap before | gap after |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1.5B | bench-py | `bug_fix+scaffold` | 33 | 69.7% (23) | 66.7% (22) | **7%** | 23.7% | 2.9x | 2.8x |
| 1.5B | bench-py | `function_implementation` | 102 | 67.6% (69) | 31.4% (32) | **59%** | 6.1% | 11.1x | 5.1x |
| 1.5B | bench-ts | `bug_fix+scaffold` | 33 | 57.6% (19) | 54.5% (18) | **8%** | 18.6% | 3.1x | 2.9x |
| 1.5B | bench-ts | `function_implementation` | 102 | 65.7% (67) | 30.4% (31) | **68%** | 13.4% | 4.9x | 2.3x |
| 7B | bench-py | `function_implementation+scaffold` | 34 | 44.1% (15) | 17.6% (6) | **64%** | 2.9% | 15.0x | 6.0x |
| 7B | bench-ts | `function_implementation+scaffold` | 34 | 47.1% (16) | 26.5% (9) | **58%** | 11.8% | 4.0x | 2.2x |

Nothing is pooled. The arm-level rows carry no ratio at all — their two sides are
measured over *different material* (`headroom` spans 257 tasks, these draws cover
34 or 135), so the quotient would divide a rate on one set by a rate on another.
The 3B was re-scored too and has no contrast to compare against; it falls to
k=1 (`bench-py`) and k=4 (`bench-ts`), both under ADR-0019's wall.

**The scorer was a large part of the gap and nowhere near all of it — 7% to 68%,
bimodal.** About a fifteenth on `bug_fix+scaffold`, three fifths to two thirds
everywhere else. There is no single answer, and a pooled one would land between
two clusters that share no members.

**The gap never closes.** `psi_draw` still runs 2.2x-6.0x `headroom` after both
are on one bar. It is not a lenient-scorer artefact of `headroom`; the two stay
different quantities, as `responsiveness.py` has always said.

**Scaffolded bug-fix barely moves (-3.0pp both arms); `function_implementation`
loses 35-36pp.** A scaffolded task hands the worker a well-formed file to edit,
so its candidates arrive lint-clean; an unscaffolded one asks for a file from
nothing, and that is where `lint` and `format` take their toll. That is a
property of **task shape**, not difficulty, and it cuts across the keep-or-retire
reasoning in session/3.

**`pinned-pass` falls to zero in every stratum, on every run.** Under the bench's
own bar not one cell passes on all of its draws, so gate-scored `psi_draw` is no
longer distinguishable from *cells that ever pass at all*. The screen `psi_draw`
was meant to be — cheap detection of dead cells — has become the same
measurement as the pass rate.

**Over half the bar is whitespace.** `lint` is the largest rejection cause
(2,707 rows). Its leading finding is `W293` "blank line contains whitespace" on
924 of them (34%), `E501` over-long line on 446 (17%) and `I001` unsorted
imports on 49 — **1,419 of 2,707, 52%, lead with something `ruff format` erases
without a model in the loop.** The share of the gap attributable to "the bar" is
real, but the bar doing the work is largely a *whitespace* bar rather than a
correctness one. #113 measured +13.7pp for a zero-token pre-gate formatting
pass; this is the mechanism. Gate-scored `psi_draw` must not be read as "how
many problems the model can solve" — it is "how many it solves and types tidily".

## Contradicts

1. **session/3's "the gap is almost entirely the scorer, not the material"** —
   written earlier today and carried into the proposed #224 amendment.
   **Refuted on all six strata.** 7-8% on `bug_fix+scaffold`, 58-68% elsewhere,
   with 2.2x-6.0x surviving everywhere. The amendment text at
   `records/evidence/responsive-fraction-2026-08-15/proposed-224-amendment.md`
   should not be posted as written.
2. **The quoted "2.9x-15.2x" gap range** re-derives as **2.9x-15.0x**. The 15.2x
   is what you get dividing two already-rounded percentages (44.1 / 2.9); the
   exact counts are 15/34 over 1/34.
3. **The `scope` rung has rejected nothing, anywhere, and structurally cannot.**
   `mcgyvr.contract` refuses a contract whose target lies outside its own
   `scope.allow`, and the bench writes exactly one file — that target. Tally
   across every committed gate-scored run: `lint` 1449, `format` 952,
   `acceptance` 609, `structure` 30, `syntax` 13, **`scope` 0**. Four of the five
   declared rungs can fire on bench material. The declaration is accurate about
   what runs and must not be read as five working checks.
4. **A verification circulated during this session reported n=1080 and n=238**
   against this tool's 1215 and 272, and `65 -> 14` against `76 -> 15` on
   `bench-scaffold-ablation-7b/stock/bench-py`. The difference is a key
   collision: intersecting rows on `(task, draw)` merges `greedy-0` with
   `sampled-0`, silently dropping exactly one row per task (135 and 34
   respectively). The correct key is `(task, arm, draw)`. Verified directly —
   `results.jsonl` holds 1215 unique `(task, arm, draw)` and 1080 unique
   `(task, draw)`.

## Also changed

`responsiveness.cells` takes a `rows_name` so the same draws can be read under
either bar; the default is unchanged, so every figure already derived from it
keeps its meaning. `responsive.py` now emits both bars per stratum, computes the
share of the gap, and — the guard that matters — **refuses to print a fraction
for a `psi_draw` row with no passing draw behind it**. A zero there has two
opposite causes and the number cannot tell them apart: either the cells never
moved (a fact about the material) or nothing passed at all (every cell
pinned-fail by arithmetic, the zero a restatement of the pass rate). Under
`Gate.run` the second is reachable — five of the six re-scored ablation
condition directories land at zero or one pass. Such a row prints
`unreadable — no draw passed`, does not count as coverage, and any numerator
under ADR-0019's wall of six is flagged. None of the three runs used for
`psi_draw` is driven that far, so every figure in the table is readable; the
guard exists because the next tier down is not.

## Left open

- **Hole 2, coverage, is untouched and needs the rigs.** Six of twelve
  (tier x bar x stratum) cells over #224's two tiers still have no multi-draw
  run. Re-scoring cannot manufacture a draw that was never dispatched. S1 and S2
  as scoped in session/3 still stand, and both must run gate-scored in round
  `r1-commissioning` or hole 1 recurs in the new material.
- **`psi_draw` as a screen is now in question.** With `pinned-pass` at zero
  under the bench's bar it no longer separates "responsive" from "ever passes",
  which was the whole reason it was cheaper than measuring a lever. Whether it
  still earns its rig time is a question for A2's remaining items.
- **The 3B is effectively dead under the gate** — 1 and 4 responsive cells of 34,
  both under the wall. It was never one of #224's two tiers; it is now evidence
  that the floor unit's tier choice matters more than the record assumed.
- **The `scope` rung's inertness deserves its own decision.** Either the bench's
  one-file shape is accepted and the rung is documented as not applicable, or
  material that can exercise it is authored. It should not keep being counted in
  a five-rung declaration without a note.

next: A2's remaining items — decide whether `psi_draw` still earns rig time now
that it collapses into the pass rate, then size S1/S2
