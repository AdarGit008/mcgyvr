# config — llama.cpp

What each knob does, and which way to move it. Values are derived per rig and
per checkpoint, never copied from here.

## `--parallel` / `-np`

**Left unset, the server comes up with a small fixed number of slots and a
unified KV cache.** A wider ladder then runs as several sequential batches and
produces a plateau indistinguishable from saturation. Set it explicitly to the
top of the ladder.

**Read it back.** The server states the width it came up at on `GET /props`
(`total_slots`). Compare it with the width you declared, not only with the
ladder's top — an engine that silently reduced the width passes the second check
whenever the ladder tops out below it.

## `-c` (context)

**Total, and it divides across slots — but only when `--parallel` is passed.**
With no `--parallel` the cache is unified, every slot sees the whole `-c`, and
`-no-kvu` is overridden. Divide before you declare, or every slot gets a
fraction of what you meant.

**The per-slot share is padded up to a multiple of 256.** The engine's warning
says "rounding down"; the per-slot window it reports is the rounded-up one. Size
KV from the padded figure and confirm it on `/props`.

**There is a floor per slot**, set by the ramp tokens plus prompt headroom.
Declare at or above it, and confirm the readback rather than assuming it.

## `-b` / `-ub`

**`-ub` above `-b` is clamped to `-b`.** Raising `-ub` alone measures the old
setting under a new label. Raise both, and read `n_ubatch` from the engine's
log, not from the argv. The compute buffer scales with the effective value.

## `--n-cpu-moe N`

**Keeps the expert tensors of the first N blocks — block indices 0 to N−1 — in
host RAM.** N is an index, not a count of expert-bearing blocks: on a checkpoint
whose first blocks are dense, the first steps of N move nothing. It removes
expert tensors only; attention and KV are on the card because of `-ngl`.
`--cpu-moe` is every block. On a dense model it is a no-op. Lower N puts more
experts on the card; measure down to the floor before settling above it.

**It is bounded by VRAM, not by host RAM.** At the floor the card is full while
host RAM sits nearly idle.

**The floor is per checkpoint and per rig**, being a function of expert bytes
and KV, so re-derive it whenever either moves. Floors measured under different
hardware are not comparable to one measured now.
→ `okf/must-read/touching-rigs.md` § Spending the card for the budget arithmetic
and the walk-down

**A floor is a fit-and-throughput number and says nothing about output.**
`--n-cpu-moe` is a semantic key: two cells of one model at two values are not
comparable on output until a placement null on that build shows the key neutral.

**CPU offload is what flattens the scaling curve, not MoE.** A MoE small enough
to stay resident on the card scales with width like a dense model; offloaded
cells scale far worse.

## `--spec-type draft-mtp`

**The MTP head is charged to the card.** It sits at the last block index, so no
N at or below the floor reaches it. A
placement that loads without the flag can be refused with it. Put the head's
bytes — the tensor table's nextn block — into the floor budget, and re-derive
the floor per width: the head takes room wider ladders need for KV.

**Check the tensor table for a nextn block before declaring MTP.** A family
being MTP-native says nothing about a given GGUF; a unit that declares `mtp` on
a file with no nextn block is refused before launch.

**Draft acceptance is not speedup.** Measure against the same file with the flag
off, same build, at every width you mean to serve.

## `--no-op-offload`

**Banned — leave op offload at its default, on.** Owner ruling. With experts in
host RAM, op offload copies an expert tensor onto the card for each large batch,
so prefill runs on the GPU. `--no-op-offload` stops that copy: it frees the
copy's room in the compute buffer and costs prefill heavily, while decode does
not move.

**The buffer room it frees buys nothing.** It is far smaller than a single
expert block, so it cannot move even one block onto the card. Size for the
buffer with op offload left on: the buffer steps up once *any* expert is on the
host, then holds flat however many more follow.

## `-nkvo` / `--no-kv-offload`

**Read the direction carefully — KV lives in VRAM by default.** `-nkvo` moves it
to host RAM: buys VRAM, costs bus traffic per token. Measure before adopting.

`-ctk` / `-ctv` set the KV dtype and shrink the cache in place instead, which is
the usual lever. Treat the dtype as a semantic key: validate answers against a
same-config null before adopting one.

## `--load-mode`

**`--load-mode none` is the unmapped mode; `--no-mmap` is its deprecated
spelling.** `--mmap`, `--no-mmap`, `--mlock` and the direct-io flags all warn
and map onto `--load-mode`; mix the two spellings and only the last flag on the
command line takes effect. On the pinned upstream build spell `--load-mode` and
nothing else; on a fork image, read its `--help` first. The default, `auto`,
maps.

**Host-dependent, and the sign flips.** On a RAM-tight host unmapping stops the
model paging continuously from NVMe and wins; on a roomy host the copy is pure
cost and it loses. Re-measure on the rig you are on, and never carry the mode
across a hardware swap. `--load-mode mlock` is the one that makes the weights
unpageable.
→ `okf/must-read/touching-rigs.md` § Host RAM

## `--n-gpu-layers` / `-ngl`

**Set it to everything the card will take.** Placement is then decided by
`--n-cpu-moe`, not by this.

**An explicit `-ngl` or `--n-cpu-moe` switches off the engine's own fitter.**
The log line `n_gpu_layers already set by user … abort` is expected, not a
fault; the fit is ours to derive.

## `-t`

**Physical cores at most, and the sum across units that decode at the same time
stays inside the physical cores.** Nothing here sums `-t` across co-resident
units — each is set on its own — so check the sum by hand.
→ `okf/must-read/touching-rigs.md` § Host memory bandwidth

## Logs and endpoints

**The buffer and cache size lines do not print at the default verbosity.** The
library's info lines — `load_tensors`, `llama_kv_cache`, the scheduler's reserve
— are logged one level above the server's default threshold. Pass `-lv 4` (or
`-v`) on any launch whose log is the readback, on both arms of a comparison.

**Keep the whole log and parse it off the rig.** A sliding-window model creates
two caches and prints a size line for each, so `grep | tail -1` keeps the wrong
one.

**`/metrics` answers an error unless the server was started with `--metrics`;
`/slots` is on by default and `--no-slots` turns it off.** A status read that
gets the error is a launch flag, not a dead unit. Read activity from `/slots`
(`is_processing`).

**The server ignores a request's `model` field.** A request naming weights the
server is not holding is answered from the weights it is, with no error. Decide
what is behind a port from `GET /v1/models`, never from a dispatch that
succeeded.

**The id on `/v1/models` is derived from what `--model` was handed unless
`--alias` is set.** It will not equal a config's short name by construction;
compare on the path, or set the alias.

**A load's card peak is sampled until `/slots` reads idle, not until the
requests are closed.** The lock harness keeps sampling after it closes its
connections, with no time limit, because a unit can still be working then; a
peak taken only while the requests were open is a lower bound.

**The upstream CUDA server image carries no `llama-bench` file.** Reach the
microbenchmark through the dispatcher, `/app/llama bench`; locally built images
carry the separate binary. Probe for both before declaring an arm unbenchable.
