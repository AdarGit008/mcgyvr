# always

Read at session start. Each is an owner ruling or has burned a session.

**`archive/` is not read. Asked to, it is still not an authority.** Nothing
under `archive/` is opened on the way to a number, a plan or an answer, and a
`→ archive/…` pointer in this store is provenance for a rule, not a place to
go. When the owner names a file in it, read that file and no more, and treat
what it says as retired: a measurement in `records/evidence/` or a journal
row wins over it, and on its own it settles nothing. Owner ruling, 2026-09-05.

**A run is expandable until its first measurement, and frozen from then on.**
Levers, real tasks, fine-tunes, checkpoints, rungs — add them while the run is
being planned. Once one cell has been measured the run's shape is fixed, and
anything new is a new run under its own label with its own journal. A run
whose shape changed in flight holds rows measured under two plans, and this
store already shows what one changed list does to comparability
(→ `reading-results.md`, the level-list desync). Owner ruling, 2026-09-05.

**The rigs swap hardware. Never quote a stored spec — read it.**
RAM moved between srv1 and srv2 twice in six days. A 2026-08-25 file was quoted
on 2026-08-31 and was wrong in both directions.
→ `records/evidence/2026-08-31-inventory/{srv1,srv2}-scan.txt`

**A "do not re-derive" label is not evidence.** Every one of the three headline
ratios under that banner was wrong for a day. Recompute from journals.
→ `archive/docs/board-findings-2026-08-31.md` D6

**A claim with no artifact is not a finding.** The repo asserted three
`--cpu-offload-gb` launches at 0/4/6 GiB that exist in no log, no journal, and
no commit. → D1, same file.

**No prose is created without an explicit request.** Default to changing code,
tests and results. A finding goes in the commit message or an existing file; a
new `.md` is written only when the owner asks for one by name. Every doc written
unasked became a second source of truth that then had to be corrected against
the journals. → `archive/docs/board-findings-2026-08-31.md`

**Bits-per-weight is a guess; the tensor table is not.** Two defensible
estimates of the same GGUF's expert bytes — nominal quant width, and file size
over parameter count — disagreed by 14% and both were wrong. Sum the tensor
table instead: KAT computed 278.0 MiB of expert weight per layer, and the
measured VRAM delta was 278.0. Watch the type map — MXFP4 is ggml type **39**;
a reader missing it falls back to f32 and calls an 11.28 GiB file 71 GiB of
experts. → `records/evidence/2026-09-01-moe-offload/`
