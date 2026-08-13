---
record: session/4
lane: 231
agent: adar
started: 2026-08-13
---

## Did

**CI's baseline job failed on FLOW-03, and it was right to.** No measurement is
affected; this record exists because the fix has to be a *new* record rather than
an edit, and because the trap will fire again on another lane.

### The mechanism, read from the rule rather than guessed

`committedLog` in `tools/baseline/src/evaluators.mjs:36-50` takes the records
**added** on the lane, sorts them, and reads the last one:

```js
const md = added.filter(f => f.endsWith('.md')).sort()
const rel = md.at(-1)
```

The sort is lexicographic on the path, so "newest" means *last by filename*, not
last by time. On this lane:

    2026-08-13-checks-1-and-2-under-the-gate-adar.md   <- the session record, has next:
    2026-08-13-positive-control-prereg.md              <- picked, has no next:

`c` sorts before `p`, so a **pre-registration written before the session record
outranks it**, and a pre-registration correctly carries no `next:` — it is not a
session, it is a design fixed before dispatch.

### Why this is a new record and not an edit

Two reasons, and the second is the stronger one:

1. **REC-01 makes committed records append-only.** Lane/113 hit FLOW-03 from the
   other direction on 2026-08-13 and settled the precedent: *"the newest record
   governs… restructuring session/3 to move its `next:` would have traded a
   blocker for a mutation."*
2. **The mutated file would be a pre-registration**, edited after its results
   were known. Even an edit that touches nothing pre-registered puts the one
   document class whose integrity is the whole point into the mutation list. A
   blocker is cheaper than that precedent.

### The trap is latent elsewhere

`lane/225` carries `2026-08-11-f1-responsiveness-prereg.md` and did **not** fail,
because `2026-08-11-f1-tranches-8-9-and-sweep-adar.md` happens to sort after it
(`f1-t` > `f1-r`). That is luck, not discipline — the same pairing on a day when
the session record's stem sorted earlier would have blocked that lane too.

**Two durable fixes, both the owner's rather than mine.** Either a naming
convention that keeps a pre-registration sorting before its lane's session
records, or FLOW-03 selecting by frontmatter `record: session/N` (or commit
order) instead of by filename. The second is the correct one and is the more
expensive: `tools/baseline/` is vendored and hash-pinned under REC-06, and a
descriptor or rule change needs a judgment record in the same PR (FLOW-06,
DESC-03).

### Also here: where #231 stands

Three of six acceptance items are met — check 1 (null drift, `d = 0` of 514,
stop condition evaluated in writing), check 4 (declared bound, ±1.47pp per arm)
and the single-tier declaration, which landed with #113.

Check 2 is **recovered and decidable but not by the pre-registered mechanism**,
and that verdict is the owner's, not this lane's. Check 3 (the pinned round) and
check 5 (a second tier) have not started. Check 3 is confirmed genuinely absent
rather than assumed: `run.json` carries `bundle_sha256` — which hashes the
*system prompt*, per `measure.py:221` — and `tasks_sha256`, and no run manifest
on disk records a product revision at all.

## Left open

- **Check 2's verdict**, as session/3 left it. Marking it passed means accepting
  a mechanism the pre-registration did not name.
- **Checks 3 and 5.** Check 3 is cheap and needs no rig time; check 5 needs the
  whole battery again on a second tier, including its own null (ADR-0019 D2).
- **FLOW-03's selection rule**, above.
- **PR #245's title is stale** — it says "one flip in 514 cells", which was the
  superseded grader. This lane now reads zero.
- **A side investigation is running**, not part of #231: re-scoring the control
  with the language rung dropped, to separate "TypeScript needs more shape
  declared" from "the lint bar crushes the Python arm before the correctness
  test runs" (py lint rejects 154 of 257 at baseline against ts's 32). No model
  cost; `tools/bench/lintless.py`.

next: get check 2's verdict from the owner, then build check 3 — pinning the
product revision into run metadata is the cheapest remaining item and the one
that stops an adopted change from silently re-baselining every arm after it.
