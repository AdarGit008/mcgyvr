# Reach, absence and false positives — 3 August 2026

The three counts [#129](https://github.com/AdarGit008/mcgyvr/issues/129) asks
for, computed over the corpus [#125](https://github.com/AdarGit008/mcgyvr/issues/125)
pinned at `records/corpora/reach-2026-08-02/`. `corpus.json` fixed the
denominator; the JSONL files here are the numerators, one row per change.

```
python tools/reach/count1.py --run   # reach          (needs Docker)
python tools/reach/count2.py --run   # absence        (git metadata only)
python tools/reach/count3.py --run   # false positives (needs Docker)
```

Each tool also takes `--summarise`, which re-derives every published total from
the rows without re-measuring. `tests/test_reach_counts.py` checks that the rows
still partition the pinned corpus and that the totals are a faithful reduction
of them, offline.

Claims: [CLM-0007](../../claims/CLM-0007.json) (reach),
[CLM-0008](../../claims/CLM-0008.json) (absence),
[CLM-0009](../../claims/CLM-0009.json) (false positives).

## How the counts were taken

**In a container, at each change's own commit.** ADR-0005 and ADR-0010 put
target code in a container; CLM-0006 made that a constraint rather than a
preference, because the Count 3 resolver imports the target's own modules and
the Count 1 suites are arbitrary code by construction. Nothing here runs a
target's code on the host — host-side work is git metadata only. The suite runs
once per change rather than once per frame, because a line number only means
something in the tree that contains it.

**The declared check is the repository's own.** Each frame's command comes from
`corpus.json`'s `declared_check`, not from a detector. `mcgyvr.sandbox`'s
`detect_stack` is deliberately not reused for this: substituting mcgyvr's
inference about a repository for the repository's own declaration is the error
ADR-0006 names.

**Coverage is apparatus, not a declared check.** click declares
`[tool.coverage.run]` and immer declares `scripts.coverage`, so those two frames
are instrumented on their own terms. **mcgyvr declares no coverage**, so there
`--source=src` is this harness's choice and the mcgyvr figures are the ones to
read with that in mind.

## Count 1 — reach

Added source lines the repository's own declared checks never execute.

**Four outcomes per added line, not two.** *Reached* — the instrument saw it
execute. *Unreached* — the instrument considered it executable and it never ran.
*Non-executable* — a blank line, a comment, a docstring, or something the
instrument excludes. *Not reported* — its file never appeared in the report.
Reporting the gap as `added − reached` folds the third bucket into it, and the
third bucket is **60% of the corpus**, so that framing would overstate the gap
by more than five times. The headline is over executable added lines.

The two instruments do not define "executable line" identically — coverage.py
reports every statement line, istanbul is read here at each statement's start
line. That is a second reason the per-frame numbers are the ones to read.

### A frame's declared check is not constant over its history

`corpus.json` records one `declared_check` per frame, read at the pinned commit.
A frame's history need not agree with its tip, and immer's does not: at **10 of
its 27 pinned commits `scripts.coverage` is `jest --coverage`**, because the
project had not migrated to vitest yet. Running the tip's command at those
commits would run something the repository never declared *then* — ADR-0006's
substitution arriving through time rather than through a detector. Those 10 are
**excluded and listed** in the summary with their reason, not measured with the
wrong instrument and not silently renormalised away; they are 80 added source
lines, 0.6% of the corpus. Every row now carries
`declared_coverage_at_commit`, so the anachronism is in the data rather than in
this paragraph.

### Three rig defects found and fixed before these figures were taken

Recorded because a measurement that hid them would be worth less than none, and
the second is the failure shape that voided an earlier evidence run elsewhere:

1. **Lost rows that looked like target failures.** `uv`'s rayon pool could not
   spawn threads under a 1024-PID container ceiling, silently costing 7 of
   mcgyvr's 20 changes. The ceiling is raised and build parallelism is bounded
   directly.
2. **Stale coverage copied through a failed run.** vitest writes through
   `--coverage.reportsDirectory`, which persisted between commits, so a run that
   never produced coverage copied the *previous* commit's report. Ten immer rows
   were another commit's data. The output directory is now wiped per commit.
3. **A whole-file flag count with no calls behind it.** Count 3 originally
   recorded only the flags on added lines while reporting a whole-file total,
   which asked the reader to take seven verdicts on trust. Every flag is now
   written out; all four distinct ones turned out to be platform-conditional
   code, which is the most useful thing Count 3 found.

## Count 2 — absence

The share of corpus repositories and commits declaring no runnable check.

A check counts only where the repository *states* it — a pytest section, a
Makefile target, a `scripts.test` entry, a CI step. A `tests/` directory is not
a declaration. Every hit records the file and the signal, so a reader can
disagree with a specific line rather than with a total.

**This count's result is negative, and the reason is structural.** Absence is
zero everywhere, and it was going to be: the corpus takes one mature repository
per launch language, so every frame declared a check before any commit was
enumerated. The number is honest and the population is not a sampling frame for
the question. Anything that needs a real absence rate needs a different corpus.

## Count 3 — false positives

The candidate resolver (ghostcall, vendored at
`records/evidence/ghostcall-2026-08-02/`) run over code that shipped.

Counted the same way as the others — per change, restricted to the lines that
change added, because the rung judges added lines (`gate/changeset.py`). The
whole-file rate is recorded beside it.

**These are *presumptive* false positives.** Every file measured passed a
declared, human-gated check, which is the corpus's proxy for "accepted"; under
that proxy a `hallucinated` verdict on shipped code is wrong. The proxy is not
proof — shipped code can carry a latent bug — so every flag is listed with its
path, line and call chain, to be checked by hand rather than taken on report.

`module_missing` is **not** a false positive and is counted separately. It means
the resolver could not import a root, which is an environment outcome. It is the
failure mode that would make the rung *vacuous* rather than wrong.

**Python frames only.** ghostcall parses Python, so immer's 27 changes are not
in this count's denominator, and the JS/TS half of the launch languages has no
candidate measured at all.

## Limits that travel with every number here

These are the corpus's, and they do not weaken with a numerator attached:

- **The external frames are windowed, not sampled** — depth-120 clones, so the
  most recent qualifying commits in that window, not a sample of history.
- **n = 3 repositories**, a floor set by "one per launch language".
- **mcgyvr is 81% of the added line count**, so any pooled figure is mostly a
  fact about this repository. The per-frame split travels with any pooled figure.
- **"Accepted" is a proxy.** mcgyvr's acceptance rung has never run on any of
  these changes. What each frame holds is changes that passed a real, declared,
  human-gated check.
- **Suite outcomes are recorded, not assumed.** A non-zero suite is kept, since
  a check with a failing test still executed nearly all of it, but every row
  carries the runner's own summary line so the reader can see how non-zero.
  A commit that produced no report at all is excluded loudly, with the reason.
