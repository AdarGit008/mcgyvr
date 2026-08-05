# ADR-0012 — re-entry is refused by what the caller holds, not by what it is called

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-06

## Context

mcgyvr is invoked by a human or by an agent, and more than one instance may run
at once. Concurrency between sibling instances is a supported mode: they contend
for sources, they queue on the declared `max_parallel`, and the wait is a cost
the operator accepts in exchange for not buying more hardware. Nothing about
that needs a new rule.

Re-entry does. An mcgyvr run that reaches mcgyvr again is a different shape from
two runs side by side, and it arrived as a question — "can a worker call
mcgyvr?" — that turns out to be two questions wearing one name.

**Re-decomposition mid-run is not re-entry.** A contract that proves too large
and is split again is a loop inside one instance: one run, one capacity
accounting, one sandbox lifecycle, one delivery. There is no second mcgyvr to
permit or refuse. What that loop needs is a declared depth and fan-out budget so
it terminates by rule rather than by luck, which is #155's ceiling and #158's
undeclared context window, not this record. It is named here only because the
two were conflated when the question was first asked, and a record that does not
separate them will be read as restricting the loop.

**The obvious rule is role-shaped, and the roles do not hold still.** "A worker
may not call mcgyvr" is how everyone says it, including the issue this record
closes. It fails on a case the ladder already anticipates: a rung bound to an
agent harness with mcgyvr installed is a worker by function and an orchestrator
by shape. Under a role-based rule, every new rung re-opens the question of what
counts as a worker. Under a rule about possession, nothing re-opens: the harness
holds a sandbox, so it is refused, and no one has to adjudicate what it *is*.

**One of the three motivating reasons is weaker than it first appeared, and
saying so is the point of writing this down.** The hold-and-wait deadlock —
a caller occupying a source slot while blocking on an inner run that needs one —
is real in general and **is already absent here by construction**. `capacity.py`
acquires per source *around the dispatch, not around the task*: "a task never
owns a slot", so a slot is held only for the length of one request. By the time
anything inside a sandbox could invoke mcgyvr, the dispatch that produced the
diff has returned and its slot is released. The deadlock argument is therefore
conditional on a design mcgyvr deliberately does not have.

That does not soften the rule; it relocates its support. Two reasons remain and
both are structural rather than contingent:

- **The sandbox is credential-free by construction.** `sandbox/base.py:124`
  builds a task environment from nothing — the host environment is never
  inherited — and `credential_env_names(env) == frozenset()` is asserted at
  construction. A nested mcgyvr started in there has no key to bind, no source
  it may reach that needs one, and no Docker access it was granted. It does not
  deadlock; it fails obscurely, deep inside a container, in a process nobody is
  watching. And ADR-0013 makes the failure total for the delegated path:
  decomposition is api-tier only, the sandbox can hold no api credential, so a
  nested run inside a task container cannot decompose at all. The refusal
  written here makes an existing impossibility legible instead of leaving it to
  be discovered as a defect.
- **Value per token.** A worker is selected for being the cheapest rung that can
  do the job. Standing an orchestrator up inside it inverts the reason it was
  selected, and does so where no telemetry attributes the spend.

**Cross-repo work is the only genuine use case anyone has produced for nesting**,
and it is not v1. So the scope call and the rule are separable, and this record
keeps them separate on purpose: the rule is what governs re-entry whenever it is
attempted; v1's answer is that it is never attempted.

## Decision

**Nothing may re-enter mcgyvr while holding a pool slot or running inside a
sandbox.**

The rule is about possession at the moment of the call, not about the caller's
name. A worker holds a sandbox and is refused without anyone deciding whether it
is a worker. An orchestrator between dispatches holds neither, and the rule does
not speak to it.

**Separately, and on scope rather than on safety: v1 permits no nested run at
all.** The depth cap is zero. When it is raised, the rule above is what governs
the levels that appear.

Two riders hold at every depth:

- **Only the root run delivers.** A nested run returns a changeset to its
  caller; it never opens a branch or a PR. Nesting composes contracts, not
  deliveries. Two levels of delivery would open a pull request against a branch
  that is not itself merged.
- **Depth is declared, not discovered.** The cap is configuration and reaching
  it is a refusal naming what was reached. A run that quietly stops at a depth
  nobody chose is the failure this rider exists to prevent, and it is not
  hypothetical: `plandex-ai/plandex` at `e2d7720` walks a model fallback chain
  with `maxFallbackDepth = 10` and, at the end of it, dispatches to a model that
  provably cannot hold the input — its own comment says "if the token number
  exceeds all the fallback models, it will return the last fallback model"
  (`app/shared/ai_models_large_context.go:45`). That is what a discovered limit
  looks like in a shipping product.

**Detection is a marker in the task environment, and it is not a boundary.** A
run knows it is inside a sandbox because the sandbox says so. The marker is
spoofable and that is accepted: it exists so the refusal can name the actual
reason rather than leaving the caller to discover the problem as a failure
somewhere else. ADR-0005 and the container are the boundary. Anywhere this is
implemented must say so, so that nobody later removes a containment measure on
the belief that the marker covers it.

## Rejected: phrase the rule by role

"Workers may not re-enter" is shorter, it is how the constraint is spoken, and
it can be enforced at the dispatch site where the role is known. It also matches
the mental model a reader arrives with, which is worth more than it sounds.

It loses because the role is not a durable property of the thing being
restricted. A rung bound to an agent harness that has mcgyvr installed is a
worker by function and an orchestrator by construction; the ladder is
deliberately open about what a rung may be bound to, so this is not an exotic
case but a supported one. Every such rung would re-open "is this a worker",
and each answer would be a judgment rather than a check.

The deeper objection is that the role is not what makes re-entry unsafe.
Possession is. A rule that names the role is a proxy for a rule about holdings,
and proxies drift from what they proxy exactly when something new is added —
which is the moment the rule is most needed.

## Rejected: allow nesting in v1 behind a depth cap greater than zero

The machinery is not far away. Capacity already releases a slot at the end of a
dispatch rather than at the end of a task, so the deadlock this would otherwise
raise is absent; a cap of one would cover cross-repo work; and the riders above
would hold it in shape.

It loses on the sandbox question, which has no v1 answer. An inner run started
inside a task container needs either the host Docker socket mounted through —
straight across ADR-0005's boundary and past the credential-free environment
`sandbox/base.py` constructs — or a nested container runtime, which is a
standing operational commitment for a use case v1 does not have. Neither cost is
worth paying for cross-repo work that nobody has asked for yet.

This is a deferral, not a refusal in perpetuity. What would have to be true to
raise the cap: an answer for the sandbox boundary that does not weaken ADR-0005,
and — if capacity ever moves to per-task accounting, which `capacity.py`
currently rejects by design — slot release on wait, because the deadlock reason
would activate the moment a task owned a slot.

## Rejected: write nothing, and let re-entry fail on its own

It already half-fails. The sandbox has no credentials, so a nested delegated run
cannot bind an api source and, under ADR-0013, cannot decompose. Nothing needs
building for the common case to come out refused.

It loses on the shape of the failure. What "fails on its own" produces is an
error raised in a container, from a process the operator did not start, about a
missing credential — which names none of the three reasons this is disallowed
and reads as a configuration problem. Somebody would then fix it by supplying
the credential. A rule that is enforced by an accident is a rule that the next
person removes while making something else work.

## Consequences

- **Re-decomposition is untouched**, and the record says so where a reader meets
  the restriction. Its budget stays with #155 and #158.
- **The refusal is tested from the direction it arrives** — a contract whose
  command invokes mcgyvr — rather than as a unit test of a predicate. A
  predicate test passes on a rule that is never reached.
- **#141 is where concurrency bites first**, not here: N sibling instances
  probing one endpoint is N× the probes and N verdicts about one rig, which one
  shared verdict with a TTL would fix. Sibling concurrency is supported and this
  record does not touch it.
- **Cross-repo work requires superseding this record**, which is the correct
  cost for a scope change of that size.
- **What this gives up:** a composition pattern that is legitimate in principle
  — an agent-shaped rung that decomposes its own contract further — is refused,
  and work that could have been split below the contract has to come back up to
  the orchestrator to be split. Accepted: the orchestrator is where decomposition
  is anyway (ADR-0013), so the round trip goes to the only place allowed to do
  the work.
- **What this bets on:** that possession is the durable property and role is
  not. If a case appears where something holds neither a slot nor a sandbox and
  re-entry is still unsafe, the rule is incomplete and this record is the one to
  amend — not the enforcement, which would then be correct code implementing an
  insufficient rule.
