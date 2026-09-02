# Prior art — the nearest ten repositories (#175)

Status: complete, and **independently re-read**. Ten reviewed (one disqualified on
reading, replaced, then re-qualified by the second read), plus a four-repository
annex. A second pass by six independent readers re-derived every section against
the code: it **ran four suites the first pass reported as unrunnable**, corrected
one disqualification, sharpened two findings and added one about mcgyvr's own
`capacity.py`. Its results are in *§ Second read* and are cross-linked from each
section they correct. 2 issues filed (#183, #184); findings recorded on #179,
#183 and #184.
Started: 2026-08-06. Lane: `lane/175`.

## There is a plain-language summary, and it is not the record

`docs/prior-art-summary-2026-08-06.pdf` — nine illustrated pages, written for the
owner to read end to end. `docs/prior-art-summary-2026-08-06.tex` is its source,
committed so the PDF can be regenerated rather than only replaced
(`xelatex prior-art-summary-2026-08-06.tex`, needs TikZ and TeX Gyre Heros).

**It is a derived artefact for a human reader, and nothing may be cited from
it.** It rounds numbers, names five findings out of the dozens below, drops every
pinned sha, and explains mechanisms by analogy where this document explains them
by code. Those are the right choices for its job and the wrong ones for evidence.

So: **where the summary and this document disagree, this document wins** — the
same rule this review applies to a README against its code, turned on the
review's own output. An agent reading for what mcgyvr should do next wants this
file. The PDF is for the owner's eyes.

## Why this document lives in `docs/` and not `records/`

`records/evidence/` is the precedent for vendored material and `records/` is
append-only under REC-01. This document is written incrementally — one repository
at a time, with earlier sections corrected as later ones contradict them — so
committing it under `records/` would manufacture exactly the unclearable
mutation warns #171 is open about. A review that must be revised while it is
written belongs in `docs/`. Anything here that hardens into a claim moves to
`records/claims/` through ADR-0004's re-measurement, not by being filed in a
different directory.

#172's audit reached the same answer independently, landing at
`docs/local-ai-review-2026-08-05.md` (PR #176) hours before this was written.
The filename here matches that precedent rather than the subdirectory this
started in.

## Its overlap with the local-ai audit, stated up front

`docs/local-ai-review-2026-08-05.md` reviewed one repository under the same
filter, and three of its seven findings touch the same open issues this survey
does. That is fortunate rather than redundant: the two reviews read *different*
codebases, so where they agree the agreement is independent, and where they
disagree the disagreement is the finding. Both cases are marked inline below
rather than left for a reader to notice.

## The filter, restated

Take only what a reader who does not trust this review can re-derive: code at a
pinned sha, a test and what running it did, a number with its run. Leave README
architecture, self-reported benchmarks, and roadmaps. Where a README and the
code disagree, the code wins and the disagreement is itself recorded.

Because selection is fit-first rather than star-ranked (#175, amended
2026-08-06), the evidence bar rises rather than falls for the small repositories:
last-push and archived status are recorded for every entry, cited tests are run
or reported as not-run with the reason, and anything surviving only because
nobody has checked it is labelled unverified rather than quietly promoted.

## Environment constraint, stated once

The review host has `node` and `python3` but **no Go toolchain and no bun**.
Repositories in those ecosystems have their tests read but not run, and every
such case says so at the point it matters. This is a real limit on extraction 2
for those repositories and is not softened anywhere below. Two further suites
could not be run for reasons belonging to the repositories rather than the host,
and both are recorded where they occur (RA.Aid: no lockfile, dependencies
unresolvable six months on; SWE-agent and SWE-ReX: a live container runtime).

## Quoting third-party source: a convention

Third-party code quoted at a pinned sha is fenced as `text`, never as the
language it is written in. `ruff format` reflows a `python`-tagged block, and a
reflowed quotation is no longer evidence of what the upstream source says — which
matters most in exactly the sections where the line's *shape* is the finding.
`pyproject.toml` already excludes `records/evidence` from the formatter for the
same reason; this is that call applied to prose. Where the fence tag would
otherwise be load-bearing for a reader, an HTML comment above the block says
why.

---

# 1. plandex-ai/plandex

- **Pinned:** `e2d772072efadbe41d2946d97d79be55532dbab5`
- **Last push:** 2025-10-03 (10 months before this review). Not archived.
- **Stars:** 15.6k. **Criteria:** 5/5 — the closest fit of anything surveyed.
- **Tests:** 6 `_test.go` files repo-wide. **Not run — no Go toolchain on the
  review host.** Read only.

## Code / features

**Nine named roles, each bound to its own model, with typed fallback chains.**
`app/shared/ai_models_roles.go:6-17` declares `planner`, `coder`, `architect`,
`summarizer`, `builder`, `whole-file-builder`, `names`, `commit-messages`,
`auto-continue`. `app/shared/ai_models_packs.go:125-192` binds them: the planner
takes `anthropic/claude-sonnet-4` or `openai/o3-high`, the builder takes
`openai/o4-mini-medium`. Judgment gets the strong model; execution gets the cheap
one.

That is **#178's decision, reached independently by a shipping product** — but
recorded here as convergence, not as evidence. Nothing in the repository measures
the split; it is their design choice sitting next to ours. It raises confidence
that the shape is natural, and it proves nothing about whether it is right.

**Model selection is a function of input size, not a fixed rung.**
`ModelRoleConfig.GetRoleForInputTokens` (`app/shared/ai_models_large_context.go:47`)
takes the estimated input tokens, compares them against the role's declared
`MaxTokens`, and walks `LargeContextFallback` until one fits.
`GetRoleForOutputTokens` does the same against `GetReservedOutputTokens`.

**This is the closest thing in the survey to #158.** Our issue says no rung
declares its context window, so the decomposer's ceiling is a chosen number.
Plandex declares the window per model and *routes on it* — the ceiling is derived
rather than picked, and input and output are separate chains because they fail
differently. Whatever #158 builds, this is the shape to argue against.

**And it is where the two reviews disagree, which makes it the more useful
finding.** `docs/local-ai-review-2026-08-05.md` item 2 concluded that an
operator-declared context window "is not just missing — it is dangerous". Plandex
declares one per model and makes it the routing key. Both systems shipped; they
made opposite bets on the same fact. The reconciliation available from the code
is that plandex's declaration is **vendor-published metadata attached to a model
id**, not an operator's guess about a rig — which is a different quantity from
the one local-ai found dangerous, and suggests #158's answer is about *who
declares it* rather than *whether it is declared*. Recorded as a reading of two
codebases, not as a resolution: nothing here measures which bet pays.

## Tests / verification

**A differential syntax gate.** `app/server/model/plan/build_structured_edits.go:224`
runs tree-sitter validation on the post-edit file **only if** three things hold:
a parser exists for the path, the *pre-edit* file parsed clean
(`preBuildStateSyntaxInvalid`, set at `build_load.go:189`), and the pre-check did
not time out (`syntaxCheckTimedOut`, 500ms limit at `validate.go:15`). Three
different not-a-worker-failure conditions, each tracked separately.

**mcgyvr already holds this line, and holds it finer.** `gate/acceptance.py:123`
refuses to judge against a baseline it cannot establish
(`acceptance-baseline-failing`, `acceptance-baseline-timeout`), and
`gate/adapter.py:17` attributes findings to added lines so pre-existing state
cannot fail a worker at all — per-line where plandex is per-file. **No new issue.
Recorded as convergent and already covered**, which is a result rather than a
gap.

**Six test files in a 15.6k-star repository**, none covering role selection,
fallback, or model dispatch. The tested surface is the deterministic string
machinery — `structured_edits_test.go` (33k), `unique_replacement_test.go`,
`subtasks_test.go`, `reply_test.go`, `whitespace_test.go`,
`tell_stream_processor_test.go`. Extraction 2 from this repository is therefore
thin, and the thinness is the honest finding: the parts a reader would most want
corroborated are the parts nothing corroborates.

## Insights / wisdom

**The fallback chain degrades silently at its end, and the code says so.** The
comment above `GetRoleForInputTokens` reads: "note that if the token number
exceeds all the fallback models, it will return the last fallback model." So a
request larger than every declared window is dispatched to a model that provably
cannot hold it, rather than refused. `maxFallbackDepth = 10`
(`ai_models_large_context.go:3`) does the same on the other axis — it `break`s
out of the walk and returns whatever it was holding.

mcgyvr has already chosen the opposite, in writing: `decompose.py`'s "a request
that cannot be decomposed produces an explanation… a degenerate single contract
is worse than a refusal, because it looks like a plan." **This is the failure
mode #177's second rider names — a silent stop at a depth nobody chose —
observed in production code rather than argued from first principles.** Worth
citing there; no new issue.

**The token reserve is multiplicative, and flat.**
`inputTokens = int(float64(inputTokens) * (1 + paddingPct))`
(`ai_models_large_context.go:53`), with `TokenEstimatePaddingPct: 0.10` repeated
across every model in `ai_models_available.go` (`:148`, `:177`, `:205`, `:233`,
`:250`).

**#173 argues this exact shape is wrong** — that a prompt-fit reserve is
multiplicative while the backend's overhead is additive, so a percentage cannot
cover both. Plandex ships the multiplicative form at a flat 10% for every model.

State the limit of that observation precisely: **it corroborates that a second
system needed a reserve and reached for a percentage; it is not evidence that the
percentage works, and nothing in the repository measures whether it does.** A
second system making the same modelling choice is a reason to check the
reasoning, not a reason to adopt or to dismiss it.

**Where the two reviews agree, and the agreement is independent.**
`docs/local-ai-review-2026-08-05.md` item 1 — "a token estimate has an additive
floor that a multiplicative reserve cannot cover" — is the same axis, reached
from a different codebase, and that one had a measurement behind it. So #173 now
has a measured argument on one side and, on the other, two independent systems
that both reached for a percentage anyway. The useful reading is not that
plandex is wrong; it is that **the multiplicative form is the one people reach
for by default**, which is what makes an additive floor worth stating explicitly
rather than assuming a implementer will derive it.

**Decomposition is parsed out of markdown with a string split and a regex.**
`app/server/model/parse/subtasks.go:10` splits the model's reply on `### Tasks`,
falls back to `### Task`, and returns `nil` — logging, not erroring — when
neither heading appears. Tasks are then recognised by `^\d+\.\s`. One test
covers it.

The whole plan for a coding run is recovered from prose by heading match, with a
silent empty result as the failure mode. mcgyvr's decomposer emits through the
public contract loader as its only exit, so a malformed proposal becomes a
refusal carrying the loader's own message. **#174 — a fenced refusal parsing as
file content — was this same family of bug in our own codebase**, and this is
what the mature version of that mistake looks like at 15.6k stars. (#174 was
fixed and merged at `bcf8e72` while this survey was being written: a block
carrying no code is now a refusal, judged only against a known target and only
for the languages the gate itself owns.)

The local-ai audit found the third instance (item 3: a well-formed refusal
defeats a syntax gate *and* silently stops escalation). **Three codebases, three
occurrences, one shape: model output is recovered by pattern match, and the
absence of the pattern is indistinguishable from an empty result.** That is the
strongest generalisation this survey has produced so far, and it is worth more
than any single repository's version of it.

## What has no home

Nothing from this repository was left homeless — but nothing from it became a new
issue either. Every transferable item landed as corroboration for a decision
mcgyvr had already made (#178, #177) or as an argument-shaped input to one that is
open (#158, #173). **A first repository that files zero new issues is a
legitimate outcome**, and per #175 it is stated rather than padded.

---

# 2. OpenAutoCoder/Agentless

- **Pinned:** `5ce5888b9f149beaace393957a55ea8ee46c9f71`
- **Last push:** 2024-12-22 — **20 months before this review**, the oldest entry
  in the ten. Not archived. Every finding below is dated accordingly: this
  describes a 2024 pipeline against 2024 models.
- **Stars:** 2.1k. **Criteria:** 3/5 — decomposes into fixed phases, runs
  deterministic validation the model did not author, and selects among candidate
  patches. No worker-class ladder, no per-task isolation of its own.
- **Tests:** **none.** `agentless/test/` is not a suite for Agentless; it is the
  apparatus that runs the *target repository's* tests. There is no unit test in
  the repository. Stated plainly because the fit-first selection was justified on
  extraction 2, and here extraction 2 comes from the verification apparatus
  rather than from a suite.

## Code / features — one finding, and it is the survey's first new issue

**A demonstrating test is verified by a separate run with the opposite expected
outcome.** `agentless/test/run_reproduction_tests.py:36-64` runs the generated
reproduction test against the *unpatched* repository — `patch: ""`,
`apply_model_patch=False` — and writes it out with `verified: True` only if it
reproduces there. A generated test that passes on broken code is discarded; it
demonstrates nothing.

The regression set is derived the same way and kept separate
(`run_regression_tests.py:33`, `save_passing_tests`): run the suite on the base,
keep the tests that **passed**, judge the patch only against those. Its own
comment carries a refinement worth the whole read — XFAIL tests are excluded
from the passing set *"because they are expected to fail"*.

**Reading that against our own code found a live collision.** The catalog
defines `failing_test_first` as a command that "must fail before the change and
pass after" (`data/task-catalog.json:60`). `Acceptance.precondition()` runs every
acceptance command on the unchanged tree and refuses the run if any fails
(`gate/acceptance.py:116`, `acceptance-baseline-failing`). `contract.py:409`
makes `acceptance` a flat `str_list` with no per-command evidence tag, so nothing
can distinguish the two. `bug_fix` is therefore unreachable in both directions —
include the demonstrating command and the preflight refuses the run; omit it and
rule 5 is satisfied by the regression command alone, leaving the type's own
warrant resting on a guarantee nothing enforces.

**Filed as #183.** It is latent rather than live — `Acceptance(...)` is
constructed nowhere in `src/` yet and the decomposer never emits `bug_fix` — and
that is exactly why it is worth filing now: the run loop is about to be wired,
and wired against the current shape it would encode the collision instead of
revealing it.

## Tests / verification

Covered above — the apparatus *is* the finding. One further item, weaker and
recorded with its objection attached:

**A model is asked which tests to exclude before the patch exists.**
`select_regression_tests.py:17` prompts: "identify the tests that should not be
run after applying the patch … as the original functionality may change". The
model sees the issue text and the test list, but **not** the patch.

This is a model authoring the scope of its own gate, which is the line mcgyvr
draws and does not cross. What it buys is fewer false regressions on tests that
legitimately change behaviour; what it costs is that the same model that writes
the fix can silence the test that would catch it. **Recorded as a boundary
observation, not a candidate.** It is also the cleanest illustration of why the
gate/verifier ordering in `escalate.py` is worth having: a check the model can
edit is not a check.

## Insights / wisdom

**`MAX_CONTEXT_LENGTH = 128000`, hardcoded** (`select_regression_tests.py:13`).
The third instance in this survey of a ceiling chosen as a literal — #158's
shape again, now in a third codebase.

**The output parser is one line and fails soft.**
`_parse_model_return_lines` is `content.strip().split("\n")` guarded by
`if content:`, returning `None` implicitly otherwise. Fourth instance of the
pattern-match shape recorded above: the absence of the pattern is
indistinguishable from an empty result, and here an empty result means "exclude
no tests", which fails safe by luck rather than by design.

**What Agentless is remembered for is not what it is useful for.** Its public
claim was that a fixed three-phase pipeline beat agent loops on SWE-bench. That
number is self-reported, from 2024, on a benchmark whose contamination
discussion post-dates it — **rejected by the filter, and named here because it is
the thing most likely to be re-proposed from this repository.** What survived the
filter instead is the plumbing nobody cites: two runs, two expected outcomes, two
sets.

---

# 3. AutoCodeRoverSG/auto-code-rover

- **Pinned:** `585d3e639aeda58ef0b6a151dd1cc2721a94d267`
- **Last push:** 2025-04-24 (15 months before this review). Not archived.
- **Stars:** 3.1k. **Criteria:** 4/5 — phase decomposition, container per task
  (SWE-bench-docker), deterministic patch validation, model-agnostic dispatch
  across seven providers. No branch/PR delivery.
- **Tests: 36 files, and they were RUN.** `test/app/agents/test_agent_reviewer.py`
  passes 7/7; repo-wide `179 passed` with **16 modules erroring at import** for
  dependencies outside the subset installed here (the project expects a conda
  environment). The 179 is therefore a real number for the modules that
  collected and not a claim about the whole suite.

**The first repository in this survey whose tests ran.** That was the argument
for the fit-first rebalance, and this is where it pays.

## Code / features

**A reviewer agent that is given the empirical before/after, not asked to
predict it.** `app/agents/agent_reviewer.py:126-153` builds a thread carrying
five things: the original issue statement, the generated test, the patch, and
the stdout/stderr of running that test on **the unpatched program** and on **the
patched program**. The model is not asked whether the patch will work. It is
shown what happened and asked whether that means what it appears to mean.

For #179's Q2 — *fresh context relative to what?* — this is a fourth option
beyond the three that issue lists, and the one making the smallest demand on the
model's judgment. **Recorded on #179 directly** rather than only here.

**The verdict is two decisions, not one.** `Review` carries `patch_decision` and
`test_decision` separately, and the system prompt says outright: *"NOTE: both
the test and the patch may be wrong."* With #183 open — where the demonstrating
command is exactly the instrument that might be wrong — the question of whether
a verifier may blame the instrument rather than the work is one mcgyvr has not
asked. Raised on #179 as an eighth question.

**A rejection must carry advice.** `extract_review_result` (`:63`) rejects a
`no` verdict whose advice field is empty, and the retry loop treats that as no
verdict at all — up to five attempts, then `InvalidLLMResponse` (`:107`).
Fail-closed and bounded, which is #179's Q5 answered in a shipped system.

## Tests / verification — the finding is a test that ratifies a defect

Their advice rule does not do what their prompt asks:

<!-- Fenced as `text`, not `python`, on purpose: this is their source quoted verbatim at
     the pinned sha, and the line is 101 chars, so `ruff format` rewraps it across three
     lines and the quote stops matching what is upstream. Same reason `records/evidence`
     is excluded from the linter in pyproject.toml — do not restore the `python` tag. -->

```text
if ((patch_decision == NO) and not patch_advice) and ((test_decision == NO) and not test_advice):
    return None
```

The prompt asks for advice **per field**; the guard is a conjunction **across**
both. Probed by execution rather than by reading — the standard this review set
for itself:

| input | result |
| --- | --- |
| `patch=no` with empty advice, `test=yes` | **accepted as a verdict** |
| both `no`, both advices empty | rejected (`None`) |

So a rejection carrying nothing actionable passes whenever the other field is
`yes`, which is the ordinary case. And `test_extract_review_result_empty_advice`
**passes while pinning the weaker behaviour**: it exercises only the both-`no`
path, so the test documents the defect instead of catching it.

**This is the most transferable item in the survey so far, and it is not their
bug.** It is that a rule which reads as obviously correct — "a rejection must
come with advice" — is easy to implement one field short, and that *a test
written from the implementation rather than from the rule will ratify the
shortfall and go green forever*. mcgyvr's suite is written the way this project's
was; the defence is writing the test from the stated rule, including the mixed
case, before the implementation exists.

## Insights / wisdom

**No independence between writer and reviewer.** The reviewer calls
`common.SELECTED_MODEL` (`:185`) — the same model that wrote the patch. Their
system judges that a model reviewing its own output is worth having anyway.
Recorded without endorsement: it is the cheapest possible answer to #179's Q4
and the weakest one available, and it is what a system converges on when nothing
forces the question.

**What survived and what did not.** Its published SWE-bench figures are
self-reported and unreplicated — rejected by the filter, and named here because
they are the thing most likely to be re-proposed from this repository. What
survived is the reviewer's *inputs* and its *verdict shape*, both of which are
readable in code and testable without believing anything about a leaderboard.

---

# 4. aorwall/moatless-tools

- **Pinned:** `011ead57a5c81664e9c45e07e1f50b17e695cc63`
- **Last push:** 2025-09-01 (11 months before this review). Not archived.
- **Stars:** 642 — the smallest repository in the ten, selected on fit rather
  than reach, which is what the rebalance was for.
- **Criteria:** 3/5 — deterministic verification the model did not author,
  isolation (docker), multi-provider dispatch. No PR delivery, no decomposition
  into contracts.
- **Tests: 64 files, RUN.** `tests/testing` — **45 passed**, clean. Repo-wide —
  **180 passed, 28 failed, 37 collection errors, 143s**. The collection errors
  are optional dependencies absent from the subset installed here. **All 28
  failures are in one module**, `tests/codeblocks/test_python_parser.py`, which
  is their tree-sitter code-block parser; a failure set concentrated in a single
  grammar-dependent module is consistent with a version mismatch in this
  environment rather than a defect in the repository, and **the cause was not
  established here** — recorded that way rather than reported as "their suite is
  28 red". The module this review depends on is not among them.

## Code / features — the thing they built that we parked

`moatless/testing/` turns raw test output into structured per-test results.
`TestResult` (`schema.py:25`) carries `status` — PASSED / FAILED / SKIPPED /
ERROR / **UNKNOWN** — plus `name`, `file_path`, `method`, `failure_output`, a
parsed `stacktrace` of `TraceItem`s, and a separate `timed_out` flag.

That is precisely the shape an exit code cannot express, and it is what lets a
run distinguish *"three failed, two of which were already failing"* from *"the
suite is red"*. #183 named per-test granularity and scoped it out; this is the
same idea built, so its price is now observable rather than guessed.
**Recorded on #183** rather than opened as a competing issue.

## Tests / verification — 24 captured real logs, asserted down to stack frames

`tests/testing/python/data/` holds 24 real test-output logs captured from the
projects they target — django, pytest, matplotlib, seaborn, sphinx, sympy. The
assertions are not "it parsed"; `test_django_error` checks the extracted
`TraceItem` list frame by frame — file, method, line number, and the source
line's text — and then checks `failure_output` against the trace with the
container mount prefix stripped.

**This is the best extraction-2 artefact in the survey so far.** A parser tested
against invented output proves the parser can read the author's imagination.
These fixtures are captures, so they encode the shapes real suites actually
emit, and the diff between what a fixture contains and what a naive parser
expects *is* the knowledge.

One detail worth keeping regardless of whether we ever parse:
`stacktrace.replace("/testbed/", "")` — a path in sandboxed test output is
container-absolute and has to be normalised before it means anything to the
host. Checked against our code and **not currently a problem**: `acceptance.py`
attributes a failure to the *command* (`path=_label(command)`) and never
extracts a path from output, so there is nothing to normalise. The cost lands
elsewhere instead — a failure names a command, not a test — which is a
consequence of a deliberate choice rather than an oversight.

## Insights / wisdom — the mechanism does not generalise, and that is the finding

`moatless/testing/python/parser_registry.py:14` is a hardcoded
`Dict[str, Type[TestOutputParser]]` mapping **GitHub repository name** to parser
class. Eighteen entries — the SWE-bench project list — with `PyTestParser` as
the fallback for anything else. The parser is selected by *repo identity*, not
by detected framework.

Four Python parsers, 1,073 lines, for eighteen known repositories. Two of those
projects needed bespoke parsers because they print results in a house format.

**So the requirement is evidenced and the mechanism is unavailable to us.**
mcgyvr targets arbitrary repositories, so a repo→parser table cannot exist here;
anything equivalent would have to infer the shape from the output, which is
strictly harder than what they did. Their four-parsers-per-eighteen-repos ratio
is the best available estimate of how much shape variation is out there, and it
is the number to weigh against #183's parked item — not the elegance of the
result.

**A fork we deliberately did not take, confirmed rather than reconsidered.**
ADR-0006's family of decisions says the gate reads the target's own tools and
their exit codes rather than parsing their output. This repository shows what
the other branch costs at the scale of eighteen repositories, and mcgyvr's
universe is not eighteen repositories.

---

# 5. BuilderIO/micro-agent

- **Pinned:** `f33523ce9f9c52a698d13a2883eb2ba7fb4fb462`
- **Last push:** 2024-11-14 — **21 months before this review**, the oldest entry
  in the ten. Not archived.
- **Stars:** 4.3k. **Criteria:** 3/5 — a deterministic gate the model did not
  author (the test suite), multi-provider dispatch including local models, and a
  declared iteration bound. No decomposition into scoped units, no per-task
  isolation.
- **Tests: RUN — 51 passed, 2 skipped, 8 files** (`vitest run --exclude
  src/tests/integration`). Clean.

**The purest form of the thing our acceptance gate does**: `run()` loops
`runOne` until `testResult.type === 'success'`. The test suite is the whole
acceptance bar, and nothing else votes.

## Code / features — #146's question, answered the way we have not

`src/helpers/get-test-command.ts` obtains the acceptance command by **asking a
model**. It reads the dependency file, sends it with a prompt — "I want to run a
single command to execute the tests… should not run in watch mode… should filter
and run the specific test file" — and executes whatever single line comes back,
falling back to a hardcoded `npm test -- <name>` if there is no dependency file
or no answer.

That is #146 — *who supplies the acceptance command for the types whose evidence
needs one* — answered by inference from a manifest. mcgyvr has deliberately not
done this: ADR-0006 locates the target's own type checker, and `decompose.py:465`
refuses to emit `tests_pass` contracts precisely because `locate_test_command`
returning `pytest` for any repository with a `tests/` directory "is a guess about
the runner, not a reading of a declaration".

**Note what the prompt has to carry to work at all**: worked examples for Jest,
Vitest, minitest, rspec, pytest and unittest, plus an explicit no-watch-mode
instruction. That is the same output-shape variation moatless-tools met and
solved with per-project parsers — met here and solved with few-shot examples.
**Two repositories, one wall, two answers**, and both answers are maintenance
surfaces that grow with the number of ecosystems.

Under ADR-0013 this is decomposition-adjacent judgment rather than execution, so
if mcgyvr ever does infer a command, the tier rule applies to whoever infers it.

## Tests / verification — the record/replay that #184 came from

`src/helpers/mock-llm.ts` captures real completions to a JSON record file
(`captureLlmRecord`) for later replay. Roughly fifty lines, and it is how a
non-deterministic component gets a deterministic test.

**This, with moatless-tools' 24 captured logs, is what produced #184**: mcgyvr's
JS/TS sweep generated 160 real worker replies, parsed every one, kept the error
codes and discarded the text — while `test_worker_reply.py` asserts against
hand-authored shapes and #174 is the shape that was missed. Two repositories in
this survey keep the artefact at the moment it is free. We do not.

**#174's fix landed at `bcf8e72` mid-survey, and it sharpens the point rather
than settling it.** The fix is good and the reasoning is careful — a block
carrying no code is a refusal, judged only against a known target. But it added
ten more fixtures and **every one of them is constructed**. The next missed
shape will be missed the same way this one was: by not being imagined. That is
what #184 is about, and it is now about a file that just grew.

## Insights / wisdom — how to end a bounded loop

`run.ts:102` declares `maxRuns = 20`. On exhaustion it does three things: says
`Max runs of 20 reached`, **writes the prompt to a file**, and **prints the exact
command to resume**.

Set that beside plandex, which walks a fallback chain and then dispatches to a
model its own comment admits cannot hold the input. Same structural situation —
a bounded search that did not converge — and opposite handling. **Declared cap,
named exhaustion, recoverable state** is the shape #177's second rider asks for,
and this is the survey's positive example of it against plandex's negative one.

**Who checks the checker — three repositories, three answers.** The demonstrating
test is the instrument every one of these systems depends on, and none of them
trusts it by default:

- **Agentless** runs it against the *unpatched* code and keeps it only if it
  reproduces — machine-verified.
- **auto-code-rover** has a second model judge the test separately from the
  patch, with "both the test and the patch may be wrong" in the prompt —
  model-verified.
- **micro-agent** shows the test to the *human* and iterates on their feedback
  (`iterate-on-test.ts`) — human-verified.

mcgyvr has no answer yet, which is #183 from one side and #179's eighth question
from the other. The useful observation is not which answer is best; it is that
**three independent systems all concluded the instrument needs its own check**,
and none of them left it implicit.

---

# 6. ai-christianson/RA.Aid

- **Pinned:** `e71bb83dcfdf8796d41c746ad99bf4838d1d5914`
- **Last push:** 2026-01-30 (6 months before this review). Not archived.
- **Stars:** 2.2k. **Criteria:** 3/5 — staged decomposition (research → plan →
  implement), multi-provider dispatch with local models, reactive model
  fallback. No gate the model did not author, no per-task isolation.
- **Tests: 89 files. RUN — 764 passed, 6 skipped, 770 collected, 67.87s**
  (`uv sync --frozen --extra dev`, then
  `.venv/bin/python -m pytest -p no:cacheprovider -q --timeout=120`).
  **Corrected by the second read; the paragraph below was wrong and is kept
  with its correction rather than deleted.** `uv.lock` *is* present at this sha
  (672 KB). What fails is `pip install -e '.[dev]'` — 84 collection errors,
  `ModuleNotFoundError: No module named 'langgraph.graph.graph'`, which is their
  own open issue #252 — because the `>=`-only floors in `pyproject.toml` resolve
  to a current langgraph. The lockfile is the fix, not the obstacle, and the
  first read stopped one command short. The finding that survives is narrower and
  still real: **`pyproject.toml` constrains its dependencies with `>=` only**, so
  the environment its suite needs cannot be reconstructed from
  what the repository declares, six months on.

That last point is a finding rather than an excuse. mcgyvr's `Makefile` installs
`--frozen` from `uv.lock` and BUILD-05 exists to keep a clean checkout
installable; here is the counterexample, at a repository that was healthy in
January.

## Code / features

**The token reserve is additive, and model-specific.**
`ra_aid/anthropic_token_limiter.py:306`, `adjust_claude_37_token_limit`:

```text
effective_max_input_tokens = max_input_tokens - model.max_tokens
```

Reserved output is *subtracted* from the input window, per model, in a function
named after the model family that needed it.

**That makes three independent data points for #173**, which argues the
prompt-fit reserve is multiplicative while backend overhead is additive:

| system | shape | basis |
| --- | --- | --- |
| local-ai | additive floor | measured (`docs/local-ai-review-2026-08-05.md`, item 1) |
| plandex | multiplicative, flat 10% | unmeasured |
| RA.Aid | additive, per-model subtraction | unmeasured, and named after the model that forced it |

Two of three subtract; the one that measured found a floor. That does not settle
#173 — nothing here measures — but it moves the multiplicative form from
"reasonable default" to "the one shape nobody who hit the problem kept".

## Insights / wisdom

**A vendored capability table sourced by citation rather than measurement.**
`ra_aid/tool_leaderboard.py:3` is the Berkeley Gorilla leaderboard, pasted in
under a comment reading `# Data extracted at 2/10/2025`, ordered by
`overall_acc`, and used to pick fallback models for tool calling.

The structure is mcgyvr's `data/capability-table.json` — a vendored table with
provenance driving binding decisions. The sourcing is the opposite: ADR-0004
requires inherited research to be re-verified before adoption, and this is
adoption by citation. **Our table carries `vendored_from`, `measurement_rigs`,
`harness_caveats` and per-measurement dates; theirs carries a URL and an
extraction date that is now over a year old and still routing.** Recorded as a
fork not taken, with the staleness as the visible cost.

**Fallback keyed on the failed tool.** `FallbackHandler.handle_failure` /
`attempt_fallback` swap in a different model *bound to the tool that failed*
rather than escalating the whole task. That is a finer-grained reaction than
mcgyvr's rung escalation, and it is only available to a system whose unit of
work is a tool call rather than a contract. Noted, not transferable.

---

# 7. SWE-agent/SWE-agent

- **Pinned:** `3ea751c087f32b16e039a2233dd6eefecef325d5`
- **Last push:** 2026-07-16 — three weeks before this review, the most actively
  maintained entry in the ten. Not archived.
- **Stars:** 20.0k. **Criteria:** 4/5 — issue → patch → PR, sandboxed execution
  (SWE-ReX, reviewed separately below), multi-provider dispatch, bounded spend.
  No decomposition into scoped units.
- **Tests: 21 files. RUN by the second read.** Hermetic no-Docker subset:
  **74 passed, 2 xfailed, 23.66s**. Repo-wide with Docker
  (`-m "not slow and not ctf"`): **108 passed, 1 failed, 2 xfailed, 20
  deselected** — the single real failure is `test_replay`, whose container has
  no `swerex-remote` and no outbound DNS here. (Four further failures were the
  reviewer's own: `PermissionError: 'sweagent'`, the console script absent from
  `PATH` and resolving to the repo's own `sweagent/` directory. They pass with
  `.venv/bin` on `PATH` and are not the repository's.) The first read's "not run
  — needs a runtime" is superseded.

## Code / features — four ceilings, each a named exception

`sweagent/exceptions.py:31-43` declares `CostLimitExceededError` and three
subclasses: `InstanceCostLimitExceededError`, `TotalCostLimitExceededError`,
`InstanceCallLimitExceededError`. Spend is bounded on **two axes** — money and
call count — at **two scopes** — this instance and the whole run — and every
exhaustion is a distinct named failure rather than a return value.

mcgyvr has a `budgets` block and #59 (value-per-token rollup) open. The
transferable part is the shape: **four ceilings, four names**, so a run that
stops can always say which limit stopped it. This is the third instance in the
survey of *declared cap, named exhaustion* (micro-agent's `maxRuns`, SWE-agent's
four, against plandex's silent fallback), and by now the pattern is the finding
rather than any one repository's version of it.

---

# 8. Aider-AI/aider

- **Pinned:** `5dc9490bb35f9729ef2c95d00a19ccd30c26339c`
- **Last push:** 2026-05-22 (2 months before this review). Not archived.
- **Stars:** 48.0k. **Criteria:** 3/5 — a deterministic lint/test loop the model
  did not author, multi-provider dispatch including local models, git commits as
  delivery. No decomposition into contracts, no isolation.
- **Tests: 36 files under `tests/`. RUN by the second read** —
  `.venv/bin/python -m pytest tests/basic/ -q -p no:randomly` gives **471 passed,
  5 failed, 1 skipped, 67 subtests, 136.92s**. All five failures are
  `tests/basic/test_voice.py` raising `SoundDeviceError` from `aider/voice.py:72`
  because this host has no audio input device; with that file ignored,
  **468 passed, 1 skipped, clean**. The first read's "needs network and a
  display" was wrong on both counts — no network access occurs, `pytest.ini` sets
  `AIDER_ANALYTICS=false` and the model calls are mocked. `tests/browser`,
  `tests/scrape` and `tests/help` were not run and no repo-wide claim is made.

## Code / features — the defaults are the finding

`aider/coders/base_coder.py:105-107`:

```text
auto_lint = True
auto_test = False
test_cmd = None
```

**Lint runs automatically; tests do not; and the test command is never
inferred** — it is supplied by the user or absent. Set that against micro-agent,
which asks a model to infer the command from the manifest, and against
moatless/Agentless, which get it from benchmark metadata. **Three repositories,
three sources for the same input**, which is #146 exactly: *who supplies the
acceptance command*. The answers are user-supplied, model-inferred, and
harness-supplied, and aider — the largest and longest-running of the three —
takes the most conservative one.

## Insights / wisdom — the worker is told what the gate will run

`get_platform_info` (`base_coder.py:1148`) injects the lint and test commands
into the system prompt, with the wording switching on whether they run
automatically:

- auto: *"The user's pre-commit runs these lint commands, don't suggest running
  them"*
- manual: *"The user prefers these lint commands"*

**mcgyvr deliberately does the opposite.** `contract.py`'s field layout splits
worker-facing fields (`task`, `target`, `deps`, `interface`,
`stop_conditions`, …) from gate-facing ones, and `acceptance` is on the gate
side — the worker is not told what will judge it.

Both positions are defensible and the trade is legible: aider spends prompt
tokens to stop the model proposing work the harness already does; mcgyvr
withholds the acceptance command so a worker cannot aim at it. The second matters
more when the acceptance command is the thing being satisfied — a worker that
knows the exact test can write to the test. **A fork not taken, recorded with the
reason rather than as an oversight**, and worth re-reading if #146 ever lands on
model-inferred commands, because inference and disclosure interact.

---

# 9. SWE-agent/SWE-ReX — promoted into the ten

**OpenHands was disqualified on reading, and this replaced it.** See the
disqualification note below.

- **Pinned:** `5c995c365dfb1fd5bc56fda688be5d8538f9931f`
- **Last push:** 2026-03-02 (5 months before this review). Not archived.
- **Stars:** 562. **Criteria:** 3/5 — per-task isolation as its entire subject
  matter, backend-neutral execution, and a liveness contract. It is not an agent;
  it is the layer under one.
- **Tests:** 13 files. Not run — most require a container runtime.

This is the closest analogue in the survey to a single mcgyvr *package* rather
than to mcgyvr: `src/swerex/deployment/` is `src/mcgyvr/sandbox/`.

## Code / features

`AbstractDeployment` (`deployment/abstract.py:11`) declares four abstract
members — `start`, `stop`, `runtime`, `add_hook` — plus **`is_alive(timeout)` as
a first-class part of the interface**. Implementations: `docker`, `local`,
`remote`, `modal`, `fargate`, `daytona`, `dummy`. mcgyvr has `docker` and
`tempdir`.

Two things worth carrying:

- **Liveness is part of the sandbox contract, not an afterthought.** A
  deployment can be asked whether it is still there, with a timeout, and
  `_wait_until_alive` logs the container's own output when it does not come up.
  mcgyvr's #141 is the same question one layer over — a verdict that expires
  when a process outlives a run — and it is currently asked only of *sources*,
  never of a sandbox.
- **A `dummy` deployment ships as a first-class backend.** That is the seam that
  makes the rest testable without a runtime, and it is why their abstraction is
  worth more than the count of its implementations.

## Insights / wisdom — where mcgyvr is stronger, checked rather than assumed

`AbstractDeployment.__del__` (`abstract.py:44`) is used for cleanup. Python makes
no guarantee that `__del__` runs — on interpreter shutdown, on a reference cycle,
or under an exception during collection — so a deployment can outlive the process
that made it.

mcgyvr's `Sandbox` is a context manager whose docstring says "Use as a context
manager", with teardown on the exit path and the workspace removed on success.
**That is the stronger guarantee and it was verified here rather than assumed.**
Recorded because the survey's job includes finding the places where the prior art
is behind us, and this is one.

---

# 10. code-yeongyu/oh-my-openagent

- **Pinned:** `4ca872b57e45281a9a81190bb73637729288ffc3`
- **Last push:** 2026-08-05 — the day before this review. Not archived.
- **Stars:** 67.3k. **Criteria:** 3/5 — delegation to categorised subagents,
  model selection per category, plan-before-code staging. No gate the model did
  not author, no isolation. **In the ten for one mechanism.**
- **Tests: `bun` suite. RUN by the second read — 12,965 pass, 27 fail, 34 skip
  across 13,026 tests in 1,663 files, 171.43s** (`bun test packages/`). No bun
  and no `curl` on the host, so bun 1.3.14 was installed via `npm i -g bun` into
  a scratch prefix — the "no bun toolchain" limit was real and removable in one
  command. **The 27 failures are the reviewer's artefact, not the repository's**:
  installing with `--ignore-scripts` skipped their postinstall build. Stated that
  way rather than reported as "their suite is 27 red".
- **Licence: the Sustainable Use License** — non-commercial and internal use
  only. Not merely the `NOASSERTION` the metadata pass recorded: **copying from
  this repository is forbidden outright**, which is the strictest licence in the
  survey and the one place where #175's "findings move as decisions, not as
  files" is a legal requirement rather than a preference.

## Code / features — #162's routing matrix, factored the way we would want it

`packages/delegate-core/` is described by its own `AGENTS.md` as two
"harness-neutral primitives … purely functional — zero state, zero IO, all deps
injected". One of them resolves which model a delegation runs on.

`model-selection.ts` is 274 lines with a 167-line test file beside it and nine
cases. The resolution order, as its `AGENTS.md:19` states it:

1. user model override (promote the first reachable one if unreachable)
2. **skip sentinel if caches are cold** — `{skipped: true}` rather than a guess
3. category default model (user-set taken as-is, else fuzzy-matched)
4. user `fallback_models` array
5. hardcoded per-entry `fallbackChain` (exact, then fuzzy)
6. system default
7. `undefined`

Three things mcgyvr should take from that, and one it should not:

- **Selection is a pure function with injected dependencies.** #162 is a design
  task; this is the shape that makes a routing matrix testable without a rig, and
  it is the single most reusable idea in this repository.
- **Cold caches produce a sentinel, not a fallback.** Step 2 refuses to choose
  when it cannot see the world, and says so in the return value. That is
  mcgyvr's "absence is an outcome, not an error" written into a routing
  function, arrived at independently.
- **The chain ends at `undefined`**, not at "the last thing we looked at" — the
  opposite of plandex's terminal behaviour, in the same kind of chain.
- **Not to take: fuzzy matching of model names** (steps 3 and 5). A binding that
  resolves by string similarity can silently bind a model nobody chose, which is
  the failure #164 already cost us once.

**They also separate proactive from reactive fallback** (`AGENTS.md:389`):
`model-fallback` chooses before dispatch from hardcoded chains;
`runtime-fallback` reacts to `session.error` and is configurable per category.
mcgyvr currently has proactive binding (`propose.py`) and reactive escalation
(`escalate.py`) but has never named them as two halves of one policy. #162 should
inherit that vocabulary even if it inherits nothing else.

---

# Disqualified on reading: OpenHands/OpenHands — and re-qualified by the second read

> **Superseded in its conclusion, not in its observations.** Every fact below is
> confirmed at this sha. The inference drawn from them — that the agent is absent
> — is wrong: it was **migrated**, ten days before the pin, and the second read
> found it, read it and ran it. See *§ Second read* for
> `OpenHands/software-agent-sdk`, which restores this entry to the ten and is the
> survey's best single source on #158 and #179. This heading is left standing
> because the miss and its correction are both part of the record.

- **Pinned:** `56638693908b8ac83a2fa3bde6eb6c33aae37f4b`, last push 2026-08-05,
  83.2k stars.
- **Selected at 4/5 from its README and metadata. It scores 0/5 on the code.**

`package.json` names it `@openhands/agent-canvas` v1.10.0. The repository at this
sha is a TypeScript/React/Electron front end — vite, tailwind, playwright,
react-router — with **four Python files in the whole tree**, one of which is a
canvas UI tool. There is no decomposition, no worker ladder, no gate, no sandbox
here. The agent runtime the README describes is not in this repository.

**This is the review's own selection rule failing, caught by the rule that was
supposed to catch it**: *where the README and the code disagree, the code wins,
and the disagreement is itself the finding.* The fit table in the amendment
comment was built from descriptions and topics, and one entry in fifteen did not
survive contact. Recorded rather than quietly swapped, because a survey that
edits away its own misses cannot be audited.

Two things in it are still worth having, and both are checkable config:

- **`stryker.config.mjs`** — mutation testing wired to vitest, mutating
  `src/**/*.{ts,tsx}` with generated files and fixtures excluded. **mcgyvr does
  mutation testing by hand in every lane** — session records read "Eight
  mutations, all caught" — which is the same practice without the tooling.
- **Mock-LLM end-to-end configs** — `playwright.mock-llm.config.ts`,
  `playwright.mock-llm-docker.config.ts`, `build:mock`, `dev:mock`. A third
  independent instance of driving a non-deterministic dependency from recorded
  or stubbed responses, after micro-agent's `mock-llm.ts` and moatless's captured
  logs. #184 again, from a third direction.

---

# Annex — read for one question only

Concurrency, isolation and queueing across parallel runs, per the owner's
position that mcgyvr is promptable by human and agent and that multiple
instances may run at once. These are **not part of the ten** and were not read
for the three extractions.

## multica-ai/multica — `854b6c17`, 44.2k stars

The annex's payoff, and it is a test.

`server/cmd/server/autopilot_schedule_job_test.go:339` —
`TestAutopilotScheduleJobTwoRunnersSingleWinner`, whose comment cites a
production incident by ticket: *"covers the multi-replica claim race from
MUL-3551 §1. Two scheduler.Manager instances tick concurrently against the same
trigger; exactly one should win the claim, the other no-ops via the
sys_cron_executions uniqueness key."*

Three transferable things:

- **The claim is won by a uniqueness key, not by a lock.** Two runners race on an
  insert; the loser no-ops. No coordinator, no lease, nothing to leak.
- **The key is derived from the work, not from the worker** — `plan_time` plus
  job name and scope. That is what makes "the same work" identifiable across
  replicas, and it is the whole design.
- **Crash-after-claim is a separate test** (`:212`): recovery must keep exactly
  one run row, and a retry must *reuse* the original row rather than create a
  second. Idempotency under crash, tested.

The test's tolerance is also worth copying: it accepts `[1,2]` execution rows and
explains why in the assertion — two ticks racing a minute boundary can produce
two distinct plan_times — so the acceptable non-determinism is written down
rather than tuned away.

**mcgyvr already runs this exact mechanism one level up.** `baseline lane claim`
is atomic branch creation at origin: two agents claiming one issue race on a
refname and exactly one wins. The lane protocol *is* a uniqueness-key claim. If
run-level claiming is ever needed for concurrent instances, the design question
is already answered inside this repository — the open part is what the key is
derived from.

## stablyai/orca — `ff01fad4`, 38.1k stars

Fan one prompt across N agents, each in its own git worktree, compare and merge
the winner. Best-of-N by isolation rather than by sampling — the same idea
ADR-0004 lists as "best-of-N execution consensus" (#99's neighbourhood), with the
isolation making the comparison honest. Relevant if concurrency is ever used for
redundancy rather than throughput; nothing in it needs to be built now.

## dagger/container-use — `7461f71f`, 4.0k stars

Environments are addressable by id and loaded with explicit state:
`Load(ctx, dag, id, state, worktree)` (`environment/environment.go:89`), guarded
by an `RWMutex`. The state is passed in rather than discovered, which is what
makes an environment resumable by another process. mcgyvr's sandbox is
context-manager-scoped and deliberately not resumable — a different bet, and the
right one while nesting is refused (ADR-0012).

## cline/cline — `543dd0d8`, 65.7k stars

Coordinator splits subtasks and delegates to specialists with their own tools and
context, team state persists across sessions, worktree support, Ollama/LM Studio
bindings. Closest of the annex to being a callee, and the only one that would
have been a genuine borderline call for the ten. Not read further: its
decomposition is conversational rather than contractual, so its answers to the
three extractions would be about session state, not about gates.

---

# What the survey produced

## The ten, and what each was worth

| # | repo | fit | tests | yield |
| --- | --- | --- | --- | --- |
| 1 | plandex | 5/5 | 6 files, not run (no Go) | corroborates #178; the shape #158 must argue against; #177's rider observed |
| 2 | Agentless | 3/5 | none exist | **#183 filed** — two runs, opposite expected outcomes |
| 3 | auto-code-rover | 4/5 | **run**: 7/7, 179 repo-wide | four answers on #179 + an eighth question; a test that ratifies a defect |
| 4 | moatless-tools | 3/5 | **run**: 45 clean; 180/28/37 repo-wide | prices #183's parked item; 24 captured logs |
| 5 | micro-agent | 3/5 | **run**: 51 passed | **#184 filed**; #146's model-inferred answer; how to end a bounded loop |
| 6 | RA.Aid | 3/5 | **run**: 764 passed, 6 skipped | third data point on #173; a stale vendored table; **and a gate that has not executed since 2025-01-27** |
| 7 | SWE-agent | 4/5 | **run**: 74 hermetic, 108 with Docker | four ceilings — but three exit statuses; #183's baseline rule already built |
| 8 | aider | 3/5 | **run**: 468 passed (voice excluded) | #146's conservative answer; 17% of its routing table is measured |
| 9 | SWE-ReX | 3/5 | not run — needs a runtime | liveness in the sandbox contract; where we are stronger |
| 10 | oh-my-openagent | 3/5 | **run**: 12,965 pass | **#162's shape**: routing as a pure function, seven steps, sentinel on cold cache |
| — | OpenHands (front end) | 1/5 on code | n/a | the agent was migrated out, not absent |
| 7b | OpenHands SDK | 3/5 | **run**: 5,696 + 375 passed | the condenser trigger is 80 *events*; a verifier that raises votes `HIGH` |

**Nine of twelve had their tests actually executed** — four of them only on the
second read, which ran every suite the first pass had recorded as unrunnable
except SWE-ReX's. Every remaining not-run has its reason at the point it matters.
The first pass's four not-runs were: one wrong (aider needed neither network nor
display), one one command short (RA.Aid's lockfile), one a real limit that a
single `npm i -g bun` removed, and one genuine (SWE-ReX needs a container
runtime). **Three of four "cannot run" verdicts did not survive a second
attempt**, which is the most transferable process finding in this document.

## Two issues filed, and why only two

**#183** — `failing_test_first` must fail at baseline and the acceptance
preflight refuses any command that does. Latent today; the run loop is about to
be written around the shape that hides it.

**#184** — worker replies are parsed and discarded, so the parser's own corpus is
thrown away where it is free. Three repositories keep theirs.

Everything else landed on issues that already existed (#179, #183) or corroborated
decisions already made (#177, #178). **That ratio is the expected one** and #175
said so in advance: most of what looks liftable is already filed, and usually
narrower than the obvious lift.

## The findings that are about more than one repository

**1. Declared cap, named exhaustion — and what its absence looks like.** Four
repositories bound a search: micro-agent's `maxRuns = 20` (writes the prompt to a
file and prints the resume command), SWE-agent's four named limit exceptions on
two axes at two scopes, oh-my-openagent's chain that ends at `undefined`, and
plandex's chain that ends by dispatching to a model its own comment admits cannot
hold the input. Three do it well; the fourth is what ADR-0012's second rider was
written against, and it is the largest of them.

**2. Model output recovered by pattern match, where absence and empty are the
same value.** plandex splits a reply on a `### Tasks` heading and returns `nil`
when it is missing. Agentless's `_parse_model_return_lines` is
`content.strip().split("\n")` behind an `if content:`. local-ai's well-formed
refusal defeated a syntax gate. Ours was #174, fixed at `bcf8e72` mid-survey —
with ten more constructed fixtures, which is what #184 is about.

**3. Nobody trusts the instrument.** Every system that generates a demonstrating
test checks it, and each chose a different checker: Agentless runs it against
unpatched code (machine), auto-code-rover has a second model judge it separately
from the patch (model), micro-agent shows it to the user (human). None left it
implicit. mcgyvr has no answer — #183 from one side, #179's eighth question from
the other.

**4. Who supplies the acceptance command — three answers, no consensus.**
User-supplied (aider, `auto_test = False`, `test_cmd = None`), model-inferred
(micro-agent, few-shot over six frameworks), harness-supplied (moatless and
Agentless, from benchmark metadata). That is #146, and the survey's contribution
is that the largest and oldest of the three takes the most conservative option.

**5. The reserve is additive twice and multiplicative once.** For #173: local-ai
measured an additive floor, RA.Aid subtracts reserved output per model in a
function named after the model that forced it, plandex multiplies by a flat 10%
everywhere. Nothing here measures anything, so #173 is not settled — but the
multiplicative form is now the one shape nobody who hit the problem kept.

**6. Two ways to face the same wall, both expensive.** Test output shape varies
by project. moatless answered with four parsers and a repo-name→parser table
that only works because its universe is eighteen repositories; micro-agent
answered with six worked examples in a prompt. Both are maintenance surfaces that
grow per ecosystem, and mcgyvr's exit-code-only position is the third answer
whose cost is that a failure names a command rather than a test.

## What this survey could not do

- **Four suites unrun**, two for host reasons (Go, bun) and two for runtime
  reasons. Extraction 2 for plandex, RA.Aid, SWE-agent, SWE-ReX and
  oh-my-openagent rests on reading.
- **No repository was read exhaustively.** Each was read against mcgyvr's open
  questions, which finds what we were already looking for and is blind to what we
  were not. A second pass with different questions would find different things.
- **The one selection error was caught by reading**, which means selection errors
  that survive reading are exactly the ones this method cannot report.

---

# Second read — independent verification, 2026-08-06

Six readers re-derived sections 6–10 and the annex from the code, each given the
filter and the mcgyvr issue list but **not** the first read's conclusions until
after they had pinned their own sha. Where a first-read claim was named to them,
it was named as a claim to test. This section records only what the second read
**changed**; everything it silently confirmed stands as written above.

The exercise was worth its cost, and the reason is narrow enough to state:
**the first read's errors were all in the same direction.** Four suites reported
as unrunnable, three of which ran. One repository reported as empty, whose code
had moved. A cap structure reported as fully named, which loses a name on the way
to the run record. Every correction made the prior art look *more* capable, not
less — an under-reading bias, and the natural one for a survey working against a
clock.

## What was corrected

| Section | First read | Second read |
| --- | --- | --- |
| 6 RA.Aid | not run — no lockfile | `uv.lock` present (672 KB); **764 passed, 6 skipped, 67.87s** |
| 7 SWE-agent | not run — needs a runtime | **74 hermetic / 108 with Docker**; 1 real failure |
| 8 aider | not run — needs network/display | needs neither; **468 passed** with voice excluded |
| 10 oh-my-openagent | not run — no bun | bun installed in one command; **12,965 pass** |
| 7 SWE-agent | "four ceilings, four names" | four names, **three exit statuses** |
| — OpenHands | disqualified, 0/5 | **migrated, not absent** — re-qualified below |
| 8 aider | "the disclosure fork" | **not located**; `grep -rin disclos` hits only the privacy policy |

That last row matters more than its size. A finding no second reader could find
is a finding that cannot be audited, and #175's whole method rests on a reader
who does not trust the review being able to re-derive it. The nearest verifiable
thing is a *consent* fork — 20 `confirm_ask` sites, four of them gating the edit
loop itself (`architect_coder.py:17`, `base_coder.py:1604`, `:1620`, `:2207`) —
which may be what was meant. Recorded as unresolved rather than quietly rewritten
into the thing it probably was.

## OpenHands was migrated, not emptied — and the migration is the finding

Every observation in the disqualification holds: `package.json` really is
`@openhands/agent-canvas` 1.10.0 and the tree really is 871 `.tsx` / 831 `.ts` /
4 `.py`. What the first read could not see from the tree is *why*. Commit
`cb9138caf` (2026-07-27, "clear repository for Agent Canvas migration") deleted
**2,568 files and 486,115 lines with zero insertions**. The agent now lives at
`OpenHands/software-agent-sdk` @ `b35c2fee8b4ca2e496bb912dafd08d9face59124`,
1,232 Python files, and its suite **runs**: 5,696 passed in `tests/sdk`, 375 in
`tests/cross`, 462 in the security subset, zero failures.

So the correct entry is a **split**: caller (1/5) at one repository, agent (3/5)
at another, system 4/5 across both.

**OpenHands divided its repository along exactly the boundary this survey was
built on** — the session-holding caller on one side, the thing below the contract
on the other — and did it ten days before the pin. #175's amendment argued that
boundary from a metadata sweep and was told it was a judgement call. The largest
project in the set acted on the same distinction in production, which is the
strongest external evidence the survey produced for its own selection rule.

Restoring it also restores the survey's best #158 evidence. Their condenser's
shipped trigger is **80 events**; `max_tokens` defaults to `None` while
`effective_max_input_tokens` sits unused in the same process, and their own
comment concedes it:

```text
Treat event-count pressure as soft because that threshold is only a
history-management heuristic
```

That is mcgyvr's #158 defect — a ceiling chosen rather than measured — stated in
the first person by an 83k-star project, and discovered in mcgyvr's exact
deployment shape: benchmark runs against a fixed local-model context.

## The findings the second read added

**A gate that has not executed since 2025-01-27 (RA.Aid).** `--test-cmd`, their
acceptance step, calls `run_shell_command(cmd, timeout=timeout)` on a langchain
`@tool`, which raises `TypeError: BaseTool.__call__() got an unexpected keyword
argument 'timeout'`. The enclosing `except Exception` sets `should_break=True` —
**the same value a passing suite sets**. Run here against their own locked deps,
a green suite, a red suite and an exhausted retry budget all return the identical
signal. All six tests of the module pass, because each patches
`run_shell_command` with a `Mock` that accepts any kwarg.

This is the survey's "nobody trusts the instrument" theme in its negative form,
and it is worse than a missing check: **the mock is what kept it green.** It is
also the second repository whose gate reports two distinct outcomes through one
channel. For mcgyvr the question is direct — whether `acceptance.py`'s subprocess
boundary may be mocked in any test, and whether a boolean can carry *passed*,
*failed* and *never ran*. It cannot.

**#183's baseline rule is already built (SWE-agent).** Their edit tool runs
flake8 before and after every edit and rejects only **new** errors, reverting via
`undo_edit()`, with a select set chosen for brokenness rather than style
(`F821,F822,F831,E111,E112,E113,E999,E902`) — and the line-number-shifting
machinery that differencing a check across an edit actually needs. mcgyvr filed
#183 as an open question; here is a shipped answer at edit granularity.

**Four names, three verdicts (SWE-agent).** `InstanceCallLimitExceededError` —
the step cap — subclasses `CostLimitExceededError`, so `agents.py:1182` records
it as `exit_cost`. A run that exhausts its steps reports that it ran out of
money. The first read drew the opposite lesson from the same four classes, and
the sharpened version is the useful one: an exception hierarchy chosen for
handling convenience silently collapsed two ceilings into one reported outcome.
Worse, `forward_with_handling` loops on `n_format_fails < max_requeries`, but the
two tool-driven requeries never increment the counter — so the declared cap is
not the operative one, and only the cost limit ends it.

**Trajectory fixtures decay; parser fixtures do not (OpenHands).** This is a real
qualification of #184 rather than support for it. They captured six real Sonnet-4
completions, committed them, and built the replay — then **overwrote it with
hand-authored mocks six days later**, reason given: *"Real fixture data may have
different tool call sequences than current agent"*. `test_hello_world_with_real_llm_data`
still passes and reads none of it, eleven months on. So #184 should be written to
capture what the **parser** consumes — reply shape, stable against our own
changes — not what a **run** produced, which is coupled to the tool schema at
capture time and dead within a release. aider's corpus is the model to copy:
99,961 lines of real replies diffed whole against a golden file holding 577
parsed blocks and **33 recorded parse failures**, kept as gold rather than
excluded.

**#179's eighth question has two shipped answers, and they agree.** May a
verifier blame the instrument rather than the work? OpenHands:
`EnsembleSecurityAnalyzer` fuses by max-severity and **a child that raises
contributes `HIGH`**, with the stated reason "prevents a broken analyzer from
silently degrading safety". SWE-agent: the reviewer samples five times, discards
replies outside `score_range` as uninterpretable, subtracts
`reduce_by_std × std`, and returns `accepts=[-100.0]` when nothing parses — the
instrument is checked by resampling itself and is forbidden to abstain. **Both
fail closed.** Neither lets an unreadable instrument excuse the work. That is a
convergent answer from two independent systems, and it is the answer #179 should
take.

**17% of the most-measured routing table is measured (aider).** The
model→edit-format binding is a 3,128-line hand-maintained YAML, 357 entries keyed
on exact model-name string, plus a 21-branch substring cascade where ordering is
load-bearing. Only **57 of 342 routed models** have a published run behind them,
and **no code path reads the leaderboard** — `polyglot_leaderboard` appears in
four `.py` files, all plotting scripts. The feedback edge from measurement to
routing does not exist in the project that measures most.

Their own data, on the exact model class srv1/srv2 run: Qwen2.5-Coder-32B scores
**71.6% well-formed on `diff`** against **99.6% on `whole`**, and the shipped
binding picks `diff` — verified by running their code. (The two runs used
different endpoints, so the pass-rate doubling is confounded; the 28-point
well-formedness gap is the defensible half.) The routable property this exposes
is **reply well-formedness** — median 94.2% on diff, minimum 64.4%, 1,598
unparseable replies across 69 runs. mcgyvr generates that signal on every
dispatch and discards it, which is #184 and #162 meeting at a single number.

**oh-my-openagent's sentinel is three-valued (verification, sharpened).** Every
first-read specific holds — 274 lines against 167 of tests, genuinely pure with
injected dependencies, terminating at `undefined`. The refinement: the cold-cache
sentinel requires **four** conditions, distinguishing "cache empty" from "cache
never populated". That is moatless's `UNKNOWN` — absence as an outcome rather
than an error — arrived at independently at the routing layer. And the fuzzy
matcher was *measured* rather than asserted: `qwen3` resolves to
`openrouter/qwen3` over `local/qwen3-coder-30b`, so **locality is invisible to it
and the remote wins on name length**, and `isModelAvailable("gpt-5")` returns
true against only `gpt-5.6-sol`. That is #164's failure reproduced on demand.

**The real #162 lesson is prompt portability, not the chain.** oh-my-openagent
carries 12 model-specific prompts for one role and 6,455 lines across two, plus
hooks blocking model pairings that are legal on capability. A routing matrix that
selects a worker still owes an answer for the prompt that goes with it.

## The annex finding is about mcgyvr

`capacity.py:111` bounds dispatch with a `threading.BoundedSemaphore`, acquired
at `:207` with no timeout. The module's docstring sets out four deliberate
decisions and names nested acquisition "the worst failure this module could
have" — and **the word "process" does not appear in the file.**

The bound is per-process. srv1 and srv2 are host-wide and shared, and this
repository's own workflow runs lanes as parallel worktrees. Two lanes each
dispatch `max_parallel` at the same rig, and the declared capacity is silently
doubled. The cross-process case is not merely unhandled; it is unstated, which is
why nothing has flagged it.

All three annex repositories are ahead of us here, in different ways:
container-use takes a host-wide `flock` the kernel releases on death; orca
derives occupancy from a query, so it survives a restart; multica claims by
uniqueness key with no coordinator at all. **mcgyvr is the only design reviewed
that blocks forever.**

multica's artefact verifies in full, and the second read found a better one
beside it. The claim is `ON CONFLICT ON CONSTRAINT uq_sys_cron_execution DO
NOTHING` against `UNIQUE (job_name, scope_kind, scope_id, plan_time)` with
`runner_id` a plain column — work-keyed, not worker-keyed, exactly as reported —
and `MUL-3551` is cited **15 times** across a migration, a query and five tests,
its section numbers partitioning the suite. The stronger test is
`internal/scheduler/concurrent_claim_test.go:36`: eight goroutines on a start
barrier asserting `wins==1, steals==0, conflicts==7`, plus a database-side proof.
And the loser question is answered — it does not block, poll, back off or
requeue. `manager.go:303` returns on `Conflicted` with "Silent no-op is the
expected case", and nothing is lost because the claim precedes the work and the
work item is regenerated on the next tick. **There is no queue because there is
nothing to queue**, which is a cheaper answer than the one mcgyvr's pool is
reaching for.

Two smaller annex results: cline's folder-lock table has **no caller and no
test**, and its reaper cannot fire after `SIGKILL`; orca's 121 tests ran clean
here.

## An eleventh repository, found while selecting the tenth

`langchain-ai/open-swe` (MIT, 10.5k stars, pushed 2026-08-06) was read in depth
before the tenth slot resolved. It scores 4–5/5 and **its full suite runs clean
here: 1,672 passed, 30.74s**. It carries findings the ten do not:

- `settle_review_check.py` answers #179's eighth question in production code —
  *the review not completing is reviewer infrastructure failing, not the PR* —
  and returns a conclusion of `neutral`. Set against OpenHands and SWE-agent,
  which both fail closed, that makes **two answers, not one**, and the
  distinction between them is what mcgyvr actually has to decide: whether the
  instrument's failure is charged to the work or to neither party.
- `names_failing_on_base` — baseline subtraction, which is #183's rule again.
- A three-valued CI verdict distinguishing "could not tell" from "nothing
  failing".
- A sandbox circuit breaker that **refuses** auto-recovery, because a fresh
  sandbox "would throw away anything not yet committed while still looking like a
  recovery" — #141 with the reasoning attached.

It is recorded here rather than promoted into the ten, because the ten were
selected under a stated rule and renumbering them after the fact would make the
selection unauditable. It is the first candidate for any next pass.

## What the second read could not do

- **SWE-ReX still has not been run.** It is the one first-pass not-run that
  survived a second attempt; it genuinely needs a container runtime.
- **No repository was read exhaustively on the second pass either**, and the
  second readers were given mcgyvr's issue list, so they were steered toward the
  same questions. Independence here means independent derivation, not independent
  curiosity.
- **`open-swe` has one reader, not two.** Everything in the list above is
  first-read evidence by this document's own standard.
- The five sections the second read did not cover — 1 through 5 — **have had no
  independent verification at all.** Given that four of six second reads
  materially corrected their target, the correct prior is that sections 1–5
  contain errors of the same kind, in the same direction.
