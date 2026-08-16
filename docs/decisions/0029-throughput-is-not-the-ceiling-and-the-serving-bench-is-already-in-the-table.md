# ADR-0029 — throughput is not the ceiling, and the serving bench is already in the table

Status: Accepted
Supersedes: none
Superseded-by: none
Amends: none
Date: 2026-08-16

## Context

The prior-art dig
([`docs/hybrid-orchestration-prior-art-2026-08-16.md`](../hybrid-orchestration-prior-art-2026-08-16.md))
proposed taking two things from SGLang, bundled as one action:

1. **a serving-throughput benchmark**, modelled on `python/sglang/benchmark/serving.py`
   — tokens per second under concurrency, which `tools/bench/` does not measure;
2. **cache-aware rung selection**, modelled on
   `sgl-model-gateway/src/policies/cache_aware.rs` — a radix tree over prompt
   prefixes, routing each request to the worker that already has the most of it
   warm, falling back to shortest-queue when load is imbalanced.

The framing was that this is where "value per token" meets throughput: a cache
hit is tokens not recomputed, and `pool.py` today selects a source by name and
nothing else.

Both halves were checked. They fail for different reasons.

## The bench half is redundant

`data/capability-table.json` `concurrency_findings` already holds the
measurement, taken on rig_b on 2026-08-01:

* **CON-04** — continuous batching on a 12 GB card: 1 request 68 tok/s, 2 → 127
  (1.9×), 4 → 168 (2.6×), 8 → 289 (4.7×), 12 → 402 (6.6×), 16 → 489 (8.5×).
  Ceiling ~490 tok/s, bounded by memory bandwidth rather than compute. Its
  recorded consequence is already the operational one: "capacity beyond the knee
  buys latency variance, not throughput."
* **CON-05** — prefix caching: 43.3% hit rate on a 39-token shared prefix, 19%
  wall-clock speedup.

A new serving bench would re-derive these. The gap the dig saw was in
`tools/bench/`, which measures acceptance and gate score; it did not look at the
capability table, where the serving numbers live. That split is deliberate and
[ADR-0024](0024-comparable-measurements-come-from-one-rig-and-one-build.md)
depends on it: the bench measures what a worker can *do*, the table measures what
a rig can *serve*.

## The routing half is a lever we do not price

Prefix-affinity selection is genuinely absent, and it would genuinely help. Two
things stop it.

**It buys speed, and speed is not the constraint.** The project's direction is
the capability ceiling: a task the floor unit cannot do does not become doable
because its prompt was warm. [ADR-0017](0017-the-floor-is-the-product.md) makes
the smallest tier the product, and every open trunk issue is about what that
tier can *reach*. Tokens per second has never been a pass bar here and adding a
routing lever that optimises it would make one by implication.

**It costs the seam.** `pool.py` states the rule that keeps a second backend
affordable: "Supporting a new backend is therefore a config entry naming one of
these, not a new integration." Prefix affinity breaks that. To route on cache
warmth the selector must know what one specific backend has cached — vLLM and
SGLang expose it, Ollama's behaviour differs, a hosted provider's is invisible.
The rung choice stops being a property of the ladder and becomes a property of
the server, which is the boundary the seam exists to hold.

There is a real counter-argument and it should be recorded rather than buried:
every local worker receives the same shared system prompt of roughly 2 KB, which
is about 50× the prefix CON-05 measured, and CON-05's own note says the benefit
"should be substantially larger" at that size. That sentence is a projection.
`data/README.md` holds the line it violates — "Nothing in the table is estimated
or interpolated" — and the honest status of the larger benefit is unmeasured, not
established.

## Decision

> **DECIDED (2026-08-16, owner).**
>
> 1. **No serving-throughput benchmark is built.** CON-04 and CON-05 are the
>    project's serving measurements. A question about throughput under
>    concurrency is answered by re-running the rig measurement that produced
>    them, not by a second instrument in `tools/bench/`.
> 2. **`tools/bench/` measures acceptance, not speed.** The split between the
>    bench and the capability table is kept: what a worker can do, versus what a
>    rig can serve.
> 3. **Rung selection stays backend-neutral.** No selector reads a
>    backend-specific cache state. A rung binds a source by name; what that
>    source does with its KV cache is the source's business.
> 4. **The 2 KB-prefix benefit is unmeasured and is not to be cited as a
>    figure.** CON-05's "should be substantially larger" is a projection.
>    Anything that wants to act on it measures it first, at the real prompt size,
>    on a rig.

## Consequences

**A real speedup is left on the table, knowingly.** Prefix-aware routing on a
batching backend with a shared 2 KB system prompt would probably be worth
something. This record declines it on grounds of what it costs, not on grounds
that it would not work — so the way back is open and named: measure the hit rate
at our real prompt size, and if the number is large enough to argue for spending
the seam, argue for it in a new record.

**Backends may still cache.** Nothing here discourages pointing a rung at a
server with RadixAttention or automatic prefix caching. The benefit is collected
for free by the backend. What is refused is *routing on* it.

**The dig's underlying observation stands and is not this record's target.**
`pool.py` really does select by name only. Whether that is the right selection
layer is #277's question and #16's question. This record says only that cache
warmth is not the input that should change it.
