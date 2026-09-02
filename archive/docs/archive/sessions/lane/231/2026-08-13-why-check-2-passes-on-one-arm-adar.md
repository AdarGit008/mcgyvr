---
record: session/7
lane: 231
agent: adar
started: 2026-08-13
---

## Did

**Check 2's verdict, owner-approved: PASSES for `bench-ts`, NOT ESTABLISHED for
`bench-py`, and the criterion is amended as a correction to its author's design
rather than to the result.**

The pre-registration (`f73f47bf`) is **not edited**. It is a pre-registration;
amending one after its results are known is the failure it exists to prevent, and
REC-01 makes it append-only besides. This record carries the verdict; that
document stands exactly as declared.

### What was pre-registered, and what happened

Recovery required **direction** and a **named signature**. Direction was
recovered decisively. The signature — completion tokens rising ~3.5×, from
CLM-0017 — did not appear at all: 1.03× and 1.02×.

**The criterion was wrong, and knowably so before dispatch.** The rule declares
output *shape*, and shape expresses as length **or** as form. The pre-registration
borrowed "length" from different material, a different harness and a different
model, and its own limitations section said the historical number bounds nothing
here. It then required that number anyway.

**Amended requirement:** a mechanism is *identified and measured, consistent with
what the rule does* — not the specific mechanism another instrument saw. Still
falsifiable: it would have failed had the delta been made of parse refusals
(pre-registered as a separate report, and it was 1–2 rows), or had no rung
profile moved. It did not survive by luck. The measured mechanism is **form**:
lint +43/+124, any-adapter-finding +34/+42, and 34/42 fewer candidates reaching
the acceptance rung at all.

### The per-arm split, which is the load-bearing half

| arm | full bar | correctness only |
|---|---|---|
| `bench-ts` | 33→11, p = **1.05e−5** | 61→23, **p < 0.001** |
| `bench-py` | 23→15, p = 0.057 | 70→68, **p = 0.856** |

TypeScript recovers the effect twice, under two different bars. **Python does
not, and not for want of power** — 70 live cells and 30 discordant pairs on the
correctness scoring. Things moved; they did not move net.

So the control was **inert on the Python arm**. That is not a defect in the arm —
the effect is genuinely absent in Python — but check 2's entire job is
demonstrating that the instrument can detect a known effect, and on `bench-py` it
demonstrated nothing. **`bench-py` is uncommissioned until it has a control that
works on it.** #133 is the standing case: an all-zero measurement with no working
control cannot separate "no effect" from "broken rig".

**A caution on the obvious candidate.** #246's +13.7pp is the only large Python
effect on record and it is a *bar* effect — it works by satisfying style rules
the gate rejects on. Commissioning `bench-py` with it would commission the arm
against the very thing this lane found is ~87% style with no correctness content.

## Left open

- **`bench-py` needs a positive control**, and it is not #246 for the reason
  above. Until then no Python-arm result is quotable, which reaches #225, #224
  and every arm below the trunk.
- **Check 3 (the pinned round)** — cheap, no rig time, confirmed genuinely absent
  rather than assumed.
- **Check 5 (a second tier)** — should follow the bar decision, not precede it.
- **#248 blocks** and is unowned.
- **The three digests** (bar, model, condition) have no issue yet; ADR-0026
  names them as its central consequence.

next: open the issue for the three digests, then find a positive control that
works on the Python arm — without it, half the bench is uncommissioned and the
trunk's Python figures cannot be read.
