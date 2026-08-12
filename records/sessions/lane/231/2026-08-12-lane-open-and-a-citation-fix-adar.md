---
record: session/1
lane: 231
agent: adar
started: 2026-08-12
---

## Did

Opened the lane and landed one correction carried over from #225. **No
measurement was run and #231's own work has not started.**

### The correction

PR #244 (`d3e5dd04`) landed ADR-0021's swept-cell amendment and called it the
record's **third**. ADR-0021 has **four** `## Amendment` sections and it is the
fourth:

| line | section |
|---:|---|
| 75 | 2026-08-11 — separation is not a requirement |
| 106 | 2026-08-11 — overlap may be total, and the aim is met per model |
| 140 | 2026-08-12 — the 400 is counted in paired cells, both arms |
| 167 | 2026-08-12 — only the bench half is ever swept |

The ADR itself was never wrong: its heading carries no ordinal and its internal
references are relative (*"the amendment above"*). Three citations of it were:
two in `records/sessions/lane/225/2026-08-12-screen-and-denominator-adar.md` and
one docstring in `tests/test_redundancy.py`. All three are corrected here, and
the #225 record carries a note saying so rather than being silently rewritten —
the error reached `main`, so anything quoting `d3e5dd04` inherited it.

Corrected in place rather than footnoted at each site, because a miscount is not
a finding that changed. The commit messages and the squash commit still say
*third* and are immutable; this record is the pointer for anyone who follows one
of them here.

**Why it landed on this lane rather than #225's.** `lane/225` is alive and #225
is still open — PR #244 deliberately carried no closing keyword — but the lane is
spent for new work: its merge-base with `main` is now the pre-merge tip, so a
second PR from it would re-show all 41 commits. That is the failure the workflow
record warns about, so the fix rides here instead.

## Left open

**#231's actual work has not begun.** The issue is the commissioning gate — null
drift, a known effect recovered, and a pinned round — and it owns the number
every open question downstream is waiting on:

- ADR-0021's sizing table is **conditional on `psi` and prices five candidates**,
  because none of them is measured. At 400 authored the row spans **4.5pp
  (psi=0.10) to 11.3pp (`psi_draw`=0.659)** — a 2.5x range on one unmeasured
  input, wider than the denominator correction that amendment made.
- `psi_draw` = 0.659 is **not** `psi`. It is resampling sensitivity across draws
  at temperature; the contrasts that matter run greedy, which is deterministic,
  so the mechanism it measures is absent from them.
- #225's authoring stays **paused** at 280 of 400 pending this. Whether the last
  120 problems are worth authoring, whether the reserve keeps being authored to
  the instrument's bar, and whether the split changes prospectively all turn on
  the answer.

next: work #231 proper — the commissioning gate. Nothing in this session
constrains its design, and the psi it measures is the input ADR-0021's fourth
amendment names as outstanding.
