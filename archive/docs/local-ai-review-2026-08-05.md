# What local-ai knows — an evidence audit

**Issue:** #172 · **Lane:** lane/172 · **Date:** 2026-08-05
**Reviewed:** `local-ai@815df9b`, three surfaces — test results, research, code.
**Filter applied:** an item is reported only if a reader who does not trust the
author can re-derive it. Everything below carries either a recomputation done in
this repository or a file-and-line a reader can open. Items that could not meet
that bar are in [Rejected](#rejected), with the reason.

Nothing in this document is a copy of local-ai. It is what local-ai *learned*,
and where that lands here.

---

## The headline: the run that was supposed to be clean is mostly not

**#172 asked for a binary verdict on `data/mcgyvr_evidence/2026-08-03-clean`.
The verdict is: one of its five measurements is sound. Three are void. One is
contaminated but still readable.**

The directory's own `REPORT.md` does not say this. The commit that landed it —
`8e24291`, *"run 3: the gate ran, and the acceptance commands defeated
themselves"* — does. **`REPORT.md` was committed already stale and was never
corrected**, so anyone reading the evidence directory in file order reaches
conclusions its author had already withdrawn in the commit message.

| Measurement | `REPORT.md` says | Actual status |
|---|---|---|
| ghostcall FP | 0/78, floor is zero | **Sound.** Survived all three runs. |
| tokens | median **−26.8%**, "use the negative tail (−89.0%)" | **Sound but the report's numbers and its recommendation are wrong** — see below. |
| breadth | 0/60, "correctness assertions are beyond local models" | **Void.** Harness artifact. |
| scope | 0/16, "same root cause as breadth" | **Void.** Same artifact. |
| repair | 0/9, "ruff can't fix logic errors" | **Contaminated** — 4 of 9 rows are the artifact. Conclusion survives on the other 4. |

**The artifact:** the acceptance commands were `python -c "from target import f"`,
which writes `__pycache__/`. The gate's `commands:workspace-stable` check saw a
new file and failed the task *before its assertions were judged*. Every task
failed for a reason that has nothing to do with the model. The author's own
words: *"a floor exactly as fake as the ceiling the missing acceptance commands
produced in runs 1 and 2, and from the same root: the harness, not the rung."*

**Verified here, not taken on trust.** `raw/repair.jsonl` carries the failure
classes and they are 4× `commands:workspace-stable`, 1× `compliance:type-form`,
4× real `cmd:` assertion failures. So repair's real denominator is 4, not 9 —
and ruff `--fix` converted 0 of those 4.

**Blast radius here: zero.** No claim in this repository depends on any of the
void measurements. `records/` cites only the **2026-08-02** run, and only its
`premise` subcommand — CLM-0005's re-evaluation of stored HumanEval+ completions
through `ast.parse` and EvalPlus. That path touches neither the gate nor
acceptance commands, which is the same reason ghostcall survived. CLM-0004 rests
on the vendored context experiment, also untouched. This was checked rather than
assumed.

**A rig defect worth naming separately:** `raw/breadth.jsonl` and
`raw/scope.jsonl` record only outcome booleans — their keys are
`any_passed` / `first_pass_accepted` / `candidate_produced`, with **no
failure-reason field at all**. The zeros are therefore uninterpretable from the
evidence files alone; the cause survives only in a commit message. An evidence
row that records *that* something failed but not *why* cannot support the
conclusion drawn from it, and that is exactly how `REPORT.md` came to blame the
models.

### The tokens result, recomputed

This one is worth having, and the report states it backwards. Recomputed here
from `raw/tokens.jsonl` (20 rows: 1 errored, 19 usable):

| Set | n | min | median | mean | max | rows that **under**-estimate |
|---|---:|---:|---:|---:|---:|---:|
| all usable | 19 | +0.0% | +9.1% | +32.6% | +448.7% | **0** |
| with chars/token guard | 18 | +0.0% | +8.8% | +9.5% | +22.5% | **0** |

Positive = over-estimate. **Not one row under-estimated.** The report's table of
negative numbers is the *pre-correction* view, computed before a measured
**348-token chat-template floor** was subtracted from every count; the corrected
figures are in the directory's own `claims/tokens.json`, which the report
contradicts.

The +448.7% outlier is a single bad row — `src:acceptance.py`, 37,352 chars
reported as 1,702 tokens, i.e. **21.95 chars/token**, which no real tokenizer
produces. `--context-window 8192` was declared while the model served 2048, so
the count was silently capped. That one row moves the mean from +9.5% to +32.6%.

---

## What we can take

### 1. A token estimate has an additive floor that a multiplicative reserve cannot cover

**Take.** The backend charges a non-zero constant no text-based estimator can
see — measured at **348 tokens** by probing with a minimal prompt. Subtracting
it flipped the sign of an entire error band. In local-ai's run 2 the floor plus
one truncated row *"between them accounted for its entire apparent error band."*

**Apply.** `gate/preflight.py:57` charges `ESTIMATE_RESERVE = 0.32`,
**purely multiplicatively**, and `worker/prompt.py:57` already states the gap in
its own words: CLM-0011's band *"was measured over prompt content, never over a
finished prompt, because until now no finished prompt existed."* A finished
prompt exists now. A multiplicative reserve on a 500-token prompt sets aside 160
tokens against an overhead measured at ~348 — it under-covers small prompts and
over-covers large ones. Independent corroboration that the term is real:
local-ai's own cap author carries `_PROMPT_OVERHEAD_TOKENS = 600` as a separate
additive constant (`token_cap_setter.py:46`).

**Benefit.** The one failure `check_prompt_fits` exists to prevent — shipping a
prompt the backend then rejects — is the one the current shape is weakest
against, precisely where prompts are small and the reserve is smallest. **New
issue.** Not a re-measurement of CLM-0011; an additive term it never covered.

### 2. An operator-declared context window is not just missing — it is dangerous

**Take.** `--context-window 8192` against a model serving 2048 produced a
silently truncated count that *passed the ceiling test* and became a +449%
outlier. The replacement is a self-validating guard: **chars-per-token**, since
no real tokenizer averages past ~8 on source. It needs no operator declaration
and it validates itself.

**Apply.** **#158** — "No rung declares its context window, so the decomposer's
ceiling is a chosen number." This is evidence that the obvious fix (make the
operator declare it) imports a new failure mode: a *wrong* declaration is worse
than an absent one, because it is trusted. A derived-and-checked value is the
better shape.

**Benefit.** #158 gets a design constraint from someone else's outage rather
than from ours, and a cheap invariant worth asserting wherever a token count
arrives from a backend.

### 3. A refusal that is well-formed defeats a syntax gate *and* silently stops escalation

**Take.** local-ai's models emitted `{"status":"blocked"}` and it was accepted as
valid code — it passes `py_compile`. Because escalation fires on *failure*, a
refusal read as success meant the cascade never climbed. Catching it took one
regex; the measured result was **3/8 → 7/8 escalation levels passing**
(`ed26b70`). *(Their figure, from the commit message — not independently
re-run here.)*

**Apply. mcgyvr is exposed to the same shape, demonstrated, not inferred.** Run
against this repo's own parser:

| Reply | `parse_reply` returns |
|---|---|
| ` ```python` / `# I cannot complete this task.` | **`ParsedFile`** |
| ` ``` ` / `{"status": "blocked", "reason": "unsafe"}` | **`ParsedFile`** |
| ` ```python` / `def f(x): raise NotImplementedError` | **`ParsedFile`** |
| `I am sorry, I cannot help with that.` (unfenced) | `ReplyError` ✓ |

`worker/reply.py` is strict about *ambiguity* — one fenced block or nothing —
and that correctly catches the unfenced refusal. It has no view on a refusal
that arrives **inside** the fence. The dict literal is valid Python, so syntax
and lint both pass. What stops it here is an acceptance command, which is
exactly what **#132** exists to count the absence of and **#146** to supply.

**Benefit.** This sharpens #132 from an evidence-quality question into a
correctness one: where no runnable check is declared, a refusal is not merely
unverified, it is *accepted*, and the escalation ladder never fires. **New
issue**, cross-referenced to #132/#146 and #41.

### 4. An adversarial verdict-parsing matrix, learned in production

**Take.** `tests/test_verifier.py` encodes the cases a verdict parser must fail
closed on, including one labelled as a real bug (*"The F3 bug: rejection phrasing
must not parse as approval"*):

| Reply | Must not parse as |
|---|---|
| `Cannot approve - breaks the contract.\nESCALATE` | APPROVE |
| `I would not APPROVE this.\nREMEDIATE: fix X` | APPROVE |
| `APPROVED with reservations` | APPROVE (exact word only) |
| `Overall solid work.\nAPPROVE` | APPROVE (first line only) |
| `APPROVE_WITH_NOTES` | APPROVE (no prefix shadowing) |
| `APPROVE: contract met` | *must still parse* — punctuation is not disqualifying |
| unparseable / empty | anything — returns None, never fails open |

The extractable rule, which is what transfers: **the verdict token is the first
word of the first line, matched as an exact word; everything else is None.**

**Apply.** **#41** — "Verifier outcomes and strict verdict parsing" — open and
unbuilt. Also #42: local-ai's companion rule is *"the verifier judges everything
or nothing — never a truncation"*, enforced by refusing oversize input **before
any call**.

**Benefit.** #41 can be built with the adversarial matrix already known instead
of discovering F3 the way local-ai did. Test cases are the sanctioned transfer
shape — this is the same route the four ghostcall false positives took on
2026-08-02.

### 5. A class of failure that neither context nor model size ever fixed

**Take — and this one is re-derivable entirely inside this repository**, from
evidence #118 already vendored. Recomputed from
`records/evidence/local-ai-2026-08-02/data/context_exp/`:

- On qwen2.5-coder:3b, six tasks (t02, t03, t06, t17, t18, t19) passed in **none**
  of the four context conditions.
- On qwen3-coder-30b-a3b — at ceiling everywhere else, 18–19/20 per condition —
  exactly **one** task never passed: **t02**.
- t02 therefore failed **8/8 cells**: both models, every condition, 0.4 KB
  through 8 KB of bundle.

The failures, from the rows: `input was mutated: [[1, 3], [2, 6]] != [[2, 6],
[1, 3]]` (t02), `annotation is typing.List[str], want list[str]` (t17),
`safe_divide(True, 2) should raise TypeError, got 0.5` (t19). Every one is
mechanically checkable — mutation of an argument, a pinned annotation form,
`bool` accepted where a number is required. None is a judgment call.

**Apply.** **#110 (E12 — semantic checks in the gate)**, and it says something
sharper than "add semantic checks": **escalation cannot fix this class.** The
30B failed t02 in all four conditions. Spending a higher rung on it buys
nothing.

**Benefit.** A named class of failure where a deterministic check replaces the
*entire* escalation ladder rather than one rung of it — the strongest form of
the #81 argument, and it does not depend on local-ai staying reachable. It also
feeds **#162**: a routing matrix needs a cell for "no rung fixes this", which a
linear ladder cannot express.

### 6. Capability is task-shape-dependent, not scalar — the argument #162 needs

**Take.** local-ai's escalation levels are a *task-shape taxonomy* — modify-function
(L5), multi-file import (L6), binary search (L7), recursive flatten with error
handling (L8) — and the recorded result is **"3/8 reliable, recursion kills
1.5B"**, with 1.5B refusals escalating to a 3B that handles the recursive tasks.
*(Their figures, unverified here — but the taxonomy is the transferable part,
and it is a structure, not a number.)*

**Apply.** **#162** — "Retire the ladder: design the routing matrix." #162
already establishes the *cost* axis is not orderable (its own three-rung climb
had the declared-cheapest rung 8× slower **and** weaker). This adds the
*capability* axis: a rung's competence varies by task shape, so "measurably
better than the one below" is not a property a single ordering can carry.

**Benefit.** #162's matrix gets a second named axis with evidence behind it,
from a system that hit the wall in production.

### 7. The pattern behind all of it — the finding I would keep if I could keep one

Three independent defects in local-ai, all the same shape:

1. `acceptance.commands` was read nested, task sets wrote it flat → `from_dict`
   ignored the unknown key, defaulted to `[]`, and **no run ever executed a
   correctness test.** "Passed" meant lint-clean. Runs 1 and 2 were reinterpreted,
   not refined.
2. `__pycache__` tripped `workspace-stable` before assertions were judged →
   every task failed for a reason unrelated to the model. Run 3's breadth and
   scope.
3. A structured refusal parsed as valid code → the gate passed it and escalation
   never fired.

Each produced a *confident, specific, wrong* number that looked exactly like a
result. Each was invisible until someone checked the mechanism instead of the
number. None was caught by a test.

**Apply.** This is the argument for **#113/#111**'s harness carrying a
**positive control** — the same gap #167 already names for the JS/TS bundle
null. A measurement that cannot fail visibly has not been shown to measure
anything. local-ai's own guard is the transferable form: after `4bafb19`,
`_verify()` **round-trips every generated contract through `from_dict` and
refuses to write a set whose acceptance commands come back empty** — the
producer asserts the consumer actually received what it emitted.

**Benefit.** A cheap, general invariant for our own rigs, and three worked
examples for why #167's missing positive control is not a formality. **Comment
on #167 and #113**, no new issue.

---

## Rejected

Listed so the discipline is auditable.

| Item | Why |
|---|---|
| breadth 0/60 and scope 0/16 as capability findings | Harness artifact. `REPORT.md`'s "beyond local models" reading is withdrawn in its own commit. |
| `REPORT.md`'s token band (−89% to +449%, median −26.8%) and "use the negative tail" | Pre-correction. Recomputation gives 0 under-estimating rows; there is no negative tail. |
| "Local models ≤7B have a coverage ceiling of 0.0" | Rests entirely on the void measurements. |
| Model-landscape and MoE research (`subagent_*.md`, `moe_scale_sweet_spot`, `external_landscape_synthesis`) | local-ai's layer per the standing boundary — model choice and serving stay there. |
| Hardware research (`hardware_baseline_and_ram_ceiling_2026-08-04`, srv1 XMP at 3200 MT/s, the 80B CUDA illegal-memory-access on 12 GB) | Same boundary. Host facts, and the last is a llama.cpp bug. |
| `REVIEW_ARCHITECTURE_2026-07-28.md` (1,240 lines), `REVIEW_2026-07-26.md` | Architecture opinion. No runs behind them. |
| gpt-oss:20b "3× retry recovers 3 tasks (70→80%)" | Real direction, but n=3 tasks on one thinking model, no linked data file. Cite as anecdote in #152 or not at all — **it does not settle #152**. |
| `failure_categories.py`'s 27-category vocabulary | Standing reject (#123: "there is no failure_category in this codebase and none is added"). |
| `context_prune.py` | Standing reject (#115, ADR-0001 boundary 8). Not re-litigated. |
| `deps[].level` | Deferred twice (#115/#116) pending the deps-per-contract distribution, which run 3 **again** could not produce — the decomposer needs credentials that were unavailable. |
| local-ai's `CHARS_PER_TOKEN = 3` as a replacement for our chars/4 | Not adoptable as a number, but see the note below — it corroborates something. |

**One near-miss worth recording.** local-ai divides by 3 where we divide by 4 and
then reserve 32%. Those are the same margin: 4/3 = 1.33 against our 1.32. Two
independent derivations — theirs from "real ratios run 3.2–3.8 chars/token",
ours from DeepSeek-Coder-V2's measured p05 — landed a point apart. That is
corroboration of the *magnitude*, and it changes nothing, which is why it is
here and not above.

**And one thing that did not conflict, though it looks like it should.**
local-ai measured 0/18 rows under-estimating on Qwen; CLM-0011 measured Qwen
under-counting **51.4%** of 2,387 units. These are different objects — a finished
prompt with the template floor subtracted, versus raw content units — with n=18
against n=2,387, on a corpus with no dense JS/TS literals (CLM-0011's extreme
unit is −73.3% on exactly that). **local-ai's result does not overturn CLM-0011
and must not be cited as if it did.** What it contributes is finding 1, which
CLM-0011 never covered.

---

## Summary

| # | Finding | Lands in | Benefit |
|---|---|---|---|
| 1 | Additive template floor (348 tok) uncovered by a multiplicative reserve | **new issue** | Closes the gap `prompt.py` already names, where the check is weakest |
| 2 | Declared context windows are trusted and can be wrong; derive and self-check | **#158** | A design constraint from someone else's outage |
| 3 | Fenced refusals parse as file content; escalation never fires | **new issue** → #132/#146/#41 | Turns an evidence gap into a demonstrated correctness gap |
| 4 | Adversarial verdict-parsing matrix + the first-word rule | **#41** | Build it right the first time |
| 5 | A failure class no context and no model size fixed (t02, 8/8) | **#110**, #81, #162 | Deterministic check replaces the whole ladder, re-derivable in-repo |
| 6 | Capability is task-shape-dependent — the second matrix axis | **#162** | Evidence for the axis the ladder cannot express |
| 7 | Three harness defects of one shape; the round-trip guard | comment on **#167/#113** | Why a positive control is not a formality |

Two new issues, four existing issues fed, two comments. Findings 1, 3 and 5 are
verified inside this repository; 2 and 7 rest on local-ai's commit record with
the mechanism stated; 6 transfers as a structure, not a number.

**Adoption still runs through ADR-0004.** Nothing here enters
`data/capability-table.json` or a claim by citation. This document is the input
to those decisions, not the decision.
