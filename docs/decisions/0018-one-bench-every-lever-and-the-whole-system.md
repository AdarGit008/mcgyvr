# ADR-0018 — one bench, every lever, and the whole system measured

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0017 (extends P1; does not disturb P1–P3)
Date: 2026-08-09

## Context

[ADR-0017](0017-the-floor-is-the-product.md) settled *what* to improve: the floor,
because every property that makes mcgyvr worth using is a property of the small
end of the ladder. It did not settle *how a floor raise is recognised*, and the
#220 audit found that the gap had consequences.

The audit read all 69 open issues against P1–P3 and produced
`docs/floor-audit-2026-08-09.md`. Two of its findings force this record:

**The project owned a floor instrument and did not know it.** ADR-0017 claimed
none existed; `tools/bundle/tasks/` (20 JS/TS) and `tools/bundle/python/tasks/`
(20 Python) are real contracts with runnable acceptance against checked-in
references, measured on qwen2.5-coder:3b at 45/55/50/45% and 65/70/70/70% across
four conditions. Both sit in the band a floor instrument must occupy by level;
only the JS/TS arm has been shown to move under condition. That ADR is amended
accordingly, and its own Python figure is corrected there — the 35/50/55/65%
this paragraph first carried is CLM-0017's arm B, the vendored local-ai
instrument, not this repository's task set.

**Four measurement rigs had grown, none comparable to the others.** Prompt work
was measured on 20 tasks (`tools/bundle/`), difficulty on 12–20 per tier
(`tools/breadth/`), fine-tuning on 164 (HumanEval+), worker capability on 499
(the #197 pool). Four scales, four noise floors. This is why "+1.9pp on
HumanEval+", "+4 tasks in 20 on the bundle set" and "0/50 on the pool" could not
be laid beside each other — and why nobody could see that one line of prompt was
worth an order of magnitude more than the tune it was competing with.

#113 specified the fix in its own words long before any of those rigs were built:
*"a condition matrix varying exactly one thing per axis… a pass-rate report per
condition, carrying n, model, rig."* It was written down and then not followed,
which is the same shape ADR-0017 found in the pool.

Owner direction of 2026-08-09 added four requirements that this record makes
binding.

## Decision

**Q1 — every lever is measured on one bench, and a measured null closes an arm.**
Each way of raising the floor — prompt assembly, decomposition, target
granularity, output caps, attempts, weights — is an *arm* against a single task
set, a single held-out set, a single noise floor. An arm is finished when it
reports an effect **or** reports "no effect, measured, at this power." Both are
completions. **No lever is dropped for producing a small gain**, and no lever is
retired without a number.

This replaces the bar's former job. `MIN_QUALITY_GAIN = 0.03` was never an
adoption threshold — `src/mcgyvr/propose.py:32` shows it is the separation two
*rungs* need before both are worth carrying — and #189 borrowed it. A bar now
does two separate things: it states the **reality floor** below which an effect
is indistinguishable from the instrument's own noise, and it states a **per-lever
adoption rule**, because a +1pp prompt change that ships to every rung in one run
and a +1pp fine-tune costing GPU hours, an export path, a quantization step and a
capability-table entry are not the same proposition. Located as #229.

**"Ruled out" means measurably ruled out.** An unresolvable result is a failure of
the instrument, not a verdict on the lever — the lesson of #189, whose "miss" at
+1.9pp was judged by an instrument that could not resolve +4.8pp.

**Q2 — effects are comparable, not addable, and composition is measured.** Two
levers that fix the same three tasks give +3, not +6. Two that interact could give
more. One bench buys one scale; **whether effects compose is an empirical
question**, and it is answered rather than assumed.

The combination space over *n* levers is 2ⁿ, and the all-on cell is not a corner
of it — **it is the product with every improvement switched on**, so it is a
first-class measurement. Staged so it is affordable: baseline + singles + all-on
answers whether the whole differs from the sum; leave-one-out then gives each
lever's marginal worth *inside* the full system, which is the shipping question.
Combinations are pre-registered by rule before the singles run. Located as #233.

**Q3 — nothing is trusted uncommissioned, and a round is the unit.** Before any
arm is read, the bench must measure its own drift over two identical runs, and
must **recover an effect already known to be there** — CLM-0017's output-shape
line, worth ~+20pp. An instrument that cannot find a known effect cannot be
trusted to find a new one.

**The code under test is pinned, not only the tasks.** Every arm in a **round**
runs against one product revision; an adopted change lands at the round boundary,
never mid-flight. Without this a winning arm silently re-baselines its own
siblings and comparability — the entire point of one bench — is lost. Located as
#231.

**Q4 — the bench is parameterized by target tier, so a new model is a re-run.**
ADR-0017's P3 says the floor can move. This makes it operational: adding a small
model means running the battery, not rebuilding it, and the commissioning gate
proves that by re-running against a second tier before any arm is dispatched.

**Corollary — the instrument is declared, and protected at the point of entry.**
`tools/replies/pin.py` walks every run under `records/measurements/` into
`golden.json`, which `tools/finetune/build_dataset.py` then reads — so a bench run
joins the training corpus the moment it lands. #189 trained on tier `d1`, which
*is* `tools/bundle/tasks/`, which is half the floor instrument. Instrument sets
are therefore declared once as data and respected by the admission gate, the pin
and the dataset builder alike. Located as #230.

## Rejected: a strict sequential chain over every issue

The drift was locally-defensible steps adding up to a wrong direction, which
makes serialization a tempting cure. It is the wrong one. A total order puts
upstream rule design and baseline hygiene in line behind floor measurement, which
serves nobody — and the tree already ran a version of it: five nodes blocking all
64 remaining issues, which froze the cheapest floor raises in the project behind
ten hours of rig time. **Parallelism was never the problem. The absence of an
arbiter of evidence was.** One bench is that arbiter, and arms run in parallel
*because* they share it.

## Rejected: start a new repository

Also considered on 2026-08-09. The drift is a process failure, not a code
failure: 1,155 tests pass, mypy is clean over 99 source files, the baseline gate
reports 92% readiness with zero blockers, and the contract schema, sandbox, index,
decomposer, gates and runners all work. A new repository discards that and — far
worse — the evidence layer, which is the most expensive thing here and the least
reconstructible: the pool cost real money and two spend-limit interruptions,
and CLM-0004/0012/0017 and the floor probes are months of rig time.

The process that produced the drift travels with the issues, not the directory.
mcgyvr is already the second repository, founded off local-ai to escape inherited
mess; founding a third to escape a measurement-discipline problem repeats a move
that did not fix it the first time.

## Rejected: run the full combination space

2⁶ = 64 cells at a widened bench is on the order of 25,000 dispatches — roughly
sixteen pool sweeps — to answer a question that baseline + singles + all-on
answers in eight. The staged design escalates to the full factorial only when the
cheap stages leave a discrepancy unexplained. **Whatever is not run is stated**;
silent truncation of a design space reads as coverage.

## Consequences

- **The trunk is sequential and short.** #229 → #230 → (#227, #217) → #113 →
  (#225, #224) → #231. Only the widening costs meaningful rig time, and the four
  cheap stages before it are what size it. Everything else in the tree either
  hangs off the gate as an arm or is parked outside the queue entirely.
- **Parked is not blocked.** Delivery, packaging, release, records discipline and
  v2 leave the dependency graph. They do not compete with the floor question for
  the same judgment and should not queue behind it. The audit's largest finding
  was that a blanket block prices cheap floor raises at zero for as long as it
  holds.
- **The bench scores the way production does.** `Gate.run`'s verdict, not a
  bespoke scorer — otherwise a change that writes outside `scope.allow` passes on
  the bench and fails in the product.
- **Two outcome axes, not one.** Pass rate cannot rank levers alone: #81 moves
  cost to zero and pass rate not at all. This is narrower than #59, which is the
  product's rollup and stays parked.
- **Some levers are not bench-measurable, and that is stated rather than forced.**
  #81's task types do not exist on the bench and its claim is a suite assertion.
  It remains a floor issue; it is simply verified elsewhere and is not a factor in
  the combination space.
- **Cost is admitted.** Commissioning spends rig time before any question is
  answered, pre-registration forecloses attractive post-hoc analyses, and one
  pinned revision per round means a win waits for a boundary. That is the
  decision, not a side effect of it.
