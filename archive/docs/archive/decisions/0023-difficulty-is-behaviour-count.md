# ADR-0023 — difficulty is behaviour count, and it is calibrated from wisdom

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none
Date: 2026-08-11

## Context

#225 aimed a steering band at 30–50% for the 3B twice and undershot both times:
1/23 ts and 5/23 py on the second attempt. Both re-aims steered the same two
dials — reference size and assertion count — and both were derived from the
retired rulers' rate–size mapping, which does not transfer. The floor probe's
d2 tier read 41.7%; bench material at d2-class size reads 4.3%.

Two tranches were spent discovering that by authoring. The question this record
settles is what the third tranche should steer instead.

## The measurement that decides this record

All four numbers below are re-derivable from material already on disk. MBPP+ is
read here only as a **shape reference** — no problem is adopted from it, and its
378 ids remain on the campaign blocklist (ADR-0020, `tools/instruments.json`).

The 3B reads **70.6% base / 60.6% plus** on MBPP+ and roughly **4%** on this
bench. Those two sets differ as follows:

| | MBPP+ | bench-ts | bench-py |
|---|---:|---:|---:|
| assertions per problem (median) | 3 | 13 | 11 |
| error-path assertions (median) | 0 | 5 | 6 |
| problems with ≥ 1 error path | 1 of 378 (0.3%) | 104 of 109 (95%) | 103 of 109 (94%) |
| spec prose words (median) | 15 | 146 | 146 |
| reference solution lines (median) | 3 | 27 | 19 |

The decisive figure is not in that table. EvalPlus's "plus" arm tests the *same
378 problems* against a median of **105 generated inputs** instead of 3 — a
35-fold increase in assertions — and it costs the 3B **10pp** (70.6 → 60.6).

So assertion *count* is not what is expensive. Those 105 inputs re-test the
same one or two behaviours. Our 13 assertions test thirteen **different
specified behaviours**, five of them error paths, and acceptance is
all-or-nothing: a model that gets twelve right scores zero. Four times the
assertions over *different* behaviours costs ~57pp; thirty-five times the
assertions over the *same* behaviours costs 10pp.

That is why both re-aims failed. They cut lines and they cut assertion counts,
and they left the multi-rule, multi-error-path spec shape untouched — the g0
band still carried a 7–11 assertion floor over a spec that named several rules
and several rejections. The dial they turned was not the one that binds.

## Decision

> **DECIDED (2026-08-11, owner).**
>
> 1. **Difficulty is the count of independently specified behaviours that must
>    all be simultaneously correct.** Reference size and assertion count are
>    noisy proxies for it and are not steered directly.
> 2. **The floor band is authored to a behaviour budget:** 2–4 specified
>    behaviours, at most one error path. Size is an output of that, not an
>    input.
> 3. **Calibration reads prior art for shape statistics only.** Behaviours per
>    problem, error cases per problem, spec length, tests per problem, paired
>    with the rates small models achieved. **No public dataset supplies a
>    problem** — the adopt-nothing sourcing verdict and the contamination
>    blocklist both stand, and a public set cannot be made non-public by
>    construction.
> 4. **A checker tests what the contract states and no more.** A checker that
>    pins behaviour the spec never names is a defect, not strictness.

## Why (4) is in this record

It was found while deriving the table above. 104 bench and 106 reserve Python
checkers accepted only `ValueError`, while their TypeScript twins use
`assert.throws(fn, Error, ...)`, which any `Error` subclass satisfies. The
contracts say "reject ... with an error" and never name a type. So the
idiomatic Python answer to "reject a non-string argument" — a `TypeError` —
failed the py arm and passed the ts one, on problems that are supposed to be
the same problem twice.

That is a behaviour the bench was scoring and no contract had specified, which
makes it the same failure as (1) in miniature: difficulty arriving from
somewhere other than the stated task. Every ts-vs-py contrast the campaign has
drawn sat on top of it, #226's most of all.

## Consequences

- **The 1.5B is located before the band is authored.** ADR-0021 makes it the
  floor unit and it has never been swept; a behaviour budget aimed at an
  unmeasured model is the third blind re-aim.
- **`admit.py`'s 5-assertion floor may conflict with a 2–4 behaviour budget**
  and is revisited when the brief lands, not before.
- **The prior-art read produces a table, not a task set.** Its output
  parameterises the generator brief and cites its sources.
- **The checker fix is retrospective at zero model cost.**
  `tools/bench/regrade.py` re-scores completions already on disk against the
  corrected checkers, so every py rate the project has quoted is recoverable
  without a token. Original `results.jsonl` files are never rewritten.
