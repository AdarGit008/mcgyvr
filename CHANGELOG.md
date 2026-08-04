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
- Signature slice and an `IMPORT` kind on the symbol index
  (`src/mcgyvr/orchestrator/symbols.py`) — the deterministic half of ADR-0007
  (#115, E7). `Symbol` carries the declaration without its body, so the text a
  contract will ship as `deps[].signature` comes from the parser rather than
  from a model: the decomposer names which symbols a contract depends on, the
  index states what they look like. A signature is therefore reproducible from
  a checkout — two extractions over unchanged bytes produce the same text, and
  a reviewer can diff a contract's `deps` against the index instead of trusting
  it. Python signatures are unparsed from the `ast` node the collector already
  visits, keeping decorators (`@property` is interface, not implementation) and
  the docstring, with the body replaced rather than trimmed; JS/TS signatures
  are the node's own text with the body field sliced off, which is verbatim and
  so diffable. Both come out of the passes that already run, so neither costs a
  second parse and no third parse site is introduced — `context_prune.py` stays
  closed as won't-do. `SymbolKind.IMPORT` makes a file's dependencies readable
  from the index rather than re-derived, in both languages: the name is the one
  depended upon rather than the one locally bound, `detail` is the module it
  comes from (relative imports keep their dots), and the whole statement is on
  the signature, which is where an alias survives. A star import is recorded
  under `*` rather than dropped. A re-export is not an import — it is already
  an export, and ADR-0007 leaves the barrel file in the "the index cannot name
  this" bucket. `SymbolTable.imports(path)` narrows to one file, which is the
  question a decomposer asks of a target. Sizing the context budget from this
  is #50's; enforcing it remains `check_prompt_fits`.
- Decomposition (`src/mcgyvr/orchestrator/decompose.py`) — a prompt and an
  indexed repository become validated contracts (#50, E7). This is the judgment
  step, and the design question is how little of a contract a model's opinion is
  allowed to author. The answer generalises ADR-0007: a model decides
  *relevance* — which kind of work this is, which file it lands in, which of a
  file's symbols the target needs — and the repository decides *fact*. So the
  seam is not "the model writes a contract and we check it" but "the model
  writes references and the index resolves them": a `Proposal` names a symbol
  and there is no field on it that could carry a signature. Four properties are
  structural rather than remembered. Every emitted contract came through
  `contract.loads`, the same entry point direct mode uses, because that is the
  only way out of the module — so "an emitted contract is one the direct-mode
  API accepts" is a property of the code path, and a document the loader rejects
  becomes a refusal carrying the loader's own field-naming message. A dependency
  the index cannot state is refused rather than described, which is ADR-0007's
  deliberate trade: a missing dep degrades a prompt, an invented one poisons it
  and reads as authoritative. A request nothing can be made of returns an
  explanation and an empty contract list — there is no fallback that wraps an
  unparsed prompt in one big contract, because a degenerate single contract is
  worse than a refusal for looking like a plan. And nothing is emitted that no
  configured ladder can serve, checked with the catalog's own `servable()`
  against a real config, naming what the ladder *can* run. Contract ids are
  derived from the work rather than from a clock, so the same prompt over the
  same repository yields the same contracts; two identical proposals collide and
  the duplicate is refused rather than given an ordinal. `context.max_input_
  tokens` is sized off `Contract.worker_view()` — the only accessor a worker
  prompt may be built from, so what is measured is what will be sent — floored
  at the schema default and with no margin added, the error band being #117's to
  measure rather than this module's to invent.
- The token estimator's error band, measured and fed back (#117, E13).
  `estimate_tokens` is four characters per token and says so; nothing knew what
  that cost. `tools/tokens/measure.py` measures it against the real tokenizers
  of the models the capability table ships, and CLM-0011 registers the result
  over 2,387 units (`records/measurements/tokens-2026-08-03/`). The corpus is
  *captured, not constructed*: a recording `estimate` is passed to the real
  `explore()` through the seam it already has, so every string measured is one
  production actually asked the estimator to count. Queries are each frame's own
  exported names, sorted and capped at 40 per frame with the cap reported. The
  headline is that the proxy **under-counts more often than it over-counts**,
  and by how much depends on the vocabulary: Qwen2.5-Coder median −0.8% (p05
  −17.6%), gpt-oss −0.5%, but DeepSeek-Coder-V2 −17.9% and under-counting 94.9%
  of units, because a 100,000-token vocabulary splits the same text into more
  tokens than a 151,643-token one. The band is language-dependent (JS/TS −7.9%
  against Python +2.2% on Qwen), and worker-view documents are under-counted on
  **100% of units on every vocabulary** — which is exactly the text a prompt
  budget is enforced against. Three vocabularies, not four: Qwen3-Coder ships
  Qwen2.5-Coder's vocabulary and produced identical counts on all 2,387 units,
  established from the counts rather than from a model card.
- `check_prompt_fits` reserves the measured band and says which count it
  enforced with. `TokenCount.ESTIMATE` is charged `ESTIMATE_RESERVE` (0.32 —
  the worst vocabulary's p05, rounded up) on top of itself; `TokenCount.
  TOKENIZER` is exact and reserves nothing. Only the under-counting tail is
  reserved against, because the directions are not interchangeable:
  over-estimation costs context, under-estimation ships a prompt the backend
  then refuses. A rejection now names which of the two it was, so it can be
  attributed to the proxy rather than to the prompt. The reserve leaves a
  measured ~5% residual — stated, where before it was unquantified.
- A `measure` dependency group, deliberately not `dev` and not a default group,
  so `make setup` and CI never install a tokenizer. The measurement uses one;
  the product must not, since a tokenizer in `dependencies` would defeat the
  point of a model-free proxy. Runtime dependencies are unchanged.
- `Proposer` — the judgment seam, with no default binding. A caller supplies
  one; `RecordedProposer` returns a fixed list, which is what makes "the same
  prompt and repository yield the same shape" an assertion about the decomposer
  rather than about a model's temperature. The deterministic pass always runs
  first and is handed over as `Evidence` (ADR-0001 boundary 2) — a proposer
  reads what exploration found and has no way to ask the repository for more.
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
- Availability probing (`src/mcgyvr/availability.py`) — per-source liveness,
  priced at one short timeout per run (#22, E3). The problem is cost, not
  detection: a ladder escalates, so a dead source discovered at dispatch time is
  discovered again on every attempt, and three rungs on one dead host would be
  three timeouts for one fact. A verdict is therefore cached for the life of an
  `Availability`, a batch is probed concurrently, and the timeout is seconds
  where the dispatch timeout is two minutes — a local 7B taking ninety seconds
  to answer is healthy, a host taking ninety seconds to accept a connection is
  not. A probe reads the protocol's model-list path and never sends a
  generation, which would cost tokens and would conflate a host that is down
  with a model that is not loaded. Classification turns on the fact that any
  HTTP answer proves something is listening, so the question is whether a
  *dispatch* would work: transport failure and 5xx are down; 401 and 403 are
  down because the source is answering and would refuse every rung on it
  identically; and **404 and 405 are live**, because the model-list path is
  optional and reading it as down would silently shorten the ladder by skipping
  a source that serves generations perfectly well. That asymmetry tracks the two
  kinds of source mcgyvr talks to, which fail differently: a **local backend**
  (Ollama, llama-server, vLLM, LM Studio, TGI, on hardware the user controls)
  characteristically fails by not running, or by not implementing the model
  listing at all — which is what the 404 arm is for; a **hosted provider** fails
  by rejecting a key that is wrong, expired or revoked — which is what the 401
  arm is for, and which is a different fault from the unset variable
  `source_map` already catches without a network. Nothing branches on the
  distinction, since nothing reliably separates them — a local server can want a
  key and a self-hosted vLLM can sit on a public hostname — so the reason text
  names the credential variable when there is one and says none is configured
  when there is not. Probing is opt-in —
  `source_map(config)` still touches no network, and reachability enters through
  `SourceProbe`, a two-method structural type that hands endpoints down and gets
  back source-name-to-reason, so `pool.py` still knows nothing of HTTP, timeouts
  or retries and nothing above the seam gains a way to learn where a rung runs.
  An unreachable source's rungs become ordinary `Skipped` entries carrying the
  probe's own words, in declared ladder order alongside the structurally-skipped
  ones; everything down is an empty ladder that can say why, not a hang.
- Type-check command locator (`LanguageAdapter.locate_type_check_command`) —
  the adapter capability ADR-0006 asks for (#114, E12). mcgyvr never chooses a
  type checker and never synthesises its flags; it locates whatever the target
  repository already declared and returns that invocation. Python finds a
  checker in the files that checker itself reads — `[tool.mypy]`, `mypy.ini`,
  `.mypy.ini`, a `[mypy]` section in `setup.cfg`, `[tool.pyright]`,
  `pyrightconfig.json` — and JS/TS treats a `tsconfig.json` as the declaration,
  yielding `tsc --noEmit`. A repository declaring none yields `None`, which is
  load-bearing rather than a shrug: a `type_annotation` contract is not
  available there, and the contract loader already refuses one with no
  acceptance command. Detection parses rather than greps, because a substring
  match fires on a dependency pin, on a comment, and on another tool's key that
  happens to contain the name — each of which would fabricate a command for a
  repository that runs no checker, failing in the sandbox as though the worker
  were at fault. The returned command is bare: `mypy` with no arguments reads
  the repository's own `files` and `exclude`, and adding a path would substitute
  mcgyvr's idea of the scope for the one the project wrote down. Strictness is
  whatever the repository set — imposing `--strict` on an unannotated repository
  is not a stricter check but a different one that every rung fails, converting
  spend into a guaranteed zero. Two guards hold the absences: no forbidden flag
  in any arm's output, and nothing in the locator or its helpers calls a
  subprocess, an import or an eval, asserted by parsing their ASTs rather than
  by inspection.
- The decomposer emits the located type-check command into a contract's
  `acceptance` (#142, E7). ADR-0006 ended by naming the gap — "what is missing
  is not a step; it is whoever fills the list in" — and this is that: a
  `type_annotation` proposal that declares no acceptance command of its own gets
  the checker the target's language adapter located, and a repository declaring
  none yields a refusal saying so rather than a contract that cannot load. A
  proposal carrying its own commands is neither overruled nor appended to; only
  `type_check` is filled in, because `locate_test_command` guesses a runner
  rather than reading a declaration and `failing_test_first` needs a specific
  test no locator can name. **The command is emitted exactly as located** — the
  target is never appended, which settles the question #114 left for this layer.
  Measured, not assumed: `tsc --noEmit file.ts` discards `tsconfig.json`
  entirely, so on a `strict: true` project the project-wide run reports `TS7006`
  and exits 2 while the per-file run over the same file exits 0 — appending
  would silently replace the check with a weaker one that passes. mypy's
  `exclude` likewise does not apply to a file named on the command line. The
  case that motivated appending — bare `mypy` exiting 2 with "Missing target
  module, package, files, or command" on a repository that configures no
  `files` — is caught by `Acceptance.precondition` against the unchanged tree,
  before an attempt is spent and without charging a worker, as is the larger
  version of the same problem: a repository carrying a backlog of pre-existing
  type errors.
- `mcgyvr pool --probe` — additionally ask each source whether it is answering,
  drop the rungs of any that is not, and report every source that was asked with
  how long it took and how the verdict was reached. `--probe-timeout` sets the
  budget.
- Capacity semaphore and concurrent dispatch (`src/mcgyvr/capacity.py`) — the
  bound `max_parallel` had been declaring since E1 and nothing was enforcing
  (#23, E3). `Capacity.of(config)` holds one semaphore per **source**, because a
  ladder of four rungs on one machine is four names for one card, and
  `runner.dispatch(..., capacity=)` holds a slot for exactly the length of one
  request. That placement is the whole of the escalation guarantee: a task moving
  from a local rung to an API one occupies each source only while it is talking
  to it, so "escalation does not leak or double-count" follows from where the
  acquisition sits rather than from a per-task ledger that could be got wrong —
  a task never owns a slot. A slot is returned however the dispatch leaves, so a
  backend that times out does not cost the source capacity for the rest of the
  run. `run_batch` runs a batch of jobs under that bound, defaulting to as many
  threads as there are slots in total and returning one outcome per job **in
  input order**, since ordering by completion would make a batch reproducible
  only on a quiet machine; a job that raises becomes a named failure beside its
  neighbours' results rather than sinking the batch. `Usage` reports per source
  the acquisitions, the peak concurrency actually reached, and the time callers
  spent *waiting* — the last being the one number that says a declared capacity
  is the ceiling. A nested dispatch to a source the calling thread already holds
  is refused by name rather than deadlocking silently against itself, which at
  the default `max_parallel: 1` is what it would otherwise do. Measured on the
  executor: 12 jobs of 50 ms across sources of capacity 3 and 2 took 0.205 s
  against 0.604 s serial (2.94x, floor 0.15 s set by the two-slot source).
- The binding proposal states what a capacity number does not buy (CON-02). A
  single-slot server handed concurrent requests **serializes them rather than
  refusing them**, so an over-declared `max_parallel` is not an error anyone will
  see — it is a queue nobody will. The config schema already carried CON-01's
  good news that distinct models genuinely run concurrently on one card, and the
  good news is the half that gets remembered.

- Tier ladder and within-family escalation (`src/mcgyvr/route.py`) — which rung
  a contract is tried on, and the named moment a family is spent (#24, E3). The
  ladder is ordered cheapest-to-dearest in two nested ways, and this module
  walks only the inner one: `plan()` returns the rungs of **one** family in
  config order with the attempts each is allowed, and `climb()` runs that plan
  against an attempt function the caller supplies. Crossing from local to API is
  a spend decision with its own rules (monotonic ascent, a global ceiling, the
  verification upgrade) and stays #43's, so an exhausted family here ends the
  climb rather than quietly reaching for a dearer rung — asserted both
  behaviourally, against a ladder whose API rung is usable and never touched,
  and structurally, over every family the catalog declares. `Exhausted` is its
  own type carrying an `Exhaustion` reason, because *rungs spent*, *every rung
  declined* and *no rung at all* are three different facts about an install and
  want three different responses. A **decline** — a rung answering that this is
  not work it can do (#81's rule) — advances without spending an attempt and
  without being recorded as a failure, since a deterministic tool emitting a
  plausible-but-wrong edit costs far more than one that steps aside. Every rung
  tried is handed the capacity to dispatch under, closing the gap #23 left:
  `dispatch` is unbounded by default, so a walk that bounded only its first rung
  would enforce a source's limit on some of its own dispatches. Nothing here
  assembles a prompt, applies a diff or runs a gate, which is what lets every
  rule be asserted without a model, a backend or a sandbox.
- `ladder.tiers[].attempts` (default **1**) — how many times a rung is tried
  before escalation moves on, making attempt budgets policy in config rather
  than a constant in code. The default is escalate-rather-than-retry: a second
  attempt re-runs the same model on the same input, and the figure this rule was
  inherited with (worker-tier remediation rescued 2 of 35 failures) says that is
  usually spend without a result — a figure carried from local-ai and **not
  re-verified here**, which is why it argues for a default rather than being
  quoted as a measurement (#152). Raising it is most defensible on the dearest
  rung, which has nowhere to escalate to. A contract's `limits.attempts` caps it
  per task and the lower of the two applies, so neither an operator nor a
  contract author can raise the other's ceiling. The deterministic family gets
  exactly one attempt whatever either says, because a tool fails identically on
  retry.
- `Catalog.family_of(source)` — the one definition of "a rung is `api` exactly
  when its source declares a credential", lifted out of the catalog's internals
  so routing asks for it rather than restating it. A family is a **cost class,
  not a location**: re-pointing a rung between two local machines does not change
  it, and local-to-hosted does, which is what makes it the right thing to route
  on.
- `mcgyvr pool` shows each rung's family and attempt budget beside its model.
  Both are decided before anything is spent, and a routing decision nobody can
  read is one nobody can check.

- Escalation policy and its ceiling (`src/mcgyvr/escalate.py`) — which family a
  task climbs to next, what stops it, and what an acceptance actually rests on
  (#43, E6). `ascent()` answers the whole climb before anything is dispatched:
  the families from the contract's floor upward, each family's rungs, the
  attempts each is allowed, and the two ceilings — with no network and no
  model, so routing is diffable rather than merely deterministic. **Ascent is
  monotonic structurally**: the plans are the catalog's rank-ordered families
  filtered once, so a family appears exactly once and ranks only increase.
  Ping-pong between a local rung and an API rung is not prevented by a check
  that could be forgotten; there is nowhere in the shape for it to happen. A
  floor works the same way — families below it are absent rather than skipped.
  `escalate()` walks that ascent against a caller-supplied attempt function and
  ends in one of six machine-readable `Outcome` members, because a caller
  responds differently to a ladder genuinely spent, each of the two ceilings, an
  install with nothing to run, and a ladder that **declined throughout** — the
  last of which says nothing at all about what the ladder can do and must not
  be reported as though it did.
- `budgets.max_attempts` — a hard ceiling on what one task may spend across
  every rung and every family. **Unset is not unbounded**: the bound is then the
  ladder's own budget, which `mcgyvr pool` now prints. Leaving the unset case
  meaning "the ladder bounds it" rather than a number keeps a default this
  project has no measurement behind out of the schema, and keeps two knobs from
  fighting — an operator who raises `max_escalations` does not want a ceiling
  they never set cutting the climb back. `budgets.max_escalations` gains its
  first consumer at the same seam: it bounds *moves*, not tries, because the
  cost an escalation carries is the attempts already spent below it. **Neither
  ceiling charges a decline** (#81's rule reaching the task level): a rung that
  stepped aside spent nothing, so a ladder of rungs that all decline is walked
  in full at no cost.
- A verification policy is **upgraded the moment work leaves the deterministic
  family**, whatever the contract declared. `verification.policy: gate_only`
  describes a tool's output through the gate; leaving it in force once a model
  is doing the work would accept a model's output on a warrant that was never
  about a model. What the install can then do about it is a capability question,
  and `Assurance` is where the difference is recorded: `VERIFIED` is reachable
  only by a verifier that ran and agreed, and a keyless install reaches
  `UNVERIFIED` — accepted on the gate, labelled as exactly that, which is E6's
  third first-class configuration and where #44 attaches. Asserted by driving
  the whole policy × family × verifier matrix rather than a list of cases.
- The gate runs before any verifier, structurally: `judge()` returns on a
  rejected gate before the verifier is so much as named, so a deterministically
  rejected change costs zero verifier spend. #32 stated that ordering; nothing
  held it until now, and it is asserted with a verifier that raises if it is
  ever called — a counter checked for zero would pass against one called and
  ignored, which is the spend the rule exists to prevent.
- A retry prompt carries the **failing checks only** (`RetryNotes`, rendered by
  `build_prompt(retry=...)`). Re-reading the passing checks is spend that
  carries no information. Three exclusions, each for its own reason: checks that
  produced no finding did not fail; observations are findings the gate
  deliberately did not reject on, so quoting them would ask for changes never
  required; and an environment issue is a tool that was not installed, which is
  not something the worker did or can fix.
- `climb(permit=...)` (`src/mcgyvr/route.py`) — a caller-supplied budget
  predicate, asked before each attempt is funded, reported as the new
  `Exhaustion.WITHHELD`. A task-wide ceiling spans families so it cannot be
  computed from one plan, and it may not live in `route.py` either; a predicate
  keeps both true, exactly as the attempt function does. `WITHHELD` is distinct
  because a family that was not allowed to finish must not read like one that
  was tried and could not.
- `mcgyvr pool` prints the ceilings that bound a task, and where an unset one
  comes from. A ladder printed without them reads as though every rung will be
  tried, and by default most of them will not.

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

- Decision `0004-inherited-research-is-re-verified-before-it-is-adopted` —
  research carried over from local-ai is checked against its own cited sources
  and against mcgyvr's measurements before it becomes an issue, and a retained
  number is either registered in `records/claims/` or dropped from the text that
  uses it. Written after an audit of the six inherited architecture decisions
  found the premise they are sized against uncited and contradicted by the
  measurements vendored in `data/`.
- Decision `0005-gate-checks-never-run-target-code-on-the-host` — no gate check
  imports, executes or plugin-loads target-repository code in the orchestrator
  process. For a check that validates against installed packages this is
  correctness before it is safety: on the host it would resolve against mcgyvr's
  own environment, not the target's.
- Decision `0006-the-type-checker-is-the-target-repositorys` — mcgyvr locates
  whatever type checker a repository already declares and never synthesises its
  flags. Imposing `--strict` on an untyped repository rejects every change on
  every rung, and escalation cannot fix it.
- Decision `0007-dependency-signatures-come-from-the-index-not-from-a-model` —
  the decomposer names which symbols a contract depends on; the deterministic
  index states what they look like. A model-authored signature would be an
  unchecked hallucination entering the worker prompt as ground truth.
- Decision `0008-sampling-breadth-is-policy-and-selection-is-the-first-gate-pass`
  — how many draws a rung gets is configuration policy, defaulting to one, and
  the winner is the first candidate the gate accepts. Consensus selection has
  nothing to rank when the gate's last rung is already execution.
- Decision `0009-output-discipline-is-a-cap-not-a-stop-sequence` — v1 bounds a
  worker reply with `limits.max_output_tokens` and a named failure, and sends no
  stop sequences. Against a whole-file reply shape the proposed stop set
  truncates at the second definition and yields a valid partial file.

- Worker prompt bundle and the single-file output protocol
  (`src/mcgyvr/worker/`, #25). A worker is now sent two messages: a measured
  skill bundle as its system prompt, and the contract as the user message —
  the split CLM-0004 varied only the system half of. The shipped Python
  bundle is byte-identical to the `c2` condition the measurement was taken
  on (45% → 70% first-pass acceptance on qwen2.5-coder:3b, ~2.5× faster),
  and a test holds the two files equal, so a reworded bundle fails rather
  than quietly invalidating the numbers. The ≤2 KB ceiling is enforced by
  the loader, not documented: the 8 KB condition measured *worse*, so an
  oversized bundle is a load-time refusal naming what to re-measure. One
  bundle per language adapter, selected by asking the gate's adapters which
  one owns the contract's target rather than by a second table of
  extensions; a target no adapter owns gets no bundle rather than another
  language's.
- The JS/TS bundle is an unmeasured idiom port and says so in its own first
  line. CLM-0004's confidence note bars generalising its percentages to
  another language until re-measured, so the bundle carries no evidentiary
  weight and `Bundle.measured` is how a caller tells the two apart.
- A worker's reply becomes a file only when it is unambiguously one file.
  `parse_reply` accepts exactly one fenced block and refuses everything else
  by name — no fence, two blocks, an unterminated fence, an empty block.
  Truncation is refused before parsing, because a reply cut off at the cap
  can still contain a syntactically perfect block and nothing in the text
  says the tail is missing; only the backend's stop reason knows. A contract
  declaring `unified_diff` is refused rather than parsed as whole-file
  content, which would apply a patch's body lines as source. No stop
  sequences are derived: ADR-0009's decision stands, and the absence is
  recorded where the derivation would have lived.
- `check_prompt_fits` has its first production caller. Assembly measures the
  two messages together against the contract's own `max_input_tokens` and
  returns a `PreflightIssue` rather than raising, since a caller needs the
  assembled prompt in order to report what did not fit. The estimate is
  injectable and the count says which kind it was, so a caller with a real
  tokenizer opts out of CLM-0011's 32% reserve — and the assembled prompt is
  now a thing that exists to re-measure the band over.

- The JS/TS bundle-size experiment (`tools/bundle/`, #144) — the instrument
  that would settle whether `prompts/javascript.md` earns its place, built and
  verified as far as it can be without a worker. **No sweep has been run and
  there is no JS/TS claim record**; `tools/bundle/README.md` states why in the
  file rather than leaving it to an absence. The condition ladder repeats
  CLM-0004's: c0 none, c1 369 bytes, c2 1 877, c3 8 883, nested so size is the
  only variable, with c2 held byte-identical to the shipped bundle by both the
  rig and a test. The task set is 20 JS/TS contracts, each with a reference
  solution and a runnable acceptance script, all validated by the real contract
  loader; `--selftest` runs every reference against its own acceptance and is
  green 20/20, which CLM-0004's design makes a precondition rather than a
  nicety. Dispatch goes through mcgyvr's own `Request`/`runner_for` and replies
  through `parse_reply` with the backend's real stop reason, so a reply this
  project would refuse is scored as a failure by its refusal code rather than
  quietly run. Acceptance needs no toolchain: Node 24 executes TypeScript by
  stripping types — a requirement the rig now probes rather than assumes.
  `node_runs_typescript()` runs a `.ts` file instead of reading `--version`, so
  `--selftest` and a sweep refuse on a Node that cannot strip types, and the
  tests that run acceptance skip on the same predicate. Presence was the wrong
  question: on an older Node every task fails identically and the symptom is
  indistinguishable from a model that cannot write TypeScript.

  The worker a sweep dispatches to is now configuration rather than a command
  line: a git-ignored `tools/bundle/worker.local.json` supplies the endpoint,
  protocol, model and — new — the *name* of the variable holding a key, so a
  model served anywhere reachable can run the experiment while the acceptance
  side stays local and needs nothing but Node. Flags beat the file; unknown
  keys and key *values* are refused rather than ignored; a declared key that is
  not in the environment stops the run instead of sending twenty
  unauthenticated requests. `tools/bundle/worker.example.json` is the committed
  shape.

  **The rig refuses Ollama's native `/api/generate` before dispatching.** Every
  request it sends is `quality_sensitive`, and `runner.generate` refuses those
  on a caveated path under CAV-01 — which measured that path scoring a model at
  32.3% against a true 84.1%. The command this repository had been documenting
  since the instrument was built (`--protocol ollama`) could therefore only have
  produced eighty dispatch errors and no measurement, one request at a time.
  `--protocol openai` is the same port on the same server.

  A sweep now writes `run.json` beside its rows — endpoint with any embedded
  credentials stripped, protocol, model, a SHA-256 per condition, the rig's
  revision, and one entry per invocation. Resuming into a directory whose
  manifest names a different worker or ladder is refused: a rate is not quotable
  without the backend that produced it (CAV-02), and blending two into one
  denominator yields a table that looks like a single measurement.

- `target_content` on the contract schema (#150) — the current content of the
  target file, verbatim, as a worker-facing field of its own. A worker asked to
  fix a bug was told to reply with the complete new content of a file it had
  never been shown: `worker_view()` exposed nine keys and none of them was the
  file as it stands, so the only slot available was `task`, which is documented
  as "what to do, in words". #144's task set is what surfaced it, having put
  fenced source into that field in 12 of its 20 contracts.

  Carried on the contract rather than read from the tree at dispatch, on the
  round-trip property: direct mode publishes the schema as public API, so
  `parse(dumps(c))` round-trips the bytes a worker was actually sent and
  `build_prompt` stays pure. Empty means the target does not exist yet or its
  content is not needed — the documented meaning, not a forgotten field — and
  content declared against a *pattern* target is rejected at load, since there
  is no one file it could be the content of. The prompt renders it as its own
  section under a header naming the target and saying it is the file to change,
  fenced wider than any backtick run inside it (a file containing fences would
  otherwise end its own block, the rule `worker.reply` already parses under).
  No fit-check change was needed: an assembled prompt too large for
  `context.max_input_tokens` was already a preflight issue rather than a
  truncated dispatch.

  The worker/orchestrator split (#94) is now asserted as an equality between
  the view's keys and the schema's `worker_facing` fields, rather than as a list
  of keys someone remembers to update — which immediately exposed drift: `id`
  was in the view and undeclared. It is declared now. Being *in the view* and
  being *rendered* stay different claims; neither `id` nor
  `context.max_input_tokens` is spent on the worker.

  #144's 12 contracts now state their starting code in the slot. Because a
  rewritten contract changes the prompt a sweep measures exactly as a reworded
  bundle does, `run.json` gained a SHA-256 per task alongside the per-condition
  ones, and resuming into a directory measured against a different task set is
  refused rather than averaged.

- The decomposer fills `target_content`, so delegated mode stops sending blind
  (#155). #150 built the slot and filled it only where contracts are authored by
  hand; `decompose()` now puts the target's current content on every contract it
  emits. Three questions #150 had no standing to settle, settled here.

  **Which contracts get it: all of them**, with no list and no catalog key. The
  premise that the deterministic tier never needs content — a tool reads the
  file itself — is false in the running system: `escalate.ascent` climbs from a
  contract's floor family upward and the deterministic family binds no rung at
  all until #81 (`route._why_empty`), so a `format` contract reaches a model rung
  today exactly as a `bug_fix` does. Content a tool ignores costs it nothing,
  because that tier builds no prompt to carry it. So the rule is the schema's
  own, from the other side: fill the slot when there is exactly one file it could
  be the content of.

  **The bytes come from the index, not a fresh read at emit time.** The index is
  the state resolution and exploration already judged from, so two contracts
  emitted from one decomposition cannot disagree about one file, and no second
  unbounded read appears inside a step whose whole cost model is that the index
  was built once. The reconstruction is exact rather than approximate:
  `index_source` splits a `surrogateescape` decode on `\n`, and joining on the
  same separator inverts it byte for byte. `Proposal` gains no field — a
  proposer that could state a file's content could state one the repository does
  not hold, which is what ADR-0007's seam exists to prevent.

  **A target too large to send is refused.** `_resize` sizes
  `context.max_input_tokens` off `worker_view()`, so with the content inside that
  view a budget derived from it can never be exceeded by it: inlining a
  4 000-line file would simply raise the ceiling to swallow it, leaving
  `check_prompt_fits` asking whether a number exceeds itself. `max_input_tokens`
  is now an argument to `decompose()` and the sizing stops there. Refusing rather
  than emitting a blind contract follows from the output protocol rather than
  from strictness — with `whole_file` the reply *is* the file's complete new
  content, so a target too large to send is too large to receive back — and the
  refusal names the measured size, the target's own share of it, and #126 as the
  fix.

  The default ceiling is 32 768 estimated tokens and it is **policy, not
  measurement**: nothing mcgyvr reads declares a rung's context window, not the
  config and not the capability table, whose entries carry quality, throughput
  and VRAM and no window at all. The number says so in the source and is an
  argument precisely because a caller that knows its ladder should overrule it.
  #158 is where a declared window would replace it.

  Recorded rather than fixed: `_indexed` refuses a target the index does not
  hold, so the delegated path cannot emit a contract that *creates* a file, and
  the schema's "empty means the target does not exist yet" is reachable from
  direct mode only. Filed as #159 and held by a test, so the asymmetry is
  recorded rather than assumed.

- A worker on another machine can be detected and bound (#161). `detect` swept a
  hardcoded `localhost` on five ports and `propose` sized rungs against this
  machine's `nvidia-smi`, so the deployment mcgyvr exists for — an agent on a
  laptop, offloading to rigs elsewhere — reported "Backends reachable: none" and
  `init` refused to write anything. `mcgyvr detect --host <name>` and
  `mcgyvr init --host <name>` (both repeatable) sweep named machines; the
  default is still `localhost` alone, so a single-machine install takes exactly
  the path it always took.

  **The ports were already a table and the host was the literal**, so the change
  is the cross product: `targets_for()` expands hosts over `PORT_CONVENTIONS`. A
  host is a bare name or address and never a port, because identification here
  is *by* port convention and a port nobody conventionally uses carries no claim
  about which protocol answers on it.

  **A source name and a backend kind stopped being the same string.** Two rigs
  both run Ollama on 11434, and `sources` is a mapping, so an unqualified name
  is one rig silently overwriting the other in the config. Names are qualified
  with the host (`srv1_ollama`) exactly when a sweep covers more than one — and
  qualification is keyed on hosts *probed* rather than hosts that *answered*, so
  a source does not get renamed when a box is down. `Backend.kind` carries the
  convention (`ollama`) separately, because the capability table's
  `requires_backend` matches on what the server *is*: a model measured on Ollama
  is measured on Ollama whether the source is called `ollama` or `srv2_ollama`.

  **Fit evidence is now chosen by where the backend is, not by which claim is
  stronger.** A VRAM test is a statement about this machine's card, so it
  governs local backends and no others — applying it to a remote rig rejects a
  7B on a 12 GB machine because the laptop asking has none. For a rig elsewhere
  the evidence is its own model listing. That is deliberately the weaker claim
  and is labelled as such: vLLM lists what it has loaded, Ollama lists what has
  been pulled, so it establishes the rig is *provisioned* for the model, not
  that the model is resident. Unlike a VRAM estimate it cannot be wrong about
  which machine it describes. A local install is untouched by this — its model
  listing is still not evidence about a card that is right here and unreadable.
  Only measured models are admitted, so a rig's model list is not a back door
  around the table.

  **Two things the proposal now refuses to be silent about**, both because the
  measured evidence says they are wrong and neither is fixable here. A ladder
  spanning machines says so and names #162: rungs are ordered by measured
  quality, which belongs to the weights, while throughput belongs to the card
  and is not in the table per host — so a cheaper rung on a slower machine can
  cost more wall-clock than the rung above it. And when more than one rig holds
  the same weights, `_serving_source` takes the first host *named*, which is a
  fact about the command line; the rung's reasons now say so rather than letting
  list order read as a decision.

  Verified against two real rigs over a tailnet: `init` on a GPU-less laptop
  binds four sources across two machines, `pool --probe` reports them live, and
  `runner.dispatch` returns completions through the config `init` wrote.

  Found and filed rather than fixed: `init` binds Ollama as `api: ollama`, the
  protocol CAV-01 exists to warn about, so every rung of a default install is
  `quality_safe=False` while `api: openai` on the same port and model is not
  (#164).

- Ollama is asked one way and dispatched to another (#164). `detect` recorded a
  single `api` per backend and `init` wrote it straight into the config, so the
  most common local install there is came out bound to Ollama's native
  `/api/generate` — the path CAV-01 is a record of, which scored
  `qwen2.5-coder:7b` at 32.3% against a true 84.1%. Every rung of a default
  install was therefore `quality_safe=False`, and a `quality_sensitive` request
  was refused outright, so **an `init`-written config could not serve a
  measurement at all**. The uncaveated path was one word away in a file the tool
  had just written itself.

  Asking and dispatching are now separate facts. `PORT_CONVENTIONS` carries
  both, and for every backend but one they are the same answer. Ollama is the
  exception because each of its protocols is better at a different thing: the
  native `/api/tags` is the only listing that enumerates models *pulled but not
  loaded*, which is exactly the inventory a proposal needs, while the
  OpenAI-compatible shape on the same port dispatches with the same model ids
  and no caveat. So detection still asks natively and the config binds
  compatibly — not a compromise between the two, but each used for what it is
  actually better at.

  The rule lives in `binds_as_for()` reading the one convention table, so a
  `Backend` built by hand — in a test, or by some future caller that is not
  `probe` — cannot silently take the caveated default. A test caught exactly
  that during the work.

  `init` explains the switch among its decisions rather than leaving it to look
  like a bug: a config saying `api: openai` for a source `detect` called Ollama
  needs its reason attached, and the reason is CAV-01 with the numbers.

  Verified against a live Ollama on two rigs: a `quality_sensitive` request,
  which the previous configuration refused outright with `QualityCaveatError`,
  now dispatches and returns `quality_safe=True`. This is what unblocks #144,
  which cannot take a measurement on a caveated path.

### Changed
- A bundle's leading provenance marker is stripped at load
  (`worker.bundle.strip_provenance`) and no longer reaches the worker or the
  ceiling. #25 put the "UNMEASURED" marker in `javascript.md` so the caveat
  could not be lost by reading the file alone; #144 found the cost — those 162
  bytes were 8% of what the loader handed a worker, they opened its system
  prompt by telling it its own instructions were an unmeasured port whose
  figures should not be cited, and they were charged against the 2 KB limit
  `MAX_BUNDLE_BYTES` exists to enforce. The marker stays in the file, which was
  the right half of #25's decision. Stripping it is also what lets #144's two
  acceptance conditions hold at once: without it, a bundle cannot both carry an
  UNMEASURED marker and be byte-identical to the condition a sweep measured,
  because the marker is in the bytes.

- `README.md` and `data/README.md` no longer describe `AdarGit008/local-ai` as
  archived; it is not. ADR-0001 is left as written — a decision record states
  what was decided, and is not edited to track a fact that changed after it.
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
- `detect.Endpoint` is now `detect.ProbeTarget`, and `DEFAULT_ENDPOINTS` is
  `DEFAULT_PROBE_TARGETS`. The two concepts had collided on one name: a probe
  target is a *candidate* address that may turn out to have nothing behind it
  and exists before any config does, while `pool.Endpoint` is somewhere a rung
  is configured to run. Naming them apart keeps "where might something be" and
  "where does this rung run" from reading as the same idea.
- `mcgyvr.orchestrator.index` exposes the per-file primitives a build is made
  of (`read_source`, `index_source`, `IndexAssembler`, `enumerate_files`) so
  the cached build reuses them rather than reimplementing the bounds. Both
  builders assemble through `IndexAssembler`, so a cached build and a fresh
  one cannot drift into reporting differently.
- A targeted read records whether the caller already held it (`TargetedRead.
  supplied`) alongside its real estimated cost, and an exploration reports what
  supplied context saved it (`Exploration.saved`). A free read stays visible and
  costed rather than disappearing from the account.
- The index cache format is version 2: an entry's symbols carry a signature, so
  a version 1 cache is discarded and rebuilt rather than served without one.
- `orchestrator.read._estimate_tokens` is now the public `estimate_tokens`, so
  the decomposer sizes a context budget with the same proxy the read plan spends
  against instead of growing a second one that could drift from it. What the
  proxy's error actually is remains #117's to measure.
- The resolver and the read planner name the symbol kinds they act on rather
  than excluding references. A reference and an import are both occurrences of
  a name declared elsewhere, so neither makes a file a candidate for that name
  or anchors a window in it — stated positively, adding a kind is a decision
  about what it should mean rather than a silent reclassification.
- `mcgyvr index --symbol NAME` prints each definition's signature under it, so
  the text a contract would carry as a dep is checkable against the file
  without loading the index.
- `pyyaml` is now a runtime dependency. The config file is YAML because it
  carries policy that needs comments to stay hand-editable (ADR-0001).
- Worker bindings are named `<role>_<locality>_<model>` (for example
  `worker_local_qwen2.5-coder-7b`), replacing the positional `local-N`. A
  name says what a binding IS rather than where it sits in an ordering, so
  inserting a rung cannot silently change what a policy reference means.
