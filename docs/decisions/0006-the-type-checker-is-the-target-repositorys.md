# ADR-0006 — the type checker is the target repository's

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

#109 carried six architecture decisions over from local-ai; ADR-0004 records what
survived verification and on what terms. The fourth is filed as #97, which asks for a
new gate step running `mypy --strict` over the changed `.py` files — the source
document's pseudocode adds `--ignore-missing-imports`. The flags are the whole
decision, and they are the whole problem.

`--strict` turns on `disallow_untyped_defs`, so on a repository that carries no
annotations mypy reports `no-untyped-def` against essentially every function a worker
adds. Every change is rejected, on every rung, and escalation cannot fix it: a stronger
model writes the same unannotated function into the same untyped file and is rejected
for the same reason. mcgyvr runs against arbitrary user repositories — its definition
of done is a stranger's install path (ADR-0001) — and it has no way to know in advance
whether that stranger annotates anything. Against a repository that does not,
`--strict` is not a strict gate; it is an off switch with an error message.

The shipped catalog already decided this, and says so twice. `data/task-catalog.json:51`
defines the `type_check` evidence kind as "The project's type checker passes on the
changed target." The `type_annotation` guarantee at `:110` is blunter — "Annotations
are added to the named target and the project's type checker accepts the result. The
checker, not the worker, decides whether the inference was right." Both sentences turn
on a possessive that is not ours. #97's flags overrule the data file that defines the
vocabulary #97's own task type is drawn from.

The landed Python adapter already follows exactly this policy for the tool next door.
`PythonAdapter.lint` and `.format_check` resolve `ruff` on PATH and run it with
`cwd=repo` (`src/mcgyvr/gate/adapters/python.py:77`, `:115`); the only flags passed
shape the output and the path handling, and there is no `--select` and no `--config`.
ruff reads the target's own configuration; mcgyvr reads ruff's verdict and attributes
it to added lines. A type check that synthesised its own flags would be the only tool
in the gate that argues with the repository about the repository's standards.

#97's stated tie-breaker is false here. It picks mypy over pyright "for
zero-external-dependency integration", but mypy is a dev-group dependency
(`pyproject.toml:26`) and absent from the runtime dependencies, which are pyyaml and
three tree-sitter packages (`pyproject.toml:8-13`). In an install it would be resolved
on PATH by `require_tool` (`gate/adapter.py:120`) exactly as pyright would be — and the
JS/TS adapter already resolves `eslint` and `prettier` that way
(`gate/adapters/javascript.py:123`, `:165`), so Node tooling for the second launch
language is a cost this gate already pays.

## Decision

**mcgyvr never chooses a type checker and never synthesises its flags. It locates
whatever the target repository already declares and runs that. A repository declaring
none is not type-checked.**

The mechanism is a locator capability on `LanguageAdapter`, sibling to
`locate_test_command` (`gate/adapter.py:101`) — the interface's existing precedent for
reading a stack's convention off the repository, "a fallback for when the contract
declares no acceptance command; the contract always wins when it does"
(`adapter.py:102-105`). Python sniffs `[tool.mypy]` and `[tool.pyright]`; JS/TS reads
`tsconfig.json` and yields `tsc --noEmit`. Neither present yields `None`. Strictness is
whatever the repository set: mcgyvr's own tree declares `strict = true`
(`pyproject.toml:64-67`), so under this rule mcgyvr checked by mcgyvr is checked
strictly — because it asked to be.

The located command is emitted by the decomposer (#50) into the contract's `acceptance`
list (`contract.py:389`), where #38's sandboxed runner already executes it. This is
deliberately not a new gate step, and the gate's own prose says why:
`gate/acceptance.py:1-6` opens by naming what that rung runs — "the contract's declared
checks — its test suite, its type-checker". The seam was built for this and closed.
What is missing is not a step; it is whoever fills the list in.

The rest of the machinery already holds the line. `contract.py:862` refuses to load a
`type_annotation` contract with an empty `acceptance`, on the stated grounds that its
guarantee needs evidence only a command can produce. So the honest description of
today's gap is that the schema already demands a type-check command for the one task
type whose guarantee requires one, and nothing yet supplies it. Where the locator
returns `None`, the decomposer does not emit `type_annotation` for that repository —
the contract would fail to load anyway, which is the correct outcome arriving at the
correct layer.

This disposes of the mypy-versus-pyright question entirely. #97 stakes its tool choice
on a benchmark reading 231 false positives and 76 false negatives for mypy against 15
and 4 for pyright; ADR-0004 traced that comparison to a single blog post contradicting
itself on the same day, and no figure from it is carried here. The question stops being
mcgyvr's: the repository resolved it when it wrote its config, and mcgyvr runs what it
wrote. An unverifiable number stops being load-bearing when it stops being ours.

## Rejected: impose `--strict`, gated behind an opt-in flag

The case for it is real. Strict catches the most. `no-untyped-def` is not noise on a
project whose annotations are the point — it is precisely the finding that stops a
worker adding an unannotated function to it — and #97's motivating failure, a generated
function typed `-> list` that returns `None` on one code path while its caller assumes
otherwise, is one a permissive config will miss. Deferring to the target means a
repository with a lax `[tool.mypy]` gets a lax check, which is strictly less than the
same subprocess could catch. And the flag answers the untyped-repository objection head
on: the source document proposes shipping the step behind a contract-level
`detect_type_errors: true`, defaulted off, so a cautious operator enables it where it
works, the false-positive rate is measured on real diffs, and the default flips once it
is known. That is the ordinary way to introduce a check whose cost is unmeasured — and
the document concedes in the same section that the cost is unmeasured, owing both a
false-positive rate and a misattribution rate for added-lines filtering on multi-line
type errors, which ADR-0004 registers as debt rather than resolving.

It loses twice.

The flag is a second way to say something already said. Declaring the command *is* the
opt-in: a contract carrying a type-check command in `acceptance` has opted in, and one
that does not, has not. A `detect_type_errors` key alongside it makes two switches for
one behaviour, and two switches can disagree — a contract with the flag true and no
command, or a command and the flag false, has a meaning nobody has written down. There
is also nowhere to put it. `mcgyvr.contract` rejects any key not in the declared field
set, with the reason stated in the error: "An ignored key is a contract that does not
do what it says" (`contract.py:659`). Adding the key is a schema change, and the
contract schema is public API from v1 — ADR-0001 boundary 1 makes direct-mode agents
author contracts themselves, and `SCHEMA_VERSION = 1` (`contract.py:75`) is what they
pin against. A redundant switch is not worth a version of a public schema.

`--strict` on an untyped repository is also not a stricter setting of the same check.
It is a different check, one that always fails. A gate finding is worth having because
a better worker can clear it; `no-untyped-def` on every added line of a repository that
annotates nothing cannot be cleared by any rung, because clearing it means annotating
the surrounding file — a change outside the contract's scope, which scope validation
(#34) rejects if a worker attempts it. So the gate rejects, the task escalates, the
ladder exhausts, and spend is converted to a guaranteed zero. That is worse than not
type-checking at all: it turns a silent gap into a budget sink, and the north star
measures accepted work per unit of expensive-token spend (ADR-0001).

## Rejected: run the target's checker on the host

Host-side execution is cheaper — no image, no sandbox lifecycle — and a type checker
wants whole-project context that is already on disk. #97 assumes it, placing
`run_type_check()` among the gate's own steps.

ADR-0005 forbids it, and mypy is the clean illustration of why. It loads
`plugins = [...]` from the target's configuration and imports each at startup, so "run
the repository's checker with the repository's config" is "execute a stranger's Python
inside the process holding provider credentials" (ADR-0001 boundary 6, `SECURITY.md`).
It fails on correctness before it fails on safety: on the host the checker resolves
imports against mcgyvr's own environment rather than the target's, so a check whose
entire premise is *the project's* checker on *the project's* code would be measuring
the wrong project. The acceptance list runs in the per-task sandbox against the
repository's own installed dependencies. That is the only place this check means what
it says.

## Consequences

- A repository declaring no type checker is not type-checked, and `type_annotation` is
  unavailable there rather than silently degraded — `contract.py:862` already refuses
  the contract, so the refusal costs no rung and names its own reason.
- The mypy-versus-pyright choice leaves this project. There is no benchmark to defend
  and no "upgrade path at merge-gate time" to schedule; a target that switches checkers
  gets the new one on its next task with no change here.
- #97 as written cannot be implemented, and not only because of where it runs: it
  places the new step "after lint (step 6), before acceptance commands (step 7)" in a
  `Gate.run` that has five steps, with acceptance last at `gate/runner.py:113`. It
  should be closed and re-filed as a locator on the adapters (#35 and #36 are closed;
  this is an additive capability on a shipped interface) plus decomposer wiring under
  #50, which is where the unsolved part actually lives.
- The locator is a heuristic and will sometimes be wrong. The contract always wins when
  it declares its own commands, exactly as `locate_test_command` documents at
  `adapter.py:102-105`, so a caller in direct mode is never overruled by a sniff.
- What is given up: type errors go uncaught on any repository that runs no checker. How
  much work that covers is unmeasured, and this record does not guess at it — that is
  the bar ADR-0004 sets. The gap is not closed by imposing a checker either. A project
  that has never run one carries a backlog of pre-existing errors, and the added-lines
  filter that makes lint fair (`adapter.py:85`) does not survive a type error whose
  cause is on an added line and whose report is three files away.
