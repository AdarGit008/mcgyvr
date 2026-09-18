# config — vLLM

What each knob does, and what it does not do. Values are derived per rig and per
model, never copied from here.

## `--cpu-offload-gb`

**Moves weights to host RAM — but only on one of the two model runners.** The
older runner installs the weight offloader; the newer one accepts the flag and
never reads it. Which runner a model takes is architecture-dependent, so the
same flag is live for one checkpoint and inert for another on the same rig.

**Verify it with the engine's own offloaded-parameter line in the log, never
with RAM figures.** Host memory moves for unrelated reasons, and the card tells
you nothing here.

**The bench declaration gate does not subtract it.** A cell is weighed at full
weight and refused if it does not fit, whatever the flag says. Do not expect the
offload to buy you admission.

→ `okf/must-read/touching-engine.md` for why offloading to host RAM is worse
than it sounds, and when to reach for llama.cpp instead.

## `kv_offloading_size` / `kv_offloading_backend`

**A host-RAM tier behind the prefix cache, not a smaller card pool.** Completed
KV blocks are copied to host RAM and promoted back on a prefix hit; the GPU pool
is unchanged. Offloading is active only when `--kv-offloading-size` is set.

## `--max-num-seqs`

**The batch width, and it is on no HTTP endpoint** — not in the server info, not
in the metrics, not on the model card. The bench harness reads it off the
running process argv over ssh, records it as observed, and refuses on a mismatch.
`kv_cache_max_concurrency` on `/metrics` looks like the answer and is KV
capacity, not the flag.

**Set it to the top of the ladder.** Below it the ramp queues at the scheduler
and prints a plateau indistinguishable from saturation. The bench harness
refuses a declared width under the widest level; a sweep cell typed by hand is
not checked.

## `--gpu-memory-utilization`

**A share of the whole card, not of what is free.** The engine asks for
`total × util`, refuses at startup when free memory is below that, and — unless
KV is pinned — gives the KV pool whatever the share leaves after weights and
activations.

Raising it **backfills freed weight space with KV cache**, which is why card
occupancy stays flat whether or not weights were offloaded. **Never use card
occupancy to judge placement.**

**Under util-sizing, `--max-num-seqs` is a cap the pool need not honour.** The
pool is sized from whatever VRAM survives the weights, so a cell can declare a
wide batch and hold a few. The engine states what it actually got — a KV cache
token count and a maximum-concurrency line — and **that line is the only width
readback vLLM offers.** Read it on every cell.

**Cells that come in under the ladder are the offload and large-model cells**,
where weights crowd the pool. Check the readback there first.

## `--kv-cache-memory-bytes`

**Pins the KV pool in bytes, and the pool then ignores util.** The same pool
comes up on every start, in either order, beside a loaded neighbour and after a
restart. Util still does one thing: the startup check against free memory.

**The engine does not keep a pinned unit inside its share.** Weights plus
activations plus pinned KV can run past `total × util` with no warning, and only
the card running out stops it, as an OOM at start. The sum — non-KV peak plus
pinned KV inside the unit's room — is checked by us. A fleet unit without the
pin is refused at lock.

## KV sizing

**The KV requirement is max-model-len times batch width times bytes per token,
with bytes per token read at the cache dtype the entry actually launches with.**
An fp8 element is half a 16-bit one, so the requirement halves under the fp8
dtypes and holds under the 16-bit ones; any other value is refused by name
before the card is weighed. **Sizing at the wrong dtype refuses cells that
fit.** It is a declaration, not a runtime cap: the engine allocates KV per token
used, so the printed maximum concurrency is a worst case.

**`--kv-cache-dtype` is a semantic key.** It changes the pool and can change the
attention backend in the same move (→ `okf/must-read/touching-engine.md`). Spell
the dtype concretely — `auto` follows the model dtype — and compare answers against
a same-config null before adopting one; pool size and tok/s do not validate it.

**Do not derive this across rigs.** The two candidate weights-plus-residue bases
give answers far enough apart to change a decision — the same trap `always.md`
records for bits-per-weight.

## Co-residency — two vLLM servers on one card

**`util` is a budget for weights, KV and activations. The CUDA context is on top
of it.** Each server pays its context before a single weight loads, so the
budget for `n` servers is `1 − n × (context / card)`. Measure it on the rig: launch
one server on an empty card, read the card's `used`, subtract `total × util`, and
count the remainder once per server.

**SETTLED: `util` is a per-server share of the whole card, and a resident
neighbour does not shrink it.** A co-resident server gets the pool its solo run
gets at the same util.

**What a neighbour does is raise the floor under the free-memory precondition**,
which caps how high a *later* server's util may be set. The engine refuses at
startup when free memory is below the requested share, and that refusal is
arithmetic, not chance — one step under the ceiling runs, one step over refuses,
reproducibly.

**Launch them sequentially, each healthy before the next starts.** vLLM profiles
live free memory during init, so two starting together race and one dies on a
util that works alone. This is settled and it is the important half of the
ordering question.

**In compose, sequence on `service_healthy` with a healthcheck, never on
`service_started`.** `service_started` fires when the container runs, not when
the engine has taken its share; the later unit dies on the race and a restart
policy retries it until it sticks, so the pair looks healthy. Read each
container's `RestartCount` — anything above zero is a hidden crash.

**Which order is NOT settled, and this file and the emitter disagree.** This
file has ruled small-first — give the small model its share while the card is
empty, because large-first leaves the second server a budget smaller than the
first already occupies. The emitter sequences largest-first; the case for that
order is that the large unit is the one that cannot recover from measuring a
card a neighbour has already taken a share of. The measurement cited for
largest-first compares *racing* against *sequencing*, not one order against the
other, so it does not settle the direction. **Treat the order as an open ruling; do not
quote either rule as decided.**

**Retry a refusal before believing it** → `okf/must-read/touching-rigs.md`
§ Spending the card. The co-residency driver retries and stamps `tries=` on the
row; the single-server sweep does not, so retry it by hand. A solo floor taken
as a single draw is not a floor.

**How many servers co-reside is arithmetic, then a readback.** Context overhead
per server plus each server's weights against the card; then check every pool
readback — a server whose weights leave less than one request's worth of KV
does not co-reside, whatever the sum says.

**Wait for the card after a teardown.** `docker rm -f` returns before the CUDA
context is released, and the next server profiles live free memory. Read `free`
until it settles before launching.

## Sleep mode

**The sleep routes exist only under `VLLM_SERVER_DEV_MODE=1`, and freeing memory
also needs `--enable-sleep-mode`.** Without the variable `/sleep`, `/wake_up` and
`/is_sleeping` are 404 — that means the routes are off, not that the unit is
awake. With the variable and without the flag the routes still answer. Judge a
sleep by the card's memory dropping, never by the status.

**A `/v1/models` 200 does not decide that a vLLM unit is serving.** The serve
probe also reads `/is_sleeping`, and only an explicit `true` takes the unit out
of service; a 404 there means awake.

**Level 1 parks the weights in host RAM and is refused here.** It needs host RAM
the size of the weights; read available memory after the wake before counting
that RAM as returned.

**Level 2 discards the weights, and `/wake_up` does not bring them back.** The
wake reallocates memory and restores buffers; the weights return only through
`reload_weights`. A fast level-2 wake is an allocation, not a load — check a
woken unit's reply text, never its token rate or its `/v1/models`.

**A sleeper keeps its CUDA context.** Size anything placed beside a sleeper
against the card it actually leaves, read live.

## `VLLM_SERVER_DEV_MODE`

**A measurement switch, never a serving one.** It exposes `/server_info` and the
sleep routes — and `/collective_rpc`, which executes a method inside the engine.
Set it on a bench launch that needs the resolved config; never on a unit
listening on an open interface.

## What actually ran is in the startup log

**One version string is not one instrument.** The same image selects different
attention backends, linear kernels and samplers by compute capability, and
`/server_info` reports the policy asked for (`auto`), not what resolved. Read the
attention backend and the kernel line from the startup log, pin the backend with
`--attention-backend`, and refuse a unit whose log names another. Search the
whole log, and match the fallback sentence as well as the success sentence.

**Make a kernel contrast with `--linear-backend <kernel>` on one checkpoint.**
The engine logs the kernel it chose (`Using <X>LinearKernel for …`); record that
line on every arm. Exllama cannot take an AWQ checkpoint, so a
Marlin-against-Exllama pair needs a GPTQ one.

## `--enforce-eager`

**Off by default and not a safe default.** No compute-capability gate here
forces eager mode — CUDA graphs capture on 7.5 — and forcing it can cost a large
multiple at every width, a single stream included. Measure it before it enters a
config; a comparison that keeps it on both arms for symmetry quotes neither
rig's throughput.

## Compute capability 7.5

AWQ works, Marlin MoE kernels are selected, bfloat16 falls back to float16
automatically, FlashAttention 2 is unavailable and attention falls to another
backend, and the FlashInfer sampler falls back. **None of these blocks a load;
only capacity does.** Native FP8 compute needs 8.9.
→ `okf/must-read/touching-engine.md`
