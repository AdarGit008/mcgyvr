# config — llama.cpp

Engine: `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481`.

## `--parallel` / `-np`

**Defaults to 4 slots.** Left at the default, n=8 runs as two batches of 4 and
produces a plateau indistinguishable from saturation. Every config sets 8.

**It is read back.** `/props total_slots` states the width the server actually
came up at; `claim()` refuses if `/props` does not answer it, and refuses if the
readback is below the widest level. Recorded with `provenance: "observed"`.
→ `llamacpp.py:698-715`

Two caveats: the check compares the readback to `max(levels)`, **not** to the
declared width, under a message that says `--parallel {width}` — an engine that
silently reduced 16 to 8 passes whenever the ladder tops out at 8. And the
console summary never prints it (`run.py` reads `declared["value"]`, this
backend returns `slots`), so it is only visible in the JSON.

## `-c` (context)

**Total, and it divides across slots** — but only when `-np` is passed.
`-c 4096 --parallel 8` gives 512 tokens/slot against a 475-token completion.

**Floor is 987 tokens/slot** = `RAMP_TOKENS 475 + PROMPT_HEADROOM_TOKENS 512`.
All entries declare 1024 and read 1024 back off `/props`.
→ `llamacpp.py:163`

## `--n-cpu-moe N`

Keeps attention and shared layers on the card, puts the experts of N layers in
host RAM. This is what lets a 30B MoE serve from a 6 GB card.

**It is bounded by VRAM, not by host RAM.** Corrected 2026-09-01: at srv2's
measured floor the card holds 11,787 of 11,911 usable MiB while host RAM sits
nearly idle. This entry previously said "bounded by host RAM"; that was written
before the floor was ever measured directly, and the artifacts it cited already
said VRAM (srv1's `--n-cpu-moe 36` refusal reads "6 GB card **full**").
→ `okf/must-read/touching-rigs.md` for the budget arithmetic and the ladder

Measured floors, 2026-09-01, `np=8 ctx_slot=2048`, on today's hardware:

| rig | checkpoint | floor | at the floor |
|---|---|---|---|
| srv2 | Qwen3.6-35B-A3B UD-IQ3_XXS | **6** (0 refuses) | 43.4 / 69.3 / 73.1 at n=1/4/8, vram 11,787 MiB |
| srv2 | KAT-Coder-V2.5-Dev Q2_K | **7** (0 and 4 refuse) | 47.2 / 70.3 / 71.2, vram 11,417 MiB |

→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/srv2-ncmoe-floor.tsv`

Lower N = more on card = faster, until it refuses. The gradient is steep and
monotonic: 6 → 8 → 12 gives 43.4 → 37.9 → 30.7 at n=1. **Walk down to the floor;
do not settle above it.** Every archived run of this architecture sat at 24-99,
i.e. 3-12x above its real floor, which cost ~2.4x at n=8.

A floor is a fit-and-throughput number and says nothing about output.
`--n-cpu-moe` is a semantic key: two cells of one model at two `ncmoe` values
are not comparable on output until a placement null on that build shows the
key neutral, and the one null measured so far (srv1, 2026-09-02, 0 vs 99)
showed it is not. → ADR-0041, `okf/must-read/touching-rigs.md`

The older floors (2026-08-25, Qwen3-Coder-30B Q4_K_M: srv1 below 40, srv2 below
20) were measured when the two rigs held each other's RAM and are not comparable
to the current hardware. They are also per-checkpoint: the floor is a function of
expert bytes and KV, so it must be re-derived for every model.
→ `records/evidence/2026-08-25-moe-expert-offload/`

**CPU offload is what flattens the scaling curve, not MoE.** `m_ling` — a MoE
small enough to stay resident on srv1's card — scales 2.27x like a dense model,
while offloaded cells run 1.11–1.74x.

## `-nkvo` / `--no-kv-offload`

**KV offload to the GPU is ENABLED by default** — read the direction carefully.
The KV cache normally lives in VRAM. `-nkvo` moves it to host RAM: buys VRAM,
costs PCIe traffic per token. Untested here.

`-ctk` / `-ctv` set the KV dtype (q8_0, q4_0) and shrink it in place instead.

## `--no-mmap`

**Host-dependent, and the sign flips.** On a RAM-tight host it stops the model
paging continuously from NVMe; on a roomy one the copy costs.
Measured 2026-08-25: **+63% on the 16 GB rig, −12% on the 48 GB rig.**
Which rig is which has since swapped — re-measure, do not copy the flag over.

## `--n-gpu-layers` / `-ngl`

All entries use 99 (everything the card will take). Placement is then decided by
`--n-cpu-moe`, not by this.
