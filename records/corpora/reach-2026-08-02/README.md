# Reach corpus — 2 August 2026

The fixed set of accepted changes that [#125](https://github.com/AdarGit008/mcgyvr/issues/125)'s
three counts are computed over. `corpus.json` is the data; this file is why it
contains what it contains.

Re-enumerate and diff against the pinned copy:

```
python tools/reach/enumerate.py --check
```

It fetches each external frame **at its pinned sha**, not at whatever the
default branch holds today, and exits non-zero on any drift. As of writing it
reports `frames: 3, changes: 77, added_source_lines: 14272`.

## Why a corpus at all

#125 asks for changes "enumerated and pinned as data rather than described".
The failure it is written against is the one ADR-0004 was written against: a
number quoted without the rows behind it. A percentage over "some recent
commits" cannot be rechecked, and cannot be recomputed after the resolver
changes. This corpus fixes the denominator before any numerator exists.

## The frames

| repo | language | role | unit | changes | added source lines |
|---|---|---|---|---|---|
| `AdarGit008/mcgyvr` | Python | self | first-parent merge into `main` | 20 | 11,563 |
| `pallets/click` | Python | external | non-merge commit | 30 | 1,032 |
| `immerjs/immer` | JS/TS | external | non-merge commit | 27 | 1,677 |

**One external repository per launch language**, which is what #125 asks for —
the two shipped gate adapters are `python.py` and `javascript.py`.

`immerjs/immer` replaced `date-fns` during this lane. date-fns has become a
mise + pnpm + tsgo monorepo whose suite is expensive to instrument, and the
substitution is not just convenience: immer **declares its own coverage
command** (`vitest run --coverage`, `package.json` `scripts.coverage`), and
click declares `[tool.coverage.run]` in `pyproject.toml`. Count 1 is a question
about what *the repository's own declared checks* execute, so a frame that
declares its own instrument is measured on its own terms rather than on ones
this repository imposed. That is ADR-0006's reasoning ("the type-checker is the
target repository's") applied to coverage.

**mcgyvr does not declare coverage** — `Makefile:16` is `uv run pytest` and
there is no `[tool.coverage]` block. This does not disqualify the frame.
Coverage is measurement apparatus, not a declared check: Count 1 runs the
repository's declared suite and observes which added lines it executed. The
distinction matters for reading the result — the instrument is imposed on the
mcgyvr frame and native to the other two.

## What "accepted" means here, precisely

#125 says "changes the acceptance rung already accepted". Taken literally, no
such corpus exists yet: mcgyvr's acceptance rung has never run over any of
these repositories, including its own history. What each frame actually
contains is **changes that passed a real, declared, human-gated check** — a
merged pull request on a protected branch for mcgyvr (ADR-0002), a landed
review for click and immer.

That is a proxy, and it is the proxy the measurement needs, because the
question is what a *passing* check does not reach. But it is not the literal
population #125 names, and no percentage computed here should be quoted as "of
changes mcgyvr accepted".

## Limits worth stating before anyone quotes a number

- **The external frames are windowed, not sampled.** Both were enumerated
  inside a depth-120 shallow clone at the pinned commit, so they are the most
  recent qualifying commits in that window. immer yields 27 rather than its
  limit of 30 because the window ran out, not because three were rejected.
  Neither frame is representative of its repository's whole history.
- **n = 3 repositories.** Two external projects are a floor set by "at least
  one per launch language", not a sample size that supports generalising to
  Python or JS/TS as ecosystems.
- **mcgyvr dominates the line count** — 11,563 of 14,272 added source lines,
  81%. Any corpus-wide figure is mostly a fact about this repository. The
  per-frame counts are the ones to read; a pooled figure needs the split
  printed beside it.
- **Added lines only.** Deletions and binary changes carry no line attribution
  by construction, matching `gate/changeset.py` — `added_lines` is the same
  quantity the rung would filter on, so the corpus and the rung disagree about
  nothing.
- Test and documentation additions are excluded. The rung's territory is source.

## What is not here yet

Counts 1, 2 and 3 themselves. This lane pins the denominator and verifies
ghostcall ([CLM-0006](../../claims/CLM-0006.json)); the counts need each frame's
suite run under coverage **in a container**, per ADR-0005 and ADR-0010, and
that is the next session's work.
