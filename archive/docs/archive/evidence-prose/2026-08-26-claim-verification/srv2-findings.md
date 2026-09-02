# srv2 crew — verification findings (2026-08-25)

Rig: `srv2` (100.69.72.51), reached over Tailscale ssh. All work non-destructive.

## Pre-existing host state, recorded before any change

```bash
ssh srv2 'systemctl is-active ollama; systemctl is-enabled ollama; systemctl show ollama -p Environment'
```
```
inactive
enabled
Environment=... OLLAMA_NUM_PARALLEL=0 OLLAMA_MAX_LOADED_MODELS=0 OLLAMA_KEEP_ALIVE=-1 OLLAMA_HOST=0.0.0.0:11434
```
ollama was **inactive** on arrival and was left inactive. No unit files, drop-ins,
governor/turbo/RAPL settings were touched.

A container was already running and holding 11,882 MiB of the 12,288 MiB card:

```bash
ssh srv2 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"; docker inspect llama-sweep --format "{{.State.StartedAt}}"'
```
```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","4","-t","10","-c","4096","-fa","on","--no-mmap","--host","0.0.0.0","--port","8080"]
2026-08-25T16:40:57.846250558Z
```
mounts `/usr/share/ollama/.ollama/models/blobs:/blobs`, `/home/adaramir/ggufs:/models`, port 8080.
It was **stopped (`docker stop`, not removed)** to free the card, and **restarted at the
end of this session** — see the closing section.

---
### H2 — [V] verified
**Claim:** srv2 is an RTX 3060, 12288 MiB, cc 8.6, driver 595.84, 16 GB RAM dual-channel (post-swap).
**Verdict:** Exact on every field. 2 x 8 GB DDR4-2667 in ChannelA-DIMM0 and ChannelB-DIMM0 = dual channel, 16 GB.
**Evidence:**
```bash
ssh srv2 'nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv; free -g; sudo dmidecode -t memory | grep -E "Size|Locator|Configured Memory Speed"'
```
```
NVIDIA GeForce RTX 3060, 12288 MiB, 8.6, 595.84
Mem: total 15 (GiB, i.e. 16 GB)
Size: 8 GB   Locator: ChannelA-DIMM0   Configured Memory Speed: 2667 MT/s
Size: No Module Installed  Locator: ChannelA-DIMM1
Size: 8 GB   Locator: ChannelB-DIMM0   Configured Memory Speed: 2667 MT/s
Size: No Module Installed  Locator: ChannelB-DIMM1
```
CPU is an i9-10900F, 20 threads, max 5200 MHz.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/srv2-sysinfo.txt`

### H3 (srv2 arm) — [V] verified
**Claim:** srv2 holds llama.cpp server-cuda-b10481 = sha256:b2497f88... and vllm/vllm-openai:v0.26.0 = sha256:ffb2d59b...
**Verdict:** Both digests match to the character on srv2. (The "both rigs identical" half is the srv1 crew's.)
**Evidence:**
```bash
ssh srv2 'docker images --digests'
```
```
ghcr.io/ggml-org/llama.cpp  server-cuda-b10481  sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce
vllm/vllm-openai            v0.26.0             sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52
```
Note `vllm/vllm-openai:latest` on srv2 carries the *same* digest as `:v0.26.0`, so a
cell that said `:latest` is not distinguishable from `:v0.26.0` on this host today.
**Bears on:** `records/evidence/2026-08-24-engine-sweep/README.md`

### H5 (srv2 arm) — [V] verified, with a thread-count caveat
**Claim:** STREAM triad srv2 23.8 GB/s post-swap.
**Verdict:** 24.3 GB/s best-of at 4 threads — within 2% of the recorded 23.8. But the
figure is **thread-count dependent** and the record does not state the thread count:
24.3 (t=4) / 23.0 (t=8) / 22.2 (t=10) / 20.3-21.1 (t=20). Reading it at the host's full
20 threads gives 20.3, which is 15% below the recorded number. The claim is verified
against the best-of reading; the record should pin `OMP_NUM_THREADS`.
**Evidence:**
```bash
scp records/evidence/2026-08-25-moe-expert-offload/drivers/triad.c srv2:/tmp/
ssh srv2 'gcc -O2 -fopenmp -o /tmp/triad /tmp/triad.c && for t in 4 8 10 20; do OMP_NUM_THREADS=$t /tmp/triad 3.0; done'
```
```
STREAM triad: 24.3 GB/s  (threads=4,  best=0.0247 s, checksum=3.500)
STREAM triad: 23.0 GB/s  (threads=8,  best=0.0261 s, checksum=3.500)
STREAM triad: 22.2 GB/s  (threads=10, best=0.0271 s, checksum=3.500)
STREAM triad: 20.3 GB/s  (threads=20, best=0.0295 s, checksum=3.500)
```
Measured with the campaign's own driver, unmodified. The checksum line confirms the loop
was not elided. Also confirms the memory swap is still in place (13.3 GB/s was the
pre-swap single-channel figure; nothing here is near it).
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:10`

### L1 (bonus, srv1 crew's claim — confirmed on srv2) and a correction to L2
**Claim (L1):** b10481's default slot count is 4.
**Verdict:** Confirmed on srv2. **But** the pre-existing default-`-np` server reports
`n_ctx_slot = 4096` at `-c 4096`, not 1024, because with no explicit `-np` the build
runs a **unified** KV cache (`kv_unified = 'true'`). Every cell in the record's own
`np-semantics-probe.txt` passed `-np` explicitly and got `kv_unified = 'false'`, which
is the regime where `-c` divides. So L2's "-c is a TOTAL divided across slots" holds
**only when `-np` is given explicitly**; the default 4 slots share one unified 4096-token
cache instead. This is a real qualification on L2, not a refutation.
**Evidence:**
```bash
ssh srv2 'docker logs llama-sweep 2>&1 | grep -i n_ctx_slot'
```
```
load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
```
against the record's probe, every row of which has an explicit `-np`:
```
srv1	np=4	c=4096	slots=4	ctx_slot=1024	kv_unified = 'false'
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/np-semantics-probe.txt`


### H4 (srv2 arm) — [V] verified
**Claim:** Weights byte-identical across rigs: 35B-A3B IQ3_XXS `9c964e657212fea1...`,
7B IQ4_XS `f7eff217195ff980...`, qwen3-coder-30b Q4_K_M `1194192cf2a187eb...` (18,556,688,736 B).
**Verdict:** All three prefixes reproduce on srv2, and the 30B blob's size is exactly
18,556,688,736 B. (Byte-identity *across* rigs needs the srv1 crew's half; srv2's side is exact.)
**Evidence:**
```bash
ssh srv2 'sha256sum /home/adaramir/ggufs/*.gguf /usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a
          stat -c "%s %n" /usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb... /home/adaramir/ggufs/*.gguf'
```
```
f7eff217195ff98092353ab2a101882e5a756513d6080d6fdd6bcae2f21831ac  Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf
9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe  Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a  .../blobs/sha256-1194192cf2a187eb...
18556688736 /usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb...
 4218473248 /home/adaramir/ggufs/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf
13211155424 /home/adaramir/ggufs/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md` ("The two winners" table)

### V1 (srv2 arm) — [P] partial: direction and order of magnitude verified, the 5.02x figure is not, and its cited numbers are miscited
**Claim:** `--enforce-eager` costs srv2 5.02x (2,601.7 vs 518.2 agg; 181.7 vs 36.2 at n=1).
**Verdict:** Re-running both sides today: **3.83x** on the aggregate pair (2,699.9 vs 704.4 at
n=16) and **4.95x** at n=1 (213.7 vs 43.2). The **no-eager side reproduces** (2,699.9 vs the
record's 2,601.7, +3.8%); the **eager side does not** (704.4 vs 518.2, **+36%**). So the flag is
real and expensive on srv2 — but "5.02x" is not what a re-run gets, and the honest reading from
today's pass is **~4x**.

Separately, **both numbers V1 quotes are misattributed inside the record's own files**:
- `518.2` is the **`perf-interactivity`** cell (`--enforce-eager --performance-mode interactivity`),
  not the baseline. The baseline eager cell reads **530.1**. The README's headline row
  ("as every prior run in this tree configured it | 518.2") names the wrong cell, which flatters
  the ratio: 2601.7/530.1 = **4.91x**, not 5.02x.
- `181.7` is the n=1 reading of the **`s2-noeager-kvfp8-len1024-seqs256`** cell, not of the
  no-eager baseline (which reads **197.1**). `36.2` does not occur at n=1 in any srv2 1.5B cell
  (nearest are 36.3 `kv-fp8_e5m2` and 36.4 `no-prefix-caching`; the baseline is **34.2**).
  So "181.7 vs 36.2 at n=1" is not an eager/no-eager pair — it crosses three axes.
  The controlled n=1 pair from the record's own data is 197.1 / 34.2 = **5.76x**.
**Evidence:**
```bash
# both cells, same driver, same host, back to back
ssh srv2 'python3 /tmp/vcells.py \
  "eager-baseline|--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16 --enforce-eager|1,8,16" \
  "noeager-baseline|--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16|1,8,16"'
```
```
srv2  eager-baseline    LAUNCH ok start_s=78.0 vram=10219
eager-baseline   n=1   43.2    p50=11.00  cap_frac=1.00
eager-baseline   n=8   357.3   p50=10.63  cap_frac=1.00
eager-baseline   n=16  704.4   p50=10.79  cap_frac=1.00
srv2  noeager-baseline  LAUNCH ok start_s=94.4 vram=9959
noeager-baseline n=1   213.7   p50=2.22   cap_frac=1.00
noeager-baseline n=8   1544.1  p50=2.46   cap_frac=1.00
noeager-baseline n=16  2699.9  p50=2.81   cap_frac=1.00
```
`cap_frac=1.00` at every level: every request produced the full 475 tokens, so no level is a
short-reply artefact. The no-eager server's own log confirms graph capture happens on this card
(cc 8.6), which is the mechanism V2 asserts:
```
ssh srv2 'docker logs verify-vllm 2>&1 | grep -i "Graph capturing"'
Capturing CUDA graphs (PIECEWISE): 100%|...| 7/7
Capturing CUDA graphs (FULL): 100%|...| 5/5
Graph capturing finished in 1 secs, took 0.07 GiB
```
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:19` and `:69-70`;
cell data in `records/evidence/2026-08-24-config-sweep/srv2-1.5B.jsonl`

### V5 — [V] verified
**Claim:** srv2's best vLLM cell is no-eager + `--max-model-len 1024` + `--max-num-seqs 256` +
`--kv-cache-dtype fp8` = 6,445.1 agg tok/s at n=256.
**Verdict:** Reproduces and slightly exceeds: **6,600.6** and **6,602.5** on two independent
loads today, +2.4% over the recorded 6,445.1. The named cell is confirmed as the best cell
tested (it beats the same cell without fp8 by 5.4%).
**Evidence:**
```bash
ssh srv2 'python3 /tmp/vcells.py "best-fp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256"'
```
```
srv2  best-fp8  LAUNCH ok start_s=... vram=11805
best-fp8   n=1    202.0   p50=2.35   cap_frac=1.00
best-fp8   n=16   2808.2  p50=2.70   cap_frac=1.00
best-fp8   n=256  6600.6  p50=18.36  cap_frac=1.00
```
`cap_frac=1.00` at n=256: all 256 requests returned the full 475 tokens.
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:19` (headline table),
`srv2-1.5B-stage2.jsonl` cell `s2-noeager-kvfp8-len1024-seqs256`

### V14 — [V] verified, and strengthened
**Claim:** Four independent takes of srv2's best 1.5B cell agree within +/-1.8%
(6,445.1 / 6,452.2 / 6,480.6 / 6,562.0).
**Verdict:** The four recorded takes do lie within +/-1.8% of their mean (6,485.0; band
6,368-6,602). Two further independent takes today — separate container loads, cold each time —
read **6,600.6** and **6,602.5**. All **six** takes now span 6,445.1-6,602.5, i.e. within
**+/-1.21%** of the midpoint 6,523.8. The claim holds and the band is tighter than stated.
**Evidence:**
```bash
# two separate loads of the identical cell in one run of the driver
ssh srv2 'python3 /tmp/vcells.py \
  "best-fp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256" \
  "best-nofp8|...|1,16,256" \
  "best-fp8-take2|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256"'
```
```
best-fp8        n=1 202.0  n=16 2808.2  n=256 6600.6
best-fp8-take2  n=1 202.4  n=16 2815.7  n=256 6602.5
```
The two takes differ by **0.03%** at n=256, 0.20% at n=1 and 0.27% at n=16.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` §5

### M5 (srv2 arm) — [V] verified for vLLM
**Claim:** srv2 repeats within 0.2%.
**Verdict:** Two independently loaded takes of the identical vLLM cell differ by **0.03%**
at n=256 (6,600.6 vs 6,602.5), 0.27% at n=16, 0.20% at n=1. The 0.2% figure is right for the
aggregate at high concurrency; at low n the spread is at the stated bound rather than inside it.
Note this is *repeatability of a reload*, which is the stronger form.
**Evidence:** the `best-fp8` / `best-fp8-take2` pair above (separate `docker run`, cold start
each, ~93 s launch each).
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` ("Bounds on all of the above")

### V6 — [P] partial: the n=256 win reproduces, "does nothing at n=16" does not
**Claim:** fp8 KV does nothing at n=16 (558, indistinguishable from baseline) and wins at n=256
(6,445 vs 6,088): it halves bytes per token rather than speeding a kernel up.
**Verdict:** The **n=256 half is verified**: fp8 6,600.6 against no-fp8 6,261.7 in an otherwise
identical cell, **+5.4%** — the record's +5.9% (6,445.1/6,087.7). The **n=16 half is not**. In a
properly controlled pair (same `--max-model-len 1024 --max-num-seqs 256`, fp8 the only
difference) fp8 reads **2,808.2 against 2,698.8 at n=16 — +4.1%**, which is 20x srv2's 0.2%
repeat spread and so is not "indistinguishable".

The record's own "558 at n=16" is not a controlled comparison either: 558.0 is the
**`kv-fp8`** cell of stage 1, which carries `--enforce-eager --max-model-len 8192
--max-num-seqs 16`, against a baseline of 530.1 in the same family — itself +5.3%, not nothing.
So the mechanism sentence ("halves bytes per token rather than speeding a kernel up") is not
supported by either the record's numbers or mine: fp8 gains ~4-5% at concurrencies where KV is
demonstrably not the binding constraint (1,024-token ceiling, 16 sequences).
**Evidence:**
```bash
ssh srv2 'python3 /tmp/vcells.py \
  "best-fp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256 --kv-cache-dtype fp8|1,16,256" \
  "best-nofp8|--gpu-memory-utilization 0.85 --max-model-len 1024 --max-num-seqs 256|1,16,256"'
```
```
best-fp8    n=1 202.0  n=16 2808.2  n=256 6600.6   (vram 11805)
best-nofp8  n=1 217.9  n=16 2698.8  n=256 6261.7   (vram 11085)
```
Note the sign flips at n=1: no-fp8 is **faster** single-stream (217.9 vs 202.0, +7.9%), which is
consistent with fp8 costing a conversion in the decode kernel and only paying back once KV
capacity binds.
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:78-84`

### V13 — [P] partial: the 1.5B half verified, the 7B half untested
**Claim:** vLLM reproduces across srv2's 32GB->16GB RAM change (6,562.0 vs 6,445.1/6,452.2/6,480.6;
1,617.2 vs 1,604.7): a model resident on the card never touches system RAM in the decode path.
**Verdict:** The 1.5B half is verified twice over on the post-swap 16 GB host — 6,600.6 and
6,602.5, inside the pre-swap band. The 7B half (1,617.2 vs 1,604.7) was **not re-run**: it
needs a separate ~4 min model load and the budget went to V1/V5/V6 and the llama.cpp contrasts.
The mechanism is independently supported here: at `--gpu-memory-utilization 0.85` the engine's
own startup line accounts for **all** of weights, activation and KV on the device
(1.1 GiB weights + 0.45 GiB activation + 8.29 GiB KV), with nothing host-resident in the
decode path.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` §5

### V12 — [ ] untested
**Claim:** Speculative decoding (n-gram) loses at every concurrency tested.
**Would need:** two more vLLM loads (`--speculative-config '{"method":"ngram",...}'` at
`--max-num-seqs 16` and at 256) at ~95 s launch + ~40 s bench each. Not run inside the 60 min
srv2 budget; the section-2 claims were prioritised as instructed.

### L11 (srv2 arm) — [V] verified
**Claim:** srv2, 35B-A3B IQ3_XXS, `--n-cpu-moe 25`, `-c = np x 1024`: 44.9 tok/s at np=1 rises to
254.5 at np=32/n=32 (5.67x); p50 59.7 s at np32/n32.
**Verdict:** Reproduces. **44.5 agg (45.34 decode) at np=1 -> 235.3 at np=32/n=32 = 5.29x**,
p50 **64.59 s**. VRAM matches the record to the MiB: **6,069** at np=1 and **8,635** at np=32.
The 5.29x/5.67x difference is inside this cell's own run-to-run spread (see M5 below, 5.2%),
so this is the same result, not a smaller one. `truncated=0/32` — every slot returned all 475
tokens, so the width sweep is not starving slots (the trap the record names).
**Evidence:**
```bash
ssh srv2 'python3 /tmp/lcells.py \
  "L11-np1|/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf|-ngl 99 -np 1 -c 1024 --n-cpu-moe 25 -fa on|1" \
  "L11-np32|/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf|-ngl 99 -np 32 -c 32768 --n-cpu-moe 25 -fa on|32"'
```
```
L11-np1   CONFIG  vram=6069  slots=1   ctx_slot=1024  kv_unified=false
L11-np1   n=1   agg=44.5   decode_tok_s_p50=45.34  p50_lat=10.68  ttft_p50=0.17  truncated=0/1
L11-np32  CONFIG  vram=8635  slots=32  ctx_slot=1024  kv_unified=false
L11-np32  n=32  agg=235.3  decode_tok_s_p50=7.67   p50_lat=64.59  ttft_p50=2.77  truncated=0/32
```
`-c = np x ctx_slot` was set as the record requires, and the server confirms `ctx_slot=1024`
in both cells, so the two rows differ only in width.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md` §1

### M3 — [V] verified
**Claim:** "Expert offload does not batch" is a statement about `-np 4`, not about expert offload:
at 32 slots a comparable MoE reaches 5.67x rather than 2.06x.
**Verdict:** Verified by the L11 pair above — the same model and `--n-cpu-moe` at 32 slots
batches **5.29x** (44.5 -> 235.3). The correction the record issued to its own §5 stands: the
2.06x figure is a property of llama.cpp's default slot count, not of expert offload. Latency
moves with it rather than being traded away (p50 64.6 s at np32/n32 for 32 replies, against
10.7 s for one reply at np=1 — 32x the work for 6x the wall).
**Evidence:** as L11.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` ("CORRECTION — the offload
rows measured a default, not a property")

### L6 (srv2 arm) — [F] FALSIFIED
**Claim:** `--no-mmap` is +63% on srv2 (16 GB host).
**Verdict:** **Not reproduced, and not by a small margin.** At the record's own cell
(`qwen3-coder-30b` Q4_K_M, `--n-cpu-moe 20`, `-t 10`, `-c 4096`, `-fa on`), `--no-mmap` is worth
**+2.1% on a cold page cache** and **+5.0% warm** — against the claimed +63%.

| cell | decode tok/s | record |
|---|---|---|
| `--no-mmap` | **44.82** | 42.86 / 44.82 (matches exactly) |
| mmap, warm page cache | **42.68** | — |
| mmap, **page cache dropped** (`echo 3 > drop_caches`, `free` shows 14 GB free) | **43.91** | **26.28** |

The **`--no-mmap` side reproduces to the second decimal** (44.82 against the record's own 44.82),
so the instrument agrees with the record; it is the **mmap side that does not**. The record's
26.28 is 40% below what the same argv produces today on a demonstrably cold cache.

**Why the record's mechanism does not apply at this cell.** `--n-cpu-moe 20` puts 11,283 MiB of
the 18.56 GB model on the card, leaving only ~7 GB host-side — which fits in 15.4 GB of RAM with
room to spare, so the mapping has no reason to thrash. The record's measured mechanism
("821 MB/s of sustained NVMe reads during decode, free=207 MB, page cache pinned at maximum")
describes a host with almost no free memory; that is the regime at *high* `--n-cpu-moe`, not at
20. The +63% is most likely a property of whatever else held srv2's RAM when that row was taken,
not of the flag — which is the same class of confound as the invalid `docker --memory=15g` cell
the record itself retracts (claim M8).

**What survives:** `--no-mmap` is still the better flag on srv2 at this cell, and the sign is
still opposite to srv1's. The **magnitude** does not survive. Any rung that prices `--no-mmap` at
+63% on a 16 GB host will be wrong by a factor of ~12.
**Evidence:**
```bash
# warm pair, back to back in one driver run
ssh srv2 'python3 /tmp/lcells.py \
  "L6-nommap|/blobs/sha256-1194192cf2a187eb...|-ngl 99 -np 1 -c 4096 --n-cpu-moe 20 -t 10 -fa on --no-mmap|1" \
  "L6-mmap|/blobs/sha256-1194192cf2a187eb...|-ngl 99 -np 1 -c 4096 --n-cpu-moe 20 -t 10 -fa on|1"'
# then the decisive cold-cache arm
ssh srv2 'sync; sudo sh -c "echo 3 > /proc/sys/vm/drop_caches"; free -g; \
  python3 /tmp/lcells.py "L6-mmap-coldcache|/blobs/sha256-1194192cf2a187eb...|-ngl 99 -np 1 -c 4096 --n-cpu-moe 20 -t 10 -fa on|1"'
```
```
L6-nommap          CONFIG load_s=23.6 vram=11297
L6-nommap          n=1 agg=44.4 decode_tok_s_p50=44.82 ttft_p50=0.10 truncated=0/1
L6-mmap            CONFIG load_s=18.8 vram=11283
L6-mmap            n=1 agg=41.7 decode_tok_s_p50=42.68 ttft_p50=0.22 truncated=0/1

              total  used  free  shared  buff/cache  available
Mem:             15     0    14       0           0          14      <- cache dropped
L6-mmap-coldcache  CONFIG load_s=21.1 vram=11283
L6-mmap-coldcache  n=1 agg=43.2 decode_tok_s_p50=43.91 ttft_p50=0.12 truncated=0/1
```
`drop_caches` is a transient kernel action, not a persistent host setting; nothing was left changed.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` §3 and
`raw-postswap-squeeze-concurrency.txt:32`; and the CORRECTION §3 in
`records/measurements/serving-sweep-2026-08-25/README.md`, which rests on this figure.

### M5 (srv2 arm) — [F] FALSIFIED for llama.cpp (verified for vLLM, see above)
**Claim:** srv2 repeats within 0.2%.
**Verdict:** True of vLLM (0.03% at n=256 across two cold loads) and **false of llama.cpp**.
Two cold loads of the identical llama.cpp cell, run minutes apart by the same driver, read
**45.34 and 42.98 tok/s — 5.2% apart**, 26x the claimed bound.

The record's own width-sweep table already contains this evidence and does not read it: the
n=1 column of the srv2 35B sweep is **44.7 / 44.4 / 40.0 / 44.8 / 44.9** across np 1/4/8/16/32.
Those five cells are a single-stream measurement that should not depend on `-np` at all
(that is claim L22), so their **12% spread is run-to-run noise on a figure the record treats as
exact**. The 0.2% bound appears to come from repeated requests against **one already-loaded
server**, which is a much weaker form of repeatability than reload-to-reload.
**Evidence:**
```bash
ssh srv2 'python3 /tmp/lcells.py \
  "L11-np1|...|-ngl 99 -np 1 -c 1024 --n-cpu-moe 25 -fa on|1" \
  ... \
  "M5-L11-np1-take2|...|-ngl 99 -np 1 -c 1024 --n-cpu-moe 25 -fa on|1"'
```
```
L11-np1            n=1 agg=44.5 decode_tok_s_p50=45.34  (vram=6069)
M5-L11-np1-take2   n=1 agg=42.2 decode_tok_s_p50=42.98  (vram=6069)
```
Identical argv, identical resolved config, identical VRAM; 5.2% apart.
**Consequence:** every llama.cpp contrast in this corpus under ~5% is a tie on srv2, not only
on srv1. That includes L7 (~1.6 tok/s on ~45, i.e. 3.6%) and L14 (0.6%).
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` ("Bounds on all of the
above"); `width-sweep/README.md` §1 table, n=1 column

### L18 — [V] verified
**Claim:** A smaller quant of a bigger model beats a bigger quant of a smaller one:
35B-A3B IQ3_XXS (13.21 GB) 67.04 tok/s vs 30B-A3B Q4_K_M (18.56 GB) 44.84 on srv2.
**Verdict:** Both sides reproduce within 1%. 35B-A3B IQ3_XXS at the recorded winner argv reads
**67.47** (record 67.04, +0.6%); 30B-A3B Q4_K_M at `--n-cpu-moe 20 -t 10 --no-mmap` reads
**44.82** (record 44.84, -0.04%). Ratio **1.51x** against the recorded 1.50x.
**Evidence:**
```bash
# 35B side: the rig's own winner configuration, single 160-token completion after a warm-up
ssh srv2 'curl -s http://localhost:8080/completion -d "{\"prompt\":\"Write a Python function that merges two sorted lists.\",\"n_predict\":160,\"temperature\":0,\"cache_prompt\":false}" | python3 -c "import json,sys; t=json.load(sys.stdin)[\"timings\"]; print(t[\"predicted_per_second\"], t[\"prompt_per_second\"], t[\"prompt_ms\"])"'
```
```
S1_decode 67.47   prefill_tok_s 111.8   ttft_s 0.089     # argv: -ngl 99 --n-cpu-moe 4 -t 10 -c 4096 -fa on --no-mmap
L6-nommap n=1 decode_tok_s_p50=44.82                     # argv: -ngl 99 --n-cpu-moe 20 -t 10 -c 4096 -fa on --no-mmap
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md` ("Findings", 2nd bullet)

### L17 — [V] verified (the recorded figure is conservative)
**Claim:** srv2, 7B Q4_K_M, `-np 32 -c 32768 -b 1024 -ub 1024 -fa on`: 726.2 agg tok/s at n=32.
**Verdict:** **784.6** at n=32 today, +8.0% over the recorded 726.2. The claim holds as a floor.
VRAM 6,357 MiB; `truncated=0/32`.
**Evidence:**
```bash
ssh srv2 'python3 /tmp/lcells.py "L17-7b-q4km|/blobs/sha256-60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463|-ngl 99 -np 32 -c 32768 -b 1024 -ub 1024 -fa on|32"'
```
```
L17-7b-q4km CONFIG vram=6357 slots=32 ctx_slot=1024 kv_unified=false
L17-7b-q4km n=32 agg=784.6 decode_tok_s_p50=24.75 p50_lat=19.36 ttft_p50=0.14 truncated=0/32 wall=19.4
```
(the blob is ollama's `qwen2.5-coder:7b`, 4,683,074,048 B, served by llama-server directly)
**Bears on:** `records/evidence/2026-08-24-engine-sweep/README.md:120` (cell B2-5)

### L16 — [V] verified (the recorded figure is well under today's)
**Claim:** srv2, 1.5B Q4_K_M, `-np 128 -c 131072 -no-kvu -b 2048 -ub 2048 -fa on`: 1,396.4 agg
tok/s at n=128.
**Verdict:** **1,667.1** at n=128 today, **+19.4%** over the recorded 1,396.4. Direction and
configuration verified; the recorded number is low by more than any repeat spread found here,
so the cell is worth re-recording. VRAM 4,899 MiB; `truncated=0/128`.
**Evidence:**
```bash
ssh srv2 'python3 /tmp/lcells.py "L16-15b-q4km|/blobs/sha256-29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104|-ngl 99 -np 128 -c 131072 --no-kv-unified -b 2048 -ub 2048 -fa on|128"'
```
```
L16-15b-q4km CONFIG load_s=2.3 vram=4899 slots=128 ctx_slot=1024 kv_unified=false
L16-15b-q4km n=128 agg=1667.1 decode_tok_s_p50=13.09 p50_lat=36.42 ttft_p50=0.11 truncated=0/128 wall=36.5
```
Note `--no-kv-unified` is spelled `-no-kvu` in the record; both resolve, and the server reports
`kv_unified=false` with `ctx_slot=1024` — i.e. 128 x 1024 = the 131,072 asked for.
**Bears on:** `records/evidence/2026-08-24-engine-sweep/README.md:116` (cell B2-1)

### L22 — [P] partial
**Claim:** The single-stream S1 column of serving-sweep-2026-08-25 is a property of its named
configuration and does NOT depend on `-np`.
**Verdict:** The S1 value itself reproduces at the named configuration (**67.47** against 67.04),
so the column is a real measurement of its argv. But the *independence from `-np`* is **not
established at the precision the column implies**, and the record's own data argues against it:
the srv2 35B width sweep's n=1 column reads 44.7 / 44.4 / **40.0** / 44.8 / 44.9 at np =
1/4/8/16/32 — a 12% spread, with np=8 an 11% outlier. My own reload-to-reload spread on that
same cell is 5.2% (M5). So S1 is `-np`-independent only to within roughly +/-5-12%, which is
larger than several of the differences the S1 column is used to argue about.
**Not run for want of budget:** the direct contrast (winner argv at `-np 1` vs `-np 8`, same
`ctx_slot`) — two loads, ~2 min.
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md` ("What survives", final line)

### L10 (srv2 arm) — [P] partial
**Claim:** srv1's TTFT is 5.5-6.0 s across every configuration; srv2's is 0.67 s.
**Verdict:** srv2's sub-second TTFT is confirmed on every cell measured here, but I cannot confirm
the specific **0.67 s** because that figure was taken with the sweep's 527-token corpus prompt and
every cell here used the short 10-token prompt. Measured TTFT (`prompt_ms`) on the short prompt:
**0.089 s** at the winner argv, 0.10-0.22 s on the 30B cells, 0.17 s on the 35B at `--n-cpu-moe 25`,
2.77 s at np=32/n=32 (32 prompts queued behind one another). Prefill rate at the winner argv is
111.8 tok/s, which would put a 527-token prompt at ~4.7 s, **not 0.67 s** — so either the recorded
0.67 s was measured with prompt caching on, or the sweep's prefill was much faster than this
container's. Flagged as needing the sweep's own prompt to settle.
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md` ("The two winners" table, TTFT row)

### M2 (srv2 arm) — [P] partial: the confound is real, its stated size is not
**Claim:** The two "legal cross-host contrasts" (1.95x on 35B, 1.32x on 7B) are confounded:
srv2 carried `--no-mmap` in every cell and srv1 in none, and that flag alone is worth
+63%/-12..-18%.
**Verdict:** The **existence** of the confound is verified — srv2's winner argv does carry
`--no-mmap` (`docker inspect llama-sweep` above, and every srv2 cell in the sweep's `cells/`).
The **magnitude** is falsified on srv2's side: at the record's own cell for that figure the flag
is worth **+2.1% cold / +5.0% warm**, not +63% (see L6). A 2-5% flag cannot account for a 1.95x
cross-host ratio, so the correction's arithmetic ("the 1.95x and 1.32x ratios fold host, thread
count and `--no-mmap` together") overstates the `--no-mmap` term by roughly an order of magnitude.
The srv1 side of the flag (-12..-18%) is the srv1 crew's to check.
**Not run for want of budget:** the `--no-mmap` on/off pair on the **35B** at `--n-cpu-moe 20`
(the model the 1.95x contrast actually used) — two loads, ~2 min. L6 was tested on the 30B,
which is the cell the +63% was measured on.
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md` (CORRECTION §3)

### L7 — [ ] untested
**Claim:** KV-cache q8_0 at `-c 4096` across 4 slots frees only ~36 MiB and costs ~1.6 tok/s.
**Would need:** one load of the winner argv with `-ctk q8_0 -ctv q8_0` against the already-read
f16 baseline (67.47 tok/s, 11,837 MiB) — ~90 s. Note in advance that **1.6 tok/s on ~67 is 2.4%,
which is under the 5.2% reload spread M5 falsified**, so a single pass could not settle the sign
of the cost even if run; the 36 MiB VRAM half is the part that would settle cleanly.

### L14 — [ ] untested
**Claim:** Context buys nothing: srv2 35B at np=8, 1024 -> 8192 tokens/slot costs 1,126 MiB and
loses 0.6% throughput.
**Would need:** two loads at `-np 8 -c 8192` and `-np 8 -c 65536` — ~3 min. Same caveat as L7:
0.6% is far inside the 5.2% reload spread, so only the **VRAM** half (1,126 MiB) is decidable
by a single pass. The VRAM half is the one worth recording and it is cheap.

### L19 (srv2 arm) — [ ] untested
**Claim:** srv2 (4 CPU layers) flat from `-t 10` to `-t 20`; under ncmoe 48 srv2 is flat past
4 threads.
**Would need:** two loads of the winner argv at `-t 10` and `-t 20`, plus two at `--n-cpu-moe 48`
with `-t 4` / `-t 20` — ~5 min. Partial support exists in what was measured: H5's triad thread
scan shows srv2's memory bandwidth **falls** from 24.3 GB/s at 4 threads to 20.3 at 20, which is
consistent with extra threads contributing nothing to a bandwidth-bound decode, but it is a
bandwidth measurement, not a decode measurement.

### M4 — [ ] untested
**Claim:** Decode under expert offload is memory-bandwidth-bound: srv2 turbo off->on (2.8->5.2 GHz)
moves decode under 3% while prefill gains 11%; package power peaked at 40.0 W against a 65 W cap.
**Would need:** toggling `intel_pstate/no_turbo` and reading RAPL. **Deliberately not attempted** —
the brief forbids turbo/governor/RAPL changes on this host, and `no_turbo` is exactly such a
setting. The independent evidence collected here is consistent with the conclusion (H5's triad
scan; the flat 4-to-20-thread decode implied by it), but the claim as written is out of scope
for a non-destructive pass.

---

## Close-out: srv2 restored

```bash
ssh srv2 'docker ps --format "{{.Names}} {{.Status}}"; nvidia-smi --query-gpu=memory.used --format=csv,noheader; systemctl is-active ollama; systemctl is-active llama-moe'
```
```
llama-sweep Up 2 minutes (healthy)
11847 MiB
inactive        <- ollama, exactly as found (enabled but not running)
failed          <- llama-moe, exactly as found (disabled, failed before this session)
```
- The pre-existing `llama-sweep` container was `docker stop`ped, never removed, and **restarted**
  with its original argv and mounts; it is healthy again and holding 11,847 MiB (11,882 on arrival).
- Every container this session started (`verify-vllm`, `verify-lcp`) was `docker rm -f`'d by the
  driver at the end of each cell; none remain.
- No systemd unit, drop-in, governor, turbo, RAPL or BIOS setting was touched. No package was
  installed; every image used was already present. `gcc` was used to build the record's own
  `triad.c` into `/tmp`.
- One transient kernel action was taken and is named in the L6 evidence: `echo 3 >
  /proc/sys/vm/drop_caches`, to give the mmap arm a cold page cache. It persists nothing.
- Scratch left in `/tmp` on srv2 (harmless, and it is what produced the numbers):
  `lcells.py`, `vcells.py`, `vllmramp.py`, `runl.sh`, `triad.c`, `triad`, and the raw outputs
  `vout.txt`, `lout.txt`, `l6.txt`, `h4.txt`.

## Summary

| claim | verdict | one line |
|---|---|---|
| H2 | **[V]** | RTX 3060 / 12288 MiB / cc 8.6 / driver 595.84 / 2x8 GB DDR4-2667 in ChannelA+ChannelB — exact |
| H3 (srv2) | **[V]** | both pinned digests match on srv2 to the character |
| H4 (srv2) | **[V]** | all three sha256 prefixes and the 18,556,688,736 B size reproduce |
| H5 (srv2) | **[V]** | 24.3 GB/s best-of vs 23.8 recorded; but it is 20.3 at 20 threads — the record should pin the thread count |
| L6 (srv2) | **[F]** | `--no-mmap` is +2.1% cold / +5.0% warm at the record's own cell, not +63%; mmap side does not reproduce (43.91 vs 26.28) |
| L7 | [ ] | not run; and 1.6 tok/s on 67 is inside the 5.2% reload spread anyway |
| L10 (srv2) | **[P]** | srv2 TTFT is sub-second everywhere (0.089 s at the winner argv) but 0.67 s needs the sweep's 527-token prompt to check |
| L11 (srv2) | **[V]** | 44.5 -> 235.3 at np=32/n=32 = 5.29x; VRAM 6,069/8,635 matches the record exactly |
| L14 | [ ] | not run; only the 1,126 MiB half is decidable in one pass |
| L16 | **[V]** | 1,667.1 at n=128 against the recorded 1,396.4 (+19.4%) — recorded figure is low |
| L17 | **[V]** | 784.6 at n=32 against the recorded 726.2 (+8.0%) |
| L18 | **[V]** | 67.47 vs 44.82 = 1.51x, both sides within 1% of the record |
| L19 (srv2) | [ ] | not run; triad thread scan is consistent with it but is not a decode measurement |
| L22 | **[P]** | S1 reproduces (67.47 vs 67.04) but `-np` independence holds only to +/-5-12%, and the record's own n=1 column spreads 12% |
| V1 (srv2) | **[P]** | ~4x, not 5.02x (2,699.9 vs 704.4); no-eager side reproduces, eager side is +36%; and 518.2 / 36.2 / 181.7 are all miscited cells |
| V5 | **[V]** | 6,600.6 and 6,602.5, +2.4% over the recorded 6,445.1 |
| V6 | **[P]** | n=256 win reproduces (+5.4%); "does nothing at n=16" is false — +4.1% in a controlled pair |
| V12 | [ ] | not run |
| V13 | **[P]** | 1.5B half verified twice on the 16 GB host; 7B half not re-run |
| V14 | **[V]** | two more takes land inside the band; six takes now within +/-1.21% |
| M2 (srv2) | **[P]** | the confound exists but `--no-mmap` is 2-5%, so it cannot explain a 1.95x gap |
| M3 | **[V]** | 5.29x at 32 slots — the correction to "expert offload does not batch" stands |
| M4 | [ ] | out of scope: needs turbo/RAPL changes the brief forbids |
| M5 (srv2) | **[F]** for llama.cpp, **[V]** for vLLM | vLLM reloads repeat at 0.03%; llama.cpp reloads differ by 5.2% |

### The two findings that move other claims
1. **L6 is falsified and M2 depends on it.** The `--no-mmap` +63% figure is the load-bearing
   number in the correction that retired the sweep's cross-host contrasts. It is 2-5% today,
   cold cache included, at the exact cell it was measured on.
2. **M5 is falsified for llama.cpp.** srv2's 0.2% repeatability holds for vLLM and not for
   llama.cpp, where reload-to-reload spread is 5.2%. That makes L7 (2.4%), L14 (0.6%) and the
   difference between L11's 5.29x and 5.67x all ties rather than results, and it means srv2 has
   no privileged status as "the rig that repeats".
