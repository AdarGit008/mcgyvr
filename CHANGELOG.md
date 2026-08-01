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
- Target resolution (`src/mcgyvr/orchestrator/resolve.py`) — a phrase a caller
  would actually type becomes a ranked shortlist of paths (#48, E7). The whole
  cost argument is that a model reads a few files rather than a repository, so
  something must choose those few files; if that chooser were itself a model
  the saving would be circular. This is the deterministic bridge, and it calls
  no model — there is nothing in it but the index (#47) and string work.
  Scoring is two-tier: a whole-query match (the phrase reduced to content words
  and squashed to letters, equal to a symbol name or a filename — so "the fetch
  helper" finds `fetchHelper`) is a near-certain hit and dominates anything
  fuzzy; failing that, per-token matches accumulate across symbol names,
  filenames and path components, each token weighted by how rare it is in the
  repository so a common word cannot outvote a rare one, and scaled by how much
  of a name it accounts for so a named symbol beats a fragment of a longer one.
  Test files are demoted rather than excluded, so they surface when asked for
  without crowding out source. Two things are held rather than hoped for: every
  candidate reports the evidence that ranked it, so the expensive reader can
  judge the shortlist instead of trusting it; and ambiguity is an outcome, not a
  guess — when no candidate clearly leads its runner-up the verdict says
  `AMBIGUOUS` and hands back the contenders, rather than promoting a coin-flip
  to "the answer".
- `mcgyvr resolve QUERY [REPO]` — resolve a natural-language target to a ranked
  shortlist, with the evidence behind each candidate and `--limit` to cap it.
- Bounded targeted reads (`src/mcgyvr/orchestrator/read.py`) — the one place in
  exploration where tokens are spent (#49, E7). Attach, index and resolve all
  cost nothing; here the orchestrator finally reads source, so this is where the
  north star is won or lost. A candidate's query-relevant symbol definitions and
  text hits become line anchors, each widened to a bounded window and merged
  with its neighbours so an overlap is read once; a candidate that matched only
  on its filename has no anchor, so its window is the file head — the imports
  and top-level shape that stand in for "what is this file". Three commitments
  are structural. The spend is bounded and recorded: a budget in estimated
  tokens caps the exploration, every region carries its own cost, and the
  estimator is a plain deterministic function of the text — no model to ask —
  that a caller owning a real tokenizer can replace to account exactly. Every
  read is attributed to the candidate rank that motivated it and the reason the
  region mattered, so the spend is auditable against the shortlist. And
  exhaustion forces a decision rather than silent continuation: the first region
  that does not fit ends the read, it and everything after it are recorded as
  deferred with what they would have cost, and the plan is marked exhausted. A
  caller that overruns gets an explicit partial plan, never a quietly truncated
  one.
- `mcgyvr read QUERY [REPO]` — resolve a target, then read the regions it
  justifies within `--budget` estimated tokens, with `--context` to set the
  window size; what was read and what was deferred are both reported.
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

### Changed
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
