# config — llama.cpp

What each knob does, and which way to move it. Values are derived per rig and
per checkpoint, never copied from here.

## `--parallel` / `-np`

**Defaults to a small number of slots.** Left at the default, a wider ladder
runs as several sequential batches and produces a plateau indistinguishable from
saturation. Set it explicitly to the top of the ladder.

**It is read back.** The server states the width it actually came up at, and the
harness refuses if that endpoint does not answer, or if the readback is below
the widest level.

Two caveats. The check compares the readback to the *widest level*, not to the
declared width, so an engine that silently reduced the width passes whenever the
ladder tops out below it. And the console summary never prints the value — it is
visible only in the JSON.

## `-c` (context)

**Total, and it divides across slots** — but only when `--parallel` is passed.
Divide before you declare, or every slot gets a fraction of what you meant.

**There is a floor per slot**, set by the ramp tokens plus prompt headroom.
Declare at or above it, and confirm the readback rather than assuming it.

## `--n-cpu-moe N`

Keeps attention and shared layers on the card and puts the experts of N layers
into host RAM. This is what lets a large MoE serve from a small card.

**It is bounded by VRAM, not by host RAM.** At the floor the card is full while
host RAM sits nearly idle.

**Lower N is faster, and the gradient is steep and monotonic — walk down to the
floor and do not settle above it.** Archived runs of these architectures sat
several times above their real floor and gave away a large multiple of
throughput for it.

**The floor is per checkpoint and per rig**, being a function of expert bytes
and KV, so re-derive it whenever either moves. Floors measured under different
hardware are not comparable to one measured now.
→ `okf/must-read/touching-rigs.md` for the budget arithmetic and the walk-down

**A floor is a fit-and-throughput number and says nothing about output.**
`--n-cpu-moe` is a semantic key: two cells of one model at two values are not
comparable on output until a placement null on that build shows the key neutral,
and the one null measured so far shows it is not.

**CPU offload is what flattens the scaling curve, not MoE.** A MoE small enough
to stay resident on the card scales with width like a dense model; offloaded
cells scale far worse.

## `--no-op-offload`

**Banned — leave op offload at its default, on.** Owner ruling. With experts in
host RAM, op offload copies an expert tensor onto the card for each large batch,
so prefill runs on the GPU. `--no-op-offload` stops that copy: it frees the
copy's room in the compute buffer and **cuts prefill by half or more, while
decode does not move at all.**

**The buffer room it frees buys nothing.** It is far smaller than a single
expert block, so it cannot move even one block onto the card. Size for the
buffer with op offload left on: the buffer steps up once *any* expert is on the
host, then holds flat however many more follow, and that single step is the
whole of the drift.

## `-nkvo` / `--no-kv-offload`

**Read the direction carefully — KV lives in VRAM by default.** `-nkvo` moves it
to host RAM: buys VRAM, costs PCIe traffic per token. Untested here.

`-ctk` / `-ctv` set the KV dtype and shrink the cache in place instead, which is
the usual lever.

## `--no-mmap`

**Host-dependent, and the sign flips.** On a RAM-tight host it stops the model
paging continuously from NVMe and wins large; on a roomy host the copy is pure
cost and it loses. Re-measure on the rig you are on, and never carry the flag
across a hardware swap.
→ `okf/must-read/touching-rigs.md`

## `--n-gpu-layers` / `-ngl`

**Set it to everything the card will take.** Placement is then decided by
`--n-cpu-moe`, not by this.
