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
- `Capacity.concurrency()` reports the one figure `Usage` structurally cannot:
  how many dispatches this process had in flight **across** sources at once,
  against the declared total (#200). `Usage.peak` is keyed by source, so a batch
  that ran `local` three wide and then `fast` two wide reports 3 and 2 whether
  or not the two ever overlapped — a batch working two rigs together and a batch
  draining them in series are indistinguishable in it. Tracked rather than
  derived, because a maximum of sums is not the sum of maxima and the coinciding
  moment is the whole point. #185 is what made the number meaningful, by taking
  the bound host-wide.

  It arrived through a flake. `test_a_mixed_batch_...` asserted a wall clock —
  six 50 ms jobs required to beat a 300 ms serial floor by 30% — and failed at
  232 ms on a loaded box: faster than serial, per-source peaks intact, so the
  concurrency had plainly happened. The clock was standing in for the
  cross-source property, because nothing measured it. A stopwatch cannot
  distinguish "the sources never overlapped" from "the box was busy".

  The tests no longer time anything. Jobs **rendezvous on a barrier** — each
  holds its slot until N parties hold theirs — so a busy machine makes a test
  slower and never wrong, while a series-draining executor never trips it. The
  bound test's assertions were also split by kind: `<=` (never exceeded) is
  safety and no load can cause a violation, so sleeping jobs still test it;
  `==` (the ceiling was reached) is liveness and moved to the barrier tests
  where it is deterministic. Measured after: 25/25 capacity runs under
  eight-core load, 8/8 full-suite runs, against 2 failures in ~14 before.
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

- The JS/TS bundle sweep ran, and it found no effect (#144, CLM-0012, the
  measurement in `records/measurements/jsts-bundle-2026-08-04/`). Two full
  80-cell sweeps of the four-condition ladder on `qwen2.5-coder:3b` at Q4_K_M,
  one per rig, measured first-pass acceptance of 45% (`c0`, no bundle), 55%
  (`c1`), 50% (`c2`, the shipped `prompts/javascript.md` byte for byte) and 45%
  (`c3`). No rung separates from having no bundle at all: net deltas against
  `c0` are +2, +1 and 0 tasks against a `±1`-task noise floor the design set in
  advance, built from flips in both directions, McNemar exact `p` of 0.50, 1.00
  and 1.00. CLM-0004's Python effect was +5 tasks.

  The two rigs are what put the noise floor on the record instead of assuming
  it. `temperature=0` is not bit-reproducible across different cards: 19 of 80
  cells returned different completion-token counts and 4 flipped verdict — yet
  every condition total was identical, because the flips paired within their
  condition. So a re-roll moves about one task per condition, which is the size
  of the largest delta observed.

  **The mechanism is the transferable half.** CLM-0004's gain came from output
  rules cutting completion tokens 403 → ~124, and completion tokens dominate
  wall time. This run measured them flat at 166.8/167.3/169.4/176.6, latency
  flat to match. The 3b was not rambling on this task set, so the device the
  bundle works through had nothing to act on — which predicts where a bundle
  pays by a property that can be checked before running a ladder (does `c0`
  over-produce?) rather than by language.

- The control CLM-0012 could not run has been run, and the null is about
  neither the language nor the serving stack (#167, CLM-0017, the measurement
  in `records/measurements/python-bundle-2026-08-07/`). CLM-0004's Python task
  set was recovered from `AdarGit008/local-ai` — still there, pinned to the
  commit the 2026-07-28 run was made at, and provably undrifted since — and
  three arms ran on `qwen2.5-coder:3b` Q4_K_M at the endpoint CLM-0012 used.

  **Serving stack: ruled out.** CLM-0004's instrument, re-run byte-unchanged
  against Ollama, reproduces the effect (35/50/55/65% across `c0`–`c3`; +3, +4,
  +6 tasks paired against `c0`) and reproduces its never-passing set *exactly*
  (t02, t03, t06, t17, t18, t19). CAV-02 is a real rule that does not bite here.

  **Language: ruled out.** The same twenty tasks, ported to mcgyvr contracts and
  run through mcgyvr's rig against the same endpoint, are flat: +1 task at every
  rung, the same task each time, p = 1.00.

  **It is the harness, and one sentence is the whole effect.**
  `render_user_message` already ends every user message by demanding the
  complete file as one fenced block and nothing else — the output-shape device
  CLM-0012's own token analysis identified as the mechanism. Through it the 3b
  emits 111.8 completion tokens at `c0` where local-ai's contract draws 427.4.
  A positive control settles it without the port in the way: the *original*
  contracts under the *original* harness at `c0`, with that one sentence
  appended and nothing else changed, score 11/20 at 121.5 completion tokens
  against 7/20 at 427.4 — matching the entire 1 972-byte bundle's 11/20 and
  beating it on tokens. The remaining ~1 500 bytes of standards, checklist and
  pitfalls bought nothing measurable on either task set.

  This discharges CLM-0012's scoping sentence and supersedes its attribution of
  the flat token curve to the task set; CLM-0004 is neither withdrawn nor
  weakened, and now has a stack it demonstrably applies to.

- Decision `0012-re-entry-is-refused-by-what-the-caller-holds` (#177) — nothing
  re-enters mcgyvr while holding a pool slot or running inside a sandbox, and
  the rule is about possession at the moment of the call rather than about the
  caller's role, because a rung bound to an agent harness is a worker by
  function and an orchestrator by shape. v1 permits no nested run at all, kept
  as a separate scope statement so the rule survives the scope changing.
  Re-decomposition mid-run is named as *not* re-entry — it is a loop in one
  instance, and its budget stays with #155/#158. The record corrects the
  argument it was filed on: the hold-and-wait deadlock is already absent by
  construction, since `capacity.py` acquires around the dispatch and a task
  never owns a slot, so the rule rests on the credential-free sandbox and on
  value per token instead.

- Decision `0013-decomposition-is-api-tier-only` (#178) — the `orchestrator`
  role may bind only to a source in the `api` family, refused at load rather
  than labelled at runtime. The argument is asymmetry of consequence, not
  quality: a worker's diff meets six checks built to catch it, while a
  well-formed contract for the wrong work passes all of them and arrives as a
  clean PR. Decomposition is therefore always api-tier — mcgyvr's binding in
  delegated mode, the calling agent's in direct mode — so a keyless install
  gets direct mode rather than a local decomposition nobody chose. The rule is
  a proxy (a source that declares a credential) and says so; the verifier is
  left open to #179 rather than swept in by symmetry.
- The breadth campaign (`tools/breadth/campaign.py`) and its record
  (`records/measurements/breadth-campaign-2026-08-06/`). Every model on a host,
  smallest first, probed up a difficulty ladder to the tier where it genuinely
  fails, then swept there with eight serial draws and no early exit — fourteen
  model-runs over two hosts. Breadth's value turns out to be a property of the
  rung and nothing else, ranging from +8 tasks of 20 at the bottom of the
  ladder to zero on the strongest rung (CLM-0014). Two rows measure the
  768-token cap rather than a model, and say so.
- `tools/breadth/selectivity.py` and its result: what breadth is worth when the
  checker is weaker than ours. It thins each acceptance to a fraction of its
  assertions, re-selects from candidates already on disk with no worker
  dispatched, and judges the winner by the full file. Pooled over 30 sweeps the
  gain from one draw to eight falls from +5.0 to +1.9 as the checker goes from
  whole to a quarter, while accepted-but-wrong answers rise with every extra
  draw (CLM-0016). Validated by reproducing 4751 of 4751 original verdicts at
  full strength before any weakened cell was read.
- `--sampled-temperature` on the breadth rig, and the first measurement of a
  number inherited from DEC-6 and never tested. Only the weakest model gains
  from raising it; per-draw quality falls in every cell; T=1.3 fails by
  producing replies the parser refuses rather than worse code (CLM-0015).
- `tools/breadth/tasks/d1r/` — t20 with its contract repaired, as a variant set
  the campaign driver cannot climb into. Its acceptance asserted a case its own
  contract declared unstated. Repairing it changed no outcome (0 of 36 draws
  before and after), so the defect was real and explained nothing.
- Decision `0019-the-bar-is-a-reality-floor-and-a-per-lever-rule` (#229) — the
  bar splits in two. A **reality floor**, which is a property of the instrument
  and binds at *resolution* rather than at drift; and a **per-lever adoption
  rule**, because a reversible prompt line and a fine-tune costing GPU hours are
  not the same proposition. For a reversible zero-marginal-cost lever the bar is
  whatever the bench resolves, so a small gain is adoptable. Three verdicts
  replace two — EFFECT, NULL and UNDECIDED — and only NULL retires a lever.
- `tools/power/` — the paired-power arithmetic that decision runs on, derived
  from the checked-in records rather than asserted. In a paired design the
  discordant pairs carry the power, so nominal *n* is the wrong denominator, and
  with `m` discordant pairs the best-case two-sided p is `2 / 2**m` — below six
  nothing is detectable at any effect size. Applied to what the repository
  already held: **eleven of the twelve bundle contrasts ever measured were
  unresolvable before the model was dispatched**, and the Python arm is 5%
  responsive — nineteen of its twenty tasks pinned — while reading 65–70% and
  looking in band. Greedy re-run drift is 0–1 task across four model sizes, so
  #216's ±0.7pp transfers and the instruments are quiet but coarse. Sizes the
  bench at **n = 400** paired tasks (+5 to +8pp over the measured discordance
  range), whose cost is authoring rather than the 3–5 rig-hours it runs in.
- `tools/instruments.json` and `tools/instruments.py` (#230) — the measurement
  sets, declared once as data and read by every producer that could reach them.
  `tools/problems/admit.py` already refused pool problems that collide with
  them; `tools/replies/pin.py` and `tools/finetune/build_dataset.py` had no
  concept of a set they must not draw from at all, which is how the #189 pilot
  came to train on **622 examples from `d1` and 116 from `d2`** — `d1` being not
  a copy of `tools/bundle/tasks/` but that directory itself, half the floor
  instrument. A run is recognised three ways, because provenance hides in three
  places: the tier it declared, the contract digests it pinned, and the
  instrument id space its tasks fall in. A run that answers none of the three is
  unclassifiable rather than clean, and raises.
- Instrument protection at the point of entry and again at the point of use.
  The pin stamps every run's verdict into `golden.json` (**9,173 of 12,331
  replies are instrument material**) rather than dropping them — ADR-0016
  requires the parser to be measured on the population it faces, and a stamp
  serves both readers where an exclusion would serve neither. The dataset
  builder then refuses stamped material, cross-checks the stamp against a live
  classification, and treats **disagreement as fatal** rather than resolving it
  the permissive way. Rebuilt clean, the training corpus is **608 examples over
  150 problems** — smaller than #189's 738 and 7.5× wider in problems.
- `docs/what-a-tune-may-train-on-2026-08-10.md` — the guard removes three
  quarters of the captured replies from the training path, so it ships with the
  answer to what is left: the #197 pool today, #225's reserved split when it
  exists, and "no usable source yet" recorded as a finding rather than worked
  around.

- `docs/adoption-bar-prior-art-2026-08-10.md` — searched before choosing a
  number. The noise side converges on discordance as the binding quantity, and
  one source's HumanEval figure matches `tools/power`'s to the decimal. We did
  not find a published adoption threshold in what was searched; reported gains
  cluster at 9–51pp, an order of magnitude above the margin in question.

- `docs/bench-sourcing-2026-08-10.md` (#225) — the in-repo inventory recorded
  before any outside set is considered: the five retired sets with their n,
  language, 3B rates and CLM sources as the *specification* of in-band
  material, the vendored local-ai originals and the pool as adjacent material
  barred from the bench, and the sourcing order the rest of the search must
  follow.

- `records/measurements/mbpp-plus-3b-2026-08-10/` (#225) — MBPP+ measured
  against the floor model through the rig sweeps' own serving path: 70.6%
  base / 60.6% plus, greedy, EvalPlus 0.3.1 against Ollama on srv1. The
  issue's "plausibly between d3 and the pool" hypothesis is refuted — MBPP+
  reads above d1, at the easy end the retired sets already covered — and the
  d3→pool collapse is confirmed as a unit-of-work cliff, not
  small-function difficulty. The contamination caveat travels with the
  number, cutting against the easy-end placement rather than for it; the
  operational conclusion (locator, never anchor) survives either way.
  `docs/bench-sourcing-2026-08-10.md` §3 records the outside-set search:
  the 2026-08-07 adopt-nothing verdict adopted under the bench's strictly
  higher bar, and MBPP+'s 378 ids joining HumanEval's 164 in the campaign's
  decontamination blocklist.

- `tools/bench/` and `docs/bench-design-2026-08-10.md` (#225) — the bench
  campaign's design of record and its first committed mechanisms, landed
  deliberately before any generated problem exists: `split.py`, the
  bench/reserve split rule (salted per-id hash — blind by the commit date,
  stable under the pauses the #197 record guarantees, pinned by test so it
  can never drift), and `mbpp-entrypoints.json`, MBPP+'s 378 entry points
  joining HumanEval's 164 in the item-level decontamination blocklist. The
  design fixes the names (`bench-ts`/`bench-py`, flat roots, `b<nnn>-<slug>`
  ids, reserve outside the declared roots), the declared-target
  anti-triviality rule multi-symbol files need, the manifest-only serving,
  the 2048 sweep cap, and the campaign order in which the declaration
  precedes the first sweep.

- `tools/bench/admit.py` (#225) — the bench admission gate, live and
  smoke-tested end to end. The pool gate's execution machinery imported by
  path, with the bench's own semantics: `b<nnn>-<slug>` ids; the
  `meta.json` sidecar carrying `file_shape`, shape and `steering_band`
  labels plus a `multi_symbol` problem's per-arm `target_symbol`;
  **declared-target anti-triviality** — the stub is the reference with
  only the target symbol's behaviour degraded (Python shadows, TypeScript
  renames the mandated `export function` form or refuses as its own named
  failure), helpers intact, so the checker guarantee means the same thing
  at every file shape; both front doors screened over every declared
  function; and the near-duplicate screen running across the split by
  screening every candidate against the whole manifest, the pool, and the
  instruments. `--pin` computes the half from the pre-declared rule and
  places reserve problems outside the roots the declaration will walk;
  `--verify` holds tree, manifest and split rule to each other; `--cells`
  reports realized counts per steering cell. Offline invariants pinned in
  `tests/test_bench_gate.py`.

- The orchestration core ported from local-ai as **library code**: nineteen
  levers, each stated first as a behaviour test in `tests/red_port/` and then
  implemented. The port's finding was that mcgyvr was a library of seams with
  no assembled driver — `escalate()`'s `attempt`, `decompose()`'s `propose`
  and `judge()`'s `verifier` were unbound parameters, and
  `runner.dispatch_role` had no caller at all.
  **That finding still stands after the port.** These levers are not wired
  together: 28 of 35 public entry points have no production caller,
  `runner.dispatch` among them, and there is still no `run` subcommand. A task
  can be driven to a commit only by writing the orchestration `src/` does not
  contain. An adversarial review of this work
  (`docs/port-pressure-test-2026-08-29.md`) found nine critical defects that a
  passing suite does not reach — read it before building on any of this.
  - `deliver.py` writes an accepted change into the repository it was attached
    to and commits it, re-confirming at commit time what acceptance
    established at build time. It refuses a dirty tree, diffs against the
    sandbox base commit rather than the attach revision, and restores a
    byte-exact snapshot on every non-committing exit. `config.delivery.*` was
    validated and read by nothing; it is now read.
  - `telemetry.py` records every attempt exactly once, whether it returned or
    raised, as append-only JSONL with corrections folded latest-wins. No
    module-level state and an `flock`ed whole-line write, so several
    orchestrators can share a sink.
  - `verify.py` gives `dispatch_role` its first caller: the verifier prompt,
    the anchored first-token parse, and the refusal to let a model judge its
    own output. The semantic rung stays non-blocking and reaches the reviewer
    as notes, which is what #129 measured and chose.
  - `repair.py` fixes what a gate rejection can fix deterministically and
    re-runs the gate, so a repairable failure costs no model call.
  - `deterministic.py` binds the tier-0 floor in the *plan*. All four
    deterministic task types previously planned nothing to run on their own
    floor, so each was a model call for work `ruff` does for free. The floor
    now plans a tool — but **nothing executes one**, and binding it regressed
    `escalate()`, which raises on all four types where it previously fell
    through to a model. Both are open; see the pressure-test report.
  - Also: `waves.py` (DAG waves on `depends_on`), `pending.py` (stash and
    resume work stranded by an unreachable verifier), `cooldown.py`,
    `consensus.py`, `cleanup.py`, `attempt.py` (a retry is told what the
    previous one got wrong), `gate/typecheck.py`, `worker/scoped.py`, and
    per-task-type output caps.
  Verified against 18 regression tests pinning what mcgyvr already did better
  than local-ai — sandbox isolation, context assembly, availability probing,
  failing-test-first acceptance, secret scanning, determinism. None regressed.

- **The driver (`src/mcgyvr/drive.py`) and `mcgyvr run`** — the two seams the
  2026-08-29 pressure test named as standing between the port and a working
  orchestrator, and the command that roots them. `run_tool_step` executes a
  deterministic `ToolStep` inside a sandbox, which `deterministic.py` planned
  in full and said was "the caller's" to run — there was no caller, so the
  cheapest family in the catalog planned commands nothing executed.
  `dispatch_prompt` turns a `WorkerPrompt` into a `Request`, which is the first
  time `contract.limits.max_output_tokens` reaches anything and the first
  production caller `runner.dispatch` has had. `worker_attempt` is the attempt
  function `escalate`, `climb` and `judge` were each written to receive: prompt,
  dispatch, parse, apply, gate, judge, with the retry note carried from the last
  judgement on the same rung so `climb` keeps owning how many attempts a rung
  gets. `mcgyvr run CONTRACT --repo PATH` drives a deterministic contract to a
  gate verdict, and to a commit with `--commit`.
- `Contract.acceptance_commands` and `Contract.demonstration_commands` — the
  contract's command strings as argv. Nothing split one into the other, so a
  contract's acceptance bar was declared, validated at load, and executed by no
  code path.
- `drive.Recording` — where attempt records go and which orchestrator is
  writing them, giving `telemetry.observe` its first caller. The orchestrator id
  is a value the caller constructs, never derived from the process, and it is
  part of the attempt id rather than only a field beside it: `fold` keys
  attempts by that id and a repeat supersedes, so two orchestrators on one
  contract and one rung would otherwise have written one row that erased the
  other (§9).
- `gate.findings.Finding.for_model` and `Finding.names_a_file` — one rendering
  for the operator and one for anything a model reads. An acceptance finding
  carries the command it ran in `path`, and `acceptance` is a contract field
  #94 keeps off every model-facing surface.
- `pool.SourceMap.role_model` — which model a role runs, for callers above the
  seam. `role()` returns a `RoleBinding`, which carries an `Endpoint`, which
  carries `credential()`.

### Fixed

- **Pattern E — five declared boundaries that nothing was holding** (pressure
  test 2026-08-29).
  - **#94 on the retry path.** `RetryNotes.of` rendered findings with `str()`,
    which prints the finding's path first — and an acceptance finding's path is
    the command. So `contract.acceptance`, excluded from `worker_view()` on
    purpose, reached the worker prompt of every retried task. `verify.gate_summary`
    handed the reviewer the same command, one function below a docstring saying a
    reviewer "cannot be shown `acceptance`". Both render through `for_model()`
    now, and the rule is declared by the check that raises the finding rather
    than relearned by each consumer.
  - **D20 at the port's own sinks.** A `base_url` may carry userinfo, and a URL
    is quoted in every runner transport error, every availability verdict and
    `mcgyvr sources` — so a key written into the config reached logs a key in the
    environment never does. It is refused at load, where `Config.secret` already
    says a credential belongs in the environment; `redact.safe_url` and
    `redact.scrub` are the second line, for URLs that reach a message without
    passing the loader, and telemetry's `error_detail` is scrubbed because the
    exception it quotes is the caller's.
  - **§9's no-global-mutable-state.** `capability.shipped_table` and
    `catalog.catalog` held their value in a module variable — a name anything in
    the process could reassign, silently re-answering every capability question
    or re-keying every contract digest. Both are memoised; `sandbox.base`'s exit
    latch is too, because a rule that allows one legitimate `global` allows the
    next one that claims to be. There are now zero `global` statements in `src/`.
  - **The seam.** `verify.reviewer_for` asked `source_map.role(VERIFIER_ROLE) is
    None` — a yes/no question answered with a live credential — and imported
    neither forbidden name, which is how the import guard missed it. It asks
    `role_model` now. The guard itself had three bypasses (`import mcgyvr.pool`,
    a relative import, and `.role()` needing no import at all) and reported on
    spelling; it catches all three, and a test feeds it modules that must fail.
- **Pattern B — nothing owned the bytes** (pressure test 2026-08-29). Five
  modules wrote file content and disagreed about where truth lives. The rule
  they now hold: *the tree is the owner, content never travels as a value, and
  one seam commits.*
  - **Two deliveries, and the second applied no bar.** `tools/missions/run.py`
    imported nothing from `deliver`: it read a `str` carried four hops from
    `judge`, wrote it with its own `_place` and committed it with its own
    `_commit_delivery` — no re-gate, no digest, no repository lock. It was also
    the implementation with the mileage on it. It delivers through
    `deliver.deliver` now, and a guard test fails a third commit site.
  - **The channel that string travelled in is gone.** `Judgement.value`,
    `route.Result.value`, `route.Accepted.value` and `Delivered.value`, along
    with every `[T]` that existed only to carry them. `drive.worker_attempt`
    mints instead of carrying: it reads the bytes back off `sandbox.workspace`
    after the gate, because a binding minted from the caller's own string is
    true by construction and checks nothing.
  - **`RepairOutcome.content`** was a second copy of a tree `repair` mutates in
    place, added for a caller that would hand it to `deliver`; that caller is
    gone and nothing read the field. `repaired` — which paths differ from what
    the worker left — is the claim that survives.
  - **`Consensus` carries `Accepted` bindings, not a string.** `best_of` resets
    the workspace after every draw including the winning one, so the winner was
    in no tree anywhere. The reset stays — a losing draw must leak nowhere
    (#D22) — and each draw is now bound where its verdict was reached, one line
    after its gate and one before its reset. `Consensus.winner` is the bytes and
    the verdict as one value; there is no `content` field to offer instead.
  - **`Cleanup.regate`** read `cleaned and not accepted`, so the branch where a
    rewrite went unannounced was the branch where the gate said *yes* — an
    accepted change carried onward under a verdict reached on bytes the
    formatter had already replaced. It is true whenever bytes were rewritten.
  - `deliver.Accepted` is the one value allowed to carry content, and only
    because `Accepted.read` mints it off the tree the gate judged and pairs it
    with a digest. A guard test fails any new dataclass carrying `content`
    beside no digest; three pre-verdict types are listed with an argument each.
- **The self-verification refusal is no longer defeatable by spelling**
  (pressure test 2026-08-29, §4's first item). A model does not review its own
  output, and that rule was decided by `strip().casefold()` on two names read
  out of a config file — which catches a different capitalisation and nothing
  else. `qwen2.5-coder` and `qwen2.5-coder:latest` are one pull of one blob and
  compared unequal, so the accidental case was a working install's, not an
  attacker's; a provider prefix, a registry path, a zero-width space, a Cyrillic
  homoglyph and a non-breaking hyphen were the deliberate ones.
  `verify.model_identity` is now what the two names are compared through: NFKC,
  invisibles dropped, confusables folded to Latin, the routing prefix and a
  trailing `:latest` removed, separators removed. It normalises only what a
  registry itself treats as noise and never guesses at similarity — `mistral`
  beside `mixtral` is two models, and so is `qwen2.5-coder:32b` reviewing
  `qwen2.5-coder:7b`, which is the ordinary local install and would lose its
  verifier entirely to a rule that matched on resemblance. The refusal still
  names both models as the operator spelled them, because a normalised name in
  the message points at a config line that does not exist.
- **A delivery mode is a promise, and all three made the same one** (pressure
  test 2026-08-29, §4). `delivery.mode` defaulted to `pull_request`, and every
  mode committed onto the checked-out branch: one commit, one ref, HEAD advanced,
  nothing pushed and nothing branched. `handoff` came back as the literal word
  `pull_request`. Now `branch` builds the commit as objects — a scratch index
  seeded from HEAD, `commit-tree` parented on it, `update-ref` on a new
  `mcgyvr/<contract-id>` — so the operator's HEAD, index and working tree are
  read and never written, and the handoff carries the pasteable
  `git push -u <remote> <branch>` beside `Delivery.branch`. `none` still commits
  onto the checked-out branch. `pull_request` is retired through a declarative
  `Field.retired`, so the loader's message says what the value was actually
  doing rather than that it is unknown. Building a forge client was rejected:
  it would make the seam that must be certain about what it writes also own
  network transport, credentials and one forge's API shape, none of it reachable
  from a test that does not mock the acceptance boundary (ADR-0014). So was
  `checkout -b` / `commit` / `checkout -`, which reaches the destination by
  moving the operator's HEAD twice through states they never asked for.
- **A rebind is a defence only where it runs before the mutation** (pressure
  test 2026-08-29, §4). `param-mutation` collected rebinds with `ast.walk`,
  which has neither order nor control flow, so a rebind anywhere in a function —
  in dead code, in a branch that returns, textually after the mutation —
  cleared every mutation in it. The canonical `if target is None: target = []`
  followed by `target.append(extra)` mutates the caller's list whenever the
  caller passed one, and was accepted. The walk is now in execution order and
  threads which names may still be the caller's object on *some* path to here;
  a branch merge is a union, so a rebind defends only where no path skips it,
  and an arm that cannot fall through contributes nothing. Swept against the old
  implementation over `src/`, `tests/` and `tools/`: 67 hits identical, one
  addition — a bench task's own reference solution, which is the canonical shape
  and is legitimate only because its contract orders in-place work.
  - That is why the `contract_text` stand-down was threaded rather than deleted.
    It had no caller: `LanguageAdapter.structural_checks` took no contract, so a
    contract asking for in-place work was unsatisfiable. `Contract.prose` — the
    two fields the worker is given — now flows through `Gate.run` to the
    adapter, from both call sites that hold a contract, so the commit-time gate
    is not a stricter bar than the sandbox one. It is passed as text and not as
    a `Contract`, so an adapter cannot start judging by `risk` or `verification`
    (#94).
- **A module that cannot be imported is not a style note** (pressure test
  2026-08-29, §4). `UP035` was demoted by code, and it covers two different
  things: `typing`→`collections.abc`, which is style, and
  `collections`→`collections.abc`, which is an `ImportError` on 3.10 and later —
  and `requires-python` is `>=3.12`. So a worker file holding
  `from collections import Mapping` was accepted with zero findings, and reached
  the verifier under the heading saying no check is asking for it to be fixed.
  The demotion is now withdrawn per *line* rather than per code. Ruff's two
  UP035 diagnostics are identical in code, rule, message, severity, url and
  offered fix — they differ only in filename and end column, so a message-text
  discriminator was impossible rather than merely fragile, and that fact is
  pinned by a test that fails the day ruff diverges. The discriminator is an AST
  family over `ImportFrom` nodes naming `collections`, reported on `structure`
  so a ruff-less install rejects too, with 3.9's `_collections_abc.__all__`
  written out rather than introspected — the verdict is about the worker's file,
  not about mcgyvr's own interpreter.
- A dispatch error no longer occupies the cell it failed to fill (#217).
  `tools/breadth/measure.py`'s `done_keys` counted **any** row as a recorded
  cell, so the row saying "this draw reached no worker" was indistinguishable
  from one saying what the worker replied — and a resume skipped it forever. A
  269-problem sweep lost **152 of 807 draws (18.8%)** to a contiguous srv2
  outage that closed on its own; re-running the identical command printed
  `resuming: 807 draws already recorded` and dispatched nothing. The rows file
  is append-only, so refilling means rewriting it: the displaced rows are kept
  verbatim in `dispatch-errors-invocation-<n>.jsonl` and the rewrite is recorded
  in `run.json` against the invocation that did it. Not behind a flag — needing
  to notice is the defect's own first failure mode. Last-row-wins was rejected
  because three readers would each carry the rule, and one of them
  (`pin.py._join_candidate`, which matches the *first* row) would take the reply
  corpus down with a `KeyError` rather than its own `PinError`.
- A run directory now states whether an observation reached every cell it set
  out to fill, in `run.json`, at the head of `summary.md` and in the exit code —
  the old summary counted lost draws in its last line, which is where a reader
  stops looking and where a multi-hour run's operator was never looking. The
  question is derived from what every manifest already records, so `--audit`
  can ask it of the whole corpus at once: **87 breadth-shaped run directories
  judged, 0 holed.**
- A dead backend stops the run rather than re-learning the same fact for hours.
  Three consecutive tasks losing *every* draw to transport cannot happen on a
  healthy backend; the outage above spent five hours proving it 51 times.
  Row-level behaviour is unchanged — a failed draw is still a row, and the
  resume fills what the abort left. `--abort-after-dead-tasks 0` disables it.

### Changed
- `src/mcgyvr/propose.py` states `MIN_QUALITY_GAIN`'s provenance where the
  constant lives: it is a rung-separation floor, #189 borrowed it as an adoption
  bar, and that borrowing is withdrawn. The value and its own job are unchanged.
- `records/measurements/finetune-pilot-2026-08-07/summary.md` carries an
  amendment: the measurements stand, the verdict does not. HumanEval+ at n = 164
  resolves +6.9pp, so "miss at +1.9pp against a +3pp bar" was UNDECIDED rather
  than a verdict on the tune. The record's own finding that backend numerics
  swing deltas 2.6pp is now one of ADR-0019's reality-floor figures.
- `records/claims/CLM-0013.json` carries a correction: the measurement stands,
  its consequence does not generalise, and the sentence shipping breadth with a
  default of 1 is withdrawn. It was taken on the strongest local rung against
  the easiest task set, where 18 of 20 tasks passed on the first draw; the
  collapse-to-mode mechanism it leans on is likewise rung-specific — 5 of 20
  tasks collapsed there against 0 of 20 on srv1's four models.
- `prompts/javascript.md` states a measured null result instead of an
  `UNMEASURED` marker, and `Bundle` grew `BundleStanding` because a boolean
  could no longer carry the answer. Both shipped bundles are now the artifact a
  sweep was taken on, so `measured` reads `True` for both and has stopped being
  the interesting question; it is demoted to a derived property meaning
  provenance only. The outcome moved into the type: `MEASURED_BENEFIT` for
  Python, `MEASURED_NO_EFFECT` for JS/TS, `UNMEASURED` for anything unswept.
  "Measured" is a word a reader takes as endorsement, and one of these two
  bundles has not earned it. Rewriting the marker did not forfeit the
  measurement, because `check_c2_is_the_shipped_bundle` compares the *stripped*
  body — the property the stripping change below was for.

- `prompts/python.md` moved from `MEASURED_BENEFIT` to a new
  `BundleStanding.MEASURED_REDUNDANT`, and gained the provenance marker it
  never had (#167, CLM-0017). Neither of the two existing values could say what
  is true: `MEASURED_BENEFIT` reads as an endorsement of a gain mcgyvr's path
  does not get, and `MEASURED_NO_EFFECT` would write off an artifact that is
  worth about four tasks in twenty to a harness whose prompt lacks output
  discipline. The new value says the effect is real and this project already
  supplies it — redundancy is redundancy *with something*, and naming that is
  the difference between a fact and a shrug. Same reasoning that produced
  `BundleStanding` in the first place, applied once more: the type carries the
  outcome because a reader takes the shorter word as endorsement.
  `strip_provenance` keeps the new marker out of the prompt and off the
  ceiling, so `python.md`'s body is still the measured `c2.md` byte for byte.

- `MAX_BUNDLE_BYTES` stays one constant, now for a stated reason rather than
  for want of evidence. #144 asked whether the ceiling should become
  per-language; a per-language ceiling needs a language whose curve has a peak,
  and JS/TS measured flat, so there is no JS/TS peak to place one at. That is
  not the same as JS/TS agreeing that 2 KB is right, and the comment says so.

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
- The positive control's premise is corrected in the places that carried it
  wrong (#225). CLM-0017's ~+20pp ran on local-ai's unported **Python**
  contracts under local-ai's own harness — not "the twenty JS/TS contracts" as
  ADR-0020 and #231's body both said (the same arm-A/arm-B confusion #234
  repaired, standing in two more places) — and across harnesses the effect
  nulls, because mcgyvr's own user message already carries the rule. Both
  documents now say so, and the route ADR-0020 left to #225 is chosen there:
  check 2 becomes a rule-ablation condition recovered directionally on the
  generated bench, where n = 400 makes it decidable; un-releasing `bundle-ts`
  — which never bought the exactness it was priced at — lapses unchosen.
- ADR-0019's "eleven of the twelve" headline miscounted its own table (#225).
  The live `tools/power/report.py` reports **nine** of twelve contrasts
  structurally unresolvable and **zero** of twelve rejecting, and the zero is
  what the argument rides on; the correction note names where the figure
  propagated.
