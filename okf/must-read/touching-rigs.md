# touching-rigs

Any ssh, any launch, any measurement on a rig.

## Before

**Prove reachability** → gate 2

**Read the card and RAM, do not assume.** Query the card's memory totals and the
host's available memory on the rig, at the moment you are about to launch. The
rigs swap hardware; a stored spec is a guess.

**Read `used`, and find out whose it is.** A card can be held by a process
nothing in this repo started. Query the compute apps
(`nvidia-smi --query-compute-apps=pid,used_memory --format=csv`) before planning
a budget around free VRAM.

**Under vLLM the pid that holds the card names no model.** vLLM retitles its GPU
worker, so the pid the driver reports has the command line `VLLM::EngineCore`
and nothing else. The model and the flags are on its parent's command line —
join on the parent pid. Matching the worker's own line finds nothing and reads
as an empty card.

**Bracket one character of any `pgrep -f` / `pkill -f` pattern sent over ssh**
(`[l]lama-server`). Unbracketed, the pattern matches the shell that carries it,
and `pkill` kills the ssh session before it reaches the target. Stop a sampler
you started by its pid file, not by name.

## Card memory

**A card has four buckets: `total = reserved + used + free`.** The driver's
reserve is memory no process is ever given. It is constant within a boot and
moves across boots, so read it, never store it.

**Take the VRAM term from `free`, never from `total − reserve`.** The two agree
only on an idle card, and the wrong one places experts on a card with no room
for them.

**Read it after the previous cell tears down.** That is the only moment that
shows what the next launch actually gets — a live mapping also depresses what
the host reports as available.

## What a context costs

**KV is charged per caching layer, never one width for all of them.**
Architectures declare which layers cache: a full-attention interval, a
sliding-window split, a per-layer head-count array, a compressed latent that
caches no separate V. A single width applied to every layer is wrong by a large
factor on some of them. Read each layer's widths from the header and sum the
layers that actually cache. → `okf/config/llama.cpp.md` for the engine's own
cache lines, which are the readback.

**An undeclared sliding-window split is refused, not guessed.** Where a header
states a window but no per-layer pattern, alternating is a guess. Refuse the
placement until the pattern is read from the engine's cache lines.

**The non-caching layers charge per slot, not per token.** Linear and recurrent
layers hold a fixed state for every slot. Raising context is cheap on them;
raising `--parallel` is not.

**`--n-cpu-moe` moves expert tensors only, and saturates at the block count.**
KV stays on the card under it. KV leaves the card only under llama.cpp's `-nkvo`
→ `okf/config/llama.cpp.md`.

## Host RAM — the weights must fit it, or nothing you measure is real

**Never put a model on a rig whose RAM cannot hold what that model keeps
resident.** Owner ruling. Not a wake, not a sleep, not a bench cell, not a hand
launch.

**Nothing serves off NVMe or swap here, because the failure is silent.** Under
memory mapping an oversized model does not refuse and does not OOM: it starts,
slowly, and then pages off NVMe for as long as it serves. Nothing has failed, so
no gate fires, the health endpoint answers, and the run reports a disk benchmark
as a decode rate.

**Which bytes have to fit depends on the loading mode.** Mapped — the engine's
default — the whole blob pages through the page cache, host-side experts
included, so the blob is what must fit. Under `--load-mode none` only the
host-side expert tensors are allocated and nothing is read from the blob during
decode, so the experts are what must fit.
→ `okf/config/llama.cpp.md` `--load-mode`

**Host RAM is asked two questions, and they fail differently.** The blob against
available memory decides mapped or unmapped; short of it, unmap — the cost is
wake time, not decode. The host-side experts against available memory decide
whether the model goes on this host at all; short of that, nothing errors and
every request is served off swap. Keep a small margin on the first and a real
one on the second. If neither mode fits, the placement is wrong — take a smaller
checkpoint, a deeper quant, or another rig.

**Read available memory with nothing serving.** An unmapped unit depresses it by
its own experts, so a reading taken while it serves feeds the decision its own
answer.

**Whether unmapping pays is host-dependent** → `okf/config/llama.cpp.md`
`--load-mode`.

**The host-side experts are anonymous shared memory, and that swaps.** What
unmapping buys is that experts are not re-read from the blob per token. It does
not buy unpageability. Anything that depends on the experts staying resident
needs swap off or `--load-mode mlock`.

**Wake time tracks RAM headroom, not model size.** A blob that overflows its
host's RAM wakes far slower than a much larger blob that fits. Never extrapolate
a wake or a load from parameter count, quant or engine; the axis that predicts
it is whether the blob fits.

**A container memory cap does not simulate a smaller host.** Page cache is
charged to the cgroup that first read the file and stays charged there, so a
blob already in the host's page cache sits outside a `docker run --memory` cap
and the capped cell pages nothing. Test a RAM shortage on a host that is short,
or evict the file first (`echo 3 > /proc/sys/vm/drop_caches`) and confirm the
container's own memory counter moved.

## Host memory bandwidth

**Capacity and bandwidth are separate axes.** A rig with less RAM can have the
faster memory. Never infer one from the other, and never rank rigs on a single
axis.

**Measure bandwidth with a pure sequential read, not a STREAM triad.** Triad is
two reads and a write and reads lower; decode reads weights and writes almost
nothing, so the pure-read figure is the one that bounds it.

**Find the thread knee once per rig and set `-t` at it, never above the physical
core count.** Read bandwidth climbs with threads until either the memory or the
cores run out. Past the knee more threads buy nothing, and the second
hyperthread of a core adds no memory ports. Which of the two ran out says what
an upgrade buys: a curve still climbing at the last core wants cores, not DIMMs.

**Re-find the knee after any DIMM or CPU change.** A mismatched DIMM pair runs
part dual-channel and part single-channel; measure whether the boundary shows
before buying matched memory on bandwidth grounds.

## The image is part of the measurement

**A llama.cpp number is only valid against a stated image.** The stock CUDA
server build selects tensor-core kernels by compute capability alone, and a die
that reports the capability without the cores emulates them; a build compiled
below that architecture does not. Record `img=` on every row. → gate 3
→ `okf/must-read/touching-engine.md`

**An image pins the CUDA userspace, not the driver.** Inside the container the
host's driver answers, so two rigs on one image digest still differ. The driver
is part of rig identity — record it beside the image.

**An engine that uses io_uring needs its own seccomp profile.** Docker's default
profile does not allow the three io_uring syscalls, and an engine with no
fallback aborts at start. Give that unit a profile that is the default plus
`io_uring_setup`, `io_uring_enter` and `io_uring_register`, and nothing wider.

## Spending the card — the `--n-cpu-moe` floor

What bounds the floor, why it is per checkpoint and per rig, and what it does
not say about output → `okf/config/llama.cpp.md` `--n-cpu-moe`.

**Derive the floor, then walk down to it. Do not guess and do not copy a
neighbour's value.** The budget is free VRAM, less scratch and context, less
non-expert weights, less KV, less slot state, less any draft head
(→ `okf/config/llama.cpp.md` `--spec-type`). What remains is spent on expert
blocks from the top block index down, each at its own byte count from the tensor
table, and the first block that does not fit is the floor. A uniform per-block
average puts the floor several steps high. Both weight terms come from the
tensor table, never from the file size.

**The refusal is the measurement.** Run one cell below the predicted floor on
purpose — it names the true edge. **Retry any refusal three times before
believing it.** A launch near the memory edge fails intermittently, while a
success at the same setting is exactly reproducible.

**A placement specified before a hardware swap may no longer be launchable.**
Re-derive it against the rig as it is now, or run it outside the gate with the
headroom stated on purpose. A lower placement is not a substitute — it moves the
footprint into a band already tested.

## A rig that hard-locks under load

**A host declared `cpu_expert_offload: false` in `tools/runs/hosts.json` is
refused any placement that needs `--n-cpu-moe` above zero.** The default step
reads the key; flip it only on an owner ruling, not on a clean run.

**A BIOS power cap is not a fix until a lock-free campaign says so.** A lock
ends mid-log-stream: no OOM, no Xid, no MCE, no shutdown record.

**A hard lock can wipe the BIOS profile, power limits included.** Read the
limits back after a lock rather than assuming the profile survived it.

**Read the live power-limit key, not the rated one.** Under
`/sys/class/powercap/intel-rapl:0/`, `constraint_0_power_limit_uw` is what is in
force; `constraint_0_max_power_uw` reads the same number whatever the live limit
is, so it looks exactly like the cap being in force when it is not.

**One clean run is not an all-clear.** Locks spread across a long campaign are
not bounded by a short run that does not reproduce. Record it as a run that did
not reproduce, never as a fix.

**Stamp the power limits into the start and end markers, and write rows on the
rig as they are produced, because a lock takes the ssh pipe with it.**

**On non-ECC DIMMs a clean error count proves nothing.** Memory errors are
silent there. Before blaming software, diff the package list across the onset.

## Compose and emit

**`mcgyvr emit` writes and never deletes.** After a host is cut into
alternatives the old whole-host compose file is still there, and a wake that
finds more than one spec for the host declines. Delete the file you no longer
mean, then run `mcgyvr emit --check`.

**The file that tears a unit down is the file that started it.** Two models
alternating on one port need the down run against the file that is up, not the
one you are about to bring up.

## `tools/bench/serving/run.py` — resume and the journal

**`--resume` keys on host and label joined, and nothing else** — not backend,
not model id, not config digest. Two different configs under one label are one
cell to it.

**A refused cell counts as done.** A plain `--resume` skips refusals forever
while reporting the run finished. `--retry-failed` keeps only rows whose outcome
is exactly ok and re-measures everything else — but it does nothing on its own,
because the completed set is consulted only when `--resume` is also passed, and
nothing refuses the lone flag. Pass both.

**The journal is append-only and last-write-wins. Never delete a row to force a
re-measure.** Re-score instead; `--retry-failed` re-scores the stored levels
rather than trusting the stored outcome.

## `tools/bench/serving/run.py` — config

**Only a fixed set of entry keys is accepted; any other non-underscore key
raises.** Underscore-prefixed keys are documentation and ignored on purpose.

**The top-level document is not validated.** A misspelled section name is
silently ignored — the cell you think you declared may not exist.

**Every vLLM entry needs a measured footprint (`_footprint_mib` for the host),
or `weights_bytes` for the predicted branch.** Without either, the cell is
refused.

## After — always

**Kill what you started** → gate 7 An uncleaned container can hold a rig at
zero free RAM. List what is running and kill what the run created.
