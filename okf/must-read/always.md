# always

Read at session start. Each is an owner ruling or has burned a session.

**`archive/` is not read. Asked to, it is still not an authority.** 

**Superseded code is archived, never deleted.** The old module or function moves
to `archive/` with the tests that exist only to call it, in the same merge that
supersedes it. Deleting drops the only record of what the old code claimed.

**A run is expandable until its first measurement, and frozen from then on.**

**A measurement run keeps both rigs working the whole window.** Owner ruling
2026-09-12. Plan every run so srv1 and srv2 are both busy for its full
duration. If one rig's schedule finishes sooner, fill the remaining time with
edge cases, required measurements, experiments, or new models — never leave a
rig idle.

**The rigs swap hardware. Never quote a stored spec — read it.**

**A "do not re-derive" label is not evidence.** Every one of the three headline
ratios under that banner was wrong for a day. Recompute from journals.
→ `archive/docs/board-findings-2026-08-31.md` D6

**A claim with no artifact is not a finding.**

**No prose is created without an explicit request.** Default to changing code,
tests and results. A finding goes in the commit message or an existing file.


**Bits-per-weight is a guess; the tensor table is not.** 

**Say it about case `n`, not about case `n=5`. A behaviour belongs to a named
config, never to a rig's reputation.** Owner ruling 2026-09-09. "srv1 goes
mapped" is a fact about one machine on one afternoon and is worth nothing a week
later; "config `<tag>` places this host mapped" is reproducible, comparable and
falsifiable. Write the second. The same day this was ruled, a test fixture
called 13.0 GiB "srv1 as it stands" and **both halves went stale at once** — the
machine has 14.19 GiB, and the gate it was judged by moved from 2.0 to 0.5. A
number tied to a rig's name rots silently; a number tied to a config tag is
either still emitted by that tag or is not.
→ `records/plans/handoff.md`, O5; `tests/test_a_blob_that_overflows_ram_is_emitted_unmapped.py`
