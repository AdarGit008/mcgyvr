# Changelog

Format: [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]

### Added
- Repo founded. Scope of record is the issue tree; forks and rationale in
  `docs/decisions/`.
- Decision `0001-founding-scope-and-boundaries` — what mcgyvr is, the
  boundaries it holds, and what it deliberately does not do.
- Vendored `baseline-skill` 2.5.0 at `tools/baseline/`, pinned by
  `tools/baseline.lock.json`.
- Capability table (`data/capability-table.json`) — measured local-model
  quality and throughput, with per-measurement provenance and the harness
  caveats that make some published numbers unusable.
- Config schema and loader (`src/mcgyvr/config.py`). The schema is
  declarative data, so the config reference can be generated from the same
  definitions the validator walks. Unknown and duplicate keys are rejected;
  credentials have nowhere to go but an environment variable NAME; values
  that are legitimately optional fail at the point of use, naming the key
  and how to bind it.
- `mcgyvr config` — validate a config file and show what it resolves to.
- Hardware and backend detection (`src/mcgyvr/detect.py`). Reports GPUs and
  VRAM, host CPU/RAM, Docker, and which local backends answer — each fact
  with how it was detected, and each failed probe with what it could not
  determine. Absence is an outcome, not an error: no GPU, no Docker and no
  backend is a supported machine. Nothing is benchmarked.
- `mcgyvr detect` — show the survey and its provenance.
- Worker binding proposal (`src/mcgyvr/propose.py`). Turns a card size and
  the reachable backends into a ladder whose rungs climb in measured
  quality, stating for each binding why it was chosen and what it costs to
  pull. Equal-quality ties collapse to the faster model; a model that is
  bigger without being better is dropped by name; an unmeasured model is
  never bound. A machine with no GPU or no backend gets an empty local
  ladder and an explanation, not an error.
- `Model.best_throughput` on the capability table, restricted to
  measurements taken on a backend the model can actually run on — a figure
  from another backend describes different weights (CAV-02).

- `mcgyvr init` (`src/mcgyvr/initialize.py`) — detect the machine, propose a
  ladder, and write the config. Non-interactive, so an agent can invoke it.
  Idempotent: re-running reports a delta and never overwrites hand edits
  without `--force`. The generated file's comments are rendered from the
  same schema the loader validates against, so a comment cannot drift from
  the rule it describes. What is not configured — no key, no Docker — is
  reported with what it costs. If nothing can be dispatched to, init refuses
  and names what to bind rather than writing a config that cannot load.

- Repository attach (`src/mcgyvr/orchestrator/repo.py`) — the required first
  input to any orchestration (#46, E7). A local checkout and a clone URL
  converge on one internal state through a single code path: a canonical repo
  root (a subdirectory normalises to the toplevel), the starting revision
  everything downstream is judged against (the empty tree for an unborn repo),
  and whether the working tree is dirty. A clone lands in a working location
  with a declared lifetime — ephemeral by default, removed when the attach
  context closes, or into a caller-owned directory. The "a repository is
  required" boundary is enforced loudly: no input, a non-git directory, a file,
  an unrecognisable input, or a failed clone each fail before any work with a
  message naming what to supply.
- `mcgyvr attach` — attach a repository and show its resolved state (root,
  revision, lifetime, and any uncommitted paths).
- Deterministic index (`src/mcgyvr/orchestrator/index.py`,
  `orchestrator/symbols.py`) — the zero-token substrate the cost argument
  rests on (#47, E7). Enumerates a repository's non-ignored files through
  `git ls-files` (so `.gitignore` is honoured, not re-implemented), holds
  their text for fast search, and extracts a shallow symbol table —
  definitions, references, exports — reusing the gate's per-language
  investment: Python via the standard library's `ast`, JS/TS via tree-sitter.
  No model is called anywhere in it. The build is bounded and reported
  (`BuildStats`: elapsed time, files indexed, large/binary files skipped,
  symbols, per-language counts) and degrades to text-only on a language with
  no grammar rather than failing — a repository in an unindexed language still
  yields a searchable text index and an empty symbol table.
- `mcgyvr index` — build the index for a repository and show what it cost,
  with optional `--search TERM` (text) and `--symbol NAME` (definitions and
  references).
- Index cache (`src/mcgyvr/orchestrator/cache.py`) — exploration cost
  amortized across tasks (#52, E7). A build is persisted per repository under
  `$XDG_CACHE_HOME/mcgyvr/index`, keyed by absolute path so two worktrees of
  one repository never share entries, and reused per file. Three properties
  are structural rather than remembered: the file list is never cached (every
  build re-enumerates through git, so a deleted path is absent from the
  enumeration and the cache is never asked about it), invalidation is per file
  (each entry carries its own stamp, so a change rebuilds that file and leaves
  every other entry standing), and the cache is an accelerator that can never
  be load-bearing (an unreadable, mismatched or unwritable cache degrades to a
  full build, never to a wrong or failed one). Validity is decided cheapest
  first: a matching size and mtime reuses a file without opening it, a moved
  stamp falls back to a content fingerprint that still avoids reparsing when
  the bytes are unchanged, and only new content is parsed again. Entries
  recorded during the build's own clock tick are distrusted and revalidated by
  content, as git does for racily-clean entries. The directory is bounded
  (`DEFAULT_MAX_CACHE_BYTES`, evicting whole repositories least-recently-used
  first) and `CacheStats` reports what the cache actually did, because a cache
  that silently does nothing looks exactly like one that works.
- `mcgyvr index --no-cache`, `--refresh-cache` and `--clear-cache` — build
  without the cache, rebuild and re-store it, or remove this repository's
  cached index.
- Agent-supplied context (`src/mcgyvr/orchestrator/context.py`) — the caller's
  existing knowledge as an accelerator that can never become load-bearing (#51,
  E7). A calling agent that has already read the repository supplies the paths
  it believes matter and the text it holds; a file whose supplied content is
  verified equal to the repository's costs the exploration budget nothing, and
  the budget it did not consume goes to regions the caller has not seen. What
  keeps a fallible hint from steering the plan is structural rather than
  promised: hints may only re-rank the shortlist the deterministic pass already
  produced, so they can neither add a path nor remove one; supplied text is
  believed only when it matches the index exactly, so a stale copy cannot feed
  itself back as fact; and the hint's weight is derived from the resolver's own
  dominance threshold and pinned below it, so a boost provably cannot overtake
  a resolved leader. Within a shortlist the resolver declined to separate a
  hint decides read order and can finish a call the index had nearly made, but
  two equally-scored candidates stay ambiguous however firmly one is asserted —
  a hint may confirm a judgement, not supply one. Every rejected hint is
  reported as a `ContextFinding`, because context that contradicts the
  repository is worth more said than swallowed.
- `mcgyvr read --hint PATH` and `--holds PATH` — name a path you believe is
  relevant, or one whose current content you already hold; rejected hints are
  printed rather than silently dropped.
- Task contract schema, loader and validation (`src/mcgyvr/contract.py`) —
  the boundary between the calling agent and mcgyvr (#14, E2). In delegated
  mode a contract is an internal artifact the orchestrator produces; in direct
  mode it is public API an agent authors, and both go through one loader, so
  "a contract the orchestrator emits is one the direct-mode API accepts" holds
  because there is a single definition rather than two that agree. `SCHEMA` is
  declarative data — kind, requiredness, default and prose per key — so the
  authoring guide (#18) can be rendered from what the validator walks. Four
  things are enforced at load rather than discovered mid-task: every rejection
  names the field and says what a valid value looks like (this is API surface
  for an agent, so an unparseable rejection is a defect); unknown and
  duplicate keys fail; self-contradiction is rejected outright — a target its
  own scope forbids, a pattern both allowed and forbidden, a scope that
  permits nothing, a duplicated dependency, an output cap larger than the
  whole prompt budget; and single-target discipline holds, so a glob target is
  legal only for a task type the deterministic tier executes outright, because
  a model worker's output has exactly one destination. Path matching is never
  re-implemented — every scope decision goes through `mcgyvr.scope.Scope`.
  Field layout follows the split #94 arrived at from small-model research:
  worker-facing keys (`task`, `target`, `deps` as signatures rather than
  source, `interface`, `stop_conditions`, `output_schema`, `context`) are
  separated from orchestrator-only ones (`risk`, `verification`, `acceptance`,
  `limits`), and `Contract.worker_view()` is the only accessor for the former,
  so "orchestrator-only fields never reach the worker prompt" is enforced by
  there being no other way in. The task-type vocabulary is a seed, not the
  catalog: it declares only whether the deterministic tier can execute a type,
  which is the one bit the glob rule needs — what each type guarantees and
  where it starts belongs to #15.
- `mcgyvr contract PATH` — validate a task contract and show what it resolves
  to, with `--worker-view` to print exactly the fields a worker prompt may be
  built from.
- Source map (`src/mcgyvr/pool.py`) — the seam between a ladder and the machines
  that serve it (#20, E3). Rungs bind to sources by name and resolve at call
  time, so moving a rung to another machine, or to a hosted API, is a config
  edit and not a patch. What keeps that true is that a `Rung` carries a name and
  a model and deliberately nothing else: no URL, no protocol, no source. A
  caller above the seam cannot come to depend on where work ran, because the
  type it holds cannot say. Only `SourceMap.bind` yields an `Endpoint`, and only
  a runner should call it. Backends are a protocol question rather than a
  per-vendor integration — `openai` covers vLLM, llama-server, LM Studio, TGI
  and the hosted providers, so adding one is a config entry. A source that
  cannot serve shortens the ladder instead of raising: the rung is skipped with
  its reason in words, an install with nothing usable gets an empty ladder that
  can explain itself, and the caller decides what that means, since for a
  keyless install it may be exactly what was configured. Credentials are named,
  never held — an `Endpoint` carries the variable's name and resolves the value
  at dispatch, so a secret never sits in a dataclass and cannot reach a log
  through a repr.
- `mcgyvr pool` — show the ladder as it resolves against the declared sources,
  including which rungs were skipped and why.

- Decomposition catalog (`data/task-catalog.json`, `src/mcgyvr/catalog.py`) —
  the vocabulary of what mcgyvr can be asked to do (#15, E2). Each entry states
  what accepting it promises, which family of the ladder it may start on, and
  what evidence a contract of that type must carry. It is *data*: adding a task
  type is an edit to the JSON and nothing else, proven by a test that invents a
  type in a temporary file and drives it through contract validation rather than
  by grepping the source for names. The start is a **family** (deterministic →
  local → api) rather than a rung, because rung names are chosen by whoever
  wrote the config and a catalog naming them would only be valid on the machine
  it was written for; a family resolves against any ladder, and it is a floor a
  dearer rung satisfies. `Catalog.unservable(config)` answers "what can this
  install not start" by name rather than by count. `deterministic` is derived
  from the family rather than declared, so the two cannot disagree — the move
  ADR-0003 makes for binding names.
  The inherited local-ai vocabulary was validated rather than adopted: of
  seventeen inherited types nine are carried and eight are removed, each with
  its reason kept in the file. `function_implementation` is the only entry the
  capability table directly warrants — it is the shape HumanEval+ measures — so
  every other entry carries a structural argument in its own `warrant` field
  instead of an optimistic route. `multi_file_refactor` is removed as
  structurally unservable, not merely hard: the worker output protocol is one
  file per reply (#25), so no model rung can emit a coordinated multi-file
  change at all. `interface_design` is removed because no acceptance evidence
  exists for it. `simple_bug_fix`/`complex_bug_fix` collapse into `bug_fix`,
  because difficulty is routing state that risk (#16) and escalation (#24)
  already hold, and a second copy is one that can disagree.
- `mcgyvr catalog [NAME]` — show the vocabulary and what each type guarantees,
  `--against CONFIG` to name the types a configured ladder cannot start, and
  `--excluded` to show what was considered and removed with the reason.
- A contract whose task type requires evidence only a command can produce is
  rejected when it declares no acceptance commands. A `bug_fix` with nothing to
  run does not fail loudly — it is accepted on the gate alone, and its guarantee
  goes unbacked.

### Changed
- The task-type vocabulary moved out of `mcgyvr.contract` into the catalog. The
  contract schema now resolves the valid set per validation rather than freezing
  it at import, so a type added to the JSON is accepted without touching code —
  a snapshot taken at import would have been a copy of the catalog living in
  code, which is the thing #15 forbids.
- The shipped data files are force-included into the wheel
  (`tool.hatch.build.targets.wheel.force-include`). They are read through
  `importlib.resources` but lived only at the repo root, so an installed wheel
  fell back to a checkout path that is not there. This was already latent for
  the capability table; the catalog made it fatal, since the contract schema
  reads it and `import mcgyvr.contract` would have failed outright.
- `mcgyvr.orchestrator.index` exposes the per-file primitives a build is made
  of (`read_source`, `index_source`, `IndexAssembler`, `enumerate_files`) so
  the cached build reuses them rather than reimplementing the bounds. Both
  builders assemble through `IndexAssembler`, so a cached build and a fresh
  one cannot drift into reporting differently.
- A targeted read records whether the caller already held it (`TargetedRead.
  supplied`) alongside its real estimated cost, and an exploration reports what
  supplied context saved it (`Exploration.saved`). A free read stays visible and
  costed rather than disappearing from the account.
- `pyyaml` is now a runtime dependency. The config file is YAML because it
  carries policy that needs comments to stay hand-editable (ADR-0001).
- Worker bindings are named `<role>_<locality>_<model>` (for example
  `worker_local_qwen2.5-coder-7b`), replacing the positional `local-N`. A
  name says what a binding IS rather than where it sits in an ordering, so
  inserting a rung cannot silently change what a policy reference means.
