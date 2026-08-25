---
record: session/4
lane: 113
agent: adar
started: 2026-08-13
---

## Did

**PR #247's first CI run failed both jobs, and it was right to.** Session/3's
verification claims stand as written — `make check` did pass locally — and that
is the finding rather than an excuse: **a green suite on this machine was not
evidence about the runner**, which is the same shape as everything else in this
lane.

Changed: `.github/workflows/ci.yml`, `tests/test_bench_score.py`,
`tests/test_breadth_rig.py`. No rig time, no measurement.

### `npm ci` is not an installed toolchain

`require_tool` resolves every linter with `shutil.which`. `npm ci` puts eslint and
prettier in `node_modules/.bin`, which is **not on PATH** — so the gate could not
see them, both rungs read as *not installed*, and the preflight refused the sweep
exactly as designed. It passed locally only because this machine carries them
globally, from the owner-directed install in session/2.

*Present is not reachable* — one layer below ADR-0025's *installed is not able to
reject*, and I wrote the second while walking into the first. The workflow now
exports `node_modules/.bin` onto `$GITHUB_PATH`, and `_js_toolchain_ready()` asks
`which()` for the tools rather than checking that a directory exists.

Both directions reproduced locally before pushing again, which is what should have
happened the first time:

    PATH=/usr/bin:/bin:<uv>                        -> the CI failure, exactly
    PATH=/usr/bin:/bin:<uv>:$PWD/node_modules/.bin -> 42 passed

### Three rig tests were quietly depending on a linter

`test_breadth_rig.py`'s dispatch-error tests call `main()` with only
`_scorable_arm` applied, so they ran the **real** preflight and needed eslint on
PATH. They are about which cells hold an observation and score nothing, so
`_scorable_arm` now neutralises `require_rungs` alongside the Node capability —
which is the argument `_always_passes` already carries for the pair it stubs.

### BUILD-05 is why the guard reads the workflow, not the environment

The baseline job runs the **whole suite** through the documented bootstrap on a
clean checkout: Python tooling and nothing else. So session/3's way of making the
skip non-permanent — an assertion gated on `CI` — failed there *by construction*,
because that job is meant to have no JS toolchain.

The replacement asserts the **declaration**.
`test_ci_installs_the_js_toolchain_so_the_skip_cannot_become_permanent` reads
`ci.yml` and requires the `test` job to both install the toolchain and export
`node_modules/.bin`. It needs no environment, runs everywhere including the clean
checkout, and holds the one job that must have the tools.

The rule this implies is worth naming, because it will come up again: **a test
that needs a linter may only ever skip under BUILD-05**, so whatever keeps such a
check honest has to be a statement about *configuration* rather than about the
machine it happens to run on.

### FLOW-03, and a convention I broke by appending

The second baseline failure was mine and structural. `extractNext` reads `next:`
only **inside** the `## Left open` section — it stops at the first `##` heading
after it — so session/3's two appended `## Amendment` headings pushed its `next:`
out of reach and the lane read as having no recorded next step. All 25 recent
records in this repository put `next:` last inside `## Left open`; that is the
convention, and appending a section after it silently breaks a blocker-severity
rule.

The fix is this record rather than an edit to session/3: **the newest record
governs** FLOW-03 (`md.at(-1)` over the lane's added records), and REC-01 makes
committed records append-only, so restructuring session/3 to move its `next:`
would have traded a blocker for a mutation. The CI narrative moved here with it,
so each fact still has one home (REC-04).

**Consequence for anyone amending a record:** an amendment section belongs
*before* `## Left open`, or in a new record. Not after it.

### Two warns, neither new nor this branch's

REC-01 reports 23 historical record mutations, oldest `cb3a4f1` — the standing
warn #171 is about. REC-02 flags a high-entropy blob inside pinned candidate
replies, and the same bytes are already on `main` in
`bench-calibration-15b-f1-2026-08-11`. Both are warns; the only blockers were
BUILD-05 and FLOW-03.

### Verified as the two jobs, not as this machine

- no JS toolchain on PATH — the suite passes with **exactly one skip**, the
  paired able-to-reject check;
- `node_modules/.bin` on PATH — nothing skips;
- `make check`: **1346 passed**.

## Left open

- **#113 still stands at 7 of 8.** Nothing in this session touches the
  reproducibility item; PR #247 says so in its first line.
- **#231's checks re-run under the gate scorer**, and the null in #245 describes
  the old one.
- **The pre-gate normalisation lever** (+13.7pp at zero tokens, session/2) needs
  an issue of its own.
- **`make lint` still runs ruff only** — the repository's own JavaScript is not
  held to ADR-0025's bar. Deliberate, and named in the ADR's consequences.
- **#81's classification is an ADR-0019 amendment**, and the 31 non-conforming
  references are #225's.

next: watch PR #247's re-run to green, then #231's commissioning checks under the
gate scorer — null drift on a re-measured pair, and CLM-0017's known output-shape
effect recovered.
