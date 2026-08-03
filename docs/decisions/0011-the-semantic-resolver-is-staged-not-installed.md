# ADR-0011 — the semantic resolver is staged per run, not installed in the image

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-03

## Context

ADR-0010 adopted an environment-resolved semantic check as a sandbox gate rung
and left one thing owed: "the image cache key (`sandbox/image.py:121`) now
covers a tool mcgyvr chose, which means a standing policy on which tool and
which version is owed before the rung ships." #123 carries that forward as
scope — "the tool is added to the per-repo image … which obliges a standing
policy on which tool at which version — that policy is part of this issue, not
a follow-up."

This record sets that policy, and in setting it declines the premise. The
resolver is not added to the image.

**What the cache key means today.** `cache_key` is a hash of the base image
reference, the *contents* of the manifests and lockfiles the stack detector
named, and the build-time setup commands, and nothing else
(`sandbox/image.py:121`). The docstring above it states the property plainly:
"invalidate on a dependency change and on nothing else". Adding the resolver to
the image spends that property. Either it rides in as a setup command, in which
case the key covers it but the image is no longer the repository's dependency
set, or it rides in some other way and the key stops describing the image at
all. ADR-0010 saw the first case and asked for a policy to manage it. The
policy that manages it best is not to create it.

**What the tool actually is.** CLM-0006 verified ghostcall against its inherited
description and found the interesting half true: the *engine* — `parser.py`,
`checker.py`, `suggest.py`, `__init__.py` — imports only `ast`, `importlib`,
`inspect`, `difflib`, `dataclasses`, `typing` and `re`, and totals 173
non-blank non-comment lines. The three runtime dependencies the package
declares (click, rich, rich-click) are confined to `cli.py` and `output.py`,
126 lines of presentation a gate rung never calls. So there is no install to
perform: the thing that has to reach the container is four stdlib-only source
files, and a file can be copied into a workspace that is already bind-mounted.

**What a version policy has to achieve.** The resolver's verdicts are what the
gate reports, so a change to it changes what the gate says about identical
code. #129 measured the false-positive rate of *specific bytes*: 0 on 358
resolved chains on added lines, and four distinct flags off them, all correct
platform-conditional code. That measurement attaches to a commit, not to a
name. A policy worth having is one under which the bytes that ran cannot drift
from the bytes that were measured without someone deciding that they should.

## Decision

**The resolver engine is vendored, digest-pinned, and staged into the
workspace for the duration of one gate run. It never enters the task image, so
`cache_key` continues to cover exactly the repository's declared dependency set
and nothing else.**

The policy, in full:

- **One copy.** The engine lives at `records/evidence/ghostcall-2026-08-02/`,
  the vendored record CLM-0006 cites, pinned in its `MANIFEST.json` to upstream
  commit `56b74fc2` with a sha256 per file. There is no second copy in `src/`
  to drift from it. A wheel gets the same bytes through
  `force-include` (`pyproject.toml`), the mechanism the task catalog already
  uses, because a record outside `src/` does not ship.
- **The pin is duplicated on purpose, and tested.** `gate/semantic.py` carries
  `ENGINE_COMMIT` and a sha256 per staged file. `tests/test_semantic.py`
  asserts those equal the manifest's, and that the files on disk satisfy them.
  Re-pinning the resolver therefore means editing a constant in reviewed source
  and updating a record — it is not something a stray copy or a dependency
  resolver can do quietly.
- **The check is enforced at run time, and fail-closed means not running.**
  `verify_engine` hashes every file before anything is staged. A mismatch
  produces an environment issue and no verdict at all. An engine that is not
  the reviewed one must never reject a worker's change.
- **Only the four stdlib-only files are staged.** The presentation modules and
  their three third-party dependencies stay out of the sandbox entirely.
- **Changing the pin re-opens the measurement.** #129's false-positive figure
  is a statement about `56b74fc2`. A new commit is a new question, and the
  answer is not inherited.

## Rejected: install the resolver into the per-repo image

This is what ADR-0010 anticipated and what #123 assumed. It has one real
advantage: the tool is installed once per repository rather than copied once
per task, and copying four files into a bind-mounted directory is the kind of
cost that sounds free but is only nearly free.

It loses on three counts. It spends the cache-key property described above, in
exchange for saving a file copy. It puts a network install into the image build
— `pip install ghostcall` reaches PyPI at build time and brings click, rich and
rich-click into every task container, three dependencies that exist to print
colour to a terminal nobody is watching. And it makes the resolver's version a
property of a *cached artifact*: an image built last week carries last week's
resolver, and the gate has no way to notice, which is precisely the drift the
policy is supposed to prevent.

## Rejected: vendor a second copy under `src/mcgyvr/`

Simpler to package — no `force-include`, no checkout fallback — and it would
put the engine where a reader expects runtime code to live.

It loses because two copies of third-party source in one repository is two
things to keep equal, and the copy under `src/` would be linted and
type-checked by tooling that has no business reformatting bytes a citation
depends on. `pyproject.toml` already excludes `records/evidence` from ruff for
exactly this reason: "a formatter run there does not tidy anything, it
invalidates the citation." Staging from the record keeps one copy, and keeps it
the copy CLM-0006 points at.

## Rejected: reimplement the resolution logic as mcgyvr's own

The engine is 173 lines. Writing them would remove the vendoring question, the
packaging question and the licence question in one move, and the result would
be lint-clean, typed and ours.

It loses on evidence, not on effort. #129 measured *ghostcall*, and a
reimplementation — however faithful — is not the thing that was measured. The
one empirical statement anyone can make about this rung's false-positive rate
would stop applying to the code that ships. If the engine is ever replaced, the
replacement needs its own Count 3 before it is trusted, and that is a decision
to take deliberately rather than as a side effect of preferring one's own code.

## Consequences

- `cache_key` keeps its documented meaning, and `sandbox/image.py` is untouched
  by this issue. The obligation ADR-0010 recorded is discharged by removing
  what created it rather than by managing it.
- The staged directory (`.mcgyvr-semantic/`) exists inside the workspace for
  the length of one resolution pass and is removed in a `finally`. It is
  dot-prefixed, and it is gone before the acceptance rung takes its tree
  snapshot — the gate still judges the worker's diff and nothing else.
- The rung costs one directory copy of four small files per task, on top of a
  container that already exists. Nothing is cached between tasks, which is also
  what makes the version guarantee unconditional.
- The upstream repository is a zero-star personal project last pushed
  2026-04-19 (CLM-0006). If it disappears, nothing breaks: the bytes are in
  this repository, pinned, and their provenance is recorded.
- MIT licence and attribution ship with the engine (`force-include` carries
  `LICENSE` alongside the four files).
- What this bets on: that per-task staging stays cheap. If the resolver ever
  grows a compiled or heavyweight dependency, the copy stops being nearly free
  and this record is the one to supersede — the image layer would then be the
  right answer, together with the cache-key policy ADR-0010 asked for.
