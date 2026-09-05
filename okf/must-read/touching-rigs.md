# touching-rigs

Any ssh, any launch, any measurement on srv1 or srv2.

## Before

**Prove reachability** → gate 2

**Read the card and RAM, do not assume.** `nvidia-smi
--query-gpu=memory.total,memory.used,memory.reserved,memory.free` and `free -g`.

**Read `used`, and find out whose it is.** A card can be held by a process
→ `nvidia-smi --query-compute-apps=pid,process_name,used_memory`

## Card memory

**A card has four buckets: `total = reserved + used + free`.**

**The reserve is constant within a boot and varies ±3 MiB between boots.** 

## What a context costs

**KV is `kv_bytes` in `src/mcgyvr/serving/vramfit.py` — per layer, over the
layers the header declares as caching, never one width for all of them.** Each
layer's `k_elems`/`v_elems` come from ggufscan, and no scalar survives this
store: deepseek2 reads 4320 MiB at `-c 16384 -np 8` where the 2 KiB-per-token
law says 864. **Multiply by the layers that cache, not by `block_count`.**
Qwen3.6-35B and KAT declare `full_attention_interval = 4` — 10 of 40 layers, so
20.2 KiB/token measured, not the 80 the layer count predicts. Qwen3-Coder-30B
caches every layer: 96.2, against 96.0 predicted. **An undeclared
sliding-window split is refused, not guessed.** gpt-oss-20b declares
`sliding_window = 128` and no per-layer pattern, and an alternating guess is
wrong for two of the three split checkpoints measured. llama.cpp prints a
`llama_kv_cache: size = … (… N layers …)` line for each cache it creates on
startup (under `llama_kv_cache_iswa: creating non-SWA/SWA KV cache`); pass
those rows as `kv_bytes(layers=…)`.
→ `records/evidence/2026-09-05-context-decomposition/srv2-deepseek-coder-v2-16b/c16384-r1.log`

**The non-caching layers charge per slot, and not per token.** Qwen3.6's 30
linear layers each hold `ssm_inner_size 4096 × ssm_state_size 128 × 4 B` =
2 MiB — 60 MiB per `-np` slot, measured across np 1/4/8 at fixed `-c`. Raising
`-c` is cheap on these; raising `-np` is not.

**`--n-cpu-moe N` saturates at the layer count.** ncmoe=99 and ncmoe=40 give
byte-identical VRAM on a 40-layer model. Neither engine offloads KV, ever.

## Host memory bandwidth

Measured 2026-09-01 with a pure sequential read, not STREAM triad. Triad is
2 reads + 1 write and reads lower; decode reads weights and writes almost
nothing, so the pure-read figure is the one that bounds it.
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/{bw.c,bandwidth-2026-09-01.txt}`

**srv1 reads 40.3 GB/s and srv2 reads 27.9. The 16 GB rig has the faster
memory, by 1.44x.** Capacity and bandwidth point in opposite directions across
these two boxes. Never infer one from the other.

**srv1's llama.cpp numbers are only valid against a stated image.** The stock
`server-cuda-b10644` runs emulated tensor-core kernels on TU116 and reads ~1.6x
low in serving and 3.6x low in prefill; `llamacpp:b10644-L3` does not.
`llamacpp:b10644-nomma-dp4a` (the unpatched L2) is retired: it crashes every
MoE model at `np=8` from n=2. Record `img=` on every srv1 row. → gate 3
→ `okf/must-read/touching-engine.md`

**srv1's thread scaling is linear and never saturates — it is CORE-limited, not
DRAM-limited.** 15.7 / 30.7 / 40.2 GB/s at 2 / 4 / 6 threads: ~6.7 GB/s per
core, still climbing when it runs out of cores, against a 57.6 GB/s theoretical
ceiling it never approaches. Consequence: faster or additional DIMMs buy srv1
nothing on the memory term. Cores would.

**srv2 saturates at 10 threads.** 12.7 / 23.3 / 28.0 / 30.3 GB/s at 2 / 4 / 6 /
10, then flat through 16 and 20. `-t 20` is worth nothing over `-t 10` on the
memory term, and the second hyperthread of each core is worth nothing at all.

**srv2's mismatched 16+32 DIMM pair costs nothing measurable (2026-09-01).**
Flex mode interleaves `2 x min(16,32)` = 32 GB dual-channel and appends the
leftover 16 GB single-channel, so a knee was predicted at 32 GB. There is none:
27.9 / 27.8 / 27.6 / 27.9 GB/s at 28 / 32 / 36 / 40 GB. Do not buy matched RAM
for srv2 on bandwidth grounds. Re-measure if the DIMMs move — they have twice.

## Spending the card — find the `--n-cpu-moe` floor before anything else

**`--n-cpu-moe` is bounded by VRAM, not by host RAM.** At srv2's measured floor
the card holds 11,787 of 11,911 usable MiB while host RAM sits nearly idle.
`okf/config/llama.cpp.md` says it "is bounded by host RAM"; that predates this
measurement and is wrong.

**Every archived run of the qwen35moe family sat 3-12x above its real floor.
Correcting that is worth ~2.4x in throughput.** What the floor does to the
model's *output* is unmeasured, and "unmeasured" is not "nothing": `--n-cpu-moe`
is a semantic key until a placement null at that value, on that build, shows it
neutral (ADR-0041; measured 2026-09-02 on srv1, `ncmoe` 0 vs 99 flipped 9 of
257 verdicts against a 0-flip own null). Quote a floor for fit and speed only.
srv2, Qwen3.6-35B-A3B UD-IQ3_XXS, `np=8 ctx_slot=2048`, 2026-09-01:

| ncmoe | n=1 | n=4 | n=8 | vram MiB |
|---|---|---|---|---|
| 0 | REFUSED | | | |
| **6** ← floor | **43.4** | **69.3** | **73.1** | 11,787 |
| 8 | 37.9 | 57.1 | 60.7 | 11,263 |
| 12 | 30.7 | 52.8 | 54.7 | 10,215 |
| 24 *(archived)* | *28.6* | *34.8* | | |
| 99 *(archived)* | *21.0* | *29.8* | *30.0* | 2,803 |

KAT-Coder-V2.5-Dev Q2_K floors at 7 (0 and 4 refuse): 47.2 / 70.3 / 71.2.
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/srv2-ncmoe-floor.tsv`

**Derive the floor, then walk down to it. Do not guess and do not copy a
neighbour's value.** The budget is `free VRAM − scratch and context −
non-expert weights − KV − slot state`, where the CUDA context measured 85–147
MiB and not 1.0 GB and is folded, with the compute buffer, into
`SCRATCH_AND_CONTEXT_MIB = 768` in `src/mcgyvr/serving/vramfit.py`; what
remains, over total expert bytes, is the resident fraction, and `(1 − fraction)
× n_layers` is the floor. Both weight terms come from the tensor table, never
from the file size.
→ `src/mcgyvr/serving/ggufscan.py`

**Take the VRAM term from `free`, never from `total − reserve`.** The two
agree only on an idle card, and the wrong one places experts on a card with no
room for them. Read it after the previous cell tears down — the only moment
that shows what the next launch actually gets.

**The refusal is the measurement.** Run one cell below the predicted floor on
purpose — it names the true edge. Retry any refusal three times before believing
it; a launch near the memory edge is a 1-in-3 coin flip.

## srv1 hard-locks under CPU expert offload

**The BIOS power cap is not the fix.** `74798187` records PL1 95 W / PL2 120 W
as what stops it. srv1 froze three more times on 2026-09-01 — 20:45, 21:35 and
05:37 — and 05:37 happened with that cap in force. Not model-specific
(Qwen3-Coder-30B Q2_K, gpt-oss-20b), not depth-specific (ncmoe=99, ncmoe=18).
Each boot ends mid-log-stream: no OOM, no Xid, no MCE, no shutdown record.

**A hard lock can wipe the BIOS profile, power limits included.** srv1 read
PL1 95 W at 05:23 and 4095 W at 05:57 with nobody having touched it.

**One clean 12-minute offload run is not an all-clear.** 2026-09-01 10:29–10:41:
Qwen3.6-35B at ncmoe 99/40/32, three model loads, eight measured rows, no lock;
PL1 read 95 W at both ends and uptime stayed unbroken. The three locks were
spread across a longer campaign (20:45, 21:35, 05:37), so this bounds nothing —
record it as a run that did not reproduce, not as a fix. Stamp PL1/PL2 into the
start and end markers and `tee` rows on the rig, because a lock takes the ssh
pipe with it. → `records/evidence/2026-09-01-prompt-realism/srv1-q36-rerun.tsv`

**Read `constraint_0_power_limit_uw`, not `constraint_0_max_power_uw`.** The
latter is the CPU's rated TDP and reads `95000000` whatever the live limit is.
It looks exactly like the cap being in force when it is not.

**PL1/PL2 and the ring ratio are held from the OS on srv1, not from BIOS.**
`srv1-cpu-limits.service` writes MSR 0x610 and 0x620 every boot — PL1 95 W,
PL2 120 W, ring 4100 MHz. Source at `/usr/local/sbin/srv1-cpu-limits`, on that
box only. A BIOS value for either loses to it after boot.


**Status 2026-09-01: a 60-minute soak at 26% host-RAM occupancy did not lock.**
Ling-3.0-tiny Q4_K_M at `--n-cpu-moe 99 --parallel 8`, 26 consecutive passes,
3,660 s. `uptime -s`, PL1 95 W / PL2 120 W and memclk 3600 MT/s were identical
at both ends, and throughput was flat at 53.1–55.0 tok/s agg at n=8. Prior kills
landed at 61–150 s, so this is a strong negative — but it is **not** a clearance
of the memory overclock. Ling streams 262 MB of expert weight per token against
the killer config's 724 MB. It rules out "3600 MT/s is marginal under sustained
load"; it does not rule out "3600 MT/s is marginal under peak bandwidth".
→ `records/evidence/2026-09-01-bandwidth-and-ncmoe-floor/srv1-locktest-ling-60min.tsv`

**The run that separates footprint from stream rate has not been done.**
Footprint and bytes-per-token move together in both configs tested so far. One
checkpoint breaks the coupling: **Qwen3.6-35B-A3B UD-IQ3_XXS at `ncmoe=99`**
puts 10.35 GiB of experts in host RAM — 69% of srv1's 15 GB, the highest of
anything on disk — at only 331 MB/token. Locks → capacity is the cause.
Survives → bandwidth pressure is, and the 3600 MT/s overclock returns as prime
suspect.

| | low stream | high stream |
|---|---|---|
| 26% of RAM | Ling-3.0-tiny — **survived 61 min** | — |
| 50% of RAM | — | deepseek-coder-v2-16b — **killed 6x** |
| 69% of RAM | **Qwen3.6-35B — the outstanding test** | — |

**A placement specified before a hardware swap may no longer be launchable.**
`ncmoe=99` here needs the experts plus ~1.5 GiB of runtime residency, which
clears srv1's RAM but fails the 2 GB mmap headroom, so the serving gate refuses
it. Re-derive against the rig as it is now, or run it outside the gate with the
headroom stated on purpose. A lower placement is not a substitute: it moves the
footprint into a band already tested.

**Two facts that constrain any diagnosis.** srv1's DIMMs are non-ECC
(`EDAC ie31200: No ECC support`), so memory errors are silent and no counter can
ever show them — a clean `ce_count` proves nothing. And no package changed
between 08-26 and 08-31: kernel 7.0.0-30, driver 580.173.02 and microcode 0x104
are identical across the onset, so software is excluded.

## After — always

**Kill what you started** → gate 7 An uncleaned container held srv1
at zero free RAM for eight minutes. `docker ps` → `docker kill` 

## Resume and the journal

**`--resume` keys on `(host, label)` joined by NUL, and nothing else** — not
backend, not model id, not config digest. → `run.py:152`, `run.py:388`

**`--retry-failed` keeps only rows whose outcome is exactly `"ok"`.** Everything
else is re-measured. Without it, **`refused` counts as done** and a plain
`--resume` skips those cells forever while reporting the run finished.
→ `run.py:157`, `run.py:133-135`

**`--retry-failed` alone does nothing** — `completed()` is only called when
`--resume` is passed, and nothing refuses the lone flag. → `run.py:932`

**The journal is append-only and last-write-wins.** The barren downgrade mutates
the row before it is written; it never rewrites an existing row. → `run.py:93`

**Never delete a journal row to force a re-measure.** It turned the tree green
over five outstanding cells and destroyed nothing only by luck. Fix
`completed()` to re-score instead:
```python
if retry_failed:
    rows = {
        k: v
        for k, v in rows.items()
        if v.get("outcome") == "ok" and not barren_levels(v.get("concurrency") or {})
    }
```

## Config

**Eleven entry keys are accepted; any other non-`_` key raises.** `_`-prefixed
keys are documentation and ignored on purpose. → `run.py:300-322`

**The top-level document is not validated** — a misspelled `hosts`/`models`/
`collect` is silently ignored. So is a typo inside `serve`.

**Every vLLM entry needs a measured `_footprint_mib`**, or `weights_bytes` for
the predicted branch; without either the cell is refused.
→ `tests/test_serving_memory_declaration.py:107`, `vllm.py:1336`
