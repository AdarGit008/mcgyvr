# The Python bundle control — the result

Issue: [#167](https://github.com/AdarGit008/mcgyvr/issues/167), under
[#19](https://github.com/AdarGit008/mcgyvr/issues/19).
Instrument: [`tools/bundle/README.md`](../../../tools/bundle/README.md) and
[`records/evidence/local-ai-2026-08-02/instrument/`](../../evidence/local-ai-2026-08-02/instrument/README.md).
Tables recomputed by [`tools/bundle/python/compare.py`](../../../tools/bundle/python/compare.py).

**Neither of the two readings #167 was opened to separate is the right one.**
CLM-0012's null is not about the language and it is not about the serving stack.
It is about the harness: mcgyvr's own user message already ends with the output
rule that CLM-0004's bundle gets its benefit from, so on mcgyvr's path the bundle
arrives with nothing left to do. One sentence reproduces the whole effect.

## What ran

Three row sets were produced here; a fourth and fifth are quoted from existing
records. All on `qwen2.5-coder:3b` Q4_K_M, Ollama, OpenAI-compatible, at
`http://srv1:11434` — the endpoint CLM-0012's run A used.

| | task set | serving stack | harness | rows |
|---|---|---|---|---|
| **CLM-0004** | Python (20) | bare `llama-server` | local-ai | *(vendored)* `../../evidence/local-ai-2026-08-02/data/context_exp/results_q3b.jsonl` |
| **Arm B** | Python (20) | Ollama | local-ai, **unchanged** | `original-harness/results_q3b.jsonl` |
| **Arm A** | Python (20) | Ollama | mcgyvr rig | `results.jsonl`, `run.json`, `replies/` |
| **Probe** | Python (20) | Ollama | local-ai + one sentence | `output-rule-probe.jsonl` |
| **CLM-0012** | JS/TS (20) | Ollama | mcgyvr rig | *(existing)* `../jsts-bundle-2026-08-04/results.jsonl` |

Each row changes **one** thing from the row above it. That is the only reason a
difference between two of them can be attributed to anything.

160 cells across arms A and B, **0 lost to dispatch errors and 0 replies the
parser refused**. Sampler and cap are CLM-0004's throughout: `temperature=0`,
`max_tokens=768`, one remediation round. Arm A's reply bodies are kept in
`replies/` per ADR-0016.

**Arm B ran the vendored instrument with nothing edited.** `context_exp.py`
computes its bundle directory from `parents[2]`, so the directory shape it
expects was rebuilt around it in a temp tree rather than its path constants
being changed — see the instrument README.

## The result

**CLM-0004 — Python, `llama-server`, local-ai harness** *(vendored, for reference)*

| Condition | pass@1 | after remediation | mean latency | mean prompt tok | mean completion tok |
|---|:---:|:---:|---:|---:|---:|
| `c0` | **9/20 (45%)** | 9/20 | 4.69 s | 198 | 402.9 |
| `c1` | **12/20 (60%)** | 13/20 | 1.54 s | 272 | 94.6 |
| `c2` | **14/20 (70%)** | 14/20 | 1.89 s | 605 | 124.5 |
| `c3` | **12/20 (60%)** | 13/20 | 2.11 s | 2032 | 118.1 |

**Arm B — Python, Ollama, local-ai harness unchanged**

| Condition | pass@1 | after remediation | mean latency | mean prompt tok | mean completion tok |
|---|:---:|:---:|---:|---:|---:|
| `c0` | **7/20 (35%)** | 9/20 | 5.91 s | 198 | 427.4 |
| `c1` | **10/20 (50%)** | 10/20 | 2.19 s | 272 | 108.5 |
| `c2` | **11/20 (55%)** | 13/20 | 2.60 s | 605 | 144.8 |
| `c3` | **13/20 (65%)** | 13/20 | 3.00 s | 2032 | 142.1 |

**Arm A — Python, Ollama, mcgyvr rig**

| Condition | pass@1 | after remediation | mean latency | mean prompt tok | mean completion tok |
|---|:---:|:---:|---:|---:|---:|
| `c0` | **13/20 (65%)** | 14/20 | 2.35 s | 252 | 111.8 |
| `c1` | **14/20 (70%)** | 14/20 | 2.27 s | 326 | 96.3 |
| `c2` | **14/20 (70%)** | 14/20 | 2.65 s | 659 | 135.5 |
| `c3` | **14/20 (70%)** | 14/20 | 3.96 s | 2086 | 120.8 |

## Reading 2 is dead: the effect reproduces on the Ollama path

Arm B is CLM-0004's own instrument against the stack mcgyvr dispatches on, and
**the bundle works there**. Paired against `c0`: `c1` +3, `c2` +4, `c3` +6, with
completion tokens collapsing from 427.4 to 108.5–144.8 and latency from 5.91 s to
2.19–3.00 s — the same mechanism CLM-0004 described, at the same magnitude.

The replication is tighter than the totals show. **Arm B's never-passing set is
CLM-0004's, exactly**: `t02`, `t03`, `t06`, `t17`, `t18`, `t19` fail in all four
conditions on both stacks. The tasks that are hard are hard for reasons the
serving stack does not touch.

The two differ in where the curve peaks — CLM-0004 peaks at `c2` and gives 2
tasks back at `c3`; arm B climbs to `c3`. At n=20 with a ±1-task floor that is
one to two tasks of disagreement about the *shape* of a curve whose *existence*
both agree on, and the falloff between 2 KB and 8 KB is the part CLM-0004's own
design called approximate. It does not affect what #167 asked.

**So CLM-0004 applies to the Ollama path.** CAV-02's warning that a figure from
another backend describes different weights is a real rule that does not bite
here: the same blob through a different server reproduced the finding.

## Reading 1 is dead too: the Python arm through mcgyvr is flat

| | gains | losses | net | McNemar exact |
|---|---|---|---:|---:|
| `c1` | t04 | — | +1 | p = 1.00 |
| `c2` | t04 | — | +1 | p = 1.00 |
| `c3` | t04 | — | +1 | p = 1.00 |

One task, the same task, at every rung — inside the ±1-task floor, and the same
null CLM-0012 measured in JS/TS. **Same task set as arm B, same endpoint, same
model, same conditions.** The only thing that changed is the harness, and the
effect vanished.

So the bundle device is not language-specific. Whatever CLM-0012 measured, it was
not JavaScript.

## What it is: arm A's `c0` is already where the bundle was going

The numbers that carry this are the completion tokens, which CLM-0012 already
identified as the column the mechanism runs through — a bundle's gain came from
output rules stopping the small model rambling, and completion tokens dominate
both wall time and the chance of a well-formed file.

| | `c0` pass@1 | `c0` completion tok |
|---|:---:|---:|
| Arm B (local-ai user message) | 7/20 | 427.4 |
| Arm A (mcgyvr user message) | 13/20 | **111.8** |

Arm A's *baseline* is where arm B's *bundle* gets to (108.5–144.8). There was no
rambling left to stop. The reason is one line, and it is visible in the rendered
prompt: `render_user_message` ends every user message with

> OUTPUT: Reply with the complete new content of solution.py, as one fenced code
> block and nothing else. Not a diff, not an excerpt, not the changed lines — the
> whole file as it should exist after your change.

local-ai's `c0` contract has no such sentence. The bundle's `c1` rung — role +
output rules, 440 bytes — is the first place one appears.

### The positive control, because the port is a competing explanation

The mcgyvr contracts were written by hand for this port, and a rewrite can make
tasks easier without anyone meaning it to. `output-rule-probe.jsonl` removes the
rewrite from the question: **local-ai's twenty contracts, local-ai's harness,
`c0`, with that one sentence appended to the user message.** Nothing else moves.

| | pass@1 | mean completion tok |
|---|:---:|---:|
| Arm B `c0` | 7/20 | 427.4 |
| **Probe — `c0` + the output rule alone** | **11/20** | **121.5** |
| Arm B `c2` — the whole 1 972-byte bundle | 11/20 | 144.8 |
| Arm A `c0` — mcgyvr, rule built in | 13/20 | 111.8 |

**One sentence matches the entire bundle** on first-pass acceptance and beats it
on tokens. The bundle's other 1 500 bytes — coding standards, edge-case
checklist, pitfalls — bought nothing on this task set that the output rule had
not already bought.

The probe lands 2 tasks below arm A's `c0`. That gap is the port's residue and it
is not hidden: arm A's never-passing set differs from the other two by one swap in
each direction (`t17` becomes reliably passable, `t20` stops passing), which is
within the floor and runs both ways rather than uniformly easier. See the threats
below.

## What this settles

- **CLM-0012's scoping sentence is discharged**, and the dichotomy it was scoped
  against was false. "Language versus serving stack" had no third option written
  down; the third option is what happened.
- **CLM-0012's null is now explained rather than merely bounded.** It attributed
  the flat completion-token curve to the task set — "the 3b was not rambling on
  this task set". The cause is the harness: the same tasks ramble at 427.4 tokens
  through local-ai's prompt and 111.8 through mcgyvr's.
- **CLM-0004 stands, and applies to Ollama.** Its numbers are not withdrawn and
  its confidence note is not weakened by anything here.
- **`prompts/python.md`'s standing rests on a prompt assembly mcgyvr does not
  use.** The 45%→70% is real and was measured against a user message with no
  output rule in it. Through mcgyvr's own assembly the same bundle over the same
  tasks measures +1 task at p = 1.00. `BundleStanding.MEASURED_BENEFIT` says
  something true about a configuration this project does not ship.

## Threats to validity

Inherited and still true: n=20, one greedy seed, ±1 task is noise; acceptance
checks behaviour, not style; tasks and references were written by the same author.

New here:

- **Arm A's contracts are a port, not the originals.** mcgyvr renders its own
  user message from structured fields, so the contract text could not travel
  unchanged. `tests/test_python_arm.py` holds the acceptance scripts and
  reference solutions to the vendored originals by digest — those decide whether
  a cell passes — but the prose a worker reads is new. **The `c0`-versus-`c2`
  comparison within arm A is immune to this**, since both conditions use the
  same contracts; the cross-arm baseline comparison is not, which is why the
  probe exists.
- **`t17` is the clearest authorship effect.** Its mcgyvr `interface` field
  renders the fully annotated signature (`def total_length(strings: list[str])
  -> int`), which states the annotation form the acceptance script checks.
  CLM-0004's version gives it in prose. `t17` never passes in the other two arms
  and always passes in arm A. `t20` moves the other way.
- **The probe puts the rule in the user message; `c1` puts its rules in the
  system prompt.** Position is not controlled. What is controlled is that both
  are one short instruction about output shape, and both collapse the token count
  to the same place.
- **One model, one rig, one seed.** Arm B was not replicated on srv2 as CLM-0012's
  JS/TS run was. The finding it carries is a positive one — the effect reproduces —
  which is the direction where a single run is weaker evidence than a null would be.
- **`c3` disagrees between CLM-0004 and arm B** (12/20 versus 13/20, and the peak
  moves). Nothing here depends on the falloff's location.
