# ADR-0007 — dependency signatures come from the index, not from a model

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

#109 carries an architecture document inherited from local-ai: six numbered
decisions, DEC-1 through DEC-6, addressed to whoever implements them here.
ADR-0004 records how little of its evidence survived checking and fixes the rule
that nothing from it is adopted before it is re-verified. This record settles one
of its mechanisms.

DEC-5 has the expensive orchestrator model author each `deps[].signature` during
decomposition — "the orchestrator populates this block during decomposition by
running AST-based pruning on the target repo", with the decompose system prompt
instructed to "inline dependency signatures". The `deps` block itself is right
and is already landed: `path`, `signature`, `note`, signature and not body, one
entry per dependency (`contract.py:189`, `:342`, `:425`). What is wrong is where
the signature text comes from.

The contract validates nothing about a signature's truth. Read the loader: the
only rule that touches `deps` at all rejects a repeated `path`, and its stated
reason is that a second entry "would silently pad the prompt" (`contract.py:873`,
`:877`). Nothing checks that the path exists, that the named symbol is defined
there, or that the text is the signature the file actually holds. Meanwhile the
field is `worker_facing=True` (`contract.py:206`), and `Contract.worker_view`
(`contract.py:483`) is the one accessor a worker prompt may be built from — so
the text reaches the model verbatim.

That is the whole problem stated in two facts. A model-authored signature is an
unchecked assertion injected into the worker prompt as ground truth — the same
failure DEC-3 (#93) proposes a new gate step to catch one step downstream, when
the worker calls the API the signature described. A pipeline cannot spend a gate
rung detecting hallucinated APIs while feeding hallucinated APIs into the prompt
on purpose. The circularity is the argument, and it needs no rate: ADR-0004
leaves the hallucination base rate **unresolved**, and this record depends only
on its not being zero.

ADR-0001 boundary 2 already forbids the shape. Exploration is deterministic
first, always, and context the calling agent supplies "is an accelerator layered
on top; it never replaces the deterministic pass". `orchestrator/context.py`
makes that structural rather than advisory. A hinted candidate's score is
multiplied by `_HINT_BOOST`, derived from the resolver's dominance threshold
rather than written as a literal — `_HINT_BOOST = 1.0 + (_DOMINANCE - 1.0) * 0.8`
(`context.py:70`). A `RESOLVED` leader beats its runner-up by at least
`_DOMINANCE`, so a boost strictly below that factor cannot overtake it
arithmetically rather than by convention. A hint naming a path the index does not
hold is dropped; supplied text that disagrees with the repository is dropped and
the repository wins, with the disagreement reported as a `ContextFinding` rather
than absorbed (`context.py:22`). The module's own summary: "Corroboration is
allowed to settle something; assertion alone is not" (`context.py:37`).

A model-authored signature is precisely the load-bearing assertion that module
exists to prevent, arriving through a different door. `context.py` polices
assertions from the *calling* agent. A signature authored by mcgyvr's own
orchestrator model is the same class of claim about the same subject — what a
symbol in this repository looks like — from inside the house, and today it gets
no scrutiny at all.

## Decision

**The deterministic symbol index produces `deps[].signature`. The decomposer
names which symbols a contract depends on; it never authors the signature text.**

A `deps` entry as #50 emits it is a reference — a repo-relative path and a symbol
name. The index resolves that reference, and the resolved text is what lands in
the contract. Judgement about *relevance* stays with the model: deciding which
three of a file's forty symbols the target actually needs is a judgement.
Statement of *fact* stays with the parser, because what `paginate` looks like is
not.

That disposes of DEC-2's other half. The "new module
`mvp/orchestrator/context_prune.py`" in #96's scope should never be created.
`orchestrator/symbols.py` already parses both launch languages: Python through
the standard library's `ast` (`_python_symbols`, `symbols.py:101`) and JS/TS
through tree-sitter, on the same three grammars the gate's JS adapter builds for
#36 — `tree_sitter_javascript`, `language_typescript`, `language_tsx`
(`symbols.py:25`, `gate/adapters/javascript.py:34`). Both run inside
`index_source` (`index.py:270`), which already holds the file's bytes. The work
is therefore a signature slice on `Symbol` (`symbols.py:53`) and an `IMPORT`
member on `SymbolKind` (`symbols.py:44`) — Python from the `ast` node it already
visits, JS/TS from tree-sitter node text minus the body field — serving both
languages from parse passes that already run.

A separate `ast` pruner would be Python-only and a third Python parse site, after
`symbols.py:103` and `gate/adapters/python.py:39`. It would break ADR-0001
boundary 8: one grammar set serves the exploration index and the gate's
structural checks, which is what makes the second language affordable rather than
a doubling.

## Rejected: let the model author signatures and verify them against the index at load

The orchestrator model already has the file open during decomposition — it read
the target to write the directive, so a signature is a by-product of a read
already paid for. Verification then closes the hole exactly: a signature that
does not match the index is rejected with the same named-field, states-the-fix
error every other contract defect gets, and the fabrication never reaches a
worker. It also keeps what the index cannot supply — a signature for a
dynamically constructed attribute, or a re-export the parser sees only as a name.

It loses on where the check would have to live. `contract.py`'s only filesystem
contact is the contract document itself: `load` reads that one path
(`contract.py:576`), while `loads` and `parse` take text (`contract.py:585`,
`:590`). Everything the loader checks is internal — scope self-consistency,
budget arithmetic against `limits.max_output_tokens` (`contract.py:882`), the
catalog's evidence rules (`contract.py:862`). That is deliberate, and it is what
makes direct mode public API: #13 fixes the schema, its validation errors and its
guarantees as a compatibility surface from v1 onward, so a contract is valid or
invalid on its own terms and testable without a checkout. Verification-at-load
makes validity a function of which repository is on disk and when — the same
document parses today and fails tomorrow.

It also pays an expensive model to produce what the index states for free and
exactly. Verification-after-generation is strictly more machinery than
generation-from-truth: the index lookup gets built either way, and this option
adds a model call, a prompt instruction and a mismatch-error path on top of it.
The residual case — symbols the parser cannot name — is better served by the
decomposer omitting the dependency than by describing it, for the reason given
under Consequences.

## Rejected: a per-model context cap of 4K/8K tokens

DEC-2 caps code context at 4K tokens for models ≤1.5B and 8K for 3B–7B, and #96
makes "1.5B model receives ≤4K tokens of code context per contract" an acceptance
criterion. If long context does degrade a small model, parameter count is the
obvious variable to size the budget by — it is the variable the whole
signature-not-body design is reaching for, and a per-tier cap is one config key
against a default that hands a 1.5B and a 30B the same number. Nothing below
disputes that a single default is crude.

It loses four ways, any one of which is sufficient.

The figures have no basis. The document calls them "conservative extrapolation"
from HCP's finding for larger models and states that HCP tested models ≥2B;
ADR-0004 found HCP's smallest was 1.3B — under the tier the caps are supposedly
extrapolated *down* to, so the margin the word "conservative" claims is not
there. The two spellings of the rule do not agree with each other either: the
document splits at 1.5B and 3B–7B, while #96 writes "4K tokens for ≤3B models,
8K tokens for 7B+", putting the 3B on the opposite side of the line.

Second, mcgyvr has nowhere to read a parameter count at routing time. `Rung` is
"a name and a model, and by construction nothing else" (`pool.py:139`), and that
is not an oversight — it is the property that lets a rung be re-pointed at a
different machine without anything above the seam noticing. `TIER_FIELDS` is
name, source, model (`config.py:148`).

Third, the one file that holds `params_b` forbids the number by its own charter:
"Every number here is measured, not estimated, and carries its provenance"
(`data/capability-table.json:3`).

Fourth, and decisively, the budget already exists in the right place.
`context.max_input_tokens` (`contract.py:219`) defaults to 4096 (`:225`) and is
declared on the contract "rather than inferred at dispatch so that a prompt which
will not fit is a contract-level failure, caught before a rung is spent"
(`contract.py:222`). Enforcement is `check_prompt_fits` (`gate/preflight.py:68`).
#96 puts the same enforcement at dispatch, which reverses that.

One budget per contract, chosen by the decomposer, defaulting to the schema's
existing 4096: no new config key, no invented number, and the failure lands
before spend rather than after.

## Consequences

- A signature in a shipped contract is reproducible from a checkout. Two runs of
  the decomposer over an unchanged repository produce the same text, and a
  reviewer can diff a contract's `deps` against the index rather than trust it.
  That is a property no amount of prompt engineering buys.
- `symbols.py` grows an optional signature slice and an `IMPORT` kind, both
  languages, no new parse site — boundary 8 holds by construction. #96's "new
  module `mvp/orchestrator/context_prune.py`" is closed as won't-do rather than
  implemented.
- Contract loading stays repo-free, so #13's compatibility surface for direct
  mode survives intact: `loads(text)` is still the whole story.
- **Given up: any dependency the index cannot name.** A dynamically constructed
  attribute, a re-export through a barrel file, a generated module — the
  decomposer must omit these or refuse the contract rather than describe them.
  This is the deliberate trade, and the asymmetry justifies it: a missing dep
  degrades the prompt, and the worker's `stop_conditions` give it a licence to
  report BLOCKED (`contract.py:350`); an invented dep poisons the prompt and
  reads as authoritative.
- **Given up: per-model tuning of the context budget.** A contract routed to a
  1.5B and one routed to a 30B carry the same default until somebody measures.
  #96's acceptance criterion is not testable as written; restated as "the budget
  is declared, enforced and reported", it is testable today.
- What this does not settle is whether the index's slice is *good*. A signature
  cut from tree-sitter node text is only as correct as the grammar and the
  slicing rule. That is a parse defect — reproducible, coverable by a test, and
  different in kind from a fabrication, which is the whole point.
