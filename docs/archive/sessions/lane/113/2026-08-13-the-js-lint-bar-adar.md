---
record: session/3
lane: 113
agent: adar
started: 2026-08-13
---

## Did

**The JS/TS lint rung can now reject, so the bench's paired arms run.** Session/2
closed with this open and declined — *"author a JS/TS lint standard, or decide
there is none … Not this lane's to pick"* — and with `--tier bench-py` running
while a paired run was refused. The standard is now authored and the refusal is
lifted.

New: `eslint.config.mjs`, `package.json`, `package-lock.json`. Changed:
`tools/bench/score.py`, `.gitignore`,
`records/corpora/worker-replies/golden.json`.

**No rig time was spent.** The only measurement below is `score.rung_report`
run against the bench corpus's own reference solutions and canaries.

**Provenance of this change.** The config and the `score.py` staging were carried
in the working tree unrecorded when this session opened, after session/2 had
already declined the decision. What this session owns is the verification, one
correction (`@eslint/js`), the reply-corpus pin, and this record. The work is
recorded here rather than folded silently into a commit because it decides
something larger than the bench — see the flag at the foot.

### Why the decision could not be deferred any longer

Deferring it is not neutral. `src/mcgyvr/gate/adapters/javascript.py` shells to
eslint; eslint 9 requires a flat config and there was none anywhere in this
repository; the adapter's own error handling scores that failure as
**"inconclusive"**, which is no findings, which is a pass. So the choice was
never *"standard, or no standard"* — it was *"standard, or a rung that reports
health while passing everything, in production and on the rig alike."*

Session/2 already recorded the same shape twice over (ruff with no config
applying the wrong rules; eslint present and parserless), and that is the
argument for picking rather than waiting: **an unmade decision here is a made
decision, and the one it makes is the worst of the three.**

### `recommended`, and not `strict` or `stylistic`

`pyproject.toml` selects a moderate, correctness-leaning set — E, F, W, I, N, UP,
B, SIM, RUF — and deliberately not the whole catalogue. `recommended` is that
shape for this language: real defects and dead code, not house style.

The reason to match rather than to optimise each side separately is ADR-0021's
denominator. **Every arm on this bench is a paired ts/py comparison**, so a bar
materially harsher on one side does not show up as a stricter bar — it shows up
as a *language effect*, sitting inside every contrast the bench will ever
publish. Picking the analogous tier on both arms is the cheapest way to keep that
out.

What is excluded mirrors `extend-exclude` in `pyproject.toml`: `tools/baseline/`
is vendored and hash-pinned (REC-06), and the task corpora are instrument
material fixed by digest in their admission manifests — a formatter run there
does not tidy anything, it invalidates a pin.

### Three mechanics, each of which was load-bearing

1. **The config is copied into every scored workspace.** A one-file temp
   workspace has no config to find, so without this the run aborts, writes no
   JSON, and the adapter scores it as inconclusive — a pass. The candidate is now
   judged by the project's bar rather than by eslint's fallback.

2. **`node_modules` is symlinked in.** The config imports `typescript-eslint` as
   an ES module and Node resolves that by walking up from the config's own
   directory. The link points at the repository's installed tree, so the parser
   version is the one `package-lock.json` pins rather than whatever is global.

3. **The link is restored after every `sandbox.reset()`.** `reset` runs
   `git clean -fdx`, and `-x` removes ignored paths — which is exactly what
   `node_modules` is. Without the re-link the lint rung would work on a task's
   first draw and silently stop on its second: a per-task decay in the bar, which
   is worse than an absent rung because it is invisible in the manifest.

**And one detail worth its own line.** The workspace `.gitignore` entry is
`node_modules`, with **no trailing slash**. The toolchain arrives as a symlink,
git treats a symlink as a file, and a `node_modules/` pattern matches only
directories — so the slash version leaves the link visible to the changeset,
where the scope rung reads it as the worker writing outside `scope.allow`. Every
candidate would fail, for a reason that has nothing to do with the candidate.
(The repository's own `.gitignore` keeps the slash: there, it is a real
directory.)

### The canary now names what it must trip

Session/2 built `rung_report` on the principle that *installed is not the
property that matters; able to reject is*. Making the JS rung real exposed the
next layer of the same problem: **checking only "did anything reject" is not
enough.**

The first jsts canary was bad *spacing*. That trips prettier and leaves eslint
looking healthy — so a jsts-only sweep passed a check that a paired sweep failed,
and an arm was scored by three rungs while declaring five with nothing saying so.

Two changes:

- **`CANARY_EXPECTS`** declares, per language, which rungs the canary is built to
  trip (`lint`, `format` on both). A declared rung that runs and does not reject
  is now its own preflight issue, named.
- **The cross-arm comparison is over declared-and-live rungs**, not over the raw
  set each canary happened to trip. Two canaries are different code in different
  languages and will naturally fire different extra checks — the jsts one trips
  `structure` and the python one does not, which is a fact about the two snippets
  and not a difference in the bar. What would be a difference in the bar is a
  declared rung live on one arm and inert on the other, and that is what is
  compared now.

The jsts canary was rewritten to earn its name — `var`, an unused `let`, and bad
spacing. Measured, all three fire at severity 2:

    no-var                              Unexpected var, use let or const instead.
    prefer-const                        'unused' is never reassigned.
    @typescript-eslint/no-unused-vars   'unused' is assigned a value but never used.

### Verified live, not by mock

`tests/test_bench_score.py` stubs `rung_report`, so it cannot see any of this.
The check that matters was run against the real corpus and the real toolchain:

    jsts   | rejected: True | by: ['format', 'lint', 'structure'] | ref passes: True | env: []
    python | rejected: True | by: ['format', 'lint']              | ref passes: True | env: []
    ISSUES: none

`preflight` returning empty is the state change: before it, a paired ts/py sweep
was refused. `make check` passes — 1344 tests.

### One correction

**`@eslint/js` was imported but not declared.** The config imports it at the top
level; it was reaching the resolver only as a hoisted transitive of `eslint`. It
resolves today, and the failure mode if a lockfile regeneration hoisted
differently is precisely the one this whole change exists to remove: eslint fails
to load its config, the adapter scores inconclusive, the rung passes everything.
Now a direct devDependency, pinned in both `package.json` and the lock.

### The reply corpus

The two null-gate runs from session/2 were captured but unpinned, which failed
`test_reply_corpus.py`. `tools/replies/pin.py` re-pinned: **19,655 replies, 404
refusals kept as gold**, both runs stamped against `tools/instruments.json` as
`bench-py` — *"257 contract digest(s) identical to it; tier 'bench-py' is
declared as it"*. That is #230's stamp-not-exclude behaving as designed: the
parser's corpus keeps them, the training path refuses them.

## Flag for the owner — this is the product's JS bar, not the bench's

Session/2's reason for declining still stands and is not dissolved by the fact
that the work is done: there is no prior JS config in this repository to inherit,
so `eslint.config.mjs` is the first statement of what the **gate** rejects in
JavaScript for every consumer, not just for `tools/bench/`. The bench forced the
question; it does not own the answer. `recommended` is defensible and argued
above, and it is reviewable in one file — but if the intended product bar is
`strict` or carries house style, changing it later re-bases every JS rate
measured under this one, so it is cheaper to overrule now than after the arms
run.

## Left open

- **#113 still stands at 7 of 8.** Nothing here closes the reproducibility item;
  it removes the reason a paired sweep could not be run at all.
- **#231's checks re-run under this scorer**, and the null in PR #245 describes
  the old one. Unchanged from session/2, and now the JS arm can participate.
- **#81's classification is an ADR-0019 amendment**, not this lane's.
- **The 31 non-conforming references are #225's**, pinned material needing an
  amendment block.
- **The keyless condition (#44)** is a lever in the matrix format and unbuilt.
- **CI installs no JS toolchain.** A runner without `npm ci` will have
  `preflight` refuse a jsts sweep — correct behaviour, and the reason it is
  listed rather than fixed is that no CI job runs a sweep today. The first one
  that does needs the install step.

## Amendment — 2026-08-13, same session: both flags closed rather than carried

Owner direction was to fix both, so neither is a standing item. **Appended
rather than edited in place** (REC-01), so two things above are now superseded
and neither was rewritten:

- the **flag section** — the bar is no longer an unrecorded decision;
- the last **"Left open"** bullet, *"CI installs no JS toolchain"* — it does now.

**The bar is now a decision of record: [ADR-0025](../../../../docs/decisions/0025-the-javascript-lint-bar-is-the-projects-and-it-mirrors-pythons.md).**
An unremarked config file in a bench lane was the wrong home for a rule that
binds `Gate.run` for every consumer. The record states the scope, the
three-instances-in-a-week context, why the arms must be *matched* rather than
each optimised (a harsher bar on one side reads as a language effect, not as a
stricter bar), the pin discipline, and the asymmetry that makes it cheap to
overrule now and expensive after the arms run. `eslint.config.mjs` cites it in
its header, so the next person to widen the rule set reads the argument first.

**CI installs the toolchain, and the able-to-reject property is now a test.**
Two changes, and the second is the one that matters:

- `ci.yml`'s `test` job gains `setup-node@24` and `npm ci`. Node 24 rather than
  the baseline job's 20 because type stripping is unflagged only from 23.6, and
  acceptance for a `.ts` target imports the solution.
- `test_every_declared_rung_can_reject_on_both_arms` — the probe I had been
  running by hand, kept. It asserts, per language, that no rung in
  `CANARY_EXPECTS` is missing from `canary_rejected_by`, that both references
  pass, and that `preflight` over a paired pair is empty. The Python arm has had
  this since session/2; the TypeScript arm — the one where the rung was actually
  inert — had nothing.

**A skip that is invisible is the same defect one layer out**, so the guard names
its two real requirements (the *pinned* parser in `node_modules`, and a Node that
strips types) rather than checking `which("eslint")`. It skips on a machine
without the toolchain and does **not** skip on CI, which is where the property is
guarded.

**One inconsistency found while verifying.** The ignore list omitted
`tools/breadth/tasks/**`. `pyproject.toml` has no equivalent entry because that
corpus is TypeScript and ruff never saw it — so the mirror was incomplete in the
one direction only eslint can reach. Those sets are retired (#240) and released
for training, but historical run manifests still pin their digests. Added.
`npx eslint .` was clean before and after, so nothing was being hidden.

**Not done, and deliberately.** `make lint` still runs ruff only; eslint is not
applied to the repository's own JavaScript. The ADR scopes itself to what the
*gate* rejects, and making `make lint` depend on `npm ci` changes every
contributor's setup for a tree that already passes. Worth doing as its own
decision, not as a side effect of this one.

next: #231's commissioning checks under the gate scorer — null drift on a
re-measured pair, and CLM-0017's known output-shape effect recovered.
