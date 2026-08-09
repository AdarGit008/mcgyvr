# `tools/power` — what an instrument can actually resolve

The arithmetic behind
[ADR-0019](../../docs/decisions/0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md).
It answers two questions and nothing else:

- **Given a bench, what is the smallest effect it can detect?** — `mde.py`
- **Given a bar, how big does the bench have to be?** — `mde.py`, and
  `report.py` applies both to the records this repository already holds.

```
python tools/power/report.py                 # every table in ADR-0019
python tools/power/report.py --section null  # just the measured null drift
```

`report.py` reads `records/measurements/` and hand-enters nothing, so re-running
it is the check on the ADR rather than a restatement of it.

## The one idea

For two conditions scored over the *same* tasks the test is McNemar's, and power
is carried by the tasks whose verdict **differs** between them — the discordant
pairs. A task that passes under both, or fails under both, is not weak evidence
of a small effect; it is absent from the statistic. So nominal *n* is the wrong
denominator, and the gap is not small: on the JS/TS bundle instrument 13 of 20
tasks never move under any condition.

Two rates, kept apart throughout:

| | meaning |
|---|---|
| `psi` | discordance rate — P(the verdict differs). A property of the **(instrument, lever)** pair, never of a task set alone. |
| `delta` | net effect — P(fail→pass) − P(pass→fail), which is what a pass-rate table reports as a difference. |

`psi >= |delta|` always. The gap between them is churn: flips in both directions
that cancel in the headline number while still spending power.

## Why the exact test, everywhere

With `m` discordant pairs the best-case two-sided p is `2 / 2**m`, so **`m >= 6`
is a hard wall** — below it nothing rejects at α = 0.05 at any effect size. The
normal approximation does not know this and will quote a minimum detectable
effect for a contrast that could never have produced one. Every instrument this
repository owned when the ADR was written sits below that wall.

`EXACT_M_LIMIT` switches the *inner* conditional sum to a normal approximation
above m = 400, purely for speed at n in the tens of thousands. The wall itself,
and every contrast we have actually measured, stay exact.
`tests/test_power_mde.py` pins the two branches to agree at the crossover.

## Using it

```python
from mde import Contrast, detectable_delta, required_n

# What did a run we already have actually establish?
k = Contrast("jsts c0->c2", n=20, gained=3, lost=2)
k.psi, k.delta, k.p_value  # 0.25, 0.05, 1.0
k.can_ever_reject  # False — unresolvable before dispatch

detectable_delta(400, 0.20)  # 0.065 -> +26 tasks, +6pp
required_n(0.03, 0.20)  # 1800 paired tasks for a 3pp bar
```

`can_ever_reject` returning `False` is a finding, not an error: it says the
contrast could not have produced a verdict whatever the model did, so its
p-value reports nothing about the lever.

## Where the numbers get used

- **#231** computes the fitness verdict — `MDE <= b` and `drift < b`, per tier,
  in writing, before any arm is dispatched.
- **#225** is sized from `required_n` once #231 measures `psi` on the
  commissioning contrast. Until then ADR-0019's measured range (0.05–0.40) is
  the planning prior.
- **#222** is sized behind #225.

## A trap this tool exists to not fall into

Truncation is read from `stop_reason`, never from `overran_cap`. The latter asks
whether the backend returned *more* tokens than it was allowed
(`src/mcgyvr/runner.py:242`); it is correctly `False` on all 12,466 measurement
rows in the repository, so filtering on it silently keeps every truncated cell.
Doing that to the pool drift comparison turns 1 discordant problem into 3.
