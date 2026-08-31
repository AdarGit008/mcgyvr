---
record: session/5
lane: 231
agent: adar
started: 2026-08-13
---

## Did

**Re-scored the check-2 control with the language rung dropped, and the result
kills my own explanation rather than the owner's.** No model cost — the
candidates were already on disk. `tools/bench/lintless.py`.

### The question

Check 2's ablation hurt the TypeScript arm more than the Python arm, and the
asymmetry is real: on the same 257 problems, 24 responded worse on ts against 10
on py, exact two-sided p = 0.024. Two explanations predicted it:

- **the owner's** — the ablated sentence declares output *shape*, and TypeScript
  needs more shape declared, so removing it costs more there;
- **mine** — an instrument artefact: the lint bar rejects 154 of 257 Python cells
  at baseline against TypeScript's 32, so most Python cells were already dead
  before the correctness test ran, and a lost cell cannot be lost twice.

`Gate.run` takes its adapters by injection, so `Gate(adapters=())` keeps scope,
secrets, structured data and acceptance and drops format/lint/structure/syntax.

### The result

| arm | n | stock | norule | delta | m | p |
|---|---:|---:|---:|---:|---:|---:|
| `bench-py` | 256 | 70 | 68 | **−0.8pp** | 30 | **0.856** |
| `bench-ts` | 255 | 61 | 23 | **−14.9pp** | 50 | **<0.001** |

**My explanation is dead.** Python was not power-limited: with lint removed it
has 70 live cells rather than 23, and **30 discordant pairs** — cells moved in
both directions, they just did not move *net*. Given room, it did nothing with
it. Meanwhile the TypeScript effect nearly doubles, from −8.6pp under the full
bar to **−14.9pp on correctness alone**.

So on this material the output-shape rule is worth **nothing for Python
correctness** and **about fifteen points for TypeScript correctness**. Its entire
Python effect under the full bar was tidiness: the ablation makes Python code
messier, not wronger.

### The correction I owe my own pushback

I argued the owner's premise failed at step one, because Python's baseline was
*lower* than TypeScript's (23/257 against 33/257) and a better-trained language
should score higher. **That comparison was made on a rate the lint asymmetry had
corrupted.** On correctness alone the ranking reverses: **py 70/256 (27.3%) vs ts
61/255 (23.9%)**. Python is ahead. The premise stands and my objection to it
does not.

### The instrument finding, which is larger than the argument

**The bar reverses which arm looks better.**

| | `bench-py` | `bench-ts` |
|---|---:|---:|
| full bar | 8.9% | 12.8% |
| correctness only | **27.3%** | **23.9%** |

ADR-0025 chose eslint `recommended` to mirror ruff's moderate select *because
every arm on this bench is a paired comparison and a harsher bar on one side
reads as a language effect*. Matched in intent, the two bars are not matched in
**bite** — 154 rejections against 32 — and that difference sits inside every
paired ts/py contrast the bench will publish. It is exactly the failure ADR-0025
was written to prevent, one level down from where it was looked for.

### The re-score validates against an independent measurement

The superseded acceptance-only null (**different dispatches**, 2026-08-12) read
`bench-py` **70/257** and `bench-ts` **60–61/257`. Re-scoring the 2026-08-13 run
A through a correctness-only gate reads **70/256** and **61/255** — the same
figures, from different runs, down a different code path. That is a real check on
the tool rather than an assertion that it works.

### What this does not establish

Two facts are now in hand — the model is better at Python here, and Python is
insensitive to this ablation — and their *correlation* is not a cause. "Less
training data for TypeScript" and "TypeScript needs more shape declared" predict
the same pair. Separating them needs the same ablation on a larger model: a
training-depth story says the gap persists, a language-surface story says it
narrows as capability rises. Check 5 already re-runs the battery on a second
tier, so this rides along at no extra cost.

## Left open

- **Check 2's pooled figure mixes two different phenomena** and should probably
  not be quoted pooled again: −5.8pp is the average of "nothing" and "a lot".
- **The bar asymmetry wants an issue.** It is a live confound in every paired
  contrast, and neither ADR-0025 nor #113 currently states it.
- **A language claim needs the second tier** to become a cause rather than a
  correlation.

next: get check 2's verdict from the owner — the pooled figure now looks like the
wrong summary of it — and file the bar-asymmetry confound before any arm runs
paired.
