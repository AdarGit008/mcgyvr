# ADR-0009 — output discipline is a cap, not a stop sequence

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

DEC-1 of the architecture document inherited from local-ai — the document
ADR-0004 put under re-verification — is the cheapest line on its own
implementation table, "~20 LOC, highest ROI per line", scheduled first. #95
carries it as v1. It asks for two things on every worker request: a stop set,

    ["```", "\n\n\n", "\ndef ", "\nclass "]

and structured-output enforcement — `guided_json` for vLLM, `format: json` for
Ollama.

The stop set is incompatible with the reply shape mcgyvr ships. #25 fixes a
worker's reply as one file's **complete** content in one fenced block, parsed
deterministically, and `output_schema` defaults to `whole_file`
(`contract.py:362`, default at `:368`). A stop sequence halts generation at its
first occurrence anywhere in the reply and is stripped from what the caller
receives. Read the four members against that.

The opening fence is the first thing a conforming reply emits, so `` ``` ``
fires before any file content exists at all. `\n\n\n` is not a triple blank
line — it is the exact byte sequence PEP 8 mandates between two top-level
definitions, so it fires at the first gap between them. `\ndef ` and `\nclass `
fire at the *first* top-level definition, not the second: what precedes it is
the module header, and the module header is all that survives. Every member
truncates a conforming Python file, the earliest match wins, and in practice
that means the reply ends before the worker has written a single definition.

The failure mode is the whole argument. Because a stop sequence is consumed by
the server and stripped from the response, the caller does not receive an error
— it receives a shorter string. A whole-file reply cut before its first
definition is still syntactically valid Python: `check_syntax` passes it
(`gate/runner.py:138`), the batched lint and format steps find nothing wrong
with the lines that are present (`:149`), and what reaches the file is missing
most of itself. That is precisely the failure class DEC-1 says stop tokens exist
to prevent, converted from loud to silent, and it arrives in the one place
mcgyvr promises it cannot — a file.

**Why this looked like a twenty-line win.** DEC-1's only measurement is the
bundle experiment already registered here as CLM-0004: a 20-task contract set
across four bundle-size conditions on one rig, medium confidence, with the
effect appearing on the small worker only (`records/claims/CLM-0004.json:4`,
`:15`). That experiment varied **bundle size** and nothing else; stop tokens
were never a condition in it. As support for a stop set it is a non-sequitur,
and the document concedes the point in its own caveat — "No published data on
stop-token effectiveness for Qwen2.5-Coder 1.5B/3B specifically." ADR-0004 fixed
what follows: a retained number is registered in `records/claims/` with a
citation stating why it supports the claim, or it is dropped from the text that
uses it. Nothing registers a stop-token effect, so nothing here asserts one.

**The contradiction #95 inherits.** DEC-1's own safety note restricts stop
tokens to models without constrained decoding, because with both enabled "the
stop token may truncate before the JSON closing brace", and it files that
interaction as untested — "Test this interaction before shipping." #95 then puts
stop tokens and `format: json` on the same Ollama request. Separately,
`data/capability-table.json` records `backends.ollama.limits` as **"no
structured-output enforcement"**, so the Ollama half of DEC-1 asks a backend for
a guarantee this project's own table says it does not give.

## Decision

**v1 bounds worker output with `limits.max_output_tokens` and a named truncation
failure. No stop sequences are sent.** The question re-opens in v2 alongside
#71.

The bound already exists and states its own semantics: `max_output_tokens` is a
"Hard cap on the worker's reply, enforced in the runner. A reply cut off at the
cap is a named failure and is never applied to a file" (`contract.py:264`). It
is cross-checked against the input budget at contract load — a cap larger than
`context.max_input_tokens` is rejected because "a reply larger than the whole
prompt budget cannot be assembled into a next attempt" (`contract.py:882`) — and
the reserve is checked before a rung is spent, by
`check_prompt_fits(prompt_tokens, context_window, output_reserve)`
(`gate/preflight.py:68`). Sizing the cap from the target's own content is #17.

Rambling is therefore already bounded, and bounded in the direction that fails
loudly. The cap and the stop set address the same behaviour and differ only in
what happens at the limit: the cap produces a named failure and no file write,
the stop set produces a plausible file. Between truncate-and-report and
truncate-and-lie there is no trade to make.

The worker-side half of the same problem is shipped too. `stop_conditions`
(`contract.py:350`) is required of every task type a model executes
(`contract.py:855`), so a worker that meets an unknown API or an ambiguous
directive has a stated licence to report BLOCKED rather than improvise. That is
output discipline expressed where the model can act on it, rather than as a wire
parameter that amputates the reply without telling anyone.

## Rejected: ship the stop set as recommended

The case for shipping is not weak. Small models do ramble around their code —
that is the behaviour CLM-0004's compact bundle attacks from the prompt side, at
a measured 45% → 70% first-pass acceptance and roughly 2.5× faster on a 3B
worker. A stop set is the standard remedy every local-inference guide names, and
it genuinely is a handful of lines in a runner nobody has written yet (#21).
There is also a configuration in which the set is entirely safe: if the reply
were a JSON object rather than a fenced block, none of the four sequences could
occur in the token stream at all, because a newline inside a JSON string is `\n`
as two characters and `def` never sits at column zero. That is the document's
own `{"content": "<file content>"}` wrapper, and under it the objection above
evaporates.

Which is exactly why the set cannot ship as written: it is safe only in
conjunction with a change nobody priced. `output_schema` is an enum with two
members, `whole_file` and `unified_diff` (`contract.py:369`). A third is a bump
to a schema that ADR-0001 boundary 1 makes public API, held at
`SCHEMA_VERSION = 1` (`contract.py:75`), and it drags in the parser #25 has yet
to write plus the structured-output half #71 has already deferred. "Twenty
lines" describes a diff to a runner that does not exist, not the change. For
`whole_file` — the default, and the protocol v1 actually ships — every member of
the set truncates a real file.

Two smaller obstacles measure the distance between the proposal and the codebase
it targets. `SOURCE_FIELDS` is `base_url`, `api`, `max_parallel`, `api_key_env`
(`config.py:109`), and an unknown key is a hard load error — "An ignored key is
a config that does not do what it says" (`config.py:701`) — so `stop:` in
`mcgyvr.yaml` does not quietly configure nothing; it refuses to start. And #95
scopes its edit to `pool.py:execute_model`, which is local-ai's function:
`src/mcgyvr/pool.py` is #20's source map — `SourceMap.bind()` at `:215`,
`source_map()` at `:257` — and holds no client, no sampling and no request of
any kind.

## Rejected: derive a safe stop set from output_schema

This is the correct long-term shape, and it belongs here as a design recorded
rather than a refusal. The parser and the stop set are two halves of one
protocol: whatever sequence reliably terminates a reply is the same fact as
whatever sequence the parser treats as the end. Split across two issues, they
drift. #25 owns the protocol, so #25 should own both, and the set should be a
function of the contract's declared `output_schema` rather than a constant in a
runner. The derivation is not academic: under `unified_diff` every body line of
a conforming patch carries a leading space, `+` or `-`, so `\ndef ` and
`\nclass ` cannot occur at column zero — the two strings that are lethal under
`whole_file` are inert under it. Same set, opposite verdicts, decided by a field
the contract already carries.

It does not ship in v1 because today it would carry nothing. The enum has two
values, and `whole_file` — the default, and the only shape #25 is scoped to
parse — has an empty safe set. The seam would buy a config surface and a
per-protocol matrix to maintain in exchange for `[]`. When the enum grows a
member whose terminator is unambiguous, this is the shape to build: derived from
`output_schema` inside #25's parser contract, never a constant, never per-source
config.

## Rejected: reverse #71 and enforce structured output in v1

The structured-output half is not re-decided here, and the document supplies no
reason to re-open it. #71 defers grammar-enforced output to v2 on three written
grounds: support varies sharply by backend, it carries a throughput cost, and
v1's parser plus a named failure already prevent a malformed reply from reaching
a file. DEC-1 addresses none of the three — it supplies no backend survey, no
throughput measurement, and no argument that the parser is insufficient.

The code hardens the first ground. "guided_json for all vLLM models" is not
expressible in mcgyvr. `Protocol` has two members (`pool.py:75`), and `openai`
deliberately covers vLLM, llama-server, LM Studio, TGI and the hosted providers
as one thing — the enum "has two members and is expected to keep having two"
(`pool.py:81`). `Endpoint` carries a source name, a base URL, a protocol, a
capacity and the *name* of a credential variable, and nothing about what the
backend can do (`pool.py:90`); `SOURCE_FIELDS` carries no capability key either;
and `Rung` is "a name and a model, and by construction nothing else"
(`pool.py:136`). A caller cannot ask what a rung's backend supports, by design:
that is ADR-0001 boundary 4, and it is what #20 built. Per-backend enforcement
therefore needs capability discovery at probe time (#22), or it needs the seam
broken. Which spelling each backend actually answers to — vLLM's `guided_json`,
the OpenAI shape's `response_format`, llama-server's `grammar` — is itself
unsurveyed, which is #71's first deferral reason restated from the code side.

## Consequences

- #95 does not ship as written. Its stop-token half folds into #21 with an empty
  set for `whole_file`; its structured-output half belongs to #71, whose stated
  first target is the verifier verdict rather than file content.
- v1's only bound on reply length is `limits.max_output_tokens`. A model that
  would have rambled now burns its cap and fails by name instead of being
  silently trimmed. That is more visible failures, not fewer — deliberately. A
  truncation is an escalation signal; a quiet partial file is a bug report from
  a stranger.
- Nothing in `mcgyvr.yaml` gains a sampling or stop key. Sampling parameters,
  when they arrive, belong in `TIER_FIELDS` (`config.py:148`) as policy, which
  is where ADR-0008 already put breadth — not in a source block, and not as
  constants in a runner.
- What was given up: whatever real token savings a correctly-derived stop set
  would produce on the top local rung. Nothing measures it. The two calibration
  items DEC-1 admits against itself — stop-token effectiveness on Qwen2.5-Coder
  1.5B/3B, and the stop-token × constrained-decoding interaction — stay open,
  and they are the precondition for re-opening this in v2.
- The general rule this record fixes, which outlives the specific set: a
  mechanism that makes a bad reply *shorter* is not a substitute for one that
  makes a bad reply *named*. Where both are available, v1 takes the named
  failure.
