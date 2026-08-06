# ADR-0013 — decomposition is api-tier only

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-06

## Context

Almost nothing in this pipeline is a model's opinion. The index is ripgrep and
tree-sitter over `git ls-files`. Resolution is string work over that index.
Reading is a budgeted walk of line anchors. The gate is a list of commands and
their exit codes. Verification reads a diff that already exists. Two steps are
opinion — **decomposition** and **worker execution** — and the system's whole
character comes from how few they are.

Those two are not symmetric, and the asymmetry is not about quality.

**A worker's output is judged by machinery built to judge it.** Scope refuses a
diff that left its contract; secrets refuses one carrying a credential; the
per-language adapter refuses one that does not parse; the acceptance commands
run the target's own suite; verification reads the result in fresh context;
escalation replaces the worker and tries again. A bad worker meets six things
whose entire job is catching it.

**A decomposer's output is the document all of that executes faithfully.**
`orchestrator/decompose.py` opens by naming its own position: "the one place in
the orchestrator where a model's opinion becomes a document the rest of the
system executes." Nothing downstream disagrees with a contract. A well-formed
contract for the wrong work passes scope — it defined the scope. It passes the
gate, passes acceptance, passes verification if the verifier only checks
conformance, and arrives as a clean pull request that does the wrong thing.
There is no check whose job is to catch it, and the cleanliness is what makes it
expensive: the reader most likely to be fooled is the agent that asked.

**ADR-0007 already narrowed what a decomposer may author; this narrows who may
author it.** That record drew the seam at references-not-facts — a proposal
names a symbol and cannot state its signature, because the index states it.
The two records do different work: 0007 bounds the *blast radius* of a
decomposer's error, this one bounds its *rate*. Neither substitutes for the
other, and 0007's existence is not an argument that the rate no longer matters —
a proposal that names the wrong symbol resolves perfectly against the index.

**Where the config stands today.** `config.py:780` validates that
`orchestrator.source` is a declared source and nothing further, so a local rung
is a legal binding; `init` proposes from whatever the machine has, which on a
keyless machine is a local ladder. An install can therefore decompose on a 3B
model without anyone choosing that, and #164 is the recent precedent for how
quietly a role can end up bound to something nobody would have picked
deliberately.

**What "api tier" means here, stated as the proxy it is.** `catalog.family_of`
(`catalog.py:160`) defines a rung as `api` exactly when its **source declares a
credential**, and deliberately as a property of the source rather than of the
model. So this record's rule is enforceable as "the orchestrator's source
declares an `api_key_env`", and that is a proxy for what is meant. A local
endpoint that declares a credential satisfies it. That is accepted rather than
patched: an operator who binds a credential to a box has told the config what
kind of endpoint it is, and mcgyvr has no per-model quality figure for hosted
models to check instead — the capability table measures local models. ADR-0003
also applies: the check must go through `family_of`, never through a source's
name, because names carry no role.

**What this decision does not rest on.** No measurement here says a local model
decomposes badly. None has been taken, and this record quotes none. It rests on
the asymmetry of consequence. If a measurement later shows a local rung
decomposing as well as a hosted one, it will still have to answer that asymmetry
rather than out-score it.

## Decision

**The `orchestrator` role may bind only to a source in the `api` family. A
binding outside it is a config error, refused at load with the reason named.**

Concretely:

- `config.py`'s role validation gains the family check, resolved through
  `catalog.family_of` rather than through the source's name (ADR-0003), naming
  the source, the family it resolved to, and the fix.
- **`init` never writes a non-api orchestrator binding.** On a machine with no
  api source it writes no orchestrator role at all and reports what that costs,
  the same way it already reports an absent Docker or an absent key.
- **Delegated mode without an api binding refuses**, naming direct mode as the
  route that still works. It does not decompose on a local rung and label the
  result.

**The framing that makes this coherent rather than restrictive: decomposition is
always done by an api-tier model.** In delegated mode it is mcgyvr's own
binding. In direct mode it is the calling agent — itself an api-tier model
holding full session context — which wrote the contracts and handed them over.
Direct mode is not the degraded path for a keyless install; it is this same rule
satisfied by a different api-tier model, and the ladder below the contract is
untouched. Value per token is earned where the verification lives.

**The verifier is deliberately not covered.** It is the other role that reads
rather than writes, and its output is a judgment rather than a document that
gets executed — a different failure shape that deserves its own evidence. #179
is where it is being decided, and this record must not be read as pre-deciding
it by symmetry.

## Rejected: allow a local orchestrator, and label the output

The machinery exists and is proven: CAV-01 gave us `quality_safe` and
`QualityCaveatError`, and #164 showed the labels working exactly as intended —
a caveated path refused a quality-sensitive request outright. Extending that to
decomposition is a small change, keeps a keyless install fully self-serving, and
is honest labelling rather than refusal, which is usually this repository's
preference.

It loses on what a label is for. A label works where something downstream weighs
it: `quality_safe` is checked by a caller that can decline the result. For a
contract there is no such weigher. The label would ride along beside a document
that the gate, the acceptance commands and the delivery step all execute without
consulting it, and would surface — if at all — on a pull request that already
looks clean. Labelling an input to a pipeline that has no step that reads labels
is documentation, not control.

There is a second, quieter reason. The consumer of a delegated decomposition is
usually an agent, not a person. A caveat in a field is exactly the kind of thing
an agent forwards without weighing.

## Rejected: measure first, then bind by measured quality

This is the repository's own discipline and it is the strongest objection to
this record. ADR-0004 exists to stop decisions being sized by numbers nobody can
source; `data/capability-table.json` exists to hold measured per-model quality;
CAV-01 and CAV-02 exist because measurement caught things argument did not. A
rule adopted on reasoning alone is the move ADR-0004 was written against.

It loses because the quantity a measurement would produce is not the quantity
that decides this. A decomposition pass rate answers "how often is the contract
good". What matters is "what does a bad contract cost", and the two do not
compose: 90% on a decomposition task and 90% on a worker task are not comparable
numbers, because in one case the missing 10% is caught by six downstream checks
and in the other it is shipped as a clean PR. A measurement that treats them as
the same axis produces a figure that is accurate and misleading.

It is a deferral rather than a refusal, and the terms are stated: what would
reopen this is not a decomposition pass rate but a demonstrated downstream check
that catches a well-formed contract for the wrong work. #179's Q2 is exactly
that question — if the verifier reads the original prompt rather than only the
contract, such a check exists for the first time, and this record should be
revisited on that basis.

## Rejected: fall back to the best local rung when no api source is bound

The best-effort reading: a keyless machine with three rigs on the tailnet has
real capability, and refusing to decompose on it feels like refusing to use what
the operator has. Bind the top local rung, get on with it.

It loses because it is silent degradation — the config would decompose at a
quality nobody selected, on a machine whose owner never made that choice. The
survey for #175 found the mature form of this failure in production:
`plandex-ai/plandex` at `e2d7720` walks a per-role fallback chain by input size
and, when the input exceeds every declared window, dispatches to the last model
anyway; its own comment states it (`app/shared/ai_models_large_context.go:45`).
The result is a run that looks normal and is not. #164 is the same shape in our
own history — a role bound one word away from the caveated path, by a tool that
wrote the file itself.

A refusal that names direct mode costs the operator one decision. A silent
downgrade costs them a plan they cannot tell is wrong.

## Consequences

- **Delegated mode now requires an api binding**, and #56 (fallbacks: no remote,
  no credentials) gains a case it must state: keyless installs get direct mode,
  and the refusal has to name it rather than reporting a missing key.
- **The README's local-only line needs qualifying.** "Without an API key, mcgyvr
  runs local-only" stays true of execution and stops being true of delegated
  decomposition. The honest sentence is that the ladder below the contract is
  local; the contract itself comes from an api-tier model, yours or ours.
- **`init` changes shape on a keyless machine**: an unbound orchestrator role
  and a stated cost, rather than a bound local one.
- **`docs/config-reference.md` regenerates from the schema** and states the
  restriction where `orchestrator.source` is documented, so the constraint
  cannot drift from the validator that enforces it.
- **The rule is a proxy and is documented as one.** A local endpoint declaring a
  credential passes the check. Accepted, because the alternative is a
  per-model quality gate that mcgyvr cannot source for hosted models.
- **What this gives up:** a fully local delegated path. A machine with rigs and
  no key can no longer ask mcgyvr to turn a prompt into contracts. Accepted,
  because in that configuration the caller is itself an api-tier model and the
  contracts it writes satisfy the same rule.
- **What this bets on:** that no downstream step can catch a well-formed
  contract for the wrong work. That is true today. If #179 decides the verifier
  reads the original prompt, it stops being true, and this record is the one to
  revisit — not by weakening the rule, but by re-pricing what a decomposition
  error costs.
