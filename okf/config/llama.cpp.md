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

**It is bounded by host RAM.**

Measured floors (2026-08-25, Qwen3-Coder-30B Q4_K_M): srv1 refused below 40,
srv2 below 20. Lower N = more on card = faster, until it refuses.
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
