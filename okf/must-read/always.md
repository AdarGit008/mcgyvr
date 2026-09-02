# always

Read at session start. All of these have burned a session.

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
