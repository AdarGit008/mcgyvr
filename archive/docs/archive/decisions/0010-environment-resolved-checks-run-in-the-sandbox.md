# ADR-0010 — environment-resolved semantic checks run in the sandbox

Status: Accepted
Supersedes: ADR-0005 in part — its rejection of a sandbox-executed check rung
Superseded-by: none
Date: 2026-08-02

## Context

ADR-0005 settled that no gate check imports, executes or plugin-loads
target-repository code in the orchestrator process, and that rule is not in
question here. It is restated below unchanged, because this record amends what
ADR-0005 *rejected*, not what it decided.

The rejected alternative it amends is the third section of that record:
"install the tools into the per-repo image and add a sandbox-executed gate
rung". ADR-0005 gave that option the better half of the argument — the image
already exists, keyed on exactly the dependency set (`sandbox/image.py:121`,
`:211`), and a check run there resolves against the target's own installed
packages inside a container that holds no credentials. It deferred anyway, on
one sentence: "the acceptance rung already runs the target's own declared
checks in that exact environment, so this rung's yield is only what those
checks miss. That quantity is unmeasured."

That sentence is where the error is. It defines the rung's value as an
increment over the declared checks, which silently assumes two things: that
every repository declares checks, and that a declared check reaches every added
line. Neither holds, and the second is false even on repositories with
excellent suites.

**The declared checks bind task types, not lines.** The catalog has nine types.
Four require a command — `type_annotation` (`type_check`),
`function_implementation` and `test_scaffold` (`tests_pass`), `bug_fix`
(`failing_test_first`, `tests_pass`) — and ADR-0005's claim that every
hallucination-prone type is among them survives checking: the other five are
either tool-produced output (`format`, `import_sort`, `lint_fix`) or carry
`references_resolved` / `no_semantic_change`, which is to say they cannot
introduce a call at all. But `tests_pass` is a verdict on a suite, not on a
diff. It reports that the suite is green. A call to a method that does not
exist, sitting on a branch no test exercises, leaves the suite green.
`type_check` binds narrower still: only where the code is annotated and only
where the checker has a view of the package being called.

**Some repositories declare nothing, and there the rung is not an increment at
all.** ADR-0005 recorded this as a consequence without connecting it to the
deferral: "for a repository that declares no checks, deterministic acceptance
stays structural." The enforcement is stronger than that phrasing suggests. A
contract whose type needs commands and carries none is rejected at load
(`contract.py:862`, over `TaskType.needs_acceptance_commands` at
`catalog.py:97`). On a repository with no runnable suite,
`function_implementation`, `test_scaffold` and `bug_fix` cannot be formed. The
rung does not add coverage there; it is the only coverage available, and it is
what makes those task types reachable at all.

No measurement of yield-over-declared-checks can report on that second case,
because those repositories produce no contracts of those types to measure. The
deferral was waiting on a number that could not, by construction, contain the
argument for the thing it was gating.

**On the tool.** #93 named ghostcall (`linosorice/ghostcall`) — described there
as ~330 lines, stdlib only, parsing with `ast`, resolving imports and
cross-referencing calls against installed packages. That size is the point, and
it explains the whole shape of this decision: ghostcall is small because it does
not answer the hard question. The interpreter does. Its design assumes it is
standing inside the environment the code will run in. Take that position away —
which is exactly what running it in the orchestrator process does, where
"installed" means pyyaml and three tree-sitter packages
(`pyproject.toml:8-13`) — and the remainder is not a lighter tool. It is a
different and considerably harder problem that the tool was built to avoid. The
sandbox is the position the tool was designed for.

ghostcall's own description is inherited and therefore a claim, not a fact:
ADR-0004 requires it to be verified before it is adopted. This record decides
the shape of the check, and names ghostcall as the candidate for it, not as a
dependency already accepted. The base rate that #93 rested on — 20–40% of
completions — is confirmed absent from the paper it cited (Delulu,
arXiv:2605.07024), and this record asserts no replacement figure, per ADR-0004.

## Decision

**Semantic checks that need a live environment run inside the per-task sandbox,
as a gate rung. They do not run in the orchestrator process, and they are not
replaced by a static approximation on the host.**

ADR-0005's rule stands and is carried forward unchanged: no gate check imports,
executes or plugin-loads target-repository code in the orchestrator process; the
gate reads the target as data, or shells out to a static tool that does the
same. What this record changes is that the sandboxed rung is **adopted rather
than deferred**, and adopted on the coverage argument rather than on a yield
number.

Concretely:

- The rung takes the shape `Gate.run` already has for acceptance — injected
  rather than constructed (`gate/runner.py:83`), running inside the sandbox
  through the seam `gate/acceptance.py` closed. It runs **before** acceptance,
  keeping the runner's existing cheap-before-expensive ordering
  (`gate/runner.py:113-118`): a sub-second resolution pass has no business
  queueing behind a test suite.
- Its findings are filtered to `FileChange.added_lines`
  (`gate/changeset.py:55`), the same restriction every other per-change check
  observes.
- The candidate implementation is ghostcall, subject to ADR-0004 verification
  before anything enters an image. If it does not survive verification, the
  decision stands and a different implementation fills it.
- The measurement is re-aimed, not dropped. #112 stops deciding whether the
  check is built and starts sizing it: how much added code the declared checks
  never reach, and how often a repository declares no runnable check at all.

## Rejected: keep deferring until the yield number exists

The discipline is right in general and it is this repository's own — ADR-0004
exists to stop decisions being sized by numbers nobody can source, and
"building a rung to catch it is building for a number nobody has" is a fair
statement of the hazard. Adopting on an argument rather than a measurement is
the move ADR-0004 was written against.

It loses because the number was defined against the wrong denominator, and no
amount of measuring the wrong ratio corrects it. Yield-over-declared-checks can
only be observed where declared checks exist, and the strongest case for the
rung is the repositories where they do not — which are, additionally, invisible
to that measurement in a specific and unrecoverable way: they cannot produce a
contract of the relevant type, so they contribute no rows at all rather than
zero rows. A measurement whose sampling frame excludes the population that
carries the effect is not weak evidence, it is no evidence.

The discipline is honoured where it applies. This record quotes no rate, sizes
no gain, and hands #112 a narrower question it can actually answer.

## Rejected: build the static resolver on the host instead

This is #120 as filed, and it was the obvious reading of ADR-0005 — the rule
forbids importing, so build the version that does not import. It needs no
container, no image policy and no third-party dependency.

It loses on the same fact that makes ghostcall small. Resolution *by import* is
not an implementation detail of the check; it is the check. Remove it and the
remaining problem — deciding statically what a dotted chain refers to, across
re-exports, conditional imports, dynamic attributes and C extensions — is
strictly harder than the one being avoided, and the honest answer for anything
past the shallow cases is "unknown", reported as a finding.

The second reason is about what a measurement would then mean. A static-only
arm would almost certainly measure near zero against the declared checks, and
that result would be cited afterwards as "semantic checking has no yield here"
by readers who never learn that what was measured was the version with its
engine removed. Producing a durable wrong conclusion is worse than producing
none.

#120 therefore closes as won't-do. Its reach was a workaround for a constraint
this record resolves, not a scope anyone chose.

## Rejected: emit the check as an acceptance command instead of a rung

Cheapest possible version: no new rung, no image policy. The decomposer already
has to emit acceptance commands, and one more line in `acceptance` costs
nothing structurally.

It loses on ownership. `acceptance` is what the *contract* declares, derived
from what the *target repository* declares. A check mcgyvr requires on every
change is not the target's to declare, and putting it there makes it silently
omissible — the exact failure the rung exists to prevent, since the repositories
that would omit it are the ones with nothing else. It also inherits acceptance's
position: last, and only when nothing cheaper already rejected the change.

## Consequences

- The per-task image stops being purely what the repository declares. That is
  the real cost ADR-0005 named and it is accepted: `cache_key`
  (`sandbox/image.py:121`) now covers a tool mcgyvr chose, which means a
  standing policy on which tool and which version is owed before the rung
  ships. The second half of ADR-0005's objection — "our mypy disagreeing with
  their mypy" — does not transfer, because a resolver has no opinions to
  disagree with; it asks the target's own interpreter and reports the answer.
- Boundary 6 is untouched. Credentials still never reach a task container
  (`sandbox/base.py:114`, `:124`), and this check runs where target code
  already runs rather than anywhere new.
- #120 closes as won't-do and #123 replaces it under #110, which is retitled
  from "Static semantic checks in the gate" — the epic now spans both sides of
  ADR-0005's line rather than only the host-side one. Its "done when" — an
  adapter reporting semantic findings "without loading a line of that repository
  into this process" — is satisfied by this shape, not contradicted by it: the
  loading happens in a container, not in this process.
- #112 is re-scoped in the same range as this record. It no longer gates the
  build, so it is no longer on the critical path, but it is still owed: the
  rung's size and its false-positive rate are both unmeasured, and a rung
  shipped without them is a rung nobody can tune.
- Anything quoted about ghostcall — size, dependency count, hit rate — is a CLM
  before it is repeated, per ADR-0004. Nothing in this record depends on such a
  number, which is deliberate.
- What this gives up: on a repository whose declared checks are thorough and
  whose suite exercises the changed lines, this rung is pure cost — a step whose
  findings the suite would have produced anyway. Accepted, because the container
  is already paid for by the acceptance rung and the marginal cost is a
  sub-second process inside it.
- What this bets on: that resolution against real installed packages is worth
  more than the image policy it obliges. If #112 reports that declared checks
  reach nearly every added line and that nearly every repository declares them,
  that bet is wrong and this record is the one to supersede.
