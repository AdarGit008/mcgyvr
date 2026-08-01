# ADR-0005 — gate checks never run target code on the host

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

Six architecture decisions inherited from local-ai arrived under #109 and were
filed as children #93 through #97 and #99; ADR-0004 records how their evidence
was re-verified. Three of the six quietly propose executing a stranger's code in
the orchestrator process. None of them says so, and two of them do not look like
they do.

DEC-6 (#99) ranks candidate outputs by fingerprinting each one, and its
`select_consensus` does that by calling `exec()` on model output — in-process,
in the process that holds provider credentials. That is the exact thing ADR-0001
boundary 6 and `SECURITY.md` exist to prevent.

DEC-3 (#93) proposes ghostcall: parse each changed file, resolve its imports, and
walk dotted call chains through `importlib` plus `getattr` against installed
packages. Resolution *by import* is the mechanism, not an implementation detail
of it. Importing a stranger's dependency runs that dependency's module-level
code, on the host, with the keys in reach.

DEC-4 (#97) proposes running the target repository's mypy host-side. mypy imports
every module its configuration names under `plugins` before it checks a line —
`load_plugins_from_config` calls `importlib.import_module` on each entry, and an
entry written as a path is resolved relative to the config file itself. A
repository under test can therefore name a module and have the orchestrator
import it, without being asked.

Three routes to the same place. The hazard is not in what these checks report, it
is in how they compute it — which is why two of them read as pure static
analysis.

For DEC-3 the argument is not only safety, and the second half is decisive.
ghostcall's headline property is that it validates calls against
*actually-installed* packages; that property is the entire reason to prefer it to
a linter. Run in the orchestrator process, "actually installed" means mcgyvr's
own runtime environment — pyyaml and three tree-sitter packages
(`pyproject.toml:8-13`). It would resolve a target's `import pandas` against an
interpreter that has never heard of pandas and report every call through it. The
property that justifies the tool is unachievable in the process the decision puts
it in — not hard, not noisy, unachievable by construction.

mcgyvr's answer to all three already exists and is landed. ADR-0001 boundary 5
gives every task its own container precisely because acceptance commands are
arbitrary shell from a contract, running on someone else's machine.
`gate/acceptance.py` is the gate's only consumer of that sandbox — the one import
of `mcgyvr.sandbox.base` anywhere under `gate/` is at `gate/acceptance.py:55` —
and its module docstring already states, for the acceptance rung alone, the rule
this record generalises: it "runs last and inside the sandbox, never on the host"
(`gate/acceptance.py:5-6`).

Every task type prone to the failures DEC-3 and DEC-4 target already requires
evidence that runs there. `type_annotation` requires `type_check`;
`function_implementation`, `test_scaffold` and `bug_fix` require `tests_pass`
(`data/task-catalog.json:108-138`), and all three of those evidence kinds carry
`needs_commands: true` (`data/task-catalog.json:50-63`). That is enforced, not
conventional: a contract of such a type with no acceptance commands is rejected
at load (`contract.py:862`, over `TaskType.needs_acceptance_commands` at
`catalog.py:97`). The live-environment check is already mandatory. It simply runs
in the right place.

## Decision

**No gate check imports, executes, or plugin-loads target-repository code in the
orchestrator process.** The gate reads the target as data — parses it,
pattern-matches it, or shells out to a static tool that does the same. Anything
needing a live environment (installed packages, an import graph resolved by an
interpreter, a type checker configured by the repository) goes through the
per-task sandbox as an acceptance command, which is the seam that already exists
for it.

The rule is satisfied today by construction, which is what makes it cheap to
keep. Python syntax goes through `ast.parse`, which parses and never evaluates
(`gate/adapters/python.py:39`). Lint and format shell out to ruff with `cwd=repo`
(`gate/adapters/python.py:77`, `:115`), so the target's configuration steers the
tool while nothing from the target is loaded into our interpreter. Changed YAML
goes through `safe_load` (`gate/structured.py:79`) rather than a loader that can
construct objects. The one dynamic import anywhere in the gate resolves the
literal string `"yaml"` — mcgyvr's own declared runtime dependency
(`pyproject.toml:9`) — and takes no name from the repository under test
(`gate/structured.py:31`).

This is the mirror image of boundary 6, which is likewise held in code rather
than in prose: `safe_env` builds a task environment from nothing rather than
inheriting the host's (`sandbox/base.py:124`), and `credential_env_names` is the
assertion a task container must satisfy (`sandbox/base.py:114`). Keys never
travel to the sandbox; target code never travels to the keys.

The consequence for the three filed issues is direct. #99's consensus artifact is
rejected outright, and it would not have worked in any case: `exec(result.output,
*args, **kwargs)` spreads the test input into `exec`'s own globals and locals
slots, which must be dicts, while `exec` accepts no keyword arguments at all — so
every input that is not literally empty raises `TypeError`, and an empty one
executes the candidate's module body without calling anything with it. The other
two, #93 and #97, cannot be implemented in the form filed. A *static* successor
to DEC-3 is buildable inside this rule — resolving dotted chains against symbols
the deterministic index already parsed, and against the contract's own `deps`
signatures, involves no import — but that is a different check with a different
reach, and specifying it is not this record's business.

## Rejected: install the tools into the per-repo image and add a sandbox-executed gate rung

This is the safe version of the same idea, and it has the better half of the
argument. `sandbox/image.py` already builds and caches an image per repository,
keyed on exactly the dependency set (`cache_key` at `:121`, `ensure_image` at
`:211`), with only the manifests copied into the build context
(`render_dockerfile` at `:158`). Adding mypy or an import resolver to that image
would put both checks in an environment where they mean what they claim:
resolving against the target's own installed packages, loading the target's own
plugins, inside a container that holds no credentials. It recovers DEC-3's
headline property instead of discarding it, and it costs one rung — `Gate.run`
already takes an injected acceptance rung and runs it last
(`gate/runner.py:83`, `:118`), which is the shape a second sandboxed rung copies.

It loses for now on two counts. First, it is a real new rung with its own
lifecycle: the image's contents stop being what the repository declares and start
being what mcgyvr chooses, which changes what the cache key means, forces a
standing policy on which tools and which versions, and creates a failure class
the acceptance rung does not have — our mypy disagreeing with their mypy on their
code. Second, the acceptance rung already runs the target's own declared checks
in that exact environment, so this rung's yield is only what those checks miss.
That quantity is unmeasured. Building a rung to catch it is building for a number
nobody has.

This is deferred pending a measurement, not refused. The measurement is the kind
ADR-0004 requires and registers as debt: run these tools over changes the
acceptance rung already accepted, and count what they catch. If the yield is
real, this rung is the right shape for it, and this record is the thing to
supersede.

## Rejected: exempt the gate process from boundary 6

The case for it is honest. The gate is ours, not a stranger's. Boundary 6 was
written about a task container running arbitrary shell from a contract; a type
checker is not arbitrary shell. The sandbox costs a container per task, and
pushing almost-static checks into it buys latency against a threat nobody has
demonstrated. A narrower version is available too: not an exemption for the whole
process, but an allowlist of read-only analysers permitted to run host-side.

It loses because boundary 6 is not a precaution, it is the load-bearing property.
ADR-0001 names sandboxing per task as what makes full autonomy defensible for
software strangers run against their own repositories; without it the product's
central promise is an unbacked assurance. And exempting the *gate* does not
narrow that boundary, it deletes it — the gate is the one component that touches
every changed file, of every task, on every rung.

"Not obviously hostile" is also exactly the reasoning a supply-chain attack is
designed to defeat. mypy's `plugins` key makes the hazard concrete rather than
theoretical: the code that would run is named by the repository under test, in a
config file the worker's own change may sit beside, and it is imported before the
first line is checked. No judgement about mypy's trustworthiness reaches that
hazard. mypy is the delivery mechanism, behaving as documented.

The allowlist variant fails for the same reason at one remove. It would enumerate
*tools*, but the hazard lives in what a tool loads, which the repository decides.
ruff sits on the safe side of the line not because it is trusted but because it
loads no code from the project it lints — a property to be checked per tool, not
a reputation to be granted.

## Consequences

- The rule binds checks that do not exist yet. A new capability on
  `LanguageAdapter` (`gate/adapter.py:50`) is constrained by it at design time
  rather than at review, which is the point of writing it down before #93 and #97
  are re-filed.
- Type checking is not lost; it was never a gate step here. `type_check` is
  already an evidence kind requiring commands (`data/task-catalog.json:50-52`)
  and `type_annotation` already requires it (`:111`). What is missing is a
  decomposer that locates the repository's own checker and emits it into
  `acceptance` (#50) — that, not an absent gate step, is why the problem looks
  unsolved.
- Every live-environment check now pays a container. That cost is accepted, and
  it is already paid by every task type whose evidence needs commands.
- What is given up, deliberately: the gate sees nothing that requires the
  target's live environment until a contract declares a command that does. For a
  repository that declares no checks, deterministic acceptance stays structural.
  That is the keyless configuration ADR-0001 boundary 3 names as supported rather
  than degraded, and this record fixes exactly what its bar consists of.
- A future check that wants to import target code is a decision to supersede this
  record, not a patch. That is the friction this record exists to add.
