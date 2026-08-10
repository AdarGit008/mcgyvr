# ADR-0020 — retire the rulers, release the local five, never train on HumanEval

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: ADR-0016 (the corpus keeps the same replies; what may be drawn from it
changes), ADR-0018 (stage order below the bench: #225 precedes #113)
Date: 2026-08-10

## Context

[ADR-0018](0018-one-bench-every-lever-and-the-whole-system.md) put one bench
under every lever. [ADR-0019](0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md)
asked what that bench has to be able to see, and measured what the existing
instruments *can* see. #230 then declared the instruments — five local task
sets, `tools/instruments.json` — and protected them at the point of entry, which
walled 9,173 of the project's 12,331 captured replies away from any training
set.

Those two results arrived on the same day and pull against each other. The
declaration is only worth its cost if the sets it protects are rulers. #229
measured whether they are.

## The measurement that decides this record

Re-derivable with `python tools/power/report.py`; nothing here is hand-entered.

Every arm on the bench is a **paired** comparison — the same task under two
conditions — so the statistic is McNemar's exact test and its power comes from
the **discordant pairs**, the tasks that changed verdict. With `m` discordant
pairs the best-case two-sided p is `2 / 2**m`, so **m ≥ 6 is a hard wall**:
below it the conditional null has too little mass to spend and the test cannot
reject however large the effect is.

**Eleven of the twelve bundle contrasts this project has ever run were
unresolvable before the model was dispatched.** Not null — unresolvable. And
nominal n is the wrong denominator: across the condition matrix only 30–45% of
the twenty tasks ever change verdict at all, and on the Python arm's root
configuration it is **1 of 20**.

At n = 20 there is **no effect size that reaches 80% power** across the measured
discordance range. That is the whole finding. The five sets total **65 tasks**:

| set | tasks | language |
|---|---:|---|
| `bundle-ts` (= tier `d1`) | 20 | TS |
| `bundle-py` | 20 | PY |
| `breadth-d2` | 12 | TS |
| `breadth-d3` | 12 | TS |
| `breadth-d1r` | 1 | TS |

The instruments are not coarse because they are noisy — greedy re-run drift is 0
or 1 task at four model sizes. They are coarse because they are **small**. No
amount of care in running them changes that.

## Decision

> **DECIDED (2026-08-10, owner).** Retire all five declared instrument sets and
> HumanEval+ as decision instruments. Release the five local sets for training.
> Take nothing from HumanEval into a fine-tune, ever.

### 1. A ruler that cannot resolve anything is not a conservative asset

It is a standing invitation to publish a number that decides nothing. #189 is
the receipt: its "+1.9pp, under the 3pp bar" reads as a negative result and is
in fact **UNDECIDED**, because the contrast it ran could not have rejected
anything at any outcome. Keeping the five sets in service would keep that
failure mode available.

Retiring is not deleting. The contracts stay, the measurement records stay, the
git history stays. What ends is the licence to produce a new number from them.

### 2. Retirement is what makes release safe

A set the project will never measure on again cannot be contaminated by training
on it. The 9,173 replies #230 walled off become fuel, and the training corpus
goes from **608 examples over 150 problems** to **1,544 over 184**
(`records/corpora/training-release-2026-08-10/`). The material was always fine;
it was the measuring that was spoiled.

### 3. HumanEval+ is retired too, and is permanently untrainable

**EvalPlus does not add problems.** It takes the 164 HumanEval problems (OpenAI,
2021) and augments the *test suites*, so the exposure question is about
HumanEval — public on GitHub for five years and mirrored into a large number of
derivative datasets.

Stated without an absence claim: **we did not find, for any of the models served
on the rigs, evidence that its pretraining corpus excluded HumanEval.** Vendor
decontamination claims where they exist are unverifiable from outside, and the
usual method — n-gram filtering — is documented as leaky against paraphrase and
translation. The prudent default is to treat every served model as having seen
it, and to put the burden on any future claim that one has not.

The consequence is not that the number is worthless. It is **reporting, not
evidence**: usable for lining up against published figures, inadmissible for
deciding whether a lever worked.

There is a suggestive local signal, offered with its confound: `qwen2.5-coder:3b`
reads **78.0% on HumanEval+ and 0/50 on the #197 pool** (#221). That gap is what
contamination looks like. It is also what a difficulty difference looks like, and
[ADR-0017](0017-the-floor-is-the-product.md) attributes it to the pool's
whole-problem unit of work sitting above the 3B's ceiling. Separating the two
needs novel tasks matched to HumanEval's difficulty, which do not exist here.
**This record does not claim the gap proves contamination.** Neither reading
makes the set safe to decide on.

Training is the asymmetric case. A tune that had seen HumanEval would make every
comparison against a HumanEval figure — ours or anyone else's — unreadable, and
unlike the local five there is no version of it we could retire our way out of.
So the bar is permanent and the scope is the 164 problems, their solutions,
their tests, and anything derived from them.

### 4. Two flags, not one

"Retired" and "trainable" are separate properties and the declaration carries
them separately:

| set | retired | trainable |
|---|---|---|
| the five local sets | yes | **yes** |
| HumanEval+ | yes | **no, permanently** |

Collapsing them would either strand 9,173 replies for no reason or release
material that must never be released. A third combination — **live and
trainable** — is refused where the declaration loads, because that is #189
exactly.

### 5. Enforced, not remembered

- `tools/instruments.json` carries `retired` (issue, date, argument) and
  `trainable` per set. HumanEval+ is declared as a **rootless external** entry
  — it has no contracts here, so it is declared by the id space already
  vendored beside the pool gate.
- Both rigs refuse a retired set where a run record would be written, and at
  the CLI ahead of the runtime check. `--selftest` and `--summarise-only` are
  not measurements and still work.
- The task **loaders** are deliberately not guarded: released contracts must
  still resolve, because rebuilding the prompt behind a released reply is what
  the release is for.
- `tools/finetune/build_dataset.py` refuses on `trainable` rather than on set
  membership, and the manifest records which sets were released, which were
  refused, and which material was released but unresolvable.

## Rejected: keep the sets and raise n

Adding tasks to `d1` would make a new instrument wearing an old name — every
historical row would describe a different denominator, and the contracts have
already been edited twice. #225 generates the replacement on a declared split
rule instead. The sets are not repairable into a bench; they are the material a
bench was needed *instead of*.

## Rejected: retire the sets but keep them protected from training

This is the "safe" option and it is the expensive one. It costs 9,173 replies
and buys nothing, because the only thing protection buys is the integrity of a
future measurement, and there will not be one. Protection without a measurement
to protect is superstition.

## Rejected: retire HumanEval+ silently, or not at all

Not at all: the 78% would stay quotable as a capability fact, and #221's
decision would rest on it. Silently: the doctrine would live only in an ADR,
and the reader who needs it is reading `tools/instruments.json`. Declaring it
as an external entry puts the refusal where the code will enforce it, and the
argument where a reader will look.

## Rejected: treat the 3B's 78%/0% gap as evidence of contamination

It is consistent with contamination and equally consistent with a difficulty
difference, which ADR-0017 already attributes it to. Claiming it would be
reaching a conclusion the design cannot support, and the decision does not need
it: the exposure argument stands on HumanEval's public history alone.

## Consequences

**The trunk order reverses below #230.** #113's task set was to be the bundle
sets; retiring them puts #225 (which generates the material) ahead of #113
(which builds the harness on it), and takes #227 off the trunk — its subject is
one of the retired sets, and the breadth rig already serves Python for
`pool-py`. #217 is unaffected.

```
#229 ✅ → #230 ✅ → (#240 ‖ #217) → #225 → #113 → #224 → #231 → arms
```

**No local ruler exists until #225 and #113 land**, and nothing can report a
verdict in the interval. This is honest rather than new: none of the five could
have reported one either.

**The bundle rig no longer measures anything.** Both its arms are retired, so
every sweep invocation exits with the retirement error. Its machinery is kept
because #225's material will need a runner.

**#189's adapter is unchanged and still untested.** UNDECIDED on the benchmark
it used (#229), inadmissible on the benchmark that matters (#230). Retirement
does not make it measurable; it makes the lever's next attempt measurable, on a
bench that can resolve it.

**A future set is declared retired=null, trainable=false**, and the declaration
refuses any other combination for a live set. #225's bench half arrives that
way; its reserved training half is not an instrument at all.

**#231's positive control loses its material, and the fix is #225's to choose.**
The control is to recover CLM-0017's ~+20pp output-shape effect, measured on the
twenty JS/TS contracts this record just released. A bench containing them cannot
measure a tune; a bench without them cannot run the control. Three routes, none
settled here: recover the effect on newly generated material and compare the
size directionally; **un-release `bundle-ts`**, which is free *today* because
nothing has been trained on the released material yet and gets less free the
longer it waits; or choose a different known effect on unreleased material.
Recorded rather than resolved, because choosing is #225's job and this record
should not pre-empt it — but the "free today" clause is a real expiry, and the
first tune drawn from `bundle-ts` closes that door.
