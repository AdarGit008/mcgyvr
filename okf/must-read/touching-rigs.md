# touching-rigs

Any ssh, any launch, any measurement on srv1 or srv2.

## Before

**Prove reachability**

**Read the card and RAM, do not assume.** `nvidia-smi
--query-gpu=memory.total,memory.used,memory.reserved,memory.free` and `free -g`.

## Card memory

**A card has four buckets: `total = reserved + used + free`.** The reserve is
GSP firmware and CUDA cannot see it — PyTorch calls srv1's 6,144 MiB card
5.61 GiB. Weigh against total-less-reserve.

**The reserve is constant within a boot and varies ±3 MiB between boots.** It
does not track card load: 475 samples while the card swept 17 → 5,330 MiB were
all 401 MiB. Pinned at 401/380; srv1 has read 399 on another boot, srv2 reads 377.

## What a context costs

**KV is 2 KiB per token per attention layer at f16, on every MoE checkpoint
measured.** `2 × n_kv_heads × head_dim × 2 B` lands on 2048 for head counts of
2, 4 and 8 alike. **Multiply by the layers that cache, not by `block_count`.**
Qwen3.6-35B and KAT declare `full_attention_interval = 4` — 10 of 40 layers, so
20.2 KiB/token measured, not the 80 the layer count predicts. gpt-oss-20b
declares `sliding_window = 128` on alternating layers: 28.0. Qwen3-Coder-30B
caches every layer: 96.2, against 96.0 predicted.

**The non-caching layers charge per slot, and not per token.** Qwen3.6's 30
linear layers each hold `ssm_inner_size 4096 × ssm_state_size 128 × 4 B` =
2 MiB — 60 MiB per `-np` slot, measured across np 1/4/8 at fixed `-c`. Raising
`-c` is cheap on these; raising `-np` is not.

**`--n-cpu-moe N` saturates at the layer count.** ncmoe=99 and ncmoe=40 give
byte-identical VRAM on a 40-layer model. Neither engine offloads KV, ever.

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

## After — always

**Kill what you started** An uncleaned container held srv1
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
    rows = {k: v for k, v in rows.items()
            if v.get("outcome") == "ok"
            and not barren_levels(v.get("concurrency") or {})}
```

## Config

**Eleven entry keys are accepted; any other non-`_` key raises.** `_`-prefixed
keys are documentation and ignored on purpose. → `run.py:300-322`

**The top-level document is not validated** — a misspelled `hosts`/`models`/
`collect` is silently ignored. So is a typo inside `serve`.

**Every vLLM entry needs a measured `_footprint_mib`**, or `weights_bytes` for
the predicted branch; without either the cell is refused.
→ `tests/test_serving_memory_declaration.py:107`, `vllm.py:1336`
