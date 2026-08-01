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

### Changed
- `pyyaml` is now a runtime dependency. The config file is YAML because it
  carries policy that needs comments to stay hand-editable (ADR-0001).
- Worker bindings are named `<role>_<locality>_<model>` (for example
  `worker_local_qwen2.5-coder-7b`), replacing the positional `local-N`. A
  name says what a binding IS rather than where it sits in an ordering, so
  inserting a rung cannot silently change what a policy reference means.
