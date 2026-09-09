# The engine sweep: which serving engine wins each rig, at the bench's concurrency

**2026-08-24, 20:18–20:59.** Four engines (ollama 0.32.15, standalone
llama-server b10481, LMDeploy TurboMind v0.16.0, vLLM v0.26.0 as the control),
three model tiers (1.5B on both rigs, 7B on srv2, 3B under LMDeploy only), both
rigs concurrently. 32 cells declared (srv1 11, srv2 21); every one either ran
or was skipped by a written rule. One pass per level except the control and
re-take cells (better-of-two). Wall-clock 41 min against the header's 200 min
estimate, because rule-driven skips and the 180 s level cap never bound.

| | srv1 | srv2 |
|---|---|---|
| card | NVIDIA GeForce GTX 1660 SUPER, 6144 MiB, CC 7.5 | NVIDIA GeForce RTX 3060, 12288 MiB, CC 8.6 |
| driver | 580.173.02 | 595.84 |
| ollama / docker | 0.32.15 / Docker 29.1.3 | 0.32.15 / Docker 29.7.1 |
| `vllm/vllm-openai:v0.26.0` | `sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52` | same digest |
| `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481` | `sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce` | same digest |
| `ghcr.io/ggml-org/llama.cpp:full-cuda-b10481` (B2-4 only) | — | `sha256:f960e6dad3c3a98d4e25e85b62517664fd6c73f8590812d4fedf1178c87a75eb` |
| `openmmlab/lmdeploy:v0.16.0-cu12.8` | `sha256:0fd7426f76331c3bed844db290ba838a01f3b2e00dcb254a6de83a86c0649576` | same digest |

Rig facts are from `srv1/runner-run.json` and `srv2/runner-run.json` (`rig_facts`). Intent
header: `records/headers/2026-08-24-engine-default-r2.json` (the `run` block
was added when this record was written). Runner: `runner.py` in this
directory, sha256 `f8dcc5f2d7a9cb6d2820796022f790a00dbe677b876c5ce8c2220d7d865fc1d7`;
cells `cells.json`, sha256 `e118d3d1…ea44e5`; repo head `8557694b`. Spec:
`sweep-spec-2026-08-24-v2.md` (session scratchpad; block (f) removed, block
(d) extended per the LMDeploy dig). Fixed conditions: one prompt ("Write a
Python function that merges two sorted lists."), `num_ctx` 1024, 475 requested
tokens, temperature 0, 180 s level cap, cap fraction counted at ≥ 470 tokens.

**The runner was invoked more than once per rig, and only the last `runner-run.json`
per rig survives** (each run overwrites it). Every run is in `rows.jsonl` and
the rig log:

| rig | run | cells | why |
|---|---|---|---|
| srv1 | 20:18:20–20:29:41 | A1-1, A1-2, C1-1, E1-1 ran; B1-1, D1-*, R1 skipped "rule (e)1" | the control bar was mis-set (CORRECTIONS 20:33) |
| srv1 | 20:30:50–20:36:56 (`--only B1-1,D1-*,R1`) | B1-1 ran; D1-1 and D1-2 refused, D1-3/D1-4/D1-5 skipped by rule (d)3; R1 re-took B1-1 | LMDeploy launch died on the incomplete snapshot (CORRECTIONS 20:38) |
| srv1 | 20:37:53–20:59:31 (`--only D1-1,D1-2,D1-3,D1-4,D1-5,R1`) | all five D1 cells ran on the corrected launch; R1 skipped ("no completed cell has a level at n=32" — the re-take only looks inside its own run) | this is the surviving `srv1/runner-run.json` |
| srv2 | 20:18:22–20:50:47 | A2-1..5, E2-1, E2-2, B2-1, B2-2, B2-4, B2-5, D2-1, D2-4, D2-5, D2-6 ran; B2-3 skipped by rule (b)4; D2-2, D2-7, D2-3, D2-8 refused; R2 re-took E2-1 | 7B and 3B snapshots incomplete on srv2 too (CORRECTIONS 20:47) |
| srv2 | 20:51:11–20:58:43 (`--only D2-2,D2-3,D2-7,D2-8,R2`) | all four ran on the corrected launch; R2 skipped (same runner quirk) | this is the surviving `srv2/runner-run.json` |

## The question and the answer

Spec §1: for each rig and model tier, which engine and configuration produces
the most completion tokens per second at the workload's concurrency (srv1
n = 32, srv2 n = 128; n = 256 read too for the engines that reach it), with
the whole model on the card — and does ollama's slot count close the gap to
vLLM's 6,445 tok/s? Rule: highest aggregate tok/s at the headline n, tie broken
by lower p50; a cell that spills or fails to launch is out.

| rig, model | winner | at headline n | runner-up | ollama's best | recommended r2 default |
|---|---|---|---|---|---|
| srv1, 1.5B | **llama-server standalone** B1-1 (`-np 32 -b 1024 -ub 1024 -fa on`, GGUF Q4_K_M) | **446.6** at n = 32, re-take R1 448.9 (p50 33.8 s) | ollama 32 slots A1-2 389.3 (p50 24.4 s) | 389.3 (A1-2, n = 32) | llama-server b10481, 32 slots; ollama at 32 slots is 13% behind and is the no-new-binary fallback |
| srv2, 1.5B | **vLLM control** E2-1 (no-eager, len 1024, seqs 256, fp8 KV, AWQ) | **5,694.9** at n = 128, 6,452.2 at n = 256; re-take R2 5,766.2 / 6,480.6 (p50 10.4 s / 18.5 s) | LMDeploy D2-1 3,855.3 at n = 128 (D2-4 4,220.9 at n = 256) | 1,011.2 (A2-3, n = 32); 992.5 at n = 128 | vLLM at yesterday's best cell, unchanged |
| srv2, 7B | **vLLM control** E2-2 (same flags, 7B AWQ) | **1,604.7** at n = 128 (p50 37.7 s) | LMDeploy D2-2 int8 KV 1,567.9 at n = 128 (p50 31.6 s) | 637.8 (A2-5, n = 32) | vLLM; LMDeploy is within 2.3% and is the alternative if vLLM's srv2 memory budget must shrink |

The decisive numbers: on srv1, llama-server 446.6 vs ollama 389.3 vs vLLM
229.7 vs LMDeploy 217.1 at n = 32. On srv2 at n = 128, vLLM 5,694.9 vs
LMDeploy 3,855.3 vs llama-server 1,396.4 vs ollama 992.5. **Ollama's slot
count does not close the gap:** at 128 slots it reaches 992–1,011 tok/s on
srv2, 5.2–5.3x the one-slot cell's best (190.3 at n = 8; it has no n = 128 level) and 5.7x short of vLLM at the same n. The whole model was on
the card in every cell that ran (`ollama ps` 100% GPU; every container's
warm-up read the card, `gpu_mem_used_mib_after_warmup` per cell row).

## Full results

Aggregate tok/s per level, from the `kind=level` rows. p50 and cap fraction are
at the rig's headline n (srv1 32, srv2 128; n = 32 where a cell stops there).
Cap fraction 1.0 means every request produced 475 tokens; 0.0 means every
request stopped at EOS before 470 (see Limits). Where a cell has more than one
row per level (re-takes), the table shows the better-of-two and names the other
attempt in the notes.

### srv1 (GTX 1660 SUPER)

| id | engine | model | config | n=1 | n=2 | n=8 | n=32 | p50 @32 | cap | status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1-1 | ollama | 1.5B Q4_K_M | 1 slot (child `-b 512`, FA auto) | 140.4 | 148.4 | 153.5 | | 9.56 s @8 | 0.0 | ok |
| A1-2 | ollama | 1.5B Q4_K_M | 32 slots, `num_batch` 1024 (child `-b 1024 -ub 1024`, FA auto) | 137.6 | 210.2 | 334.4 | **389.3** | 24.44 s | 0.0 | ok |
| C1-1 | ollama | 1.5B Q4_K_M | A1-2 + `OLLAMA_FLASH_ATTENTION=0` (child `--flash-attn off -b 1024`) | 132.5 | 199.1 | 244.6 | 323.0 | 28.50 s | 0.0 | ok |
| E1-1 | vLLM | 1.5B AWQ | no-eager, len 1024, seqs 64, f16 KV; better-of-two | 44.2 | 27.5 | 107.0 | 229.7 | 66.12 s (mean) | 1.0 | ok; control |
| B1-1 | llama-server | 1.5B Q4_K_M | `-np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on` | 151.8 | 235.0 | 373.2 | **446.6** | 33.99 s | 1.0 | ok (first skipped, rule (e)1 void) |
| R1 | llama-server | 1.5B Q4_K_M | re-take of B1-1, better-of-two | 152.2 | 236.6 | 370.3 | **448.9** | 33.76 s | 1.0 | ok |
| D1-1 | LMDeploy | 1.5B AWQ | f16 KV, batch 128, pool 0.5 | 20.9 | 20.7 | 77.1 | 217.1 | 51.55 s | 0.0 | ok (skipped by rule (e)1, then refused on both launch variants, before the launch fix) |
| D1-3 | LMDeploy | 1.5B AWQ | D1-1 + int8 KV (`--quant-policy 8`) | 20.9 | 20.7 | 81.2 | 216.8 | 57.22 s | 0.0 | ok |
| D1-4 | LMDeploy | 1.5B AWQ | D1-1 with pool 0.8 | 20.9 | 20.6 | 78.3 | 210.5 | 51.75 s | 0.0 | ok (0.8 launched; 5,058 MiB after warm-up) |
| D1-2 | LMDeploy | 3B AWQ | f16 KV, batch 128, pool 0.5 | 10.3 | 12.3 | 48.4 | 120.8 | 99.18 s | 0.0 | ok |
| D1-5 | LMDeploy | 3B AWQ | D1-2 + int8 KV | 10.3 | 12.3 | 48.5 | 121.6 | 98.89 s | 0.0 | ok |

Notes. E1-1's n = 32 attempts read 229.7 and 229.1. R1's n = 32 attempts:
the row records 448.9 as the better; B1-1's first pass 446.6 is the
`winner_first_pass_tok_s`. All ollama and LMDeploy rows are one attempt.

**Control reproduction (srv1):** E1-1 read 44.2 / 27.5 / 107.0 / 229.7 at
n = 1 / 2 / 8 / 32 against yesterday's 41.8–42.0 / 27.3 / 106.0–108.2 / 228.9–230.9
(`records/evidence/2026-08-24-config-sweep/srv1-1.5B-stage2.jsonl`, the four
no-eager len-1024 cells, for n = 1 / 8 / 32; the len-1024 cells ran no n = 2
level, so the 27.3 is from `srv1-1.5B.jsonl`'s three no-eager seqs-16 cells,
which is what CORRECTIONS 20:33 cites). The rig is in yesterday's state. The runner's
`control_failed: true` on that row is the mis-set 265 bar (CORRECTIONS 20:33);
the correct bar was 207.

### srv2 (RTX 3060)

| id | engine | model | config | n=1 | n=8 | n=32 | n=128 | n=256 | p50 @128 | cap | status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A2-1 | ollama | 1.5B Q4_K_M | 1 slot (child `-b 512`) | 114.9 | 190.3 | | | | 7.22 s @8 | 0.0 | ok |
| A2-2 | ollama | 1.5B Q4_K_M | 8 slots (child `-b 1024`) | 108.4 | 468.4 | | | | 5.10 s @8 | 0.0 | ok |
| A2-3 | ollama | 1.5B Q4_K_M | 128 slots (child `-b 2048 -ub 2048`) | 107.6 | 446.0 | 1,011.2 | **992.5** | | 36.54 s | 0.0 | ok |
| A2-4 | ollama | 7B Q4_K_M | 1 slot | 64.0 | 66.0 | | | | 24.28 s @8 | 0.0 | ok |
| A2-5 | ollama | 7B Q4_K_M | 32 slots (child `-b 1024`) | 63.9 | 159.8 | **637.8** | | | 18.78 s @32 | 0.0 | ok |
| E2-1 | vLLM | 1.5B AWQ | no-eager, len 1024, seqs 256, fp8 KV; better-of-two | 184.2 | 1,410.9 | 3,960.6 | **5,694.9** | **6,452.2** | 10.38 s (mean) | 1.0 | ok; control passed (≥ 5,800 at 256) |
| E2-2 | vLLM | 7B AWQ | same flags, one pass | 64.9 | 499.8 | 1,332.6 | **1,604.7** | | 37.74 s (mean) | 1.0 | ok |
| R2 | vLLM | 1.5B AWQ | re-take of E2-1, better-of-two | 183.5 | 1,413.3 | 3,995.4 | **5,766.2** | **6,480.6** | 10.39 s (mean) | 1.0 | ok |
| B2-1 | llama-server | 1.5B Q4_K_M | `-np 128 -c 131072 -no-kvu -b 2048 -ub 2048 -fa on` | 176.5 | 487.6 | 1,203.8 | **1,396.4** | | 43.46 s | 1.0 | ok |
| B2-2 | llama-server | 1.5B Q4_K_M | as B2-1 with `-b 512 -ub 512` | | 489.0 | 1,239.6 | 1,383.5 | | 43.31 s | 1.0 | ok |
| B2-3 | llama-server | 1.5B Q4_K_M | `-kvu`, shared prefix | | | | | | | | skipped: rule (b)4, B2-1 read 1,396.4 ≥ 1,000 |
| B2-4 | llama-batched-bench | 1.5B Q4_K_M | `-pps -kvu -npp 128 -ntg 128,256 -npl 1..256` | its own table below | | | | | | | ok, rc 0 |
| B2-5 | llama-server | 7B Q4_K_M | `-np 32 -c 32768 -b 1024 -ub 1024 -fa on` | 64.5 | 168.0 | **726.2** | | | 20.89 s @32 | 1.0 | ok |
| D2-1 | LMDeploy | 1.5B AWQ | f16 KV, batch 256, pool 0.8 (baseline) | 191.7 | 1,298.0 | 2,682.4 | **3,855.3** | 4,029.0 | 11.15 s | 0.0 | ok |
| D2-4 | LMDeploy | 1.5B AWQ | + int8 KV | 193.5 | 828.1 | 746.2 | 3,847.2 | **4,220.9** | 12.01 s | 0.0 | ok |
| D2-5 | LMDeploy | 1.5B AWQ | pool 0.5 | 189.3 | 1,332.6 | 2,640.7 | 3,833.3 | 4,102.4 | 11.26 s | 0.0 | ok |
| D2-6 | LMDeploy | 1.5B AWQ | + prefix caching | 192.0 | 1,317.5 | 2,975.2 | 3,614.7 | 4,072.2 | 11.61 s | 0.0 | ok |
| D2-2 | LMDeploy | 7B AWQ | int8 KV, batch 128, pool 0.8 | 64.7 | 433.8 | 1,259.8 | **1,567.9** | | 31.59 s | 0.0 | ok (refused once before the launch fix) |
| D2-7 | LMDeploy | 7B AWQ | f16 KV, batch 128, pool 0.8 | 65.9 | 422.9 | 1,236.2 | 1,533.0 | | 30.44 s | 0.0 | ok (refused once) |
| D2-3 | LMDeploy | 3B AWQ | f16 KV, batch 256, pool 0.8 | 122.3 | 835.3 | 2,252.0 | 2,963.3 | 3,188.4 | 16.08 s | 0.0 | ok (refused once) |
| D2-8 | LMDeploy | 3B AWQ | + int8 KV | 121.7 | 895.2 | 2,284.2 | 2,984.1 | 3,297.4 | 15.53 s | 0.0 | ok (refused once) |

Notes. E2-1's second attempts read 5,670.3 at n = 128 and 6,228.1 at n = 256;
R2's second attempt at n = 128 read 5,670.6. The refused D2-* rows of the
first run (20:44–20:46, "container exited" after 9 s) are kept beside the ok
rows of the second.

**Control reproduction (srv2):** E2-1 6,452.2 at n = 256 against yesterday's
6,445.1 (`srv2-1.5B-stage2.jsonl`, cell `s2-noeager-kvfp8-len1024-seqs256`);
the re-take R2 read 6,480.6. Three readings within 0.6% (E2-1 is 0.1% above
yesterday, R2 0.55%).

**B2-4, llama-batched-bench** (`kind=batched-bench` rows; S_TG = pl·tg / t_tg,
`-pps` shares the 128-token prompt, `-kvu`):

| batch | S_TG, tg 128 | S_TG, tg 256 |
|---|---|---|
| 1 | 206.5 | 206.7 |
| 8 | 606.9 | 599.2 |
| 32 | 2,689.6 | 2,553.4 |
| 64 | **3,186.1** | **2,832.1** |
| 128 | 3,163.2 | 2,545.9 |
| 256 | 2,809.9 | absent (needs 65,664 > `-c 34000`, as the spec predicted) |

## Findings

**(a) Ollama batches with `OLLAMA_NUM_PARALLEL`; the default one slot is a
queue.** At the same n = 8, 1 slot vs 8 slots: srv2 190.3 → 468.4 (2.5x,
A2-1 vs A2-2), srv1 153.5 → 334.4 (2.2x, A1-1 vs A1-2), 7B 66.0 → 159.8
(2.4x, A2-4 vs A2-5). The batch tier does not matter at n = 8 (A2-2 468.4 vs
A2-3 446.0, both within one pass of each other). Rule (a)4's "slots buy
nothing" test fails by a wide margin: A2-1 at n = 8 is 0.43x of A2-3. Limit:
the ramp flattens where the model stops at EOS — A2-3 reads 1,011 at n = 32
and 992 at n = 128 because 128 requests of ~294 tokens finish in 37 s while
the p50 request waits 36 s; ollama's 128-slot child is a llama-server of the same lineage as the one B2-1 drives to 1,396, so the ceiling here is what sits in front of the child, not the slot count (finding c).

**(b) srv1 has no n = 2 cliff under the llama.cpp-based engines; vLLM shows
it.** n = 1 → 2 ratios: A1-2 137.6 → 210.2 (1.53x), B1-1 151.8 → 235.0
(1.55x), C1-1 132.5 → 199.1 (1.50x), all above the spec's 1.3x pre-registered
line. vLLM E1-1 goes 44.2 → 27.5 (0.62x) and does not recover 44 tok/s per
stream at any n. LMDeploy D1-1 goes 20.9 → 20.7 (0.99x): the runner's
`note_d3` records "n=2 aggregate <= n=1 — the head GEMM cliff is present in
TurboMind too". This is **consistent with** the spec's explanation — vLLM and
TurboMind run the tied lm_head as an fp16 GEMM, which on TU116 goes through
the emulated `mma.sync` path once M ≥ 2, while ollama/llama-server run the
Q6_K head through dp4a at n ≤ 8 — and is not a proof of it: no cell isolates
the head from the rest of the model, and the 3B does not behave as predicted
(D1-2 rises 10.3 → 12.3, 1.2x, where the spec predicted the same cliff ~1.33x
larger). Per-request decode time rises 1.7–1.8x on both LMDeploy models between n = 1
and n = 2 (D1-1 16.8 s → 30.8 s p50, 1.84x; D1-2 36.6 s → 61.1 s, 1.67x), which is the
shape a GEMM-path switch would leave, but a memory-bound engine would also
show it.

**(c) Standalone llama-server beats ollama with the same engine source.**
srv1: B1-1 446.6 vs A1-2 389.3 at n = 32 (+15%; per level +10% / +12% /
+12% / +15%). srv2: B2-1 1,396.4 vs A2-3 992.5 at n = 128 (+41%), 1,203.8 vs
1,011.2 at n = 32 (+19%). The launch lines differ in what ollama adds
(`--context-shift --keep 4`, `--no-jinja`, `--flash-attn auto`) and in the
request path (ollama's `/api/generate` and its own scheduler in front of the
child). The small-ubatch arm costs nothing: B2-2 (`-b 512`) reads 1,383.5 vs
B2-1's 1,396.4 (−0.9%). Limit (spec §7b): the image is b10481 and ollama's
child is `9d77fa172` (~b10488), and ollama's child does 302–323-token EOS
stops while llama-server does 475 with `ignore_eos` — so the +15% / +41% is
"launcher plus seven builds plus request shape", not the launcher alone. The
batched-bench instrument (B2-4) reads 3,163 S_TG at batch 128 on the same file
and card — 2.3x B2-1 — with shared prefix, no HTTP, and no per-slot context;
#18030's 1,050 t/s class is reached by both.

**(d) On srv2 the engines rank vLLM > LMDeploy > llama-server > ollama on the
1.5B; on the 7B LMDeploy is within 2.3% of vLLM.** 1.5B maxima: vLLM
6,452–6,481 (E2-1, R2 at n = 256), LMDeploy 4,029–4,221 (D2-1 f16 / D2-4 int8
at n = 256), llama-server 1,396 (B2-1, n = 128), ollama 992 (A2-3, n = 128).
7B at n = 128: vLLM 1,604.7 (E2-2) vs LMDeploy 1,567.9 (D2-2) vs 1,533.0
(D2-7); at n = 32, llama-server 726.2 (B2-5) vs ollama 637.8 (A2-5). At n = 1
the 7B reads 64–66 tok/s under all four engines (A2-4 64.0, B2-5 64.5, E2-2
64.9, D2-2 64.7): single-stream is the card's bandwidth and no engine moves
it. Limit: GGUF Q4_K_M vs AWQ are different weights (spec §7a), so the
llama.cpp-vs-vLLM/LMDeploy contrast is engine plus file.

**(e) LMDeploy on srv1 runs, and is the slowest engine on the card.** 20.9
tok/s single-stream (D1-1, D1-3, D1-4 all 20.86–20.88) against ollama's
140.4, llama-server's 151.8 and vLLM's 44.2; at n = 32, 217.1 vs B1-1's 446.6
(0.49x). The 3B reads 10.3 at n = 1 and 120.8 at n = 32. Every launch on the
corrected path took 13.6–26.0 s and served. **Consistent with** the dig's
reading that TurboMind's AWQ GEMMs and decoding kernels are all `mma.sync`
kernels that TU116 executes on its FP16 units at a fraction of tensor-core
rate — the whole model is slow, not just the head, which is what 20.9 vs 44.2
at n = 1 looks like. Not proven: no cell runs a non-MMA kernel on this card.

**(f) The srv2 LMDeploy knobs.** One knob at a time against D2-1
(f16 KV, pool 0.8, no prefix cache); one pass each, so the ±11% band between
D2-5/D2-6 and the baseline at n = 32–128 is this sweep's own noise floor.

| knob | cell | n=8 | n=32 | n=128 | n=256 | reading |
|---|---|---|---|---|---|---|
| int8 KV | D2-4 vs D2-1 | 828 vs 1,298 (−36%) | **746 vs 2,682 (−72%)** | 3,847 vs 3,855 (0%) | 4,221 vs 4,029 (+4.8%) | +5% where the pool binds; the n = 8 and n = 32 readings are two different shapes — at n = 8 every request slowed uniformly (3.17–3.73 s against D2-1's 1.83–2.06 s, no straggler); at n = 32 the p50 is 3.68 s (D2-1: 3.69 s) but a tail of 8 of 32 requests took 5.3–16.71 s (two at 8.7 s, three at 10.05 s, one at 16.71 s), and the slowest set the level's wall at 4.5x the median. **Unexplained.** The int8 arm also generates 390 tokens per request where f16 generates 350: int8 KV changed the greedy output. |
| pool 0.5 | D2-5 vs D2-1 | 1,333 vs 1,298 | 2,641 vs 2,682 | 3,833 vs 3,855 | 4,102 vs 4,029 | null, as expected; the predicted queueing at n = 256 (~177 sessions) did not show — p50 21.29 s vs 21.26 s |
| prefix caching | D2-6 vs D2-1 | 1,318 vs 1,298 | 2,975 vs 2,682 (+11%) | 3,615 vs 3,855 (−6%) | 4,072 vs 4,029 | null within the noise band, as expected |
| int8 KV, 7B | D2-2 vs D2-7 | 434 vs 423 | 1,260 vs 1,236 | 1,568 vs 1,533 (+2.3%) | — | f16 at ~88 predicted sessions did not visibly queue at n = 128 (p50 31.6 s vs 30.4 s) |
| int8 KV, 3B | D2-8 vs D2-3 | 895 vs 835 | 2,284 vs 2,252 | 2,984 vs 2,963 | 3,297 vs 3,188 (+3.4%) | the pool-doubling half of quant-policy 8 is worth 3–5% at n = 256 and nothing below |

srv1 knobs: int8 KV (D1-3 vs D1-1) 216.8 vs 217.1 at n = 32, null; pool 0.8
(D1-4) launches on 6 GB (the headroom result), 210.5 vs 217.1, −3%, within
one pass; on the 3B, int8 KV (D1-5 vs D1-2) 121.6 vs 120.8, null.

**(g) Flash attention on srv1 is a help, not the door to a cliff.** C1-1 (FA
off, batch held at 1024 — the journal shows `--flash-attn off -b 1024 -ub
1024` beside A1-2's `--flash-attn auto -b 1024 -ub 1024`) reads below A1-2 at
every level: −3.7% (n = 1), −5.3% (2), −27% (8), −17% (32). Since A1-2 has no
n = 2 step to fix, the pre-registered "if C1-1 fixes it" branch never opens;
what the pair shows is that the auto FA kernel is worth 17–27% at n ≥ 8 on
this card. Limit: one pass each, and C1-1's n = 1 request stopped at 302 tokens
where A1-2's stopped at 323 — FA off changed the greedy text.

## Limits

1. **Two engines could not be forced to 475 tokens.** ollama's `/api/generate`
   and LMDeploy's `/v1/completions` have no `ignore_eos`, so every request in
   blocks (a), (c) and (d) stopped at EOS: 323 tokens on srv1's ollama and 302
   on srv2's for the 1.5B at n = 1 (varying 244–337 across a batch — greedy
   decoding under batching is not bit-stable), 355–381 on the 7B; LMDeploy
   350 (f16 KV) or 390 (int8) on the 1.5B, 376 on the 3B, 366–391 on the 7B.
   Their cap fraction is 0.0 by construction. The aggregate is tokens / wall
   so it is comparable **as a rate** with vLLM's and llama-server's 475-token
   requests, but the per-request work differs by 18–36% (302–390 tokens against 475), and a level's wall
   under ollama/LMDeploy is set by its longest request.
2. **The vLLM control cells ran through the repo's `sweep.py`** (container
   `sweep-vllm`, its own prompt and timeouts, `ignore_eos`). Their latency
   column is the mean, not p50, and their rows carry no per-request list. The
   ollama/llama-server/LMDeploy cells ran through `runner.py`'s own client.
3. **Four correction notes, dated in `CORRECTIONS.md` (20:33, 20:38, 20:40, 20:47; the 20:40 note is superseded by 20:47):** (i) the srv1 control bar
   was derived from yesterday's n = 256 maximum, not its n = 32 reading, so the
   first run skipped blocks (b), (d) and R1 for a control that in fact
   reproduces; (ii) every LMDeploy launch died in ~8 s on an
   `IncompleteSnapshotError` (`HF_HUB_OFFLINE=1` with a snapshot lacking
   `.gitattributes`/`LICENSE`/`README.md`), fixed by passing the snapshot
   directory as `model_path` with `--model-name` keeping the hub id and by
   dropping `--rm`; (iii) the 20:40 note that only srv1 was affected was too
   narrow — srv2's 1.5B snapshot is complete and D2-1/4/5/6 ran on the
   original launch, its 7B and 3B are not and D2-2/7/3/8 ran on the corrected
   one. The refused and skipped rows are kept as written; the `--only` re-runs
   append beside them.
4. **B2-3 was skipped by rule (b)4** (B2-1 ≥ 1,000 at n = 128), so the
   shared-prefix cost on llama-server is read only through B2-4's instrument,
   whose S_TG (3,163 at batch 128) is not the server's number (1,396).
5. **The re-take filter (cap ≥ 0.9) excludes every ollama and LMDeploy cell by
   construction**, so R1 and R2 could only ever re-take a llama-server or vLLM
   cell. On both rigs that was also the highest cell, so nothing was hidden
   here; it would matter on a rig where an EOS-stopped engine led.
6. Single day, single pass except E/R cells; no card/driver separation (srv1
   and srv2 differ in card, driver and CPU); the ollama child is ~7 builds
   newer than the llama-server image; the tied-head and sm75 readings in (b)
   and (e) are consistent-with, not shown.

## Post-state

Both rigs' final restore rows (`kind=restore`, `after: END`):

- srv1 20:59:28 — `env_readback: "OLLAMA_NUM_PARALLEL=0 OLLAMA_MAX_LOADED_MODELS=0 OLLAMA_KEEP_ALIVE=-1 OLLAMA_HOST=0.0.0.0:11434"`, `restored: true`, `api_ready: true`.
- srv2 20:58:40 — `env_readback: "OLLAMA_NUM_PARALLEL=0 OLLAMA_MAX_LOADED_MODELS=0 OLLAMA_KEEP_ALIVE=-1 OLLAMA_HOST=0.0.0.0:11434"`, `restored: true`, `api_ready: true`.

The same readback appears after every intermediate run's END (srv1 20:29:39,
20:36:53; srv2 20:50:44). `runner-run.json` `post_state`: GPU memory used 1 MiB on
both cards; `ollama ps` empty; `docker ps -a` holds only the pre-existing
exited strangers (`mcgyvr-vllm`, `vllm-nemotron-4b`, and on srv2
`vllm-7b-coder`, `vllm-nemotron-30b`) — no `sweep-*` container; every
`post-state-check` row reads `violations: []`. srv1's card sat at 57 °C,
16.4 W, 345 MHz; srv2's at 47 °C, 22.1 W, 210 MHz. The host-state pin
(`tools/bench/serving/configs/hosts.json`) is not modified.

## What this decides, and what it does not

Against spec §7:

- **(a)** Slots > 1 raise ollama's aggregate 2.2–2.5x at n = 8 on both rigs
  and A2-3 reaches 5.2–5.3x the one-slot cell's best on srv2; the batch tier is inert at equal n. Ollama at
  its best does not beat vLLM's control on srv2 (0.17x) and does not beat
  llama-server on either rig. Not decided: anything about the weights.
- **(b)** The small ubatch costs nothing (−0.9%); this card and model reach
  #18030's class under both the server and the instrument. Not decided: build
  attribution for the ollama-vs-llama-server gap.
- **(c)** srv1 ollama has no n ≥ 2 step; flash attention is worth 17–27% at
  n ≥ 8 and is not a cliff mechanism. Not decided: why the die behaves so.
- **(d)** TurboMind runs on TU116 (at 0.49x of llama-server) and does not beat
  vLLM on Ampere with the same AWQ file (0.68x at n = 128 on the 1.5B, 0.98x
  on the 7B); int8 KV buys 3–5% only where the pool binds and its n = 8/32
  1.5B readings are unexplained; pool fraction and prefix caching are null.
  The tied-head cliff carries to TurboMind on the 1.5B (0.99x) and not as
  predicted on the 3B (1.2x). Not decided: interactions, the 3B as a default.
- **(e)** Both rigs are in yesterday's state (srv2 E2-1 0.1% above yesterday, R2 0.55%; srv1 E1-1 inside yesterday's 228.9–230.9 band at n = 32).
- **Serving default for r2:** srv1 1.5B → llama-server b10481 at 32 slots;
  srv2 1.5B and 7B → vLLM at yesterday's best cell. Cross-rig sentences are
  not made here: the identity block is per row and the launcher differs by
  engine.

Follow-ups this implies (one line each; nothing is filed):

- Give the ollama and LMDeploy clients a 475-token fixed-length arm (a stop-free prompt, or `min_tokens` where the engine has one) so cap fraction can reach 1.0 and the re-take filter stops excluding two engines by construction.
- Re-run D2-4 at n = 8 and n = 32 (three passes) to learn whether the straggler is int8-KV-specific or a first-level warm-up artefact of the imported GEMM tuning.
- Run B1-1's flags through ollama's own child binary (`/usr/local/lib/ollama/llama-server`, `9d77fa172`) to split the +15% / +41% into launcher and build.
- If llama-server becomes srv1's default, the harness needs a llama-server launcher with the identity block (`serving_build` from `/props`, `weights_sha256` of the blob) before any r2 row is admissible.
- Price the +2.3% vLLM-over-LMDeploy 7B margin against memory: D2-2 sat at 10,945 MiB after warm-up and E2-2's KV budget is card-relative (0.85), so a co-residency round may reverse the order.
