# Telemetry is what we read, the test is the validator — a sweep

**Issue:** #201 · **Lane:** lane/201 · **Date:** 2026-08-07
**Reviewed:** all 47 modules under `tests/`, at `df8d821`.
**Method:** every module read by test name and by every `assert` line; modules
read in full wherever a name or an assertion suggested a report-only or a proxy
assertion. Every finding below carries a `file:line` a reader can open and a
named seam an instrument could attach to. Nothing here is a claim about a
module that was not opened — the [coverage table](#coverage-every-module-and-its-verdict)
lists all 47 with a verdict each, including the ones with nothing to report.

---

## The rule

**Telemetry is what we read; the test is the independent validator.** A test
that asserts only on the product's own report of its own work passes whenever
the product is self-consistent — including when it is consistently wrong
(*mode 1, self-certification*). A test that asserts on something merely
correlated with the property it cares about — elapsed time, ordering, a log
line — is environment-sensitive, and announces itself as a flake (*mode 2, a
proxy for an unmeasured property*). #200 was one instance of mode 2.

## The headline

**Seven findings, and the suite is in better shape than #200 suggested.** One
live instance of mode 2 remains — `test_availability.py:204`, the same
stopwatch shape #200 removed from `test_capacity.py`, still unfixed and
flakeable for the same reason. Five are mode 1, and the largest of them is
the index cache: **the module whose entire value proposition is "the work did
not happen" is the one module that never counts the work.** The seventh is
neither mode and was found by being taken in by it — see [F7](#f7).

The counterweight is that the repo already holds the line in more places than
it breaks it. `test_gate_runner.py`, `test_sandbox_image.py`,
`test_sandbox_docker.py`, `test_semantic.py` and `test_capacity_hostwide.py`
each build a genuinely independent witness, and three different techniques for
doing so are already in-tree. **Every fix below is a copy of a pattern this
suite already uses** — none needs an invention, and only one warrants a shipped
field.

| # | Where | Mode | Instrument belongs in |
|---|---|---|---|
| [F1](#f1) | `tests/test_availability.py:204` | 2 — proxy (wall clock) | **Test** — a barrier, as in #200 |
| [F2](#f2) | `tests/test_orchestrator_cache.py:103,122` | 1 — self-certification | **Test** — count the two seams |
| [F3](#f3) | `tests/test_orchestrator_index.py:66` | 1 — self-certification | **Test** — the fixture knows the bytes |
| [F4](#f4) | `tests/test_orchestrator_read.py:57`, `test_orchestrator_context.py:329` | 1 — self-certification | **Test** — recompute over the slice |
| [F5](#f5) | `tests/test_structured_and_preflight.py:187` | 1 — a measured constant checked against a restatement | **Test** — read the measurement |
| [F6](#f6) | `tests/test_escalate.py:776` | 1 — minor | **Neither** — delete the line |
| [F7](#f7) | `src/mcgyvr/orchestrator/read.py:378`, `CHANGELOG.md:1066` | not a witness gap — a stale claim (#66) | **Product** — the comment |

And one thing that is not a finding but bears on the last box of #201's
checklist: [silent skips](#silent-skips).

---

<a id="f1"></a>
## F1 — a wall clock still stands in for concurrency

```python
# tests/test_availability.py:186-204
def test_dead_sources_are_probed_concurrently() -> None:
    """Wall clock for n dead sources is one timeout, not n. ..."""
    ...
    started = time.monotonic()
    availability.check_all(targets)
    elapsed = time.monotonic() - started

    assert elapsed < 0.6, f"probes look serial: {elapsed:.2f}s for 6 probes of 0.2s"
```

**Mode 2, and it is #200's test with the names changed.** Six jobs, each a
`sleep`, a serial floor of 1.2s, and an assertion that the batch beat a
fraction of it. `Availability` records verdicts and nothing else — grep
`peak`, `concurrent`, `in_flight` across `src/mcgyvr/availability.py` and the
hits are two lines of module docstring and the `ThreadPoolExecutor` import
(`:54`, `:100`, `:111`); no field records it — so no instrument for the property
exists and the stopwatch is the only assertion that could have caught a serial
pool.

The margin here is looser than #200's (3× the sleep, where #200 demanded a 30%
win over the floor), and its docstring is honest that it is "asserting a thread
pool exists, not measuring one". That buys headroom; it does not change the
kind of assertion. A thread whose sleep has elapsed still waits for a free core
before it can return, so a loaded box makes this slower without making the pool
serial — the exact failure #200 measured at 2 in ~14 runs.

**The instrument is test-side, and #200 already built it.** Replace the sleep
with a rendezvous:

```python
barrier = threading.Barrier(6, timeout=30)  # a deadlock guard, not a measurement


def rendezvous(target: Endpoint, _timeout: float) -> Verdict:
    barrier.wait()  # trips only when all six are genuinely in flight
    return dead(target, _timeout)
```

A serial pool never trips the barrier and fails on the guard; a loaded box makes
the test slower and never wrong; nothing asserts on duration. **No product
change is warranted** — an operator has no use for "how many probes overlapped",
and unlike #200's `Concurrency` (which #185 made meaningful by taking the
capacity bound host-wide) there is no shipped bound here for the number to
mean anything against.

<a id="f2"></a>
## F2 — the cache reports that it skipped the work, and nothing checks

```python
# tests/test_orchestrator_cache.py:103-119
def test_second_build_reuses_every_file(tmp_path: Path) -> None:
    ...
    second = build_index_cached(repo, directory=cache).cache
    assert second.loaded is True
    assert second.reused == 4
    assert second.rebuilt == 0
    assert second.restamped == 0
    assert second.hit_ratio == 1.0
```

Every assertion in this test, and in `test_touch_without_change_does_not_reparse`
(`:122`), reads a field of one `CacheStats` object the cache filled in about
itself. **A cache that re-read and reparsed all four files and then set
`reused=4` passes this test unchanged.**

This is mode 1 in its purest form, and the product said so first —
`src/mcgyvr/orchestrator/cache.py:82-88`:

> *A cache that silently does nothing looks exactly like a cache that works,
> which is why these numbers are returned rather than logged.*

The module identified precisely the failure an independent witness exists to
catch, shipped the number that lets an operator see it, and the test then took
that number on faith. Returning the figure is what makes the cache legible in
production; it is not evidence that the figure is true.

**Two seams make this mechanical, and both are already module-level functions
imported into `cache.py`** (`src/mcgyvr/orchestrator/cache.py:45`):

| Seam | Called for | The witness |
|---|---|---|
| `read_source` (`cache.py:238`) | everything except `reused` | `reused == 4` ⇒ **0** calls |
| `index_source` (`cache.py:259`) | `rebuilt` only | `rebuilt == 0` ⇒ **0** calls |

Wrapping them with a counter — `monkeypatch.setattr("mcgyvr.orchestrator.cache.read_source", counting)`
— is the `Counting` probe from `test_availability.py:137` applied one module
over, and it turns `CacheStats` from the thing trusted into the thing
validated. `reused` is documented as "stamp matched, **file never opened**",
which is an observable fact about the process, not an opinion of the cache's.

**Test-side.** `CacheStats` is already the right shipped field; nothing about it
needs to change.

Two clarifications, so the fix lands in the right place:

- `test_change_invalidates_only_the_changed_file` (`:143`) **does** carry
  independent assertions — `definitions("delta")`, `definitions("beta")`,
  `search("no grammar")`. Those establish the index is *correct*. They say
  nothing about whether work was *skipped*, which is the separate claim
  `rebuilt == 1, reused == 3` makes on the line above.
- `test_cached_build_equals_a_fresh_build` (`:65`) compares `cached.stats.*`
  against `fresh.stats.*` (`:79-83`). Report-against-report is the right shape
  for a round-trip — but its trust bottoms out in whatever validates the
  *fresh* build's stats, which is [F3](#f3).

<a id="f3"></a>
## F3 — the root the cache suite borrows its trust from

```python
# tests/test_orchestrator_index.py:66-74
def test_build_stats_are_reported(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "a.py").write_text("def f():\n    return 1\n")
    index = build_index(repo)
    stats = index.stats
    assert stats.elapsed_seconds >= 0.0
    assert stats.files_indexed == len(index.files)
    assert stats.bytes_indexed > 0
    assert stats.languages.get("python") == 1
```

Four assertions, and only the last has an independent witness (the test wrote
one Python file). Of the rest: `elapsed_seconds >= 0.0` cannot fail short of a
clock running backwards; `files_indexed == len(index.files)` is one object
agreeing with itself, both sides filled in by the same build; `bytes_indexed > 0`
is satisfied by any non-zero number.

The fixture knows the exact answer to all three, because it wrote the file:
`files_indexed == 1` and `bytes_indexed == len(source.encode())`. That the test
reaches for `len(index.files)` instead of `1` is the tell — it is comparing the
report to the product rather than to the input.

The neighbouring tests are the contrast and the model:
`files_skipped_large == 1` (`:85`) and `files_skipped_binary == 1` (`:96`) each
sit beside an assertion that the named file is absent from the index, so the
counter is checked against an effect the test controls.

**Test-side**, and it is a two-line change. It matters more than its size
because [F2](#f2)'s `cached == fresh` comparison inherits from here.

<a id="f4"></a>
## F4 — a read plan's spend is checked against its own arithmetic

```python
# tests/test_orchestrator_read.py:56-57
assert plan.spent <= plan.budget
assert plan.spent == sum(r.estimated_tokens for r in plan.reads)
```

Both sides come off the same `plan`. The identity establishes that `spent` was
summed correctly and nothing else; `estimated_tokens` is never checked against
the text that was actually sliced, so a plan that under-counted every region
would satisfy this and stay inside a budget it had already blown. Repeated
verbatim at `test_orchestrator_context.py:329`.

The independent witness is free: the test builds the files (`build()`,
`test_orchestrator_read.py:34`) and `TargetedRead` carries the region, so
recomputing the estimate over the slice the plan says it took is available
without a new seam. `test_an_injected_estimate_is_used_for_the_budget` (`:176`)
already proves the estimate seam is honoured when it is injected — what is
missing is that the *default* path charges for what it actually read.

**Test-side.** `spent` is exactly the number the orchestrator should ship;
budget enforcement is the one place exploration spends tokens.

<a id="f5"></a>
## F5 — a measured constant, checked against a restatement of itself

```python
# tests/test_structured_and_preflight.py:187-190
def test_the_reserve_is_the_measured_undercount_not_a_round_number() -> None:
    """A margin that drifted to a tidy 0.25 or 0.5 would have stopped being measured."""
    assert 0.30 <= ESTIMATE_RESERVE <= 0.35
    assert ESTIMATE_RESERVE not in (0.25, 0.5)
```

`ESTIMATE_RESERVE = 0.32` is not a guess, and this is the module #117 completed:
CLM-0011 measured the token estimator's error over **2,387 units across three
vocabularies**, and the constant is documented — in the claim, in
`preflight.py:50-56`, and in the test's own name — as *the worst vocabulary's
p05, rounded up to the next whole percent*. The evidence is vendored at
`records/measurements/tokens-2026-08-03/summary.json` and re-derivable with
`tools/tokens/measure.py`.

**Nothing reads it.** Grep `tokens-2026-08-03` and `summary.json` across
`tests/` and `src/`: no hits. The only assertion tying the shipped constant to
the measurement it claims to come from is a hand-written band, `0.30 <= x <= 0.35`,
which is a restatement of 0.32 with room either side. It catches the drift its
docstring names — a margin quietly rounded to 0.25 or 0.5 — and cannot catch the
one that matters: a re-measurement producing a different p05, or a constant
edited away from the number the claim says it is.

This is mode 1 one tier up from the code: a *claim* about where a number came
from, validated against a restatement of the number rather than against the
source. **The repo already holds this exact line elsewhere**, and says why —
`test_claims.py:98`:

> *The vendored copy is only evidence if it is the bytes that were measured…
> Without this check a vendored tree is just a directory someone said came from
> somewhere.*

The same sentence applies here. `test_semantic.py:353` does it for engine
digests. Reading the p05 out of `summary.json` and deriving 0.32 from it is the
same move, and it makes CLM-0011's central sentence checkable by the test suite
rather than by a reader.

**Test-side.** The constant, the comment and the claim are all correct today;
what is missing is the tie.

**A smaller, related gap in the same subject.** `estimate_tokens`
(`read.py:368`) has no direct test of its arithmetic. Its only appearances in
`tests/` are `test_orchestrator_decompose.py:360` and `:497`, both of the shape
`assert built.max_input_tokens >= estimate_tokens(...)` — the product function
used as the yardstick for the product's number, so a wrong denominator moves
both sides together. Low severity precisely *because* of #117: the proxy's error
is quantified and reserved against, so the estimator is no longer an unmeasured
stand-in. A few literal-string assertions would close it.

<a id="f6"></a>
## F6 — an inequality that adds nothing

```python
# tests/test_escalate.py:771-776
assert "PREVIOUS ATTEMPT" not in first.user
assert "PREVIOUS ATTEMPT" in again.user
assert "lint" in again.user and "format" in again.user
assert "scope" not in again.user and "secrets" not in again.user
# The contract is unchanged, so a retry is the first prompt plus what failed.
assert again.tokens > first.tokens
```

The four assertions above establish the property on the text itself. The last
compares one product-reported count to another and cannot fail given them —
`tokens` is monotonic in the text by construction (`estimate_tokens`, and see
[F5](#f5)). It is not wrong, it is not load-bearing, and it reads as though the
token count were being validated when it is not.

**Neither.** Delete the line, or replace it with the difference the retry note
actually costs if that number is worth pinning.

<a id="f7"></a>
## F7 — the estimator still says its error is unmeasured

```python
# src/mcgyvr/orchestrator/read.py:378, in estimate_tokens' docstring
    ... What the proxy's error actually is remains #117's to measure.
```

**#117 closed as completed on 2026-08-03**, four days before this sweep. It was
measured — CLM-0011, 2,387 units, three vocabularies — and fed back as
`ESTIMATE_RESERVE`, which is #117's third scope bullet discharged. The sentence
above is still in the shipped docstring of the function the claim is *about*,
and `CHANGELOG.md:1066` repeats it verbatim.

Neither mode, and no instrument would have caught it: nothing here is a test
asserting the wrong thing. It is a shipped comment contradicting a shipped
claim, which is #66's class — and it is the reason this finding exists at all,
because the sweep's first draft read that docstring, believed it, and wrote
[F5](#f5) up as "the error band is unmeasured". A reader arriving at
`estimate_tokens` today is told the opposite of what CLM-0011 records, and the
docstring is the nearer source.

**Product-side, and it is two sentences.** The docstring should point at
CLM-0011 and the reserve; the CHANGELOG line is history and should be corrected
where the reserve was added rather than rewritten in place.

*Recorded as a finding of this sweep rather than quietly fixed, because the way
it was found — a stale comment successfully misleading a review that was
explicitly hunting for unmeasured proxies — is the argument for #66 being
separate work.*

<a id="silent-skips"></a>
## Not a mode, but it breaks the last box: silent skips

#201's fourth checkbox asks that coverage be legible rather than implied by
silence. Nine tests opt out of running at all when a tool is absent, and a
green suite does not distinguish "checked" from "skipped":

| Where | n | Condition |
|---|---:|---|
| `tests/test_python_adapter.py:93,105,117` | 3 | `shutil.which("ruff") is None` |
| `tests/test_bundle_ladder.py:544`, applied at `:568,617,642,706,781` | 5 | node cannot run TypeScript |
| `tests/test_structured_and_preflight.py:67` | 1 | `pytest.importorskip("yaml")` |

*Corrected 2026-08-09 under #234: this read "Four tests", counting table rows.
`tests/test_bundle_ladder.py:544` is the `requires_typescript_node` marker's
definition, not a test — it is applied to five.*

The ruff skips are the sharp one: they are the gate's lint and format rungs,
and the gate's own answer to a missing tool is an **environment issue** — a
first-class, tested concept (`test_gate_runner.py:108`,
`test_acceptance.py:83`). So the product distinguishes "the tool was absent"
from "the check passed", and the suite does not. That is a reporting gap, not a
witness gap, which is why it is filed here rather than as a finding.

---

## What the suite already does right

The fixes above are all copies. Three techniques, all in-tree today:

**Count the real calls.**
`test_gate_runner.py:142` wraps `subprocess.run` and asserts the gate spawns
exactly two ruff calls for 1 changed file and for 12 — a claim about work
avoided, proved by counting the work.
`test_changeset.py:160` does the same for change detection.
`test_sandbox_image.py:176` is the direct analogue of [F2](#f2) and gets it
right: `assert second.built is False` (the product's report) **and**
`assert runner.built_tags() == [first.tag]` (the witness), in the same test.
`test_availability.py:152` counts probes with a `Counting` stub — the same
module that carries [F1](#f1).

**Make the wrong behaviour raise, or leave a mark on disk.**
`test_gate_runner.py:49` monkeypatches `PythonAdapter.lint` to an `AssertionError`,
so "lint never runs after a secret" is proved by the absence of an exception
rather than by the absence of a finding.
`test_escalate.py:206` is the same idea as a class, with the reasoning written
down: *"A counter checked for zero would be satisfied by a verifier that was
called and whose answer was thrown away."*
`test_semantic.py:511` runs `touch ran.marker` as the expensive rung's command
and asserts the marker does not exist — the ordering claim settled by a
filesystem fact, not by a log line.
`test_semantic.py:483` records call order through subclass overrides where a
marker will not do.

**Put the witness outside the process.**
`test_capacity_hostwide.py` replays an append-only log written by six separate
interpreters, and proves mutual exclusion by having the *parent* — a process
mcgyvr knows nothing about — fail to `flock` the slot file while the winner
holds it. It is the strongest witness in the suite, and its own docstring names
the reason: "the mutual exclusion is the kernel's, not this module's
bookkeeping agreeing with itself".

And one shape that looks like a violation and is not:
`test_runner.py:880,895,945` asserts on `capacity.usage()[0].acquisitions` to
show a dispatch took a slot. The SUT is the runner; `Capacity` is a
*collaborator*, and its accounting is independently validated in
`test_capacity.py:198`. A witness that is a different unit, itself validated
elsewhere, is a legitimate composition — not the product grading its own
homework. Recorded here so it does not get "fixed".

## Is it mechanisable?

#201 declines to assume so, and the answer from the sweep is: **only for one
shape, and it is nearly a no-op.**

- **Mechanisable.** A test asserting on a wall-clock delta — a `time.monotonic()`
  or `perf_counter()` difference reaching an `assert` — is a two-line AST rule
  with essentially no false positives. Across 47 modules it fires exactly once
  ([F1](#f1)); every other timing call in the suite is a deadlock guard, a
  fixture, or an injected clock (`test_runner.py:173`). A rule that guards a
  property already held everywhere but one place is cheap to add and cheap to
  keep — but it buys almost nothing that fixing F1 does not.
- **Not mechanisable.** "Is there an independent witness" is not a syntactic
  property. [F2](#f2)'s failing test and `test_sandbox_image.py:176`'s passing
  one are the *same shape* — assert on a returned report object — and differ
  only in whether a second assertion elsewhere in the test happens to observe
  the same fact by another route. Deciding that requires knowing what the
  object means. Any linter for it would either miss [F2](#f2) or flag most of
  `test_route.py`, and a check with that error rate gets muted.

So: the stopwatch rule is worth having as a cheap regression guard on #200's
lesson; self-certification stays a review discipline. Recording the rule where
it can be read — as this document and the exemplars above — is the mechanism
available.

## Coverage: every module and its verdict

47 modules. "Clear" means: reviewed against both modes, nothing to report — the
assertions are on values the test supplied, effects it can observe, or a
witness independent of the SUT.

| Module | Verdict |
|---|---|
| `test_acceptance.py` | Clear — real commands in real repos; preconditions checked by exit status and tree state |
| `test_availability.py` | **[F1](#f1)** — wall clock for concurrency. Probe-count tests (`:152`) are exemplary |
| `test_breadth_rig.py` | Clear — `summarise` (`:203`) is checked against rows the test wrote |
| `test_bundle_ladder.py` | Clear — manifests, digests and byte-for-byte comparisons against vendored files. See [skips](#silent-skips) |
| `test_capability.py` | Clear — table-driven over a fixture table |
| `test_capacity.py` | **Reference.** Post-#200: barrier rendezvous, `Observer` as an independent counter, no assertion on duration |
| `test_capacity_hostwide.py` | **Reference.** Cross-process log replay and a host-side `flock` proof |
| `test_catalog.py` | Clear — `catalog() is catalog()` (`:425`) is object identity, not a self-report; CLI tests assert on stdout, which is the surface |
| `test_changeset.py` | Clear — attribution checked case-for-case against git (`:242`); subprocess count instrumented (`:160`) |
| `test_claims.py` | Clear — validates records against pinned manifests and digests |
| `test_config.py` | Clear — parsed values against literal YAML |
| `test_contract.py` | Clear — parsed values and refusals against literal contracts |
| `test_detect.py` | Clear — `:355` asserts duplicates collapse *before* probing, which is the actual mechanism |
| `test_docgen.py` | Clear — generated text against the schema and the committed file |
| `test_escalate.py` | **[F6](#f6)** (minor). `Recorder`/`Spy` (`:172`, `:206`) are exemplary |
| `test_gate_runner.py` | **Exemplar** — subprocess counting (`:142`), exploding stub (`:49`) |
| `test_initialize.py` | Clear — asserts on the written config file and on refusals leaving it untouched |
| `test_javascript_adapter.py` | Clear — findings against known added lines |
| `test_orchestrator_cache.py` | **[F2](#f2)** — the largest finding |
| `test_orchestrator_context.py` | **[F4](#f4)** (`:329`). `:291`'s "never read" is a claim about the plan, not about I/O — accurate as written, worth a name that says so |
| `test_orchestrator_decompose.py` | See **[F5](#f5)** — `:360`, `:497` use `estimate_tokens` as its own yardstick. Otherwise clear |
| `test_orchestrator_index.py` | **[F3](#f3)**. Skip counters (`:85`, `:96`) are correctly witnessed |
| `test_orchestrator_read.py` | **[F4](#f4)** (`:57`) |
| `test_orchestrator_repo.py` | Clear — git state read back with git |
| `test_orchestrator_resolve.py` | Clear — candidates against a fixture repo |
| `test_orchestrator_signatures.py` | Clear — extracted signatures against known source |
| `test_pool.py` | Clear — bindings against literal config; `:158` reads the source tree for imports |
| `test_propose.py` | Clear — proposals against a fixture capability table |
| `test_python_adapter.py` | Clear. See [skips](#silent-skips) |
| `test_python_arm.py` | Clear — vendored files byte-for-byte |
| `test_reach_corpus.py` | **Exemplar** — every total re-derived from the corpus |
| `test_reach_counts.py` | **Exemplar** — each count independently recomputed and cross-checked (`:126`, `:148`) |
| `test_reply_corpus.py` | Clear — pinned replies replayed whole |
| `test_route.py` | Clear — `Recorder` (`:157`) cross-checks `history` and `attempts_spent` against recorded calls |
| `test_runner.py` | Clear — asserts on the bytes sent (`sent.payload`, `sent.url`, `sent.headers`); clock injected (`:173`). `capacity.usage()` reads are a validated collaborator, see above |
| `test_sandbox_cli.py` | Clear — stdout is the surface |
| `test_sandbox_docker.py` | **Exemplar** — `RecordingRunner` proves `rm --force` and `kill` were issued |
| `test_sandbox_image.py` | **Exemplar** — `built is False` cross-checked against `built_tags()` |
| `test_sandbox_stack.py` | Clear — detection against manifests the test wrote |
| `test_sandbox_tempdir.py` | Clear — workspace removal, env scrubbing and resets checked on disk |
| `test_scope.py` | Clear — pure matching, parametrised |
| `test_secrets.py` | Clear — findings against known content |
| `test_semantic.py` | **Exemplar** — `ran.marker` (`:511`), recorded ordering (`:483`), digest pins |
| `test_structured_and_preflight.py` | **[F5](#f5)** — `:187` pins the reserve to a band restating it, not to the measurement it came from. The `counted_by` tests (`:153`, `:167`) are clear. See [skips](#silent-skips) |
| `test_type_check_locator.py` | Clear — asserts on the declared checker and that a hostile module is never executed |
| `test_worker_prompt.py` | Clear — assembled text and an injected estimate seam (`:385`) |
| `test_worker_reply.py` | Clear — parser against literal replies |

**Totals:** 47 modules — 6 test-side findings touching 8 of them (F4 spans two,
F5's smaller half is noted in a third) · 8 named as exemplars or references ·
31 clear · 3 carrying silent skips. [F7](#f7) is product-side and sits in no
test module.

## What this asks for next

Fixes are out of scope here by #201's own framing; each finding names its mode
and where its instrument belongs, which is what the issue asked for. Everything
below is filed, so no finding rests on this document being read:

| Finding | Filed as |
|---|---|
| **[F1](#f1)** — the probe stopwatch | **#204** |
| **[F2](#f2)** — the cache with no witness | **#205** |
| **[F3](#f3)**, **[F4](#f4)**, **[F6](#f6)** — counters checked against their own addends | **#206** (one issue; each is a few lines) |
| **[F5](#f5)** — `ESTIMATE_RESERVE` untied from its measurement | **#207** |
| **[F7](#f7)** — the stale `#117` pointer | a comment on **#66**, whose subject it is |
| [Silent skips](#silent-skips) | a comment on **#4**, where "what a green run means" already lives |

#204 and #205 are one change each and independent of everything else. #207 is
two changes of different weight: reading the p05 out of `summary.json` is the one
that makes CLM-0011 checkable, and the `estimate_tokens` unit test is a tidy-up.

Neither of the last two earned a new issue. #201's own instruction — file
against a specific subsystem's home where one exists — points [F7](#f7) at #66
and the skips at #4, and minting duplicates beside them would be the
contradiction DIV-02 exists to catch.

**No finding warrants a new shipped field.** #200's answer was "both" because
#185 had made the capacity bound host-wide, giving an operator a question the
telemetry could not answer. Nothing here has that property: `CacheStats`,
`IndexStats`, `plan.spent`, `PromptBuild.tokens` and `ESTIMATE_RESERVE` are all
already the right numbers to ship — several of them, as [F5](#f5) shows, the
product of measurements this repo has already done properly. They were simply
never validated by the suite. That is the sweep's answer to #201's "interesting
question", and it is a narrower answer than #200's — which is the point of not
answering it by reflex.
