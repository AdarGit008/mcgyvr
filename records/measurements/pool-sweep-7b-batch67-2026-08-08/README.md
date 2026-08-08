# The pool's hard tail, 2026-08-08 — hard problems, and a cap they overrun

**What this is.** #212 asked whether the 80 problems admitted in batches 6–7
(`p202-recase-name` … `p281-tidy-halliday-mark`) are a harder set or a set
that is harder to state unambiguously, and named two steps: read the refusals
already on disk, then run the smaller model over the same 80. This directory
holds the second step — `qwen2.5-coder:7b` on srv1, TypeScript, greedy plus
two sampled draws at T=0.7, 240 rows — and records the verdict for both.

The disk read is reproducible with the instrument the lane added:

```
uv run --no-sync python tools/problems/tail.py \
    --sweep records/measurements/pool-sweep-14b-2026-08-07/srv2-ts \
    --baseline records/measurements/pool-sweep-2026-08-07/srv1-ts \
    --compare records/measurements/pool-sweep-7b-batch67-2026-08-08
```

## The answer: harder problems, at both model sizes

| | greedy | ≥1 pass in 3 | all rows | refused | median completion tokens |
|---|---:|---:|---:|---:|---:|
| 7B, the first 189 | 36/189 (19.0%) | 53/189 (28.0%) | 97/567 (17.1%) | 6 (1.1%) | 293 |
| **7B, the 80** | **8/80 (10.0%)** | **10/80 (12.5%)** | **22/240 (9.2%)** | **9 (3.8%)** | **468** |
| 14B, the first 189 | 71/189 (37.6%) | 94/189 (49.7%) | 216/567 (38.1%) | 18 (3.2%) | 350 |
| 14B, the 80 | 15/80 (18.8%) | 20/80 (25.0%) | 46/240 (19.2%) | 29 (12.1%) | 508 |

Read the two models as ratios of their own baselines and they agree to within
noise:

| the 80 ÷ the first 189 | 7B | 14B |
|---|---:|---:|
| greedy pass | 0.53 | 0.50 |
| ≥1 pass in 3 draws | 0.45 | 0.50 |
| all rows | 0.54 | 0.50 |
| refusal rate | 3.5× | 3.8× |

**The 80 are about half as passable for both workers, and refuse about
3.5× as often for both.** A deficit that reproduces at half the parameter
count is a property of the problems, not an artefact of the larger model's
output behaviour. The hypothesis that batches 6–7 provoke malformed replies
from the 14B specifically is refused: the 7B, which almost never breaks the
output contract on the first 189, breaks it three and a half times more often
on the same 80.

The two models also agree about *which* problems: of the 80, the 14B solved
20 and the 7B 10, with 9 in common and **59 solved by neither**.

## The refusals were never a parse problem

All 47 of the 14B's refusals are `incomplete-reply`, every one at exactly 768
completion tokens — the run's `max_output_tokens` — with the backend reporting
`truncated`. Re-reading the pinned candidates (ADR-0016 keeps every one), all
47 open at character 0 with a correct ` ```ts ` fence, carry exactly one fence
marker, and have no closing fence: **well-formed code, cut off mid-token.**
Zero have a prose preamble; zero have a stray second block.

That is what the code says too. `parse_reply` refuses on the stop reason
before it scans a single fence (`src/mcgyvr/worker/reply.py:224`), so on these
47 replies the parser never looked at the text. `incomplete-reply` is a report
about the output budget, not about the reply format.

**This corrects a reading in `pool-sweep-14b-2026-08-07/README.md`,** which
took the 6 → 47 rise as "a finding about the reply format … worth a look from
whatever revisits `worker/reply.py`". Records are append-only under REC-01, so
that file is left as written; the correction lives here. Across all 1,614 rows
in the three pool sweeps there are exactly **two** genuine reply-format events,
both `no-fenced-block`, both bare code with no fence at all:
`p073-outline-diff` sampled-1 (7B, first 189) and `p249-kettle-hand-names`
sampled-1 (7B, the 80). Two in 1,614 does not motivate work on `reply.py`.

## What fills the cap is length

The 80 are bigger problems by construction: **237 median words of task prose
against 143, and 62 median reference-solution lines against 39.** Bigger
problems draw longer replies — median completion tokens 468/508 against
293/350 — and a fixed 768-token cap catches longer replies more often.

Across the 269 problems the 14B swept, the 26 that refused at least once have
reference solutions running **98 lines at the median, against 43** for the 243
that never refused. 25 of those 26 are at or above 50 lines. Below 50 lines,
in either set, nothing truncates at all.

## The 768 is the rig's number, and the contracts ask for 1024

Every refusal rate on this page was measured at a cap **no pool contract
declares**. The chain:

| | |
|---|---|
| `tools/breadth/measure.py:110` | `MAX_OUTPUT_TOKENS = 768` — "the cap is the bundle sweep's, so *truncated* means the same thing in both instruments" |
| ← `tools/bundle/measure.py:148` | `768` — "that is what the Python run allowed" |
| ← `records/evidence/local-ai-2026-08-02/instrument/context_exp.py:39` | `MAX_TOKENS = 768` — a bare constant, no comment, no derivation |

The origin is CLM-0004's local-ai instrument, vendored under #118. Each hop
adopted the number to keep "truncated" comparable across instruments, which is
a reason to hold it *fixed* and not a reason it is *right*. Nobody sized it.

Meanwhile the pool contracts declare no `limits.max_output_tokens`, so the
loader fills the schema default of **1024** (`src/mcgyvr/contract.py:279`),
and the breadth rig never reads `contract.limits` at all — it sends its own
constant unconditionally. **A production dispatch of these same contracts gets
25% more room than any sweep here gave them.**

So the 3.2% / 12.1% refusal rates are properties of the instrument, not of the
problems, and they are not the rates production would see. **How many of the 47
would complete under 1024 cannot be read off this data**: a truncated reply's
true length is censored at the cap, so the distribution above 768 is unobserved.
Recovering it needs a re-run, not an analysis.

Nothing above depends on this. The pass-gap verdict is already stated on
complete replies only, and the 7B/14B ratio agreement holds at whatever cap
both were measured at, because both were measured at the same one. What it
does bound is the cap-sizing question — which is **#17**, and which this
record is evidence *for* rather than evidence about.

## What the cap does *not* explain

Almost none of the pass-rate gap.

| set | rows | passed | refused | pass rate, complete replies only |
|---|---:|---:|---:|---:|
| the first 189 | 567 | 216 (38.1%) | 18 (3.2%) | 39.3% |
| the 80 | 240 | 46 (19.2%) | 29 (12.1%) | 21.8% |

Discarding every truncated row moves the gap from 18.9pp to 17.5pp. The
issue's own upper bound says the same thing from the other side: crediting all
29 refusals as passes still leaves the 80 below the baseline. **Raising the cap
to the 1024 these contracts declare would recover some rows and would not make
these problems easy** — the ceiling is 31% against a 41% baseline even if every
refusal is credited as a pass.

## What size-standardising could not settle, and why it is reported anyway

Holding reference-solution size constant is the obvious way to ask whether the
80 are merely bigger. Standardised to the first 189's size distribution the gap
is +16.6pp against a crude +18.9pp — but the 95% bootstrap interval is
**[−5.1, +31.9]**, which spans zero.

| ref lines | first 189: tasks, pass, refused | the 80: tasks, pass, refused |
|---|---|---|
| 0–35 | 80, 65.4%, 0.4% | 5, 20.0%, 0.0% |
| 35–50 | 46, 28.3%, 0.0% | 19, 22.8%, 0.0% |
| 50–70 | 37, 9.9%, 3.6% | 23, 33.3%, 0.0% |
| 70+ | 26, 11.5%, 16.7% | 33, 7.1%, 29.3% |

The 0–35 stratum holds 5 of the 80 and carries 42% of the standardised weight,
and the residuals flip sign across the strata. **This estimate settles
nothing and the point value must not be quoted alone.** It is recorded because
the negative result is the reason the sweep was worth its hour: re-reading the
run could not substitute for running the second model, and a lane that had
stopped at +16.6pp would have published a difficulty claim its own data does
not support.

## Verdict against #212's two hypotheses

**Harder problems.** Not "harder to state". The deficit reproduces at half the
parameter count, in the same proportion, on byte-identical contracts.

Nothing here separates *why* they are harder — larger specs and longer required
solutions are the visible difference, and "a problem needing 62 lines is harder
than one needing 39" is not a finding about clarity either way. #213 asks the
clarity question directly and is unaffected by this result: a problem can be
genuinely hard *and* ambiguously stated, and the gate proves neither.

**No rebalancing.** As #212 stated up front and this confirms: a problem that
resists two model sizes is worth keeping in a training pool.

## Caveats

- One arm (TypeScript), two models, three draws, one host each. The 7B ran on
  srv1 and the 14B on srv2, so the model and the host are confounded — the
  comparison drawn is each model against *its own* baseline on *its own* host,
  which is why the ratio table exists and the absolute columns are not
  differenced across rows.
- The three sweeps are digest-identical on every task they share, and identical
  in prompt bundle (`001c23ec…`), cap (768), temperatures and draw count. This
  was checked rather than assumed.
- `run.json` here pins **499** task digests while serving 80: `tier_digests`
  records the tier as it stands, and the pool has grown since the earlier
  sweeps pinned 189 and 269. The 80 served are listed in `invocations[].tasks`,
  and their digests match the 14B run exactly. The effect is a stricter resume
  condition than needed, not a looser one.
- 9 replies refused, 0 draws lost to dispatch errors, so no cell is missing
  from a denominator.
