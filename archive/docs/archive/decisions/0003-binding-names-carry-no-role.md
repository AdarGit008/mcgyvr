# ADR-0003 — A binding's role is derived from where it sits, not from its name

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

Bindings were to be named `<role>_<locality>_<model>` — `worker_local_qwen2.5-coder-7b`,
`orch_api_claude-opus-5` — with roles `worker` and `orch`. The convention
replaced positional names (`local-1`, `local-2`) for a good reason that still
holds: #16's risk floors will reference these names, and a positional name
silently changes meaning when a rung is inserted above it. For a policy
reference that is a rename disguised as an edit.

The `orch` half of it never had anywhere to live. Only `ladder.tiers[].name`
is a name in this config. `orchestrator` and `verifier` are blocks carrying
`source` and `model` with no `name` key at all — they are addressed by their
schema path. So no config file could contain the string
`orch_api_claude-opus-5`: `propose.binding_name()` could produce it and a
test asserted it, but nothing called it. The convention was also silent on
the verifier, which is a third role nobody had accounted for.

The question stayed open across three sessions, which is itself the signal
that the shape was wrong rather than merely unfinished.

## Decision

**A binding's role is derived from where it sits in the schema.** Under
`orchestrator` it is the orchestrator; under `verifier` it is the verifier;
in the ladder it is a worker.

The role token is therefore **deleted, not relocated**. Follow the derivation
through: the only named things are ladder tiers, and every ladder tier is a
worker, so a role token would be constant across every name that exists. It
would spend characters restating what the name's location already says. The
convention becomes:

    <locality>_<model>        e.g.  local_qwen2.5-coder-7b
                                    api_claude-opus-5

and it governs ladder tiers only. `ORCHESTRATOR` is removed and
`binding_name()` loses its `role` parameter.

This answers the verifier gap for free. The verifier is derived exactly as
the orchestrator is, so the convention never needed to name a third role —
the gap was an artifact of trying to encode roles in names at all.

`orchestrator` and `verifier` keep their inline `source` and `model`.

## Rejected: make the roles named tiers

The obvious way to give `orch` a home is to let the roles be tiers with names,
so `orchestrator:` would reference one. This is wrong about what the ladder
is.

The ladder is an escalation **order**, not a list of bindings. Its rungs are
cheapest-first; `budgets.max_escalations` caps how far a task may climb; and
the anti-inversion rules exist because each rung must be measurably better
than the one below or escalating buys latency instead of capability. Every
one of those properties describes a task failing the gate and being retried
higher.

The orchestrator does not climb. It turns a prompt plus a repository into
contracts, once. It has no rungs, no ordering, and nothing for the inversion
rules to constrain. Putting it in the ladder would subject it to semantics
that do not apply to it, in exchange for a naming convenience.

If decomposition ever grows its own retry-at-a-stronger-model behaviour, it
needs its own ordering — not a slot in the workers' ladder. Nothing specifies
that today.

## Rejected: a separate `bindings:` section

The remaining wrinkle is real: `orchestrator` and `verifier` each spell out a
`source` and a `model`, so an orchestrator bound to the same model as a ladder
rung states it twice, and #70 (source-side model swapping) would have to
change it in two places. A `bindings:` section holding named source/model
pairs, with the ladder and the roles both referencing it, removes that.

It was rejected on the grounds ADR-0001 already settled. This file is YAML
rather than JSON specifically because it carries policy a human edits, and
indirection is paid for at every read: answering "what is my orchestrator
actually pointed at" would become a lookup rather than a glance. What it buys
is de-duplicating one source name and one model string. For a file a stranger
is asked to edit, inline wins.

## Consequences

- No dead naming token. The convention as documented is now the convention as
  implemented, which is the property the config reference (#12) exists to
  hold.
- The tier `name` field's schema documentation states the convention, so it
  reaches `docs/config-reference.md` by generation rather than by being
  restated there.
- Existing example names change: `worker_api_claude-opus-5` becomes
  `api_claude-opus-5`, including in the API-source example that `mcgyvr init`
  prints when it refuses. Nothing has shipped a config yet, so no migration is
  owed.
- #16's risk floors can reference a worker by its tier name and a role by its
  schema path (`orchestrator`, `verifier`). Both are stable when a rung is
  inserted, which was the original reason for abandoning positional names.
- The duplication between a role block and an identical ladder rung stands,
  deliberately. If #70 makes it painful, this is the record of what was traded
  for it.
