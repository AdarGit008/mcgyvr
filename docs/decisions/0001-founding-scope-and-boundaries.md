# ADR-0001 — Founding scope and boundaries

Status: Accepted
Supersedes: none
Superseded-by: none
Date: 2026-08-01

## Context

mcgyvr succeeds [`AdarGit008/local-ai`](https://github.com/AdarGit008/local-ai)
(archived). local-ai was an MVP built to answer one question — whether local
inference could absorb enough coding grunt work to justify hardware spend.
That question is settled: the hardware was bought, and the measurements are
vendored in `data/`.

What local-ai became along the way was a two-tier task router whose design
inputs were one person's two machines. Its README described an API
orchestrator that decomposes and plans; no such code existed — `roles.orchestrator`
was configured and never read, and task contracts were authored by hand. Its
telemetry pipeline was never fed by a real task. It was, accurately, a
well-tested execution half with no front end and no users.

mcgyvr is a rewrite with a different premise: **a product other people
install**, where the author's hardware is a dev fixture rather than a design
input. This record fixes the boundaries that follow from that premise, and
the forks that were considered and rejected. It does not describe
functionality — functionality is read from code.

## Decision

**What mcgyvr is.** A skill installed into a TUI/CLI agent harness (Claude
CLI, hermes, pi). The user's own agent remains the orchestrator of their
session. mcgyvr owns everything below the task contract: decomposition,
execution across a configurable worker ladder, a deterministic acceptance
gate, verification, and delivery as a pull request.

**North star: value per token.** Every routing decision optimizes accepted
work per unit of expensive-token spend. Explicitly *not* "percentage of
tasks sent to local" — a cheap tier that fails and escalates costs more than
the expensive tier would have.

The boundaries this implies:

1. **Two entry modes, not three.** *Delegated*: the agent forwards a prompt
   plus a repository and mcgyvr decomposes. *Direct*: the agent authors task
   contracts itself, making the contract schema public API. A third mode —
   a user-facing `/command` with no agent in the loop — is deferred, because
   it reintroduces full planning cost against the north star and is the only
   mode that cannot lean on context the calling agent already holds.

2. **Exploration is deterministic first, always.** The orchestrator runs a
   zero-token index (ripgrep + tree-sitter symbols) before any model reads a
   file, and the model reads only what the index shortlists. Context the
   calling agent supplies is an accelerator layered on top; it never replaces
   the deterministic pass. A repository — link or local directory — is
   required input: absent one, mcgyvr fails loud rather than guessing.

3. **The ladder is configurable and degrades.** Deterministic tools → local
   models → API models. A keyless install is a supported configuration, not
   a degraded one: it runs tools and local models with the deterministic gate
   as the acceptance bar.

4. **Workers are a pool, not a machine.** Sources are endpoints with a
   capacity and a wire protocol (`ollama` or `openai`-compatible), addressed
   uniformly. Nothing above the execution seam knows which machine or backend
   served a request. This generalizes the source-blind design worked out in
   local-ai#84/#85 and drops everything specific to that author's two GPUs.

5. **One task, one sandbox.** Each task runs in its own container, torn down
   after. This is not primarily about protecting the diff — a temp directory
   would do that — but because acceptance commands are arbitrary shell from a
   contract, running on someone else's machine. A temp-directory fallback
   exists for installs without Docker and is explicitly the weaker mode.

6. **Provider credentials never enter a task sandbox.** The orchestrator
   process holds keys; a task container gets the repository and a worker
   endpoint. See `SECURITY.md`.

7. **Delivery is a pull request.** Work lands on a branch and is proposed,
   for both a local directory and a remote link. mcgyvr does not silently
   mutate a working tree it was pointed at.

8. **Two languages, adapter-shaped.** Python and JavaScript/TypeScript at
   launch. One tree-sitter grammar set serves both the exploration index and
   the gate's structural checks, which is what makes the second language
   affordable rather than a doubling.

9. **Measurement is minimal in v1.** One record per task — enough to debug
   routing and to test the north star. Energy, price tables and cost
   rollups (built and working in local-ai) are deferred; they answered a
   capex question that is closed.

10. **Documentation carries only what code cannot.** Scope of record is the
    issue tree; forks and rationale are these decision records. Nothing
    describes behaviour that code already states.

**Definition of done for v1:** a stranger's install path works — clean
machine → install the skill → `mcgyvr init` → edit one config file → offload
a real task successfully, with no API key.

## Consequences

**What this makes easy.** The product has one honest job and a testable
completion criterion. A keyless local-only install is the default path, which
is also the cheapest path to prove the north star. Sandboxing per task makes
full autonomy defensible for software strangers run against their own
repositories. Deterministic-first exploration bounds the one cost centre that
could otherwise swamp the value-per-token thesis.

**What this makes hard.** v1 is large: an exploring orchestrator, a symbol
index, a concurrent multi-endpoint dispatcher, a container builder with
caching, a two-language gate, a forge integration, and skill packaging for
three harnesses. Nothing here is individually difficult; there are simply
twelve of them, and each has to work on a machine the author has never seen.
The issue tree is sequenced so the parts that need no API key and no forge
credentials — contract, source pool, sandbox, gate — are provable first.

**What was given up.** local-ai's cost and energy instrumentation, its merge
gate, its stash-and-reverify recovery path, and its cross-family
reassignment driver are not carried. The first two answered questions that
are now closed; the last two solved problems that the per-task sandbox and
the PR boundary remove by construction.

**Known tension.** "One configuration file" and "the full ladder is
configurable" pull against each other: sources, tier bindings, ladder and
risk policy, orchestrator model, verifier, container image and setup,
language adapters, delivery mode and budgets all have to live somewhere. The
promise is held as *one file to edit, generated by `mcgyvr init`* — not as a
short file. It is YAML rather than JSON for exactly this reason.
