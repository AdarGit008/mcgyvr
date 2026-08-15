# How much of the gap was the scorer — #224 A2, hole 1

**2026-08-15, lane/266.** Derived entirely from committed runs. No model was
called, no rig was touched, and no token was spent: the candidate texts were
already on disk, and a bar is a pure function of them.

The tool is `tools/bench/gate_rescore.py`, pinned by
`tests/test_bench_gate_rescore.py`. The per-stratum table it feeds is
`per-stratum.md` beside this file, with the rows as `rows.json` and the
per-directory ledger as `rescore-summaries.md`.

---

## What was wrong

Every multi-draw run this project owns — the only source of `psi_draw` — was
scored by running the contract's acceptance command and nothing else, because
all three predate #113. Their rows carry no `rejected_by`. `headroom` and `psi`,
sitting in the same table, are scored by `Gate.run`. So #224 was comparing a
lenient-scorer number against a strict-scorer number and could not say how much
of the distance between them was the observable and how much was the bar.

5,694 candidates across 14 measurement directories were re-scored under
`Gate.run` — the same `tools/bench/score.py:score` the live sweep calls, so the
re-scored verdict *is* the sweep's verdict. Zero environment issues. Three rows
skipped, all pre-existing parse errors carried forward unchanged. No candidate
that parsed on the day failed to parse now.

## The answer, per (tier, bar, stratum)

| tier | bar | stratum | n | `psi_draw` acceptance | `psi_draw` `Gate.run` | share of gap | `headroom` | gap before | gap after |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1.5B | bench-py | `bug_fix+scaffold` | 33 | 69.7% (23) | 66.7% (22) | **7%** | 23.7% | 2.9x | 2.8x |
| 1.5B | bench-py | `function_implementation` | 102 | 67.6% (69) | 31.4% (32) | **59%** | 6.1% | 11.1x | 5.1x |
| 1.5B | bench-ts | `bug_fix+scaffold` | 33 | 57.6% (19) | 54.5% (18) | **8%** | 18.6% | 3.1x | 2.9x |
| 1.5B | bench-ts | `function_implementation` | 102 | 65.7% (67) | 30.4% (31) | **68%** | 13.4% | 4.9x | 2.3x |
| 7B | bench-py | `function_implementation+scaffold` | 34 | 44.1% (15) | 17.6% (6) | **64%** | 2.9% | 15.0x | 6.0x |
| 7B | bench-ts | `function_implementation+scaffold` | 34 | 47.1% (16) | 26.5% (9) | **58%** | 11.8% | 4.0x | 2.2x |

Two further tiers were re-scored and are reported in `per-stratum.md` but carry
no `headroom` contrast to compare against, so no share is computed for them: the
3B falls to 2.9% (`bench-py`, k=1) and 11.8% (`bench-ts`, k=4), both below
ADR-0019's wall of six and marked as such.

**No pooled figure appears anywhere.** The arm-level rows print no ratio at all,
and not only because pooling is forbidden: their two sides are measured over
*different material* — `headroom` spans all 257 tasks while these runs' draws
cover 34 or 135 of them — so the quotient would divide a rate on one set by a
rate on another.

## What it says

**1. The scorer was a large part of the gap and nowhere near all of it.** The
share ranges from **7% to 68%**, and it is bimodal rather than spread: about a
fifteenth on `bug_fix+scaffold`, between three fifths and two thirds everywhere
else. There is no single number for "how much was the scorer", and a pooled one
would land between two clusters that share no members.

**2. The gap never closes.** After both observables are put on one bar,
`psi_draw` still runs **2.2x to 6.0x** `headroom` on every stratum where they
can be compared. `psi_draw` is not a lenient-scorer artefact of `headroom`; the
two remain different quantities, exactly as `responsiveness.py`'s docstring
insists, and neither substitutes for the other.

**3. The scaffolded bug-fix stratum barely moves under the gate** (-3.0pp on
both arms) while `function_implementation` loses 35-36pp. A scaffolded task
hands the worker a well-formed file to edit, so its candidates arrive
lint-clean; an unscaffolded one asks for a file from nothing, and that is where
`lint` and `format` take their toll. This is a property of the *task shape*, not
of difficulty, and it cuts directly across the keep-or-retire reasoning in
today's earlier record.

**4. `pinned-pass` falls to zero in every stratum, on every run.** Under the
bench's own bar not one cell passes on all of its draws. Gate-scored `psi_draw`
is therefore no longer distinguishable from *cells that ever pass at all* — the
distinction between "responsive" and "solvable" collapses, and the screen
`psi_draw` was meant to be (cheap detection of dead cells) becomes the same
measurement as the pass rate.

## Figures already quoted that this contradicts

Stated loudly rather than reconciled, in this project's #243 tradition.

1. **"The gap between `psi_draw` and `headroom` is almost entirely the
   scorer, not the material"** —
   `records/sessions/lane/266/2026-08-15-responsive-fraction-per-model-bar-and-stratum-adar.md`,
   written earlier today, and carried into the proposed #224 amendment text.
   **Refuted.** Measured, the scorer is 7-8% of the gap on `bug_fix+scaffold`
   and 58-68% elsewhere, and 2.2x-6.0x of the gap survives on every stratum.
   "Almost entirely" is wrong on all six.

2. **The "2.9x-15.2x" range** quoted for the gap. The endpoints re-derive as
   **2.9x and 15.0x**. The 15.2x came from dividing two already-rounded
   percentages (44.1 / 2.9); the exact cell counts are 15/34 over 1/34 = 15.0x.
   A small thing, and it is the kind of small thing that becomes a quoted
   constant.

3. **The `scope` rung has rejected nothing, anywhere, and structurally cannot.**
   `mcgyvr.contract` refuses any contract whose target lies outside its own
   `scope.allow`, and the bench writes exactly one file — that target. Across
   every committed gate-scored run the tally is `lint` 1449, `format` 952,
   `acceptance` 609, `structure` 30, `syntax` 13, **`scope` 0**. The bench
   declares five rungs and four of them can fire on its material. The
   declaration is accurate about what *runs*; it must not be read as five
   working checks.

## What a zero would have meant, and why the table refuses to print one

Under a strict enough bar a stratum can be driven to no passing draws at all,
and five of the six re-scored ablation *condition* directories land at zero or
one pass. A `psi_draw` of 0.0 read off such a run is not a weak responsiveness
signal — every cell is pinned-fail by arithmetic, and the zero is a restatement
of the pass rate. `responsive.py` therefore prints `unreadable — no draw passed`
rather than a fraction in that case, does not count the cell as coverage, and
flags any numerator below ADR-0019's wall of six. None of the three multi-draw
runs used for `psi_draw` is actually driven that far, so every figure in the
table above is readable; the guard exists because the next tier down is not.

## Reproducing this

Each re-scored run carries a `gate-rescore.json` naming: the five rungs and
`semantic=False`; the mode declaration and the round + product pin
(`r1-commissioning`, product `ed508e612ff8`); the sha256 of every acceptance
script; and content digests of the `run.json`, `results.jsonl` and the whole
`candidates/` tree it read. Re-running the tool against an unchanged tree
reproduces the rows; against a changed one, the digests say exactly what moved.

    uv run --no-sync python tools/bench/gate_rescore.py --check <dir>

`--check` scores and writes nothing, so it is safe against a committed record.
The tool refuses to start if `ruff`, `eslint`, `prettier`, `python` or `node` is
missing, and refuses to proceed if `score.preflight` finds a declared rung that
runs but cannot reject — a missing tool is an environment issue that the gate
records without rejecting the worker, so a degraded run would otherwise read as
evidence that the bar is kinder than it is.

## What this does not close

Hole 2, coverage, is untouched and needs the rigs. Six of the twelve
(tier x bar x stratum) cells over #224's two tiers still have no multi-draw run
behind them, and re-scoring cannot manufacture a draw that was never dispatched.
`responsive.py`'s coverage table still prints all six.

## What the lint mass actually is — over half of it is whitespace

`lint` is the single largest rejection cause in the re-score (2,707 rows).
Its composition matters, because it decides whether the bar is measuring
code quality or typing habits. Leading finding on rows rejected at `lint`:

| leading lint finding | rows | share |
|---|---:|---:|
| Blank line contains whitespace | 924 | 34.1% |
| Line too long (...) | 446 | 16.5% |
| `typing.List` is deprecated, use `list` instead | 239 | 8.8% |
| Do not access Object.prototype method 'hasOwnPropert | 104 | 3.8% |
| `typing.Dict` is deprecated, use `dict` instead | 71 | 2.6% |
| Import block is un-sorted or un-formatted | 49 | 1.8% |
| Unexpected any. Specify a different type. | 42 | 1.6% |
| '_' is defined but never used. | 39 | 1.4% |

**1419 of 2707 (52%) lead with a purely cosmetic finding** —
trailing whitespace on a blank line (`W293`), an over-long line (`E501`), or
an unsorted import block (`I001`). All three are removed by `ruff format` /
`ruff check --fix` without a model in the loop.

This sharpens the finding rather than softening it. The share of the
`psi_draw`-to-`headroom` gap attributable to "the bar" is real, but the bar that
is doing the work is **largely a whitespace bar**, not a correctness one. #113
measured +13.7pp for a zero-token pre-gate formatting pass; this is why. Any
reading of the table above that treats the gate-scored `psi_draw` as "how many
problems the model can actually solve" is wrong by roughly the size of this
column — it is "how many it solves *and* types tidily".
