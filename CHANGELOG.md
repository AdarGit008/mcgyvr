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

### Changed
- `pyyaml` is now a runtime dependency. The config file is YAML because it
  carries policy that needs comments to stay hand-editable (ADR-0001).
