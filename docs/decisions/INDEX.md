<!-- Code generated from docs/decisions/0*.md by `make docs` (tools/decisions/index.py). DO NOT EDIT. -->

# Decision records — index

Generated from the records' own headers. Regenerate: `make docs`; drift fails `make docs-check`. The header conventions this reads are enforced by `tests/test_decisions.py`.

| ADR | Title | Status | Date | Amends | Amended-by |
|---|---|---|---|---|---|
| [0001](0001-founding-scope-and-boundaries.md) | Founding scope and boundaries | Accepted | 2026-08-01 | — | — |
| [0002](0002-merge-protection-on-the-default-branch.md) | Merge protection on the default branch | Accepted | 2026-08-01 | — | — |
| [0003](0003-binding-names-carry-no-role.md) | A binding's role is derived from where it sits, not from its name | Accepted | 2026-08-01 | — | — |
| [0004](0004-inherited-research-is-re-verified-before-it-is-adopted.md) | inherited research is re-verified before it is adopted | Accepted | 2026-08-01 | — | — |
| [0005](0005-gate-checks-never-run-target-code-on-the-host.md) | gate checks never run target code on the host | Amended | 2026-08-01 | — | 0010 |
| [0006](0006-the-type-checker-is-the-target-repositorys.md) | the type checker is the target repository's | Accepted | 2026-08-01 | — | — |
| [0007](0007-dependency-signatures-come-from-the-index-not-from-a-model.md) | dependency signatures come from the index, not from a model | Accepted | 2026-08-01 | — | — |
| [0008](0008-sampling-breadth-is-policy-and-selection-is-the-first-gate-pass.md) | sampling breadth is policy and selection is the first gate pass | Accepted | 2026-08-01 | — | — |
| [0009](0009-output-discipline-is-a-cap-not-a-stop-sequence.md) | output discipline is a cap, not a stop sequence | Accepted | 2026-08-01 | — | — |
| [0010](0010-environment-resolved-checks-run-in-the-sandbox.md) | environment-resolved semantic checks run in the sandbox | Accepted | 2026-08-02 | — | — |
| [0011](0011-the-semantic-resolver-is-staged-not-installed.md) | the semantic resolver is staged per run, not installed in the image | Accepted | 2026-08-03 | — | — |
| [0012](0012-re-entry-is-refused-by-what-the-caller-holds.md) | re-entry is refused by what the caller holds, not by what it is called | Accepted | 2026-08-06 | — | — |
| [0013](0013-decomposition-is-api-tier-only.md) | decomposition is api-tier only | Accepted | 2026-08-06 | — | — |
| [0014](0014-the-acceptance-boundary-is-never-mocked.md) | the acceptance boundary is never mocked, and its outcome is not a boolean | Accepted | 2026-08-06 | — | — |
| [0015](0015-a-failed-verifier-never-promotes.md) | a failed verifier never promotes: instrument failure fails closed | Accepted | 2026-08-06 | — | — |
| [0016](0016-fixtures-capture-what-the-parser-reads.md) | fixtures capture what the parser reads, not what the run did | Accepted | 2026-08-06 | — | — |
| [0017](0017-the-floor-is-the-product.md) | the floor is the product, and the ceiling is priced against it | Accepted | 2026-08-09 | — | — |
| [0018](0018-one-bench-every-lever-and-the-whole-system.md) | one bench, every lever, and the whole system measured | Accepted | 2026-08-09 | 0017 | — |
| [0019](0019-the-bar-is-a-reality-floor-and-a-per-lever-rule.md) | the bar is a reality floor and a per-lever rule | Accepted | 2026-08-10 | 0018 | — |
| [0020](0020-retire-the-rulers.md) | retire the rulers, release the local five, never train on HumanEval | Accepted | 2026-08-10 | 0016, 0018 | — |
| [0021](0021-the-benchs-obligation-is-the-floor-unit.md) | the bench's obligation is the floor unit | Accepted | 2026-08-11 | 0019, 0017, 0018 | — |
| [0022](0022-a-lever-is-never-a-difficulty-knob.md) | a lever is never a difficulty knob | Accepted | 2026-08-11 | 0018 | — |
| [0023](0023-difficulty-is-behaviour-count.md) | difficulty is behaviour count, and it is calibrated from wisdom | Accepted | 2026-08-11 | — | — |
| [0024](0024-comparable-measurements-come-from-one-rig-and-one-build.md) | comparable measurements come from one rig and one build | Accepted | 2026-08-11 | 0019 | — |
| [0025](0025-the-javascript-lint-bar-is-the-projects-and-it-mirrors-pythons.md) | the JavaScript lint bar is the project's, and it mirrors Python's | Accepted | 2026-08-13 | 0021 | 0026, 0034, 0035 |
| [0026](0026-four-lenses-record-mutate-state-the-property-and-price-the-axes.md) | four lenses: record what is unrecoverable, mutate to discover, state the property, price the axes | Accepted | 2026-08-13 | 0024, 0025 | — |
| [0027](0027-run-identity-is-one-block-and-an-unreadable-field-is-a-refusal.md) | run identity is one block, and an unreadable field is a refusal | Accepted | 2026-08-16 | 0024 | — |
| [0028](0028-a-routing-policy-is-adopted-only-if-it-is-inspectable-here-and-measured-here.md) | a routing policy is adopted only if it is inspectable here and measured here | Accepted | 2026-08-16 | — | — |
| [0029](0029-the-gate-is-the-scorer-so-there-is-no-answer-to-extract.md) | the gate is the scorer, so there is no answer to extract | Accepted | 2026-08-16 | — | — |
| [0030](0030-throughput-is-not-the-ceiling-and-the-serving-bench-is-already-in-the-table.md) | throughput is not the ceiling, and the serving bench is already in the table | Accepted | 2026-08-16 | — | — |
| [0031](0031-the-pre-gate-heuristic-verifier-is-refuted-by-our-own-replies.md) | the pre-gate heuristic verifier is refuted by our own replies | Accepted | 2026-08-16 | — | — |
| [0032](0032-a-round-boundary-is-drained-not-taken-and-the-pin-covers-the-bars-configuration.md) | a round boundary is drained, not taken, and the pin covers the bar's configuration | Accepted | 2026-08-17 | 0018, 0027 | — |
| [0033](0033-the-bar-the-prompt-and-the-weights-are-hashed-where-they-are-resolved.md) | the bar, the prompt and the weights are hashed where they are resolved | Accepted | 2026-08-17 | 0027 | — |
| [0034](0034-a-rung-that-cannot-say-what-bar-it-applied-is-a-refusal.md) | a rung that cannot say what bar it applied is a refusal, and an absent tool is not | Accepted | 2026-08-16 | 0025 | — |
| [0035](0035-the-bar-is-recorded-as-content-and-there-is-one-acceptance-ceiling.md) | the bar is recorded as content, and there is one acceptance ceiling | Accepted | 2026-08-17 | 0025 | — |
| [0036](0036-the-bare-word-bar-is-banned-adoption-bar-and-scoring-bar.md) | the bare word "bar" is banned: adoption-bar and scoring-bar name two decisions | Accepted | 2026-08-17 | — | — |
