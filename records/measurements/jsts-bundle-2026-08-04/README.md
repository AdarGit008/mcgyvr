# The JS/TS bundle-size sweep — the result

Issue: [#144](https://github.com/AdarGit008/mcgyvr/issues/144), under
[#19](https://github.com/AdarGit008/mcgyvr/issues/19).
Claim: [CLM-0012](../../claims/CLM-0012.json).
Instrument, design and threats to validity: [`tools/bundle/README.md`](../../../tools/bundle/README.md).

**No bundle rung separated from having no bundle at all.** The four-condition
ladder CLM-0004 used to take `qwen2.5-coder:3b` from 45% to 70% on a Python
task set was run unchanged in shape over a JS/TS task set, on the same model at
the same quant, and produced a flat curve. This is the "explicit finding that no
bundle effect was measurable" arm of #144's acceptance, not the claim arm.

## What ran

Two full sweeps, 80 cells each, 0 cells lost to dispatch errors.

| | run A | run B |
|---|---|---|
| Host | srv1 (GTX 1660 SUPER, 6 GB) | srv2 (RTX 3060, 12 GB) |
| Model | `qwen2.5-coder:3b` | `qwen2.5-coder:3b` |
| Quant | Q4_K_M (Ollama blob) | Q4_K_M (Ollama blob) |
| Serving | Ollama | Ollama |
| Protocol | OpenAI-compatible (`/v1/chat/completions`) | same |
| Rows | `results.jsonl` | `replication-srv2/results.jsonl` |
| Manifest | `run.json` | `replication-srv2/run.json` |

Sampler and cap are CLM-0004's, held fixed: `temperature=0`, `max_tokens=768`.
Conditions differ **only** in the system prompt; the user message is the shipped
`render_user_message(contract.worker_view())` in every cell.

## The result

Run A (srv1):

| Condition | Bundle bytes | pass@1 | after remediation | mean latency | mean prompt tok | mean completion tok |
|---|---:|:---:|:---:|---:|---:|---:|
| `c0` (no bundle) | 0 | **9/20 (45%)** | 10/20 | 2.98 s | 278 | 166.8 |
| `c1` | 369 | **11/20 (55%)** | 12/20 | 3.01 s | 337 | 167.3 |
| `c2` (shipped) | 1 877 | **10/20 (50%)** | 11/20 | 3.02 s | 664 | 169.4 |
| `c3` | 8 883 | **9/20 (45%)** | 12/20 | 3.56 s | 2 236 | 176.6 |

Run B (srv2) reproduced **every condition total exactly**: 9 / 11 / 10 / 9.
Completion tokens 168 / 165 / 167 / 175; latency 2.4 / 2.1 / 2.2 / 2.2 s.

### Why this is a null and not a small effect

Three independent reasons, and the third is the one that settles it.

**The deltas are inside the noise floor the design declared in advance.** That
floor is ±1 task (5 pp) at n=20. Against `c0`: `c1` is +2 tasks, `c2` is +1,
`c3` is 0. For comparison, CLM-0004's Python effect was **+5 tasks**.

**The deltas are built from flips in both directions**, which a real effect is
not. Paired against `c0`:

| | gains | losses | net | McNemar exact |
|---|---|---|---:|---:|
| `c1` | t04, t17 | — | +2 | p = 0.50 |
| `c2` | t05, t08, t17 | t01, t14 | +1 | p = 1.00 |
| `c3` | t05, t08 | t01, t19 | 0 | p = 1.00 |

**Two rigs put the noise floor on the record rather than assuming it.** Run B
was not a re-print of run A: 19 of 80 cells returned a different completion-token
count, and 4 of 80 flipped verdict — temperature 0 is not bit-reproducible across
different cards. Those 4 flips were **paired within their condition** (in `c1`,
t04 pass→fail against t08 fail→pass; in `c3`, t14 pass→fail against t17
fail→pass), so all four totals survived unchanged. So a re-roll moves ~4 cells
in 80, i.e. about ±1 task per condition — the declared floor, now measured. The
largest observed delta (`c1`, +2) is the size of that noise, not the size of an
effect.

### Why the Python effect did not transfer — the mechanism

This is the transferable half of the finding.

CLM-0004's gain came from a specific mechanism: output rules stop a small model
rambling, and completion tokens dominate wall time. In the Python run `c0`
averaged **403** completion tokens against ~**124** at `c2` — a 3.3× cut, which
is *why* it was ~2.5× faster.

Here the token column is flat: **166.8 / 167.3 / 169.4 / 176.6**, drifting
slightly *upward* with bundle size. Median 120.5 / 119.5 / 131.5 / 132.5.

The 3b was never rambling on this task set, so the mechanism the bundle works
through had nothing to act on. That predicts where a bundle *will* pay — workers
that over-produce without one — and it is a better guide than "which language",
because it is checkable before running a ladder: measure `c0`'s completion
tokens first.

Latency followed tokens, as it should: flat across `c0`–`c2`, and the +0.5 s at
`c3` is the 2 236-token prompt, not longer output.

### What did transfer

CLM-0004 named three failure modes **no** bundle rescued in Python. One
reproduced exactly:

- **t02** (mutating the caller's arrays through inner-array aliasing) failed
  under all four conditions, on first pass and after remediation, on both rigs.
  This is the same trap both Python models fell into under every condition.

The other two did not: **t19** (rejecting a boolean where a number is expected)
passed under `c0`–`c2`, where the Python 3b never honoured it, and **t17/t18**
(modern annotation form) largely passed. So "some failures are not a context
problem" transfers; the specific list of them does not.

### The positive control, and the one that could not be run

A null result is worth what its positive control is worth — the lesson #133
recorded when an all-zero measurement needed one. There are two here and only
one of them was available.

**What was controlled: the conditions demonstrably reach and change the model.**
Prompt tokens scale exactly as the ladder specifies (222 / 281 / 608 / 2 180 on
t01), and the *outputs* move with them — 17, 18 and 20 of 20 tasks produced a
different completion-token count under `c1`, `c2` and `c3` than under `c0` on
srv1. So the system prompt is landing and altering generation. It simply is not
altering acceptance. That rules out the failure mode a null is most often made
of: a condition that was never delivered.

**What could not be controlled: whether the Python effect reproduces on *this*
serving stack.** The clean control would be to re-run CLM-0004's own Python
ladder here; if it also came out flat, the honest conclusion would be "the
effect does not reproduce on Ollama/these rigs" rather than "it does not
transfer to JS/TS". That run is not possible in this repository today: the
Python **conditions** are vendored
(`records/evidence/local-ai-2026-08-02/data/context_exp/bundles/`) but the
Python **task set** is not — only its per-task results. Rebuilding 20 Python
tasks with acceptance would be authoring a new instrument, not re-running the
old one, and the comparison would be worth less than it looks. Filed rather than
papered over; until it is run, the language-versus-stack ambiguity is a live
alternative reading of this result and is named as such in CLM-0012.

## The honest limits

- **n=20, and 13 of the 20 tasks are condition-insensitive** — 6 pass under all
  four conditions and 7 fail under all four. Only 7 tasks are in the band where
  a bundle could show anything. A Python-sized effect (+5) would still have been
  visible inside that band, which is what makes this a null rather than a
  non-measurement; but the instrument has less headroom than the raw n suggests,
  and a *small* true effect (1–2 tasks) is not excluded by this run.
- **Two rigs are not two samples.** Runs A and B share model, quant, serving
  stack, prompts and sampler; they differ in hardware. They bound
  hardware/serving sensitivity and give an empirical noise floor. They do **not**
  bound sampling variance, which at `temperature=0` this design cannot sample.
- **One model.** `qwen2.5-coder:3b` at Q4_K_M. Nothing here speaks to other
  models, other quants, or larger workers — CLM-0004 already found the effect
  absent on a 30B at ceiling.
- **A serving-stack divergence from CLM-0004**, recorded rather than waved past:
  the Python run drove the Q4_K_M blob through bare `llama-server`; these runs
  drive the same blob through Ollama. Same underlying engine, different harness
  and prompt templating.
- **Type-annotation tasks are not type-checked** (TypeScript erases at runtime).
- **Every parse failure in both runs was `t04` hitting the 768-token cap** —
  `c2`/`c3` on srv1, `c1`/`c2`/`c3` on srv2 — scored as `incomplete-reply` and
  counted as failures, correctly, since a truncated file is refused before
  parsing. No other task was ever truncated, so the cap is not shaping the
  comparison.

## Reproducing

```
cp tools/bundle/worker.example.json tools/bundle/worker.local.json   # then edit
uv run --no-sync python tools/bundle/measure.py --out <dir>
```

`--summarise-only` reprints the table from rows already collected. `run.json`
pins the endpoint, protocol, model, four condition digests and twenty task
digests, so a resume into a directory measured against a different worker or a
different task set is refused rather than averaged.
