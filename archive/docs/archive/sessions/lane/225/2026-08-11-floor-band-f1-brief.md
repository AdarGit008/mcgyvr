# Floor band `f1` — generation brief (lane/225, Phase 4 tranche 4)

**Declared before a single problem is authored and before any sweep, per
#225's amendment point 3.** If this document postdates the calibration it is
worthless: a band whose target is written after its rate is known is not a
band, it is a rationalisation.

Design of record: `docs/bench-design-2026-08-10.md`. Shape evidence:
`docs/bench-shape-prior-art-2026-08-11.md`. Governing records: **ADR-0021**
(the floor unit is the obligation; separation is explicitly *not* required),
**ADR-0023** (difficulty is behaviour count), **ADR-0024** (srv2 measures).

## What this band is for, and why the last two missed

Two bands were aimed at 30–50% and undershot: g0 read 1/23 ts and 5/23 py on
the 3B. Both re-aims steered **reference size and assertion count**. That is
the wrong dial. The evidence:

| | MBPP+ | bench today |
|---|---:|---:|
| assertions per problem (median) | 3 | 13 ts / 11 py |
| problems with ≥1 error path | 0.3% | 95% |
| spec prose words (median) | 15 | 146 |
| reference lines (median) | 3 | 27 ts / 19 py |

The same 3B reads 70.6% on the left and ~4% on the right. And EvalPlus tests
**the same 378 problems** with 35× the assertions for a cost of **10pp** —
because those extra assertions re-test the *same one or two behaviours*. Our
thirteen test thirteen *different* behaviours under all-or-nothing acceptance.

**So the dial is the count of independently specified behaviours that must all
be simultaneously correct.** Both prior bands cut lines and assert counts and
left the multi-rule, multi-rejection spec shape untouched, which is exactly why
neither moved.

## The target

**The aim is 30–50% on `qwen2.5-coder:1.5b`** — the floor unit (ADR-0021), not
the 3B, not a pooled figure, not an average. Upstream is accepted wherever it
lands; a larger model reading high or ceilinged here is a result, not a defect.
Separation between models is explicitly not required.

| dial | MBPP-shaped (1.5B reads ~57%) | bench today (3B ~4%) | **`f1` target** |
|---|---:|---:|---:|
| independently specified behaviours | 1–2 | 8–13 | **2–4** |
| enumerated error paths | ~0 | 5–6 | **≤ 1** |
| spec prose words | 15 | 146 | **40–70** |
| ts reference lines | 3 | 27 | **8–14** |
| py reference lines | 3 | 19 | **6–11** |
| assert statements per arm | 3 | 11–13 | **5–8** |

`f1` sits deliberately *above* MBPP shape and far below the bench's. It must
not become MBPP: a set the floor unit reads at ~57% with contamination in it is
not an instrument.

### What "one behaviour" means here

A behaviour is one thing the prose obliges the solution to do that could be
independently wrong. "Return the items in input order" is one. "Reject a
repeated key" is one. "Ignore a semicolon inside quotes" is one. Counting is
done from the **prose**, not the assertions: several assertions may probe one
behaviour, and that is encouraged — it is what makes a checker sensitive
without making the problem harder (the EvalPlus result above is exactly this).

The 5-assert gate floor (`MIN_ASSERTIONS`) is **not** in tension with a 2–4
behaviour budget: it counts assertions, not behaviours, and 2–3 assertions per
behaviour clears it comfortably.

## Composition of the batch

Ids **b228–b243** (16 problems). Continues the sequence; b155, b176–b180 and
b186 stay retired and are never reused.

- **task_type:** 12 `function_implementation`, 4 `bug_fix`. Mix is controlled
  *within* the band because bug_fix passes at roughly twice fn_impl's rate, so
  an uncontrolled mix moves the band's rate without moving its difficulty.
- **file_shape:** ≥ 25% `multi_symbol` (#126's declared multi-symbol subset
  obligation, in both languages).
- **shape:** spread across `string`, `numeric`, `iteration`, `data_structure`.
  No `error_handling` primary — a band capped at one error path cannot honestly
  carry it.
- **steering_band:** `f1` verbatim in every `meta.json`. Fresh name on purpose:
  `f1` is not `g0` re-aimed, and #224 must not read any band as a stratum.
- **scaffold:** none. ADR-0022 — the bench is measured stock, and a scaffold is
  a lever, not a difficulty knob.

## Non-negotiables carried from prior tranches

1. Anti-triviality still binds. The reference with only the target symbol
   degraded — a no-op stub and an echo-first-argument stub, helpers intact —
   must **fail** the checker in both arms. A light checker makes this the
   easiest constraint to break: assert real behaviour, never "returns
   something".
2. **A checker tests what the contract states and no more** (ADR-0023). The py
   rejection helper catches `Exception`, matching ts's `assert.throws(fn,
   Error, ...)`. Never re-narrow it to `ValueError` — that defect is what made
   every ts-vs-py contrast unreadable, and two tests now pin the rule.
3. Both arms are the same problem twice: same prose, same behaviour count, same
   assertion targets, differing only in the idiomatic symbol name and the
   language rendering.
4. Front-door blocklist (542 names) and the near-duplicate Jaccard screen
   (≥ 0.55 rejects) apply against the pool's 499, the retired sets, all 220
   admitted bench problems and every sibling candidate. Write prose specific to
   the problem's own domain; never reuse a paragraph across two problems.
5. Declaration forms: ts `export function <name>(` exactly once, erasable
   TypeScript only; py a plain module-level `def`.

## The checkpoint this batch exists for

16 problems split roughly in half by the pre-declared salted hash, so ~8 reach
the bench half and are sweepable. That is a **coarse** read by design — enough
to tell 5% from 40%, not enough to state a rate.

**Stop conditions, declared now:**

- If the 1.5B reads **inside 30–50%** on the f1 bench half: the shape is right,
  and the remaining tranches toward ~400 are authored to this brief unchanged.
- If it reads **below 30%**: the behaviour budget comes down again (toward 2,
  and toward zero error paths) before any volume is bought. It does **not**
  become a third size re-aim.
- If it reads **above 50%**: the budget goes up toward 4–5 behaviours. Too easy
  is the cheaper miss and it has not happened yet.

Either miss is answered with another ~16, not with 100. Two undershoots were
each paid for at tranche scale; this one is deliberately cheap.

## Measurement

`qwen2.5-coder:1.5b` on **srv2** (ADR-0024: the measurement rig, one GPU, one
ollama build — the manifest now records the build and refuses a resume across
one). Greedy, cap 2048 — pinned non-censoring, since 768 censors d3-class work
and every bench probe has used 2048. Fresh `--out` directory. Both arms.
