# config — vLLM

What each knob does, and what it does not do. Values are derived per rig and per
model, never copied from here.

## `--cpu-offload-gb`

**Moves weights to host RAM — but only on one of the two model runners.** The
newer runner accepts the flag, hashes it into the compile-cache key, and
**ignores it**. Which runner a model takes is architecture-dependent, so the
same flag is live for one checkpoint and inert for another on the same rig.

**Verify it with the engine's own offloaded-parameter line in the log, never
with RAM figures.** Host memory moves for unrelated reasons, and the card tells
you nothing here.

**The declaration gate does not subtract it.** A cell is weighed at full weight
and refused if it does not fit, whatever the flag says. Do not expect the
offload to buy you admission.

→ `okf/must-read/touching-engine.md` for why offloading to host RAM is worse
than it sounds, and when to reach for llama.cpp instead.

## `kv_offloading_size` / `kv_offloading_backend`

Ship in this engine version for moving the KV cache to host RAM, and are
recorded as available and unset in this repo's own config capture. **Untested
here.**

## `--max-num-seqs`

**The batch width, and it is on no HTTP endpoint** — not in the server info, not
in the metrics, not on the model card. The harness reads it off the running
process argv over ssh, records it as observed, and refuses on a mismatch.

**Nothing asserts that it is at least the widest level of the ladder.** Set it
to the top of the ladder yourself, or the ramp queues at the scheduler and
prints a plateau indistinguishable from saturation.

## `--gpu-memory-utilization`

Raises the card budget — and **backfills freed weight space with KV cache**,
which is why card occupancy stays flat whether or not weights were offloaded.
**Never use card occupancy to judge placement.**

**Under util-sizing, `--max-num-seqs` is a cap the pool need not honour.** The
pool is sized from whatever VRAM survives the weights, so a cell can declare a
wide batch and hold a few. The engine states what it actually got — a KV cache
token count and a maximum-concurrency line — and **that line is the only width
readback vLLM offers.** Read it on every cell.

**Cells that come in under the ladder are the offload and large-model cells**,
where weights crowd the pool. Check the readback there first.

## KV sizing

**The KV requirement is max-model-len times batch width times bytes per token,
with bytes per token read at the cache dtype the entry actually launches with.**
An fp8 element is half a 16-bit one, so the KV size halves under the fp8 dtypes
and holds under the 16-bit ones; any other value is refused by name before the
card is weighed.

**The halving is exact, and it is measured** — a paired A/B on one card with the
same weights and the same max-model-len doubles the pool for a few percent of
single-stream throughput. **Sizing at the wrong dtype refuses cells that fit.**

**Do not derive this across rigs.** The two candidate weights-plus-residue bases
give answers far enough apart to change a decision — the same trap `always.md`
records for bits-per-weight.

## Co-residency — two vLLM servers on one card

**`util` is a budget for weights, KV and activations. The CUDA context is on top
of it.** Each server costs roughly a gigabyte of context before a single weight
loads, so the budget for `n` servers is `1 − n × (context / card)`, not `0.9`.
Three contexts alone take a quarter of srv2's card, which is why a plan drawn on
paper without counting them was wrong.

**SETTLED: `util` is a per-server share of the whole card, and a resident
neighbour does not shrink it.** Proven repeatedly — a co-resident server gets a
pool byte-identical to its solo run at the same util, and the solo curve is
linear in util.

**What a neighbour does is raise the floor under the free-memory precondition**,
which caps how high a *later* server's util may be set. The engine refuses at
startup when free memory is below the requested share, and that refusal is
arithmetic, not chance — one step under the ceiling runs, one step over refuses,
reproducibly.

**Launch them sequentially, each healthy before the next starts.** vLLM profiles
live free memory during init, so two starting together race and one dies on a
util that works alone. This is settled and it is the important half of the
ordering question.

**Which order is NOT settled, and the two rules in this tree disagree.** This
file has ruled small-first — give the small model its share while the card is
empty, because large-first leaves the second server a budget smaller than the
first already occupies. The emitter sequences largest-first, reasoning that the
large unit is the one that cannot recover from measuring a card a neighbour has
already taken a share of. The measurement cited for largest-first actually
compares *racing* against *sequencing*, not one order against the other, so it
does not settle the direction. **Treat the order as an open ruling; do not
quote either rule as decided.**

**A launch near the memory edge fails intermittently — retry before believing a
refusal.** The identical command on a verified-empty card has died once and come
up twice with byte-identical pools. A single refusal is a coin flip; a success
is exactly reproducible. This manufactured two false conclusions in one
afternoon, on settings minutes apart that had already been shown to work. The
driver retries and reports the try count on the config row.

**Solo floors taken as single draws are not floors.** Given the flake rate, one
refusal is one observation. Re-measure with retry before trusting any of them.

**The measured srv2 ceiling is two co-resident vLLM servers, both small.** A 7B
does not co-reside there at a realistic context — its weights leave far less
than one request's worth of KV. Three servers do not fit, and the arithmetic
that makes that unsurprising is the context overhead above.

## Compute capability 7.5 (srv1)

AWQ works, Marlin MoE kernels are selected, bfloat16 falls back to float16
automatically, FlashAttention 2 is unavailable and attention falls to the Triton
backend, and the FlashInfer sampler falls back. **None of these blocked a load;
only capacity did.** FP8 needs a newer card.
→ `okf/must-read/touching-engine.md`
