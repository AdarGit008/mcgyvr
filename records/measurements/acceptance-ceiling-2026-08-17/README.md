# What the acceptance ceiling bounds — 17 August 2026

What [#262](https://github.com/AdarGit008/mcgyvr/issues/262) asks for: *"one
acceptance timeout, or two with a recorded reason."* The number was three
numbers — `120.0` in `tools/bench/score.py`, `30.0` in
`tools/bundle/measure.py`, `30.0` in `tools/problems/admit.py` — under two
comments each asserting they matched. This is the measurement
[ADR-0035](../../../docs/decisions/0035-the-bar-is-recorded-as-content-and-there-is-one-acceptance-ceiling.md)
reconciled them against.

`units.jsonl` is one row per acceptance run **this tool executed** — the 514
reference timings. `summary.json` is the bands over both populations.

The 32,601 candidate rows are deliberately **not** copied here. They are a
projection of `records/measurements` itself, 7.1 MB of it, already in the tree
and re-derivable in seconds; a second copy would be a second thing to keep in
agreement with the first. `--all-units` writes them for a caller working outside
a checkout.

Re-run:

```
uv run --no-sync python tools/bench/ceiling.py --out records/measurements/acceptance-ceiling-2026-08-17
```

**Nothing dispatches.** The reference sweep runs material already on disk; the
candidate durations are read out of records already written. No model is called
and no rig time is spent — which is the reason this could be measured at all
rather than asserted.

## Two populations, and only one of them decides anything

| population | what it is | n | max |
|---|---|---|---|
| **references** | every admitted problem's checker against its own reference solution | 514 | **0.305 s** |
| **candidates** | every `acceptance_s` on disk | 32,601 | 121.391 s (a timeout) |
| candidates that **passed** | the subset a ceiling can wrongly reject | 8,230 | **28.718 s** |

The reference population is what pool admission screens, and it settles nothing:
its slowest member is 0.305 s, so 30 s and 120 s are 98x and 393x its cost. Any
argument built on "the references are fast" would have justified either number.

The population that decides is **slow but correct candidates**, and it has a
shape worth stating: one member at 28.718 s, its next at 2.500 s. An 11.5x gap
between first and second.

## The number the decision turned on

`p242-cycle-shape-report`, in `pool-sweep-14b-cap2048-2026-08-08`, passed its
acceptance command in **28.718 s** under a **30 s** ceiling. That is 4.5% of
margin on a row that is already inside a published rate. Under 120 s the same
candidate has 4.2x.

That is why the live pair reconciled **up** rather than down, even though down
would have made `admit.py`'s existing comment true and cut runaway cost 4x.

## What the two ceilings have actually disagreed about

Nothing, in every row that could have shown it:

| | rows |
|---|---|
| measured at the 120 s ceiling — could land in [30, 120) | 1,539 |
| that did | **0** |
| censored at 30 s — *could not* land in the band | 31,062 |

The three runs that could observe the band are
`bench-null-gate-15b-a-2026-08-13`, `bench-null-gate-15b-b-2026-08-13` and
`bench-control-norule-7b-2026-08-14`. Read carefully: 95% of the corpus is
censored, so this shows the two ceilings have never disagreed about a **recorded
verdict**, not that the band is empty. ADR-0035 does not rest on it.

## Timeouts

130 rows across the whole campaign, **none of them passing** — 127 at the 30 s
ceiling and 3 at 120 s, all three the same problem (`b487-shed-tail`, on the
TypeScript arm). So the cost of the wider ceiling is 90 extra seconds on rows
that were going to fail: about 3.25 h spread over every run ever taken.

A timeout is identified by either of two phrasings, because two scorers wrote
these rows — the acceptance-only path and `Gate.run` (#113). `tools/bench/ceiling.py`
carries both markers and reports the counts, so a row matched by neither shows
up as a completed run and can be argued with.

## What this does not measure

The **candidate** population is drawn from runs that were themselves censored,
so the true distribution of slow-but-correct candidates above 30 s is unknown
and unknowable from this data. The one observation at 28.718 s is a lower bound
on how close that population gets to a ceiling, not an estimate of its tail.
Registered against #262 rather than as a claim, because a claim would be
overstating what a censored sample can carry.
