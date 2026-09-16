# touching-rigs

Any ssh, any launch, any measurement on srv1 or srv2.

## Before

**Prove reachability** → gate 2

**Read the card and RAM, do not assume.** Query the card's memory totals and the
host's free memory on the rig, at the moment you are about to launch. The rigs
swap hardware; a stored spec is a guess.

**Read `used`, and find out whose it is.** A card can be held by a process
nothing in this repo started. Query the compute apps before planning a budget
around free VRAM.

## Card memory

**A card has four buckets: `total = reserved + used + free`.** The driver's
reserve is constant within a boot and moves slightly across boots.

**Take the VRAM term from `free`, never from `total − reserve`.** The two agree
only on an idle card, and the wrong one places experts on a card with no room
for them.

**Read it after the previous cell tears down.** That is the only moment that
shows what the next launch actually gets — a live mapping also depresses what
the host reports as available.

## What a context costs

**KV is charged per caching layer, never one width for all of them.**
Architectures declare which layers cache: a full-attention interval, a
sliding-window split, a per-layer head-count array. A single width applied to
every layer is wrong by a large factor on some of them. Read each layer's widths
from the header and sum the layers that actually cache. The engine prints a
cache line for each cache it creates at startup; pass those rows through as the
layer set, and use them as the readback.

**An undeclared sliding-window split is refused, not guessed.** Where a header
states a window but no per-layer pattern, alternating is a guess, and it has
been wrong on most of the split checkpoints measured.

**The non-caching layers charge per slot, not per token.** Linear and recurrent
layers hold a fixed state for every slot. Raising context is cheap on them;
raising `--parallel` is not.

**`--n-cpu-moe` saturates at the layer count**, and neither engine offloads KV,
ever.

## Host RAM — the weights must fit it, or nothing you measure is real

**Never put a model on a rig whose RAM cannot hold what that model keeps
resident.** Owner ruling. Not a wake, not a sleep, not a bench cell, not a hand
launch.

**Nothing serves off NVMe here, because the failure is silent.** Under memory
mapping an oversized model does not refuse and does not OOM: it starts, slowly,
and then pages off NVMe for as long as it serves. Nothing has failed, so no gate
fires, the health endpoint answers, and the run reports a disk benchmark as a
decode rate. If the blob does not fit host RAM the placement is wrong — take a
smaller checkpoint, a deeper quant, or the other rig.

**Which bytes have to fit depends on the mapping flag, and the difference is the
whole model.** With mapping on — the default — the whole blob pages through the
page cache. With `--no-mmap` only the host-side expert tensors are allocated and
nothing is read from the blob during decode.

**`--no-mmap` is rig-dependent and its sign flips.** It wins large on a
RAM-tight host, where it stops the continuous paging, and loses on a roomy one,
where the copy is pure cost and mmap was never the problem. Measure it on the
rig you are on; never carry the flag across a hardware swap.

**The host-side experts are shared memory, and shared memory swaps.** What the
flag buys is that experts are not re-read from the blob per token. It does not
buy unpageability. Both rigs run swap, so anything that depends on the experts
being untouchable needs swap off or a memory lock, and this fleet does neither.

**Wake time tracks RAM headroom, not model size.** A blob that overflows its
host's RAM wakes far slower than a much larger blob that fits. Never extrapolate
a wake or a load from parameter count, quant or engine; the axis that predicts
it is whether the blob fits. srv1 is the slow rig, and its ceiling is not the
biggest model — it is the model closest to overflowing its RAM.

**The product's own fit check weighs the spilled experts plus runtime, not the
blob**, and that is why an oversized model was once admitted and paged. The
bench's mapping gate is the stricter of the two and already says the right
thing: resident share against available memory less a headroom margin, evaluated
after the previous cell tears down. How much headroom is enough is bracketed,
not derived — read free memory at teardown rather than trusting a stored figure.

## Host memory bandwidth

**Capacity and bandwidth point in opposite directions across these two boxes.**
The rig with less RAM has the faster memory. Never infer one from the other, and
never rank the rigs on a single axis.

**Measure bandwidth with a pure sequential read, not a STREAM triad.** Triad is
two reads and a write and reads lower; decode reads weights and writes almost
nothing, so the pure-read figure is the one that bounds it.

**srv1 is core-limited, not DRAM-limited.** Its read bandwidth climbs linearly
with threads and is still climbing when it runs out of cores, well short of its
theoretical ceiling. Faster or additional DIMMs buy srv1 nothing on the memory
term. Cores would.

**srv2 saturates partway up its thread count.** Past the knee more threads are
worth nothing on the memory term, and the second hyperthread of each core is
worth nothing at all. Find the knee once per rig and set threads at it.

**srv2's mismatched DIMM pair costs nothing measurable.** Flex mode interleaves
the matched portion dual-channel and appends the remainder single-channel; a
knee was predicted at the boundary and there is none. Do not buy matched RAM for
srv2 on bandwidth grounds. Re-measure if the DIMMs move — they have.

## The image is part of the measurement

**srv1's llama.cpp numbers are only valid against a stated image.** The stock
CUDA server build selects tensor-core kernels on a Turing die that has none and
emulates them, reading far low in serving and worse again in prefill; the
patched build does not. Record `img=` on every srv1 row. → gate 3
→ `okf/must-read/touching-engine.md`

## Spending the card — find the `--n-cpu-moe` floor before anything else

**`--n-cpu-moe` is bounded by VRAM, not by host RAM.** At the floor the card is
full while host RAM sits nearly idle.

**Derive the floor, then walk down to it. Do not guess and do not copy a
neighbour's value.** The budget is free VRAM, less scratch and context, less
non-expert weights, less KV, less slot state. What remains is spent on expert
blocks from the top down, each at its own byte count from the tensor table, and
the first block that does not fit is the floor. A uniform per-block average puts
the floor several steps high. Both weight terms come from the tensor table,
never from the file size.

**The floor is per checkpoint and per rig.** It is a function of expert bytes
and KV, so it must be re-derived whenever either moves. A floor measured under
different hardware is not comparable to one measured now.

**Lower N is faster and the gradient is steep.** A run sitting well above its
real floor gives most of its throughput away. Walk down; do not settle above it.

**A floor is a fit-and-throughput number and says nothing about output.**
`--n-cpu-moe` is a semantic key: two cells of one model at two values are not
comparable on output until a placement null on that build shows the key neutral,
and the null measured so far shows it is not. Quote a floor for fit and speed
only.

**The refusal is the measurement.** Run one cell below the predicted floor on
purpose — it names the true edge. **Retry any refusal three times before
believing it.** A launch near the memory edge is a coin flip, while a success at
the same setting is exactly reproducible.

**A placement specified before a hardware swap may no longer be launchable.**
Re-derive it against the rig as it is now, or run it outside the gate with the
headroom stated on purpose. A lower placement is not a substitute — it moves the
footprint into a band already tested.

## srv1 hard-locks under CPU expert offload

**The BIOS power cap is not the fix.** srv1 has frozen with the cap in force.
Not model-specific, not depth-specific. Each lock ends mid-log-stream: no OOM,
no Xid, no MCE, no shutdown record.

**A hard lock can wipe the BIOS profile, power limits included.** Read the
limits back after a lock rather than assuming the profile survived it.

**PL1/PL2 and the ring ratio are held from the OS on srv1, not from BIOS.** A
boot-time service writes them every boot, on that box only. A BIOS value for
either loses to it after boot.

**Read the live power-limit key, not the rated one.** The rated-TDP key reads
the same number whatever the live limit is, so it looks exactly like the cap
being in force when it is not.

**One clean offload run is not an all-clear.** The locks were spread across a
long campaign, so a short run that does not reproduce bounds nothing. Record it
as a run that did not reproduce, never as a fix.

**Stamp the power limits into the start and end markers, and write rows on the
rig as they are produced, because a lock takes the ssh pipe with it.**

**Two facts constrain any diagnosis.** srv1's DIMMs are non-ECC, so memory
errors are silent and a clean error count proves nothing. And no package changed
across the onset, so software is excluded.

**The run that separates footprint from stream rate has not been done.**
Footprint and bytes-per-token move together in every config tested so far. The
test that breaks the coupling is a high-footprint, low-stream-rate placement: if
it locks, capacity is the cause; if it survives, bandwidth pressure is, and the
memory overclock returns as prime suspect.

## Resume and the journal

**`--resume` keys on host and label joined, and nothing else** — not backend,
not model id, not config digest. Two different configs under one label are one
cell to it.

**A refused cell counts as done.** A plain `--resume` skips refusals forever
while reporting the run finished. `--retry-failed` keeps only rows whose outcome
is exactly ok and re-measures everything else — but it does nothing on its own,
because the completed set is consulted only when `--resume` is also passed, and
nothing refuses the lone flag.

**The journal is append-only and last-write-wins. Never delete a row to force a
re-measure.** Re-score instead. Deleting turned the tree green over outstanding
cells once, and destroyed nothing only by luck.

## Config

**Only a fixed set of entry keys is accepted; any other non-underscore key
raises.** Underscore-prefixed keys are documentation and ignored on purpose.

**The top-level document is not validated.** A misspelled section name is
silently ignored, and so is a typo inside one — the cell you think you declared
may not exist.

**Every vLLM entry needs a measured footprint**, or the weight bytes for the
predicted branch. Without either, the cell is refused.

## After — always

**Kill what you started** → gate 7 An uncleaned container has held a rig at
zero free RAM. List what is running and kill what the run created.
