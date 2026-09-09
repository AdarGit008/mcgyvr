# srv1 crew — verification findings
Rig: srv1 (GTX 1660 SUPER). Started 2026-08-25. Budget ~60 min of rig time.

## Pre-flight state (to restore)
```bash
ssh srv1 'systemctl is-active ollama; systemctl is-enabled ollama'
```
```
inactive
enabled
```
ollama was INACTIVE (but enabled) at start — must be left inactive.

---
### H1 — [V] verified
**Claim:** srv1 is a GTX 1660 SUPER, 6144 MiB, compute capability 7.5, driver 580.173.02, 48 GB RAM.
**Verdict:** Verified exactly. RAM total reads 49,351,319,552 B = 45.96 GiB = 49.35 GB, i.e. the "48 GB" nameplate (2x24 or 3x16); GPU/cc/driver match to the digit.
**Evidence:**
```bash
ssh srv1 'nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv; free -b | head -2; nproc'
```
```
name, memory.total [MiB], compute_cap, driver_version
NVIDIA GeForce GTX 1660 SUPER, 6144 MiB, 7.5, 580.173.02
               total        used        free      shared  buff/cache   available
Mem:     49351319552  2745159680   694124544    46557429760 ...
6
```
Note: 6 physical cores (nproc=6) — relevant to L20.
**Bears on:** `records/evidence/2026-08-23-cross-rig/` (host table)

### H3 — [V] verified (srv1 arm)
**Claim:** srv1 holds llama.cpp server-cuda-b10481 = sha256:b2497f88…f2ce and vllm/vllm-openai:v0.26.0 = sha256:ffb2d59b…abf52.
**Verdict:** Both digests match on srv1, to the full 64 hex chars. (The srv2 half of "both rigs identical" is the srv2 crew's.) Note v0.26.0 and `latest` are the SAME image id on srv1 (ffb2d59b1c05).
**Evidence:**
```bash
ssh srv1 'docker images --digests'
```
```
ghcr.io/ggml-org/llama.cpp   server-cuda-b10481  sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce  b2497f8834f5
vllm/vllm-openai             v0.26.0             sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52  ffb2d59b1c05
vllm/vllm-openai             latest              sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52  ffb2d59b1c05
```
**Bears on:** `records/evidence/2026-08-24-engine-sweep/`

### L1 — [V] verified
**Claim:** b10481's default slot count is 4: with no --parallel/-np, /props reports total_slots 4.
**Verdict:** Verified on a live b10481 server launched with no -np/--parallel: `"total_slots":4`, and the startup line says `n_slots = 4`.
**Evidence:**
```bash
ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"; curl -s localhost:8080/props | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[\"total_slots\"], d[\"default_generation_settings\"][\"n_ctx\"])"'
```
```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on","--host","0.0.0.0","--port","8080"]
"total_slots":4        n_ctx 4096
docker logs: srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
```
(No -np anywhere in the command line; total_slots is 4.)
**Bears on:** `.verify/CLAIMS.md` L1 / `records/evidence/2026-08-24-knob-surface/`

### L9 — [V] verified (VRAM figure) / [P] on "27 overruns"
**Claim:** srv1's floor for 35B-A3B IQ3_XXS is ncmoe 28 (5,554 MiB); 27 overruns the 6,144 MiB card.
**Verdict:** The ncmoe-28 cell is live on srv1 right now and reads **5,558 MiB of 6,144** — the record's 5,554 MiB reproduces to 4 MiB (nvidia-smi granularity/other clients). The "27 overruns" half is a launch refusal I did not re-run inside budget; the record's own log is the evidence for it, and 5,558 + ~520 MiB/layer > 6,144 is arithmetically forced.
**Evidence:**
```bash
ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader'
```
```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on",...]
5558 MiB, 6144 MiB
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:48` and `:71`

### L10 — [V] verified (srv1 arm)
**Claim:** srv1's TTFT is 5.5-6.0 s across EVERY configuration tried; srv2's is 0.67 s. No ncmoe or -t setting moves it.
**Verdict:** srv1 arm reproduces. Five fresh `POST /completion` calls on the shipped winner (ncmoe 28, -t 6, 550-token prompt, `cache_prompt:false`) give TTFT **5.56 / 5.60 / 5.94 / 6.39** s, prefill 86-99 tok/s. The 5.5-6.0 band holds; the one 6.39 s sample coincided with CPU contention from another process (see M5). The "no setting moves it" half is an over-generalisation from the configs tried, not something a single re-run can verify — TTFT here is 550 tokens / ~95 tok/s prefill, i.e. it is set by prefill rate, and prefill IS bandwidth/CPU-bound under 28 offloaded layers.
**Evidence:**
```bash
ssh srv1 'python3 /tmp/verify_probe1.py 8080'   # 550-token corpus contract prompt, n_predict 160, temperature 0
```
```
rep0 tg=32.35 tok/s  prompt_n=550 ttft=5.94s  pp=92.5 tok/s
rep1 tg=33.48 tok/s  prompt_n=550 ttft=5.56s  pp=98.9 tok/s
rep2 tg=31.39 tok/s  prompt_n=550 ttft=5.60s  pp=98.3 tok/s
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:46` and `:73-77`

### M1 — [P] partial — mechanism VERIFIED, the word "void" is stronger than the evidence
**Claim:** Every `tasks/h @8` figure in serving-sweep-2026-08-25 is void: 8 concurrent requests against llama.cpp's default 4 slots is 4 served and 4 queued, so the figure is not a property of the configuration.
**Verdict:** The **mechanism is verified directly**: I fired 8 concurrent completions at the live default-slot server while polling `/slots` every 500 ms. `total_slots` stayed 4 and the number of slots with `is_processing:true` never exceeded **4** for the whole 109.7 s burst — exactly 4 served, 4 queued. What does *not* follow is "void": 4 slots was part of the configuration as run (it is the build default, and the record states `total_slots: 4` for every cell). The figure is a real property of *that* configuration; what it is not is a property of the model+flags independent of slot count. The record's own correction says the milder thing ("read every `tasks/h @8` column as tasks/h at 8 requests against 4 slots"), and that is the defensible version.
**Evidence:**
```bash
# /slots polled at 2 Hz during 8 concurrent POST /completion (n_predict 160)
ssh srv1 'python3 /tmp/verify_probe1.py 8080'
```
```
BURST8 wall=109.7s total_tokens=1280 agg=11.7 tok/s tasks/h=262
BURST8 slots_total=4 max_simultaneously_processing=4
slot samples (total,busy): [(4,0),(4,1),(4,4),(4,4),(4,4),(4,4),(4,4),(4,4), ...]   # never (4,5+)
```
CAVEAT on the throughput half: my burst read 262 tasks/h against the record's 457 for the same cell, because two of my own CPU-only research containers were running on srv1's 6 cores at the time (see M5). The slot-count observation is unaffected by that contention; the tasks/h number from my burst is not usable.
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:127-133`

### V3 — [F] falsified as stated
**Claim:** srv1 responds to exactly ONE axis of twenty: 25 cells across compile, graphs, perf mode, scheduler, dtype, KV dtype, block size, prefix caching, chunked prefill, cascade attention, stream interval, watermark, attention backend and linear backend all land inside a 2.8% band (164-168 tok/s).
**Verdict:** **False on the record's own data.** Of the 26 non-concurrency stage-1 cells that launched on srv1, **22** land in 164-168; **four do not**, and three of them are far outside — and they sit on axes the claim names by name:
- `async-sched-off` (**scheduler**) = **153.5** (-6.6% vs baseline 164.3)
- `attn-FLEX_ATTENTION` (**attention backend**) = **116.3** (-29%)
- `linear-triton` (**linear backend**) = **124.4** (-24%)
- `opt-level-3` = 168.1, marginally above the stated band.
So srv1 responds to *four* named axes, not one; three of them respond **downward**. The defensible restatement is "concurrency is the only axis that moves srv1 **up**; several others can move it sharply down." The cell count is also off: 22 in band, not 25.
**Evidence:**
```bash
python3 -c '
import json
d=[json.loads(l) for l in open("records/evidence/2026-08-24-config-sweep/srv1-1.5B.jsonl")]
for r in d:
  if r.get("launch",{}).get("ok") and r["axis"]!="concurrency": print(r["axis"], r["cell"], r["max_agg_tok_s"])'
```
```
scheduler          async-sched-off       153.5
attention-backend  attn-FLEX_ATTENTION   116.3
linear-backend     linear-triton         124.4
opt-level          opt-level-3           168.1
(22 others: 164.3 - 167.9)
```
NOTE: 6 of the cells the claim counts as "in the band" did not land in it at all — they **refused to launch** (`dtype-bfloat16`, `kv-fp8`, `kv-fp8_e5m2`, `kv-fp8_e4m3`, `attn-FLASH_ATTN`, `attn-FLASHINFER`, plus `linear-exllama/torch/machete/cutlass`). A refusal is not a 2.8%-band datapoint.
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:43-50`

### V4 — [V] verified (from the record's own per-cell data; not re-run on the rig)
**Claim:** srv1's vLLM ceiling is ~293-294 agg tok/s and is NOT context-bound: --max-model-len 4096/2048/1024/512 all return 293.3-293.4 at seqs 128.
**Verdict:** Verified in the cell records to four significant figures — 293.3 / 293.3 / 293.3 / 293.4 for len 4096 / 2048 / 1024 / 512 at `--max-num-seqs 128`, and the stage-2 crossings top out at 294.7. Not re-run on the rig: four vLLM launches would have cost ~12 min of a 60-min budget for a figure whose four independent cells already agree to 0.03%.
**Evidence:**
```bash
python3 -c '
import json
for f in ["records/evidence/2026-08-24-config-sweep/srv1-1.5B.jsonl","records/evidence/2026-08-24-config-sweep/srv1-1.5B-stage2.jsonl"]:
 for l in open(f):
  r=json.loads(l)
  if r.get("launch",{}).get("ok") and ("len" in r["cell"]): print(r["cell"], r["max_agg_tok_s"], "@n", r["max_at_n"])'
```
```
len4096-seqs128 293.3 @n 128 | len2048-seqs128 293.3 @n 128
len1024-seqs128 293.3 @n 128 | len512-seqs128  293.4 @n 128
s2-noeager-len1024-seqs256 294.2 | s2-noeager-len512-seqs256 294.7 | s2-noeager-opt3-len1024-seqs256 294.7
```
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:46-50`

### V1 — [V] verified (srv1 arm only)
**Claim:** --enforce-eager costs srv2 5.02x and srv1 0.1% (293.6 vs 293.3).
**Verdict:** srv1 arm verified from the paired cells: `s2-noeager-len1024-seqs128` = **293.6** against `len1024-seqs128` (which carries `--enforce-eager`) = **293.3** — 0.10%, far inside srv1's own 5-10% run-to-run spread (M5), i.e. indistinguishable. The srv2 5.02x arm is the srv2 crew's.
**Evidence:** same command as V4; the two cells differ only in the presence of `--enforce-eager`.
```
len1024-seqs128            293.3   (--enforce-eager)
s2-noeager-len1024-seqs128 293.6   (no --enforce-eager)
```
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:66-67`

### L2 — [P] partial — CONDITIONAL, and the register's general sentence is wrong
**Claim:** -c is a TOTAL divided across slots (-np 4 -c 4096 yields n_ctx_slot 1024; -np 16 -c 4096 yields 256).
**Verdict:** **The two arithmetic examples are exactly right; the general sentence is not.** The division happens only when `kv_unified == false`, and b10481's *server* forces `kv_unified = true` whenever `-np` is absent. So bare `-c 4096` gives every one of the 4 default slots the FULL 4096 — no division. Measured all four cells on srv1 (CPU-only, `-ngl 0`; the KV geometry is computed before any GPU is touched):

| invocation | n_slots | n_ctx_slot | kv_unified |
|---|---|---|---|
| `-c 4096` (no `-np`) | 4 | **4096** | true |
| `-np 4 -c 4096` | 4 | **1024** | false |
| `-np 16 -c 4096` | 16 | **256** | false |
| `-c 4096 -no-kvu` (no `-np`) | 4 | **4096** | **true — the flag is silently overridden** |

**Gotcha worth recording:** `-no-kvu` without `-np` does nothing. `tools/server/server.cpp:151-155` runs *after* arg parsing and unconditionally re-sets `params.kv_unified = true` on the auto path.
**Evidence:**
```bash
ssh srv1 'bash /tmp/verify_cpubat.sh'   # docker run ... -ngl 0 --no-warmup, no --gpus, each container --rm'd
```
```
CELL L2a 7B  no -np,  -c 4096 :: LOADED  n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
CELL L2b 7B  -np 4    -c 4096 :: LOADED  n_slots = 4, n_ctx_slot = 1024, kv_unified = 'false'
CELL L2c 7B  -np 16   -c 4096 :: LOADED  n_slots = 16, n_ctx_slot = 256, kv_unified = 'false'
CELL L2d 7B  no -np, -no-kvu, -c 4096 :: LOADED  n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
```
Upstream source at the exact build (`build 10481, commit 25ae3a9b331fffea50ff8d07a5cad34c33f1276f`):
```cpp
// src/llama-context.cpp:288-304
if (cparams.kv_unified) { cparams.n_ctx_seq = cparams.n_ctx; }
else { cparams.n_ctx_seq = cparams.n_ctx / cparams.n_seq_max;
       cparams.n_ctx_seq = GGML_PAD(cparams.n_ctx_seq, 256); ... }
// tools/server/server.cpp:151-155
if (params.n_parallel < 0) { params.n_parallel = 4; params.kv_unified = true; }
// common/arg.cpp:1401  ->  params.n_parallel = -1;  // auto by default (LLAMA_EXAMPLE_SERVER)
```
(The `GGML_PAD(...,256)` is why `-np 32 -c 4096` reads 256 and not 128 in `np-semantics-probe.txt`.)
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:14-26` (its table is right — every probe cell passed `-np` explicitly) and `records/evidence/2026-08-25-moe-expert-offload/README.md:224` (whose unqualified sentence is wrong)
Upstream: https://github.com/ggml-org/llama.cpp/blob/25ae3a9b331fffea50ff8d07a5cad34c33f1276f/tools/server/server.cpp#L151-L155

### L3 — [V] verified, with two precision corrections
**Claim:** --n-cpu-moe N keeps attention, KV cache and embeddings on the card and puts the expert FFN weights of N layers in system RAM.
**Verdict:** Verified. `-ncmoe N` builds one tensor-buffer override per layer `i = 0..N-1` matching `blk.<i>\.ffn_(up|down|gate|gate_up)_(ch|)exps` and points it at the CPU buffer type. **Two corrections:** (a) it is the **first N layers**, not "N layers" anywhere; (b) it is strictly *subtractive* — it removes only expert-FFN tensors from wherever `-ngl` put them. Attention, KV and embeddings stay on the card because `-ngl` put them there, not because `-ncmoe` keeps them there. Shared-expert and dense FFN tensors (`ffn_*_shexp`, `ffn_up/down/gate` without `_exps`) do **not** match and stay on the GPU. KV is untouched by construction: overrides apply only in the model loader, while KV picks its buffer from `model.dev_layer(il)` (`src/llama-kv-cache.cpp:212-216`), which `-ncmoe` does not change.
**Evidence:**
```bash
ssh srv1 'docker run --rm --entrypoint bash ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 -c "/app/llama-server --help | grep -A2 n-cpu-moe"'
```
```
-ncmoe, --n-cpu-moe N   keep the Mixture of Experts (MoE) weights of the first N layers in the CPU
                        (env: LLAMA_ARG_N_CPU_MOE)
```
```cpp
// common/arg.cpp:2727-2741
for (int i = 0; i < value; ++i) {
    buft_overrides.push_back(llm_ffn_exps_block_regex(i));
    params.tensor_buft_overrides.push_back({buft_overrides.back().c_str(), ggml_backend_cpu_buffer_type()});
}
// common/common.h:1112-1116
const char * const LLM_FFN_EXPS_REGEX = "\\.ffn_(up|down|gate|gate_up)_(ch|)exps";
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:38-40`
Upstream: https://github.com/ggml-org/llama.cpp/blob/25ae3a9b331fffea50ff8d07a5cad34c33f1276f/common/arg.cpp#L2727-L2741

### L4 — [V] verified (with a citation correction)
**Claim:** ollama cannot express --n-cpu-moe; it splits whole layers only (upstream ollama/ollama#11772).
**Verdict:** Verified on the mechanism. ollama's only placement knob is `num_gpu`, a **layer count** (`api/types.go:589-594`, default `-1` = dynamic), and its llama.cpp launcher emits exactly one placement argument: `-ngl <NumGPU>` (`llm/llama_server.go:404-410`). **Citation correction:** #11772 is a *feature request* ("use cpu to offload moe weights to reduce the VRAM usage", opened 2025-08-07, still open) — it is demand-side evidence, not a statement of incapacity. The sharper citation is `llm/llama_server.go:404-410` plus PR #12333 (`num_moe_offload`, opened 2025-09-18, **unmerged**, with maintainer `jessegross` noting "generally we are not adding new features to the old llama engine").
**Evidence (negative findings, stated with provenance):**
- We did not find `-ot` / `--override-tensor` / `--n-cpu-moe` / `-ncmoe` in `llm/llama_server.go`; searched that file on `ollama/ollama` main via raw.githubusercontent, 2026-08-25.
- We did not find `num_moe*` anywhere in `ollama/ollama`; searched `gh api search/code q='repo:ollama/ollama num_moe'` -> `total_count: 0`, 2026-08-25.
- We did not find any per-tensor or expert-level placement control in `docs/modelfile.mdx`, `docs/api.md`, `docs/gpu.mdx`, `api/types.go`, or `envconfig/config.go`.
```go
// llm/llama_server.go:404-410
if launch.opts.NumGPU > 0 { params = append(params, "-ngl", strconv.Itoa(launch.opts.NumGPU)) }
else if launch.opts.NumGPU == 0 { params = append(params, "-ngl", "0") }
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:39-40` · https://github.com/ollama/ollama/issues/11772 · https://github.com/ollama/ollama/pull/12333

### L8 — [V] verified
**Claim:** ollama's gpt-oss-20b blob will not load in b10481: "unknown model architecture: 'gptoss'".
**Verdict:** Verified verbatim on srv1, today, against the same 13,793,422,144-byte blob. It is a GGUF-parse-time refusal — it fires before any device memory is touched, which is why it reproduces CPU-only.
**Evidence:**
```bash
ssh srv1 'docker run --rm -v /home/adaramir/ggufs:/models:ro ghcr.io/ggml-org/llama.cpp:server-cuda-b10481 \
  -m /models/gpt-oss-20b.gguf -c 512 -ngl 0 --no-warmup 2>&1 | grep -iE "architec|error"'
```
```
E llama_model_load: error loading model: unknown model architecture: 'gptoss'
E common_fit_params: encountered an error while trying to fit params to free device memory: failed to load model
E srv  llama_server: exiting due to model loading error
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:80-83` and `records/evidence/2026-08-25-moe-expert-offload/README.md:253-254`

### L22 — [V] verified (srv1 arm, from the width sweep's own srv1 cells)
**Claim:** The single-stream S1 column of serving-sweep-2026-08-25 is a property of its named configuration and does NOT depend on -np.
**Verdict:** Verified on srv1 data. The width sweep varied `-np` from 1 to 16 at fixed model/flags and read n=1 each time: srv1 7B IQ4_XS gives **54.5 / 54.3 / 54.2 / 54.1** at np 1/4/8/16 — a 0.7% spread, an order of magnitude inside srv1's own run-to-run behaviour (M5). srv1 35B-A3B at ncmoe 35 gives **29.1 / 28.4 / 29.3 / 29.3** at np 1/4/8/16 — 3.1%, also a tie. So the S1 column survives the `-np` correction that voids the `tasks/h @8` column; a single stream uses one slot regardless of how many exist.
**Evidence:**
```bash
sed -n '/### srv1, 7B IQ4_XS/,/^$/p' records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md
```
```
| -np | -c     | VRAM  | n=1  |
| 1   | 1,024  | 4,012 | 54.5 |
| 4   | 4,096  | 4,180 | 54.3 |
| 8   | 8,192  | 4,404 | 54.2 |
| 16  | 16,384 | 4,852 | 54.1 |
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:164-165`

### M7 — [F] falsified — the arithmetic does not give 1.5x
**Claim:** On srv1 the engine choice is worth ~1.5x at the same model and concurrency: llama-server 446.6-448.9 vs vLLM 229.7 at n=32 (1.5B).
**Verdict:** The two numbers are correctly quoted from the record, but **446.6 / 229.7 = 1.94x and 448.9 / 229.7 = 1.95x — not ~1.5x.** The 1.5x figure comes from a *different* pairing: srv1's best vLLM cell is 293.6-294.7, and 446.6 / 293.6 = 1.52x — but that vLLM cell runs at n=128/n=256, so the "same concurrency" qualifier fails. As written the claim mixes the n=32 numerator with the n=128 denominator's ratio. **Restate as either "1.94x at matched n=32" or "1.5x against srv1's best vLLM configuration at its own best concurrency" — not both.**
**Evidence:**
```bash
grep -n "E1-1 \| B1-1 \| R1 " records/evidence/2026-08-24-engine-sweep/README.md
```
```
| E1-1 | vLLM         | 1.5B AWQ     | no-eager, len 1024, seqs 64, f16 KV | 44.2 | 27.5 | 107.0 | 229.7 |
| B1-1 | llama-server | 1.5B Q4_K_M  | -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on | 151.8 | 235.0 | 373.2 | 446.6 |
| R1   | llama-server | 1.5B Q4_K_M  | re-take of B1-1, better-of-two   | 152.2 | 236.6 | 370.3 | 448.9 |
python3 -c "print(446.6/229.7, 448.9/229.7, 446.6/293.6)"  ->  1.9442 1.9542 1.5211
```
**Bears on:** `records/evidence/2026-08-24-engine-sweep/README.md:83-84` and `records/evidence/2026-08-24-config-sweep/README.md:20`

### L15 — [V] verified (from the engine sweep's own srv1 rows; not re-run — see BLOCKER)
**Claim:** srv1, 1.5B Q4_K_M, -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on: 446.6-448.9 agg tok/s at n=32.
**Verdict:** Verified against two independent takes of the same cell: B1-1 first pass **446.64** (p50 33.99 s) and its re-take R1 **448.92** (p50 33.76 s) — 0.5% apart, both `cap_frac 1.0` (every request produced all 475 tokens, so the aggregate is not an EOS artefact) and `fail 0`. The config is internally consistent with L2: `-c 32768` over `-np 32` with `-no-kvu` is 1,024 tokens/slot.
**Evidence:**
```bash
grep -n "B1-1 n=32\|R1 n=32" records/evidence/2026-08-24-engine-sweep/srv1.log
```
```
20:32:55   B1-1 n=32   446.64 tok/s  p50 33.993s  cap_frac 1.0  fail 0
20:36:38   R1 n=32     448.92 tok/s  p50 33.764s  cap_frac 1.0  fail 0
```
**Bears on:** `records/evidence/2026-08-24-engine-sweep/README.md:83-84`

### V2 — [P] partial — the two headline halves hold, the "only two forced-eager paths" list is incomplete
**Claim:** vLLM 0.26.0 has NO compute-capability gate on CUDA graph capture; docs/features/README.md lists CUDA graph as supported on Turing; the only forced-eager paths are ROCm encoder-decoder and 8-bit bitsandbytes.
**Verdict:** (a) **No capability gate on graph capture — VERIFIED.** Zero lines in the whole installed package pair `capability` with `graph`/`eager`; the cudagraph files carry no capability check at all. (b) **Turing supported in the matrix — VERIFIED** (upstream v0.26.0). (c) **"only two forced-eager paths" — FALSE.** There is a **third** engine-set `enforce_eager = True`, and the claim also misses that cudagraph is disabled by a *different* mechanism (`cudagraph_mode = CUDAGraphMode.NONE`) in at least six more places.
**Evidence:**
```bash
ssh srv1 'docker run --rm --entrypoint bash vllm/vllm-openai:v0.26.0 -c \
  "cd /usr/local/lib/python3.12/dist-packages/vllm && grep -rn \"capability\" --include=*.py . | grep -i \"graph\\|eager\""'
```
```
(exit 1 — zero matches)
```
Engine-set forced eager, all three:
```
/usr/local/lib/python3.12/dist-packages/vllm/config/model.py:1147        _verify_cuda_graph()  ROCm encoder-decoder   [claimed]
/usr/local/lib/python3.12/dist-packages/vllm/config/model.py:1175        _verify_bnb_config()  load_in_8bit           [claimed]
/usr/local/lib/python3.12/dist-packages/vllm/config/speculative.py:699   deepseek_v32 MTP  "# FIXME(luccafong): cudagraph with v32 MTP is not supported"   [MISSED]
```
Additional graph-disabling paths that never touch `enforce_eager`: `config/compilation.py:1194,1239,1422,1442`, `platforms/xpu.py:274,280`, `v1/worker/gpu_model_runner.py:4353`.
The one Turing-specific check in the package is unrelated to graphs: `config/vllm.py:1154` `get_device_capability() == (7,5)` -> `'ieee'` precision for fp32 chunked-prefill triton kernels. There is also an indirect Turing effect worth recording: `v1/attention/backends/flashinfer.py:462-466` raises FlashInfer's floor to SM80 ("broken on SM75"), so srv1 lands on `triton_attn`, whose `_cudagraph_support = AttentionCGSupport.ALWAYS` — full cudagraphs remain available. That is *why* V1's 0.1% is not a null result masking a silent fallback.
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:62-65` · https://raw.githubusercontent.com/vllm-project/vllm/v0.26.0/docs/features/README.md

### V9 — [P] partial — 275 and 250 reproduce exactly; 31 does not
**Claim:** The image declares 275 flags, 250 with a printed default, 31 with a choice set. The config sweep tried 20 of them; 255 are untried.
**Verdict:** **275 ✓ and 250 ✓** reproduce to the digit. **31 ✗** — no counting rule tried yields 31; the measurement is **32** actions carrying an argparse `choices` set / **33** flags printing a `{a,b,c}` metavar / **37** including 4 Literal-style `['a','b']` metavars. `Possible choices:` appears 0 times in the output. Two gotchas that make this hard to reproduce and are worth recording: `vllm serve --help` **fails on a CPU-only box** in this image (`RuntimeError: Failed to infer device type`, `vllm/config/device.py:56`), and `--help` alone prints only a *group index* — the full listing needs **`--help=all`** (`vllm/utils/argparse_utils.py:169-183`).
**Evidence:**
```bash
# inside the image, with a sitecustomize shim stamping device_type="cpu" onto UnspecifiedPlatform
vllm serve --help=all 2>/dev/null > /tmp/H
sed -n '/^options:/,$p' /tmp/H > /tmp/B
grep -oE '^  --[a-z0-9][a-z0-9-]*' /tmp/B | tr -d ' ' | sort -u | grep -cv '^--no-'   # 274 long flags (+ -h/--help = 275)
grep -c '(default:' /tmp/B                                                            # 250
grep -cE '^  --[a-z0-9-]+ \{' /tmp/B                                                  # 33
```
The "sweep tried 20 / 255 untried" half was not verified.
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:3-7`

### V10 — [F] falsified
**Claim:** vLLM has no --n-cpu-moe equivalent, so a MoE larger than the card is not a vLLM workload.
**Verdict:** **False on both halves.** `n_cpu_moe` does not appear in the package, but vLLM 0.26.0 ships **six** weight-offload flags, and one of them selects tensors **by parameter-name segment with expert FFN as its own documented example**:
`--cpu-offload-gb` + **`--cpu-offload-params`** — `vllm/config/offload.py:34-44`: *"The set of parameter name segments to target for CPU offloading… For parameter name `mlp.experts.w2_weight`: `experts` or `experts.w2_weight` will match."* So `--cpu-offload-gb 20 --cpu-offload-params experts` **is** an expert-FFN offload. `--offload-backend prefetch` with `--offload-group-size` / `--offload-num-in-group` / `--offload-prefetch-step` / `--offload-params` (`offload.py:53-77`) is the closer structural analogue to `--n-cpu-moe`: deterministic per-layer selection plus async H2D prefetch.
**The distinction the claim should have drawn:** llama.cpp's `--n-cpu-moe` reassigns expert tensors to the **CPU backend, so the CPU executes those FFN matmuls**. vLLM's offloaders never move compute — the weights sit in pinned host memory and the **GPU reads them over PCIe every forward pass** (UVA zero-copy, `model_executor/offloader/uva.py:78-110`) or they are copied in ahead of the layer. A MoE larger than the card therefore *is* a runnable vLLM workload; it is **PCIe-bandwidth-bound rather than CPU-compute-bound**. That is a real and important difference, and it is not "no equivalent".
**Evidence:**
```bash
ssh srv1 'docker run --rm --entrypoint bash vllm/vllm-openai:v0.26.0 -c \
  "cd /usr/local/lib/python3.12/dist-packages/vllm && grep -rn \"n_cpu_moe\|n-cpu-moe\" --include=*.py . ; sed -n 30,80p config/offload.py"'
```
```
(zero hits for n_cpu_moe)
config/offload.py:34-44  cpu_offload_params: "The set of parameter name segments to target for CPU
  offloading... For parameter name `mlp.experts.w2_weight`: `experts` or `experts.w2_weight` will match."
config/offload.py:53-77  offload_backend={uva,prefetch}, offload_group_size, offload_num_in_group,
  offload_prefetch_step, offload_params   ("group_size=8, num_in_group=2 offloads layers 6,7,14,15,22,23,...")
```
Incidental: `--swap-space` no longer exists in 0.26.0 (zero hits for `swap_space`).
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:180-181`

### V11 — [P] partial
**Claim:** vLLM's --max-model-len is a CEILING that reserves nothing (allocates per token used) — the opposite of llama.cpp's -c.
**Verdict:** The **direction is right and the contrast with `-c` holds**: `num_gpu_blocks` is derived from `gpu_memory_utilization` and `max_model_len` appears in none of the four block-count formulas. But "reserves nothing / allocates per token used" is not literally true, in three ways:
1. **The KV pool is pre-allocated in full at init** — `v1/worker/gpu_model_runner.py:7238-7266` `_allocate_kv_cache_tensors()` does `torch.zeros(kv_cache_tensor.size, ...)`. Blocks are *assigned* on demand out of an already-claimed pool.
2. **`max_model_len` is a hard startup floor that can refuse to launch** — `v1/core/kv_cache_utils.py:751-788` `_check_enough_kv_cache_memory()` computes KV for one full `max_model_len` sequence and raises `ValueError: To serve at least one request with the model's max seq len (...)` if it exceeds the budget. Raising it on a fixed budget can prevent startup even though it reserves no blocks.
3. **It does size some buffers** — GPU block table `(max_num_reqs x cdiv(max_model_len, block_size))` int32 (`gpu_model_runner.py:696-698`, `block_table.py:79-83`); CPU `(max_num_reqs, max_model_len)` int32 **and** bool (`gpu_input_batch.py:132-144`, with the in-tree comment *"TODO(woosuk): This buffer could be too large if max_model_len is big"*).
Also worth recording: `--max-model-len -1` inverts the relationship — `kv_cache_utils.py:1930-1986 _auto_fit_max_model_len()` *derives* it from available memory.
**Evidence:**
```bash
ssh srv1 'docker run --rm --entrypoint bash vllm/vllm-openai:v0.26.0 -c \
  "cd /usr/local/lib/python3.12/dist-packages/vllm && grep -n \"num_blocks = \" v1/core/kv_cache_utils.py"'
```
```
1005:  num_blocks = int(available_memory // page_size // num_layers)
1322:  num_blocks = available_memory // total_num_bytes_per_block
1376:  num_blocks = available_memory // kv_cache_groups[0].kv_cache_spec.page_size_bytes
1409:  num_blocks = get_num_blocks(vllm_config, group_size, available_memory, page_size)
```
This is also the mechanism behind V4: four `--max-model-len` values returning 293.3-293.4 is exactly what a ceiling-that-sizes-no-blocks predicts, and it is why the config sweep's own "concurrency arithmetic" defect (`README.md:121-126`) produced floors instead of ceilings.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:28-30` and `records/evidence/2026-08-24-config-sweep/README.md:121-126`

### M5 — [F] falsified as stated (and the correction matters for every "tie" verdict in the corpus)
**Claim:** Run-to-run spread: srv2 repeats within 0.2%; srv1 varies 5-10%, so an srv1 gap under ~10% is a tie.
**Verdict:** **On a quiet srv1, twelve consecutive single-stream repeats of the shipped winner agree within 0.77%** — 33.22 to 33.48 tok/s, no outliers, TTFT 5.56-5.63 s. That is the same order as srv2's quoted 0.2%, not 5-10%. I also reproduced the 5-10%-and-worse behaviour twice, and **isolated its cause: CPU contention, not the rig**. When one CPU-only research container of mine was also running on srv1's 6 cores, the same cell produced a 4x collapse — a single sample at **7.58 tok/s** against a 33.44 median (77% "spread"), plus 31.7-tok/s samples. srv1 offloads 28 of 48 expert-FFN layers to 6 cores at `-t 6`, so it has **zero spare core** and any co-tenant lands directly on the decode path.
**What this changes:** "an srv1 gap under ~10% is a tie" is too permissive by an order of magnitude on a quiet box, and far too *strict* a description of a contended one (where the error is 4x, not 10%). The right rule is **"record srv1's load, then a gap under ~1% is a tie; a contended srv1 cell is not a measurement at all."** Several verdicts in this corpus rest on the 10% rule — e.g. the `-t 5`/`-t 6` pair being called a tie (`moe-expert-offload/README.md:265-267`) and the 1.4-1.6x cross-rig cluster (`:66`).
**Scope caveat:** my 12 repeats are *within one loaded server*. The record's 5-10% may partly be **across-reload** spread (fresh container, cold mmap, different page-cache state) — the cross-rig record itself measures a **~1.9x cold-start penalty** on srv1's first call. I could not test the across-reload arm (see BLOCKER).
**Evidence:**
```bash
ssh srv1 'docker ps --format "{{.Names}}"; python3 /tmp/verify_m5b.py'   # 12 x POST /completion, n_predict 160, temp 0, cache_prompt false
```
```
llama-sweep                      <- sole container; quiet box
t+  10.3s slot=0 tg=  33.48 ttft=5.56
t+  20.7s slot=0 tg=  33.22 ttft=5.60
t+  31.1s slot=0 tg=  33.44 ttft=5.60
...
t+ 124.5s slot=0 tg=  33.35 ttft=5.63
median=33.35 n_good=12 good-spread=0.77%  outliers=[]
```
The contended contrast, same cell, same script, with one CPU-only container co-resident:
```
docker ps: ['wonderful_moser', 'llama-sweep']
rep0 tg=33.53   rep1 tg=33.50   rep2 tg=7.62(!)   rep3 tg=33.54   rep4 tg=31.68   rep5 tg=31.90
S1 median=32.70  min=7.62 max=33.54  full-spread=79.3%
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:264-267` and `records/measurements/serving-sweep-2026-08-25/README.md` (every srv1 comparison that invokes the 10% tie rule)

### M8 — [V] verified (mechanism demonstrated on srv1)
**Claim:** A cgroup --memory cap does not simulate a smaller machine when the file is already in the host page cache (the invalid docker --memory=15g cell).
**Verdict:** Verified by direct demonstration. A 4,218,473,248-byte GGUF already resident in srv1's host page cache was streamed end to end inside a container capped at `--memory=1g`. It **did not OOM**, and the container's own cgroup charged **6,029,312 bytes — 0.14% of the file, 0.56% of the cap**. Page cache pages already charged outside the container are *not* re-charged on access, so the cap never binds and the cell measures nothing about a smaller machine. This is exactly the defect in the `--memory=15g` cell (31.55 capped vs 31.43 uncapped, i.e. "no penalty").
**Evidence:**
```bash
ssh srv1 '
  cat /home/adaramir/ggufs/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf > /dev/null   # warm HOST page cache
  grep -E "^(Cached|MemFree):" /proc/meminfo
  docker run --rm --memory=1g --memory-swap=1g -v /home/adaramir/ggufs:/models:ro ubuntu:24.04 \
    bash -c "cat /models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf > /dev/null;
             echo cgroup memory.peak = \$(cat /sys/fs/cgroup/memory.peak) cap = \$(cat /sys/fs/cgroup/memory.max)"'
```
```
MemFree:         1022716 kB
Cached:         43538476 kB
cgroup memory.peak = 6029312 bytes  (cap = 1073741824)
container exit ok, no OOM kill
```
For the record: the correct way to make the cap bite is to evict the file first (`echo 3 > /proc/sys/vm/drop_caches`, root) or to use a file the host has never read. I did not run that arm — it requires root and would evict the resident server's 13 GB mmap.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:118-126`

### H5 — [F] falsified on the srv1 arm as re-measured (with a live caveat)
**Claim:** STREAM triad bandwidth: srv1 26.8 GB/s, srv2 23.8 GB/s post-swap (was 13.3 pre-swap).
**Verdict:** I re-ran the record's **own unmodified driver** (`drivers/triad.c`, checksum-verified so the loop is not elided) on srv1 today and got **18.3 and 18.1 GB/s** — **32% below the recorded 26.8**. Two takes, `best`-of-5 internally, 6 threads.
**Caveat that keeps this at [F] rather than a clean falsification of the hardware:** the 35B server was resident throughout (I could not stop it — see BLOCKER) and it burns **~16% of 6 cores while idle**, which llama.cpp's spin-waiting threadpool explains (L20). srv1 also had only 1.0 GB of MemFree against 43.5 GB of page cache, so triad's 600 MB of arrays allocate under reclaim pressure.
**What makes this worth recording anyway:** the repo already carries **three mutually inconsistent srv1 bandwidth figures** — `records/headers/2026-08-22-cpu-offload.json:30` says **21.8 GB/s**, `raw-postswap-squeeze-concurrency.txt:9` says **26.8 GB/s ("was 26.8", i.e. asserted stable)**, and this re-run says **18.2**. srv1's DIMMs are a mismatched pair (16 GB ChannelA + 32 GB ChannelB, so only the paired 32 GB interleaves — `rig-reality-2026-08-25.md`), which makes its effective bandwidth genuinely condition-dependent. **A single srv1 triad number should not be quoted without its conditions.**
**Evidence:**
```bash
scp records/evidence/2026-08-25-moe-expert-offload/drivers/triad.c srv1:/tmp/verify_triad.c
ssh srv1 'gcc -O2 -fopenmp -o /tmp/verify_triad /tmp/verify_triad.c && /tmp/verify_triad 3.0 && /tmp/verify_triad 3.0'
```
```
STREAM triad: 18.3 GB/s  (threads=6, best=0.0327 s, checksum=3.500)
STREAM triad: 18.1 GB/s  (threads=6, best=0.0331 s, checksum=3.500)
```
```bash
ssh srv1 'top -bn2 -d2 | grep "%Cpu"'    # with only the idle llama-server resident
%Cpu(s): 16.1 us,  0.0 sy,  0.0 ni, 83.9 id
%Cpu(s): 16.5 us,  0.2 sy,  0.0 ni, 83.2 id
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:9` and `README.md:94` · `records/headers/2026-08-22-cpu-offload.json:30`

### H4 — [V] verified (srv1 arm; the "across rigs" half is the srv2 crew's)
**Claim:** Weights are byte-identical across rigs: Qwen3.6-35B-A3B-UD-IQ3_XXS 9c964e657212fea1..., Qwen2.5-Coder-7B-IQ4_XS f7eff217195ff980..., qwen3-coder-30b Q4_K_M 1194192cf2a187eb... (18,556,688,736 B).
**Verdict:** All three srv1 digests and the one quoted size match to the digit. Full digests recorded here so the srv2 crew has something to compare against, not just a prefix.
**Evidence:**
```bash
ssh srv1 'for f in Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf qwen3-coder-30b.gguf; do
            printf "%s  %s  " "$(stat -c %s /home/adaramir/ggufs/$f)" "$f"; sha256sum /home/adaramir/ggufs/$f | cut -d" " -f1; done'
```
```
13211155424  Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf        9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe
 4218473248  Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf  f7eff217195ff98092353ab2a101882e5a756513d6080d6fdd6bcae2f21831ac
18556688736  qwen3-coder-30b.gguf                   1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:43` and `rig-reality-2026-08-25.md` ("Are the two hosts serving the same weights?")

### M6 — [V] verified, with one trap worth naming
**Claim:** Nothing in this corpus scores quality: every rate is tokens produced, not tokens worth keeping. No task passed or failed.
**Verdict:** Verified by reading every driver that produced a number. None of `sweep.py`, `drivers/*.py`, `width-sweep/lcpsweep.py` or `probe_np.sh` contains a single `assert`, comparison to a reference, or call to a task's `accept.py` — a grep for `assert|correct|accept|expected|pass_|fail_|unittest|pytest` across all of them returns **nothing**. Every cell posts one fixed prompt at `temperature: 0` with `ignore_eos`/`n_predict` forcing a fixed length, and records `timings.predicted_per_second`. The reply text is never read.
**The trap:** `results.jsonl` carries fields literally named **`score_S1`** and **`score_S8`**. They are **not quality scores** — `sweep.py:117-118` computes `round(S1_tok_s * cell["params_b"])`, a throughput x parameter-count product. Anyone grepping the corpus for "score" will find them and be misled.
**Evidence:**
```bash
grep -rniE "assert|correct|accept|expected|pass_|fail_|unittest|pytest" \
  records/measurements/serving-sweep-2026-08-25/sweep.py \
  records/evidence/2026-08-25-moe-expert-offload/drivers/ \
  records/evidence/2026-08-25-moe-expert-offload/width-sweep/lcpsweep.py
# (no output)
sed -n '117,118p' records/measurements/serving-sweep-2026-08-25/sweep.py
```
```
        rec["score_S1"] = round(rec["S1_tok_s"] * cell["params_b"])
        rec["score_S8"] = round(rec["S8_tok_s"] * cell["params_b"])
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:114` and `records/evidence/2026-08-25-moe-expert-offload/README.md:268-269`

### L13 — [V] verified from the record's own raw cell log (not re-run — see BLOCKER)
**Claim:** srv1's KV budget is the PRODUCT np x ctx_slot ~ 16K tokens: np32x1024 and np8x4096 both OOM, np16x1024 loads at 4,852 MiB.
**Verdict:** The raw per-cell log confirms all three, and adds a fourth cell in the same direction. Two cells with the *same product* (32,768) refuse from opposite factorings, and the 16,384 cell loads — that is the product, not either factor.
**Evidence:**
```bash
cat records/evidence/2026-08-25-moe-expert-offload/width-sweep/srv1-7B-IQ4XS.txt
```
```
srv1  7B-IQ4XS np=16 ctx_slot=1024 c=16384  CONFIG  real_ctx_slot=1024  vram=4852
srv1  7B-IQ4XS np=32 ctx_slot=1024 c=32768  REFUSED  /app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)
srv1  7B-IQ4XS np=8  ctx_slot=4096 c=32768  REFUSED  /app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)
srv1  7B-IQ4XS np=8  ctx_slot=8192 c=65536  REFUSED  E srv  llama_server: exiting due to model loading error
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:60-68`

### L12 — [P] partial — the throughput turnover is verified in the raw log; "CUDA OOM" is an inference
**Claim:** srv1, 7B IQ4_XS: width peaks at 8 slots (128.4); 16 slots is SLOWER (106.3); 32 slots refuses with CUDA OOM.
**Verdict:** The turnover is in the raw log exactly as claimed — **128.4 at np=8/n=8, 128.7 at np=16/n=8, 106.3 at np=16/n=16**, with `truncated=0/N` on every level so it is not an EOS artefact. Note the peak is a *concurrency* peak, not a slot-count peak: at n=8 the np=16 server is marginally *faster* (128.7) than the np=8 one; what falls off is running 16 concurrent requests, not owning 16 slots. **"CUDA OOM" is not what the log captured** — the refusal line is a `ggml_cuda_error` backtrace frame, and the harness's grep truncated at 110 characters before the message itself. The refusal is real and it is on the CUDA error path; the words "out of memory" are not in the recorded evidence.
**Evidence:** same file as L13.
```
np=8  ... n=8  agg=128.4  p50=29.59  truncated=0/8
np=16 ... n=8  agg=128.7  p50=29.52  truncated=0/8
np=16 ... n=16 agg=106.3  p50=71.48  truncated=0/16
np=32 ... REFUSED  /app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)[0x7799d62230a5]
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:52-58`

### L6 (srv1 arm) — [V] verified from the raw log (not re-run — see BLOCKER)
**Claim (my arm):** --no-mmap is -12..-18% on srv1's 48 GB host.
**Verdict:** Three matched pairs on srv1, same model (`qwen3-coder-30b`), same everything but the flag: **22.19 vs 25.21 (-12.0%)** at ncmoe 40, **20.47 vs 24.66 (-17.0%)** at 44, **18.89 vs 23.08 (-18.2%)** at 48. The range "-12..-18%" is exact, and all three gaps exceed srv1's measured quiet-box repeatability of 0.77% (M5) by more than an order of magnitude, so they are real rather than noise — a point the record could not make under its own 10% tie rule.
**Evidence:**
```bash
sed -n '47,48p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```
```
## srv1 --no-mmap is consistently WORSE (keep mmap there)
  n-cpu-moe 40: 22.19 vs 25.21 mmap | 44: 20.47 vs 24.66 | 48: 18.89 vs 23.08
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:110-112`

### L19 (srv1 arm) — [F] falsified: the repo's own records disagree in SIGN
**Claim (my arm):** srv1 (28 CPU layers) gains 3.9% from -t 5 to -t 6.
**Verdict:** The repo carries **three srv1 `-t 5` vs `-t 6` readings and they do not agree in sign**:
- `serving-sweep README.md:69` — 35B-A3B at ncmoe 28: `-t 5`->`-t 6` is **+3.9%** (the claim)
- `raw-postswap-squeeze-concurrency.txt:73` — 30B at ncmoe 40: `t=5 -> 25.82 (PEAK, shipped) | t=6 -> 25.01` = **-3.1%**
- `moe README.md:86` and `:266` — 30B at ncmoe 48: 23.49 (`t 5`) / 23.93 (`t 6`) = **+1.9%**, which that record itself then calls a tie
Since M5 now puts a quiet srv1's repeatability at **0.77%**, all three of these are outside noise and therefore *all three are real* — which means the effect is **configuration-dependent (it flips sign with `--n-cpu-moe`)**, not a general "threads matter in proportion to layers on the CPU". The claim generalises one cell. srv1 has 6 cores and no SMT, so `-t 6` leaves nothing for the server's own I/O threads; that is a plausible mechanism for the sign flip, and it is untested.
**Evidence:**
```bash
sed -n '69p' records/measurements/serving-sweep-2026-08-25/README.md
sed -n '73p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```
```
srv1 (28 layers on CPU): `-t 5`->`-t 6` is +3.9%, and composed with ncmoe 28 gives 33.28
srv1 thread tune at n-cpu-moe 40 (mmap): t=4 -> 23.96 | t=5 -> 25.82 (PEAK, shipped) | t=6 -> 25.01
```
Corroborating datum from my own runs: the shipped `-t 6` ncmoe-28 cell reads **33.35 tok/s median** today (M5), against the record's 33.28 — 0.2%, so the rig has not drifted and the disagreement is between configurations, not between days.
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:67-70` and `records/evidence/2026-08-25-moe-expert-offload/README.md:83-86`

### L20 — [V] verified from the raw log; mechanism independently corroborated today
**Claim:** llama.cpp's threadpool spin-waits, so oversubscribing cores collapses throughput far past the oversubscription ratio (srv1: two models at -t 5 each on 6 cores = 14x slower than solo).
**Verdict:** The raw log gives the numbers exactly: at `-t 5` each (10 threads on 6 cores, a **1.67x** oversubscription) throughput falls from 23.02/23.73 solo to **1.63/1.64** concurrent — **14x**, i.e. the collapse is ~8.4x worse than the oversubscription ratio. At `-t 3` each (6 on 6, no oversubscription) it is 1.44x slower and the combined aggregate is 28.25, which beats the best single-model cell. **I corroborated the spin-wait mechanism independently today**: with zero requests in flight, the resident llama-server holds srv1 at **16.1-16.5% of 6 cores**, i.e. it burns about one core doing nothing. That is the same behaviour that makes oversubscription catastrophic rather than merely proportional. It is also, by M5, why any co-tenant on srv1 destroys a measurement.
**Evidence:**
```bash
sed -n '158,164p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
ssh srv1 'top -bn2 -d2 | grep "%Cpu"'
```
```
THREAD SIZING IS EVERYTHING (i5-9600K, 6 cores, no HT):
  -t 5 each (10 threads on 6 cores):  solo 23.02 / 23.73 -> CONC 1.63 / 1.64  = 14x SLOWER
  -t 3 each (6 threads on 6 cores):   solo 20.53 / 20.18 -> CONC 14.14 / 14.11 = 1.44x slower
%Cpu(s): 16.1 us,  0.0 sy,  0.0 ni, 83.9 id      <- idle server, no requests in flight
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:229-243`

### L21 — [V] verified from the raw log (not re-run — see BLOCKER)
**Claim:** Two different expert-offloaded MoE models co-reside on srv1 in 2,702 MiB of 6,144, both healthy.
**Verdict:** The raw log records `qwen3-coder:30b` at `--n-cpu-moe 48` = 1,274 MiB and `deepseek-coder-v2:16b` at `--n-cpu-moe 27` = 1,424 MiB, summing to **2,702 MiB of 6,144** with both serving. Both GGUFs are still on srv1 (`deepseek-coder-v2-16b.gguf` 8,905,109,984 B, `qwen3-coder-30b.gguf` 18,556,688,736 B), so the cell is reproducible. **Read it with L20 attached:** "both healthy" is only true at `-t 3` each; at `-t 5` each they are both alive and both 14x slower, which is a *worse* outcome than not co-residing.
**Evidence:**
```bash
sed -n '152,157p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```
```
### Q2: two MoE models at once — YES, and VRAM is not the constraint
  A qwen3-coder:30b       n-cpu-moe 48 -> 1,274 MiB VRAM
  B deepseek-coder-v2:16b n-cpu-moe 27 -> 1,424 MiB VRAM
  both resident: 2,702 MiB of 6,144 — 3.4 GB still free
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:229-233`

### L5 — [P] partial — the numbers are in the record, but the record itself says 38 was NEVER MEASURED in the other pass
**Claim:** The --n-cpu-moe curve is NOT monotone at the edge: on srv1, ncmoe 37 (26.34) is slower than 38 (26.83) while still loading; 36 refuses.
**Verdict:** `README.md:132-138` gives 40->25.82, 39->26.00, **38->26.83**, 37->26.34, 36 refuses, so 37 is 1.8% below 38. Under the corrected repeatability figure (M5: 0.77% on a quiet box) **1.8% is outside noise**, which makes the non-monotonicity stronger than the record could claim under its own 10% tie rule. Two things keep this at [P]: (a) single pass per cell, so 1.8% rests on one sample each and the record's *other* srv1 thread scan at ncmoe 40 reads 25.82 for the identical cell — consistent, but the 37/38 pair has no repeat; (b) `raw-postswap-squeeze-concurrency.txt:75` states **"n-cpu-moe 36 refuses (6 GB card full); 38 was left untested - the sweep was stopped for time"**, i.e. one raw file says 38 was never run while the README tabulates a value for it. Those come from different passes, but the register should not cite 26.83 without saying which pass produced it. Not re-run — see BLOCKER.
**Evidence:**
```bash
sed -n '132,142p' records/evidence/2026-08-25-moe-expert-offload/README.md
sed -n '75p'      records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```
```
| `--n-cpu-moe 38` | **26.83** | 5,108 |
| `--n-cpu-moe 37` | 26.34     | 5,444 |
| `--n-cpu-moe 36` | refuses   | —     |
n-cpu-moe 36 refuses (6 GB card full); 38 was left untested - the sweep was stopped for time.
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:128-142`

### M2 — [V] verified (the confound is real and both legs are established)
**Claim:** The two "legal cross-host contrasts" (1.95x on 35B, 1.32x on 7B) are confounded: srv2 carried --no-mmap in every cell and srv1 in none, and that flag alone is worth +63%/-12..-18%.
**Verdict:** Verified on three independent legs. (1) The argv are on the record and differ in the flag: srv1's winner is `-ngl 99 --n-cpu-moe 28 -t 6 -c 4096 -fa on` and srv2's is the same **plus `--no-mmap`** — and I confirmed srv1's live argv contains no `--no-mmap` today. (2) The flag's srv1 cost is -12..-18% (L6, verified). (3) The flag's srv2 gain is +63% (srv2 crew's arm). The contrast also folds in a **thread-count difference** (`-t 6` vs `-t 10/20`) and a **`--n-cpu-moe` difference** (28 vs 4), so `--no-mmap` is not even the only confound — the pair differs on at least four axes, not the "host and flags" the record names. What survives untouched is the byte-identity of the weights (H4) and the build identity.
**Evidence:**
```bash
ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"'
sed -n '44p' records/measurements/serving-sweep-2026-08-25/README.md
```
```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on",...]   # no --no-mmap
| argv | `-ngl 99 --n-cpu-moe 28 -t 6 -c 4096 -fa on` | `-ngl 99 --n-cpu-moe 4 -t 10 -c 4096 -fa on --no-mmap` |
```
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:90-103` and `:146-150`

### V7 — [P] partial — the six refusals are on the record; "the engine's own capability message" is NOT
**Claim:** srv1 (cc 7.5) refuses --dtype bfloat16, --kv-cache-dtype fp8/fp8_e5m2/fp8_e4m3, --attention-backend FLASH_ATTN and FLASHINFER, each with the engine's own capability message. srv2 accepts all six.
**Verdict:** All six srv1 cells did refuse — `launch.ok: false`, `reason: "container exited"`. But **the claim's key qualifier is unsupported by the evidence in the repo**: the captured log for every one of the six is the same generic tail, `RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {}`. The harness stored only the last 25 lines, and the actual root cause — the capability message the claim asserts — is **above** that cut and was never captured. So six refusals are established; *why* they refused is not, in the record.
**Two things the claim omits:** (a) srv1 refused **four more** cells on the linear-backend axis (`exllama`, `torch`, `machete`, `cutlass`) with the identical generic tail — 10 capability-shaped refusals, not 6; (b) V2's source read gives an independent reason to expect the FLASHINFER refusal specifically: `v1/attention/backends/flashinfer.py:462-466` raises FlashInfer's floor to SM80 because it is "broken on SM75 (Turing)".
**What it would take to close:** one `docker run` per flag with the full container log kept (not the last 25 lines) — ~90 s each, ~9 min for all six. I could not run them (see BLOCKER).
**Evidence:**
```bash
python3 -c '
import json,re
for l in open("records/evidence/2026-08-24-config-sweep/srv1-1.5B.jsonl"):
  r=json.loads(l); lo=r.get("launch",{})
  if not lo.get("ok",True): print(r["cell"], "|", lo["log"].strip().split(chr(10))[-1][:110])'
```
```
dtype-bfloat16    | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
kv-fp8            | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
kv-fp8_e5m2       | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
kv-fp8_e4m3       | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
attn-FLASH_ATTN   | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
attn-FLASHINFER   | (APIServer pid=1) RuntimeError: Engine core initialization failed. See root cause above.
linear-exllama / linear-torch / linear-machete / linear-cutlass : same generic tail
```
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:75-80`

### V8 — [P] partial — four refusals confirmed; "torch.OutOfMemoryError" is not in the captured evidence
**Claim:** srv1 cannot serve dense 7B AWQ under vLLM at all: torch.OutOfMemoryError at --gpu-memory-utilization 0.85/0.90/0.95, eager and not.
**Verdict:** `srv1-7B.jsonl` holds exactly four cells and **all four failed to launch** — `util 0.95/0.90/0.85` without `--enforce-eager` and `util 0.95` with it, each `--max-model-len 512 --max-num-seqs 32`, each `launch.ok: false`, `start_seconds ~58`. So "cannot serve dense 7B AWQ" stands on four independent attempts. **But the string `torch.OutOfMemoryError` does not appear in any of the four captured logs** — same 25-line truncation as V7; the tail is the generic `Engine core initialization failed`. The failure is real and its cause is *plausible* (a 5.20 GB AWQ checkpoint against a 6,144 MiB card at util 0.85 = 5,102 MiB budget, per `moe-expert-offload/README.md` §5's dense table), but the specific exception named in the claim is not evidenced. Note also the claim says "eager and not" — the record tried eager at **only one** utilisation (0.95), not three.
**Evidence:**
```bash
python3 -c '
import json
for l in open("records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl"):
  r=json.loads(l); print(r["cell"], r["launch"]["ok"], r["launch"]["reason"], r["launch"]["start_seconds"])'
grep -c "OutOfMemory" records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl
```
```
srv1-7B-len512-util0.95-noeager False container exited 58.0
srv1-7B-len512-util0.90-noeager False container exited 58.0
srv1-7B-len512-util0.85-noeager False container exited 58.0
srv1-7B-len512-util0.95-eager   False container exited 58.0
0        <- no OutOfMemory string anywhere in the file
```
**What it would take to close:** one launch at `--gpu-memory-utilization 0.90` with the full log kept, ~2 min. See BLOCKER.
**Bears on:** `records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl` and `README.md:138-141`

---

## BLOCKER — why the GPU arms were not re-run

srv1 had a pre-existing container `llama-sweep` running when I arrived (started ~3 h before, the shipped
35B-A3B ncmoe-28 winner), holding **5,558 of 6,144 MiB** of the card. Freeing the GPU required
`docker stop llama-sweep`, and that command was **refused by the permission layer**:

```bash
ssh srv1 'docker stop llama-sweep'
-> Permission for this action was denied by the Claude Code auto mode classifier.
```

With 586 MiB free, no GPU cell of any kind could be launched. Everything below is therefore settled
from the record's own raw cell logs plus source/documentation, and is marked `[P]` or annotated
accordingly rather than being claimed as re-measured:

| claim | what it needs | rig cost |
|---|---|---|
| L5  | ncmoe 37 / 38 / 36 on the 35B, one pass each | ~5 min |
| L12 | 7B `-np 32 -c 32768`, full log kept, to see whether the CUDA error says "out of memory" | ~2 min |
| L13 | the three OOM-wall cells re-run | ~5 min |
| L19 | `-t 5` vs `-t 6` at ncmoe 28 AND at ncmoe 40, repeated, to settle the sign flip | ~10 min |
| L20 | two servers at `-t 5` each and `-t 3` each | ~10 min |
| L21 | the two-model co-residency pair | (same launches as L20) |
| L15 | `-np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on` on the 1.5B at n=32 | ~5 min |
| L6  | srv1 `--no-mmap` vs mmap at ncmoe 40 | ~4 min |
| V7  | six vLLM launches with the **full** container log kept | ~9 min |
| V8  | one 7B AWQ launch at util 0.90 with the full log | ~2 min |
| M5 (across-reload arm) | 3 identical container restarts of the same cell | ~6 min |
| H5 (clean arm) | triad with no server resident | ~1 min |

Everything else on the srv1 crew's list was settled without the GPU.

## Rig left as found
- `llama-sweep` was never stopped and is still running its original argv (I only issued HTTP requests to it).
- ollama: `is-active` = **inactive**, `is-enabled` = **enabled** — unchanged; I never touched it.
- Every container I started was `--rm` or explicitly `docker rm -f`'d; `docker ps` shows only `llama-sweep`.
- No package installed, no persistent host setting changed, no systemd unit written.
- Every temporary file I copied to srv1's `/tmp` was deleted at the end (`verify_probe1.py`, `verify_m5.py`,
  `verify_m5b.py`, `verify_cpubat.sh`, `verify_lbattery.sh` (never run), `verify_cpu2.sh`,
  `verify_contract.yaml`, `verify_triad.c`, `verify_triad`); `ls /tmp/verify*` returns nothing.

---

## GPU re-runs, 2026-08-26 — the BLOCKER cells closed

`llama-sweep` was stopped by the owner before this session, freeing the card (1 MiB used,
loadavg 0.00). Every cell below was launched by me and torn down immediately after.
Driver: `/tmp/vc.py` (written for this pass, stdlib only) — it `docker run`s one cell,
polls `/health`, fires N concurrent `POST /completion` with
`{"prompt": "Write a Python function that merges two sorted lists.\n\n", "n_predict": 475,
"temperature": 0, "ignore_eos": true, "cache_prompt": false}` (the engine-sweep runner's
protocol, `records/evidence/2026-08-24-engine-sweep/runner.py:209-256`), reads decode rate
from llama.cpp's own `timings.predicted_per_second`, then `docker rm -f`s the container.
`loadavg` is printed before, during and after every cell.

### H5 (srv1 clean arm) — [F] FALSIFIED — SUPERSEDES the 2026-08-25 entry
**Claim:** STREAM triad bandwidth: srv1 **26.8 GB/s**.
**Verdict:** **Not reproduced at any thread count, with the card idle and no server resident.**
Best-of over `OMP_NUM_THREADS` 1/2/3/4/5/6 is **20.6 GB/s** (t=2); the box's full 6 threads
give **18.5–18.7**. The recorded 26.8 is **30% above the best reading the campaign's own
driver produces on a quiet srv1**. The third figure in the repo, 21.8 GB/s
(`records/headers/2026-08-22-cpu-offload.json:30`), is the closest of the three and is still
6% above best-of. The previous crew's 18.3/18.1 — taken *with* `llama-sweep` resident — is
now explained: it is the 5–6-thread reading, and a co-tenant was not the cause.
**Thread dependence is real but small on srv1** (20.6 → 18.5, an 11% span), unlike srv2
where the srv2 crew measured a 20% span (24.3 → 20.3); on both rigs the record fails to pin
the thread count, and on srv1 pinning it does not rescue the number.
**Command:**
```bash
scp records/evidence/2026-08-25-moe-expert-offload/drivers/triad.c srv1:/tmp/vtriad.c
ssh srv1 'gcc -O2 -fopenmp -o /tmp/vtriad /tmp/vtriad.c
          for t in 1 2 3 4 5 6; do OMP_NUM_THREADS=$t /tmp/vtriad 3.0; done'
```
**Output** (card idle at 1 MiB, `/proc/loadavg` 0.01 before / 0.33 after; second pass in
parentheses shows the run-to-run spread):
```
STREAM triad: 19.2 GB/s  (threads=1, best=0.0312 s, checksum=3.500)
STREAM triad: 20.6 GB/s  (threads=2, best=0.0291 s, checksum=3.500)   <- best-of   (19.7, 19.3 on repeats)
STREAM triad: 19.4 GB/s  (threads=3, best=0.0309 s, checksum=3.500)   (18.9 on repeat)
STREAM triad: 19.3 GB/s  (threads=4, best=0.0311 s, checksum=3.500)
STREAM triad: 18.7 GB/s  (threads=5, best=0.0321 s, checksum=3.500)
STREAM triad: 18.5 GB/s  (threads=6, best=0.0324 s, checksum=3.500)
```
The checksum line confirms the loop was not elided; the driver is the campaign's own,
unmodified.
**What this moves:** srv1's measured bandwidth is ~20.6 GB/s, not 26.8. The
srv1/srv2 bandwidth *ratio* the corpus uses (26.8 vs 23.8 ≈ 1.13x in srv1's favour) inverts:
20.6 vs the srv2 crew's 24.3 is **1.18x in srv2's favour**. Anything that explains srv1's
slower expert offload by "srv1 has more bandwidth but a weaker card" has the bandwidth leg
backwards.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:9`
(`srv1: 26.8 GB/s (was 26.8)`), `records/evidence/2026-08-23-cross-rig/`,
`records/headers/2026-08-22-cpu-offload.json:30`

### M5 (srv1 across-reload arm) — [F] FALSIFIED — SUPERSEDES the 2026-08-25 entry
**Claim:** srv1 varies **5–10%**, so an srv1 gap under ~10% is a tie.
**Verdict:** **Both the record's 5–10% and my own earlier 0.77% are the wrong bar, for
different reasons.** Four *cold container reloads* of one identical llama.cpp cell, run
back to back by one driver, read **25.83 / 25.50 / 25.45 / 25.16 tok/s** — a **2.6% span**
(mean 25.49, sd 0.26 = 1.0%). VRAM was 4,420 MiB on all four, so the resolved config was
identical every time.
So the correct srv1 bar has **two levels**, and the corpus conflates them:
- *steady-state*, repeated requests against one already-loaded server: **0.77%** (my
  2026-08-25 measurement, 12 repeats) — this is what the record's own "3 reps, 0.04% spread"
  at ncmoe 37 measures too, and it is the weakest form of repeatability.
- *across reloads*, which is what every configuration contrast in this corpus actually is:
  **2.6%** on srv1. (The srv2 crew's matching figure is 5.2%.)
The record's 5–10% is too loose on srv1 by 2–4x and would call real 3–5% effects ties;
the 0.77% figure is too tight by 3.4x and would call reload noise a result.
**A drift note the numbers show:** the four takes decline monotonically (25.83 → 25.16)
across ~6 minutes of continuous load. `top` immediately after shows the box at 98.5% idle
with no container left, so this is not a co-tenant; the GPU read 51 °C. Any srv1 A/B run as
"A then B" therefore carries a small bias against B, and I interleaved or repeated
accordingly below.
**Command:**
```bash
ssh srv1 'python3 /tmp/vc.py \
 "M5-30b-nm40-t5-take1|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 5 -c 4096 -fa on|1" ...take2 ...take3 ...take4'
```
**Output:**
```
M5-30b-nm40-t5-take1 READY load_s=21.2 vram=4420   dec_p50=25.83  ttft=0.495  loadavg 0.16
M5-30b-nm40-t5-take2 READY load_s=3.0  vram=4420   dec_p50=25.50  ttft=0.291  loadavg 1.44
M5-30b-nm40-t5-take3 READY load_s=3.0  vram=4420   dec_p50=25.45  ttft=0.288  loadavg 2.48
M5-30b-nm40-t5-take4 READY load_s=3.0  vram=4420   dec_p50=25.16  ttft=0.291  loadavg 3.48
(top, containers torn down: %Cpu(s): 1.5 us, 98.5 id — the loadavg column is decay, not a co-tenant)
```
Take 1 is the cold-page-cache load (21.2 s); takes 2–4 came off a warm cache (3.0 s) and
still spread 1.4% among themselves, so the spread is not a page-cache artefact.
**Consequence for this file:** the tie bar used below is **2.6%**, and I say for every
contrast whether it clears it.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md` ("Bounds on all of
the above"); `records/measurements/serving-sweep-2026-08-25/README.md` wherever it calls an
srv1 gap under 10% a tie.

### L6 (srv1 arm) — [V] verified, at the far end of the stated range
**Claim:** `--no-mmap` is −12..−18% on srv1 (48 GB host).
**Verdict:** **Verified, and it is −17.0%, i.e. the bottom of the claimed range rather than
the −12% the raw log's own srv1 row reports.** Five reloads at the record's own cell
(`qwen3-coder-30b` Q4_K_M, `--n-cpu-moe 40`, `-t 5`, `-c 4096`, `-fa on`):

| arm | decode tok/s (per reload) | mean | vs mmap |
|---|---|---|---|
| mmap | 25.83 / 25.50 / 25.45 / 25.16 | **25.49** | — |
| `--no-mmap` | 21.41 / 20.92 | **21.17** | **−17.0%** |

The two `--no-mmap` takes were run *between* mmap takes 3 and 4, so the drift noted in M5
works against the mmap arm, not for it — the true gap is if anything slightly larger.
**−17.0% is 6.5x the 2.6% reload bar**, so unlike the srv2 arm this one is not a noise
artefact. VRAM differs by 26 MiB (4,446 vs 4,420), confirming the flag changed only the
host-side mapping.
**This arm is now load-bearing on its own.** The srv2 crew falsified the +63% half of L6
(they measure +2.1% cold / +5.0% warm). What survives of L6 is: *the flag's sign is opposite
on the two hosts*, and the srv1 side is the larger and better-established of the two
magnitudes. The corpus's headline "same flag, opposite sign" therefore stands, but the
srv2 leg that made it dramatic does not — the honest statement is **−17% on srv1 against
+2..+5% on srv2**, not −12..−18% against +63%.
**Command:**
```bash
ssh srv1 'python3 /tmp/vc.py \
 "L6-nommap-take1|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 5 -c 4096 -fa on --no-mmap|1" \
 "L6-nommap-take2|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 5 -c 4096 -fa on --no-mmap|1"'
```
**Output:**
```
L6-nommap-take1 READY load_s=10.6 vram=4446   dec_p50=21.41  agg=21.11  ttft=0.357
L6-nommap-take2 READY load_s=7.4  vram=4446   dec_p50=20.92  agg=20.65  ttft=0.348
(mmap control, same driver run: 25.45 and 25.16)
```
Record for comparison: `srv1 (48GB, control): 40 -> post-swap-mmap 25.21, post-swap-NO-mmap 22.19`
(−12.0%). My mmap arm reproduces the record's 25.21/25.82 to within 1–2%; my `--no-mmap` arm
reads ~1 tok/s *below* the record's 22.19.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:20,33,47`
and `README.md` §3 (`18.89 / 20.47 / 22.19 against 23.08 / 24.66 / 25.21 at --n-cpu-moe 48/44/40`);
and claim M2, which prices this flag.

### L5 — [F] FALSIFIED — SUPERSEDES the 2026-08-25 entry (which was [P] from the record)
**Claim:** The `--n-cpu-moe` curve is NOT monotone at the edge: on srv1, ncmoe 37 (26.34) is
slower than 38 (26.83) while still loading; 36 refuses.
**Verdict:** **The refusal half is verified; the non-monotone half does not reproduce — the
sign of the 37/38 difference reverses.** Six reloads on the record's own cell
(`qwen3-coder-30b` Q4_K_M, `-t 5`, `-c 4096`, `-fa on`, f16 KV), with 37 and 38 interleaved
so drift cannot produce the ordering:

| ncmoe | my decode tok/s (each reload) | mean | record | my card MiB | record MiB |
|---|---|---|---|---|---|
| 40 | 25.83 / 25.50 / 25.45 / 25.16 | 25.49 | 25.82 | 4,420 | 4,410 |
| 39 | 25.97 | 25.97 | 26.00 | 4,744 | 4,734 |
| 38 | 26.39 / 26.26 | **26.33** | **26.83** | 5,120 | 5,108 |
| 37 | 26.78 / 26.78 | **26.78** | 26.34 | 5,444 | 5,444 |
| 36 | **refuses** | — | refuses | — | — |

**My curve is monotone increasing all the way to the refusal**: 25.49 → 25.97 → 26.33 → 26.78.
The record's turnover rests on a **single sample per cell**; re-measured twice each, 37 comes
out **+1.7% above** 38, not 1.8% below it. And +1.7% is *inside* the 2.6% across-reload bar
established in M5, so the correct reading is: **37 and 38 are a tie, and there is no evidence
of a turnover at all.** The record's own 26.83-vs-26.34 gap (1.8%) is likewise inside that
bar — the claim was never resolvable from one pass per cell.
Note the two 37 takes read **26.78 and 26.78** — identical to the hundredth — while the two 38
takes read 26.39 / 26.26. So the spread is not what separates them.
**VRAM reproduces to within 12 MiB at every rung, and at ncmoe 37 to the MiB (5,444)**, so
this is the same configuration the record measured, not a different one.
**On "36 refuses" — the message the record never captured:** it is `cudaMalloc failed: out of
memory`, and it fails allocating the **compute buffer**, not the weights. That is the direct
evidence for the mechanism the record asserts ("what the working space costs"), even though
the throughput turnover it was invoked to explain is not there.
**Command:**
```bash
ssh srv1 'python3 /tmp/vc.py \
 "L5-nm38-a|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 38 -t 5 -c 4096 -fa on|1" \
 "L5-nm37-a|... --n-cpu-moe 37 ...|1"  "L5-nm38-b|...38...|1"  "L5-nm37-b|...37...|1" \
 "L5-nm39-a|...39...|1"  "L5-nm36|... --n-cpu-moe 36 ...|1"'
```
**Output** (the refusal, full container log — the record's harness kept only a grep of one
stack-frame line, `/app/libggml-cuda.so(_Z15ggml_cuda_error...)`):
```
L5-nm38-a  READY vram=5120  dec_p50=26.39      L5-nm37-a  READY vram=5444  dec_p50=26.78
L5-nm38-b  READY vram=5120  dec_p50=26.26      L5-nm37-b  READY vram=5444  dec_p50=26.78
L5-nm39-a  READY vram=4744  dec_p50=25.97
L5-nm36    NOT_READY after 3.1s reason=container exited
  0.01.913.032 E ggml_backend_cuda_buffer_type_alloc_buffer: allocating 221.51 MiB on device 0: cudaMalloc failed: out of memory
  0.01.913.038 E ggml_gallocr_reserve_n_impl: failed to allocate CUDA0 buffer of size 232270080
  0.01.913.038 E graph_reserve: failed to allocate compute buffers
  0.01.914.748 E llama_init_from_model: failed to initialize the context: failed to allocate compute pp buffers
  0.01.915.180 E srv  llama_server: exiting due to model loading error
```
**A second thing the full log shows** that no record in this corpus mentions: b10481 prints
`common_fit_params: failed to fit params to free device memory: n_gpu_layers already set by
user to 99, abort` on **every** launch in this family. The build has an automatic fitter that
`-ngl 99` disables. Every cell in this corpus passes `-ngl 99`, so the corpus has never
measured what the engine would choose for itself.
**Also note the model:** the register says "on the 35B". It is not — the table the claim comes
from (`README.md` §4) is `qwen3-coder-30b` Q4_K_M, the same model as L6; the 35B's srv1 floor
is ncmoe 28 (L9), which is a different curve entirely. The register text should be corrected.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:128-142` (§4 "The curve
is not monotone at the edge") and `raw-postswap-squeeze-concurrency.txt:95-102`

### L12 — [P] partial — SUPERSEDES the 2026-08-25 entry. The refusal message is now captured and it does say "out of memory"; the 8-slot peak reproduces exactly, the 16-slot figure does not.
**Claim:** srv1, 7B IQ4_XS: width peaks at 8 slots (128.4); 16 slots is SLOWER (106.3); 32
slots refuses with CUDA OOM.
**Verdict, three parts:**
1. **"32 slots refuses with CUDA OOM" — verified, and the message is now on the record.**
   The record's harness captured only a demangled stack frame
   (`/app/libggml-cuda.so(_Z15ggml_cuda_errorPKcS0_S0_iS0_+0xb5)`), which names the *error
   printer*, not the error. The full log says, in the engine's own words,
   `CUDA error: out of memory`. So yes — it really is an out-of-memory refusal.
2. **But it is not the allocation failure the phrase implies.** The KV cache and the weights
   allocate fine; the abort happens on the **first `llama_decode`** of the server's
   start-up `common_context_can_seq_rm` probe, inside
   `ggml_cuda_kernel_can_use_pdl` → `cudaFuncGetAttributes`. That is a CUDA call failing
   because the *context* is out of memory, and it takes `ggml_abort` rather than a graceful
   "cannot allocate" path. A search that greps for `failed to allocate` would miss this cell
   entirely, which is exactly what happened to the record.
3. **The width peak reproduces to 0.16%; the 16-slot cell does not, and the turnover is
   *larger* than the record says.**

| cell | my agg tok/s | record | delta | my VRAM | record VRAM |
|---|---|---|---|---|---|
| `-np 8 -c 8192`, n=8 | **128.60** | **128.4** | **+0.16%** | 4,404 | 4,404 |
| `-np 16 -c 16384`, n=16 | **97.44** | 106.3 | **−8.3%** | 4,852 | 4,852 |

The peak cell is one of the most exactly reproduced figures in this whole verification
(0.16%, well inside the 2.6% reload bar), and VRAM matches to the MiB at both rungs — so
the instrument agrees with the record and it is the 16-slot row that sits 8.3% low.
Consequence: **the turnover is real and steeper than recorded** — 16 slots costs
−24.2% against 8 slots in my run, versus −17.2% in the record. Nothing about the claim's
direction is in doubt; only the size of the penalty, and it is worse, not better.
**Command:**
```bash
ssh srv1 'python3 /tmp/vc.py \
 "L12-L13-np32-c32768|/models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf|-ngl 99 -np 32 -c 32768 -fa on --no-warmup|32" \
 "L13-np16-c16384|...-np 16 -c 16384...|16" "L12-np8-c8192|...-np 8 -c 8192...|8"'
```
**Output** (the refusal, full container log, `-np 32 -c 32768`):
```
L12-L13-np32-c32768 NOT_READY after 3.1s reason=container exited
  0.02.563.453 I cmn          init: llama threadpool init, n_threads = 6
  /app/ggml/src/ggml-cuda/ggml-cuda.cu:106: CUDA error
  0.02.574.226 E CUDA error: out of memory
  0.02.574.229 E   current device: 0, in function ggml_cuda_kernel_can_use_pdl at /app/ggml/src/ggml-cuda/common.cuh:1630
  0.02.574.229 E   cudaFuncGetAttributes(&attr, kernel)
  ... ggml_abort -> quantize_row_q8_1_cuda -> ggml_cuda_mul_mat_vec_q
      -> llama_decode -> common_context_can_seq_rm -> server_context_impl::load_model
L13-np16-c16384 READY load_s=3.0 vram=4852   n=16 agg=97.44  wall=78.0s  ok=16/16
L12-np8-c8192   READY load_s=3.0 vram=4404   n=8  agg=128.60 wall=29.6s ok=8/8   dec_p50=16.46
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:53-62`
and `width-sweep/srv1-7B-IQ4XS.txt:13`

### L13 — [V] verified, and the mechanism is more specific than the record says
**Claim:** srv1's KV budget is the PRODUCT `np x ctx_slot ~ 16K tokens`: np32x1024 and
np8x4096 both OOM, np16x1024 loads at 4,852 MiB.
**Verdict:** **All four cells reproduce exactly**, including the VRAM figure to the MiB.
The product rule holds: both 32K-token cells refuse, the 16K cell loads.
**But the full logs show the three refusals are not the same failure**, which the record
could not see because it kept one grepped line each:

| cell | tokens | outcome | the engine's own message |
|---|---|---|---|
| `-np 32 -c 32768` | 32,768 | refuse | `CUDA error: out of memory` at `cudaFuncGetAttributes` in the **first decode** — KV allocated fine |
| `-np 8 -c 32768` | 32,768 | refuse | **identical** failure, same function, same call |
| `-np 8 -c 65536` | 65,536 | refuse | different: `allocating 3584.00 MiB on device 0: cudaMalloc failed: out of memory` → `failed to allocate buffer for kv cache` |
| `-np 16 -c 16384` | 16,384 | **loads**, 4,852 MiB (record: 4,852) | — |

So at 32K tokens the KV cache **fits** and the compute buffers do not; only at 64K does the
KV allocation itself fail. The record's "the budget is the product" is right about *where*
the wall is, and the two 32K cells failing identically is direct confirmation that
`np` and `ctx_slot` are interchangeable. The record's framing — that the wall is a *KV*
budget — is right only for the 64K cell; the 32K wall is a working-space wall on top of a
KV cache that allocated successfully.
**Command:** as L12 above, plus
```bash
 "L13-np8-c32768|/models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf|-ngl 99 -np 8 -c 32768 -fa on --no-warmup|8" \
 "L13-np8-c65536|/models/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf|-ngl 99 -np 8 -c 65536 -fa on --no-warmup|8"
```
**Output** (the 64K cell, full log — the one that really is a KV failure):
```
L13-np8-c65536 NOT_READY after 3.1s reason=container exited
  0.01.305.716 E ggml_backend_cuda_buffer_type_alloc_buffer: allocating 3584.00 MiB on device 0: cudaMalloc failed: out of memory
  0.01.305.722 E alloc_tensor_range: failed to allocate CUDA0 buffer of size 3758096384
  0.01.306.660 E llama_init_from_model: failed to initialize the context: failed to allocate buffer for kv cache
  0.01.307.421 E srv  llama_server: exiting due to model loading error
```
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md:78-88`

### L15 — [V] verified
**Claim:** srv1, 1.5B Q4_K_M, `-np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on`: 446.6–448.9
agg tok/s at n=32.
**Verdict:** **439.69 agg tok/s at n=32 — 1.5% below the bottom of the recorded band, i.e.
inside the 2.6% across-reload bar (M5), so it reproduces.** 32 of 32 requests completed,
none failed, 475 tokens each, wall 34.57 s against the record's 33.99 s.
Same GGUF blob the engine sweep used
(`sha256-29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104`, the
`qwen2.5-coder:1.5b` ollama blob), same argv including `--metrics --slots -sps 0
--no-context-shift`, one cold container reload.
**Command:**
```bash
ssh srv1 'python3 /tmp/vc.py \
 "L15-1.5B-np32-c32768|/blobs/sha256-29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104|\
-ngl 99 -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on --metrics --slots -sps 0 --no-context-shift|32"'
```
**Output:**
```
L15-1.5B-np32-c32768 READY load_s=3.0 vram=2044 loadavg=['0.90','1.53','1.17']
L15-1.5B-np32-c32768 RESULT {"n": 32, "agg": 439.69, "dec_p50": 13.94, "ttft_p50": 0.49,
                             "pp_p50": 20.4, "ok": 32, "fail": 0, "wall": 34.57}
```
Note this cell holds the whole 1.5B **plus** a 32K-token unified-off KV cache in **2,044 MiB**
— a third of the card — which is why it is the one srv1 cell that scales to 32 slots at all
while the 7B refuses at the same width (L12/L13).
**This is the srv1 half of M7** ("engine choice is worth ~1.5x on srv1: llama-server 446.6–448.9
vs vLLM 229.7 at n=32"). The llama-server leg now stands on a fresh measurement; the vLLM leg
was not re-run here.
**Bears on:** `records/evidence/2026-08-24-engine-sweep/README.md:83` (cell B1-1) and
`records/headers/2026-08-24-engine-default-r2.json:63`

### V7 — [V] verified — SUPERSEDES the 2026-08-25 [P] entry. All six capability messages now captured verbatim.
**Claim:** srv1 (cc 7.5) refuses `--dtype bfloat16`, `--kv-cache-dtype fp8/fp8_e5m2/fp8_e4m3`,
`--attention-backend FLASH_ATTN` and `FLASHINFER`, **each with the engine's own capability
message**. srv2 accepts all six.
**Verdict:** **All six refuse, and every one of them prints an explicit compute-capability
message naming the GTX 1660 SUPER and cc 7.5.** The qualifier my 2026-08-25 entry could not
support — because the config sweep's harness stored only the last 25 lines and the root cause
is above that cut — is now on the record. Six fresh launches, full container logs kept
(151–245 lines each, at `srv1:/tmp/vlogs/*.log` during the run):

| flag | start_s | the engine's own message (the `ValueError` above the generic tail) |
|---|---|---|
| `--dtype bfloat16` | 49 | `Bfloat16 is only supported on GPUs with compute capability of at least 8.0. Your NVIDIA GeForce GTX 1660 SUPER GPU has compute capability 7.5. You can use float16 instead by explicitly setting the dtype flag in CLI, for example: --dtype=half.` |
| `--kv-cache-dtype fp8` | 43 | `FP8 KV cache is not supported by the Triton attention backend on NVIDIA GeForce GTX 1660 SUPER (compute capability 7.5); native FP8 (fp8e4nv) requires SM89+. Re-run with --kv-cache-dtype float16.` |
| `--kv-cache-dtype fp8_e5m2` | 43 | *identical to the above, word for word* |
| `--kv-cache-dtype fp8_e4m3` | 43 | *identical to the above, word for word* |
| `--attention-backend FLASH_ATTN` | 43 | `Selected backend AttentionBackendEnum.FLASH_ATTN is not valid for this configuration. Reason: ['compute capability not supported']` (raised at `vllm/platforms/cuda.py:417`, `get_attn_backend_cls`) |
| `--attention-backend FLASHINFER` | 42 | `Selected backend AttentionBackendEnum.FLASHINFER is not valid for this configuration. Reason: ['compute capability not supported']` (same line) |

Each then produces the generic tail the record captured,
`RuntimeError: Engine core initialization failed. See root cause above.` — which is precisely
why the sweep's 25-line window saw nothing useful.
**Three refinements the messages give that the claim does not:**
1. **The three fp8 cells are one refusal, not three.** All three print the *same* message and
   all three name **the Triton attention backend** and **SM89+**, not cc 8.0. So the gate is
   not "cc 7.5 < 8.0" but "the backend vLLM selected for this card has no native fp8 path";
   an Ampere card (8.6) would also miss SM89 for *native* fp8. srv2 accepting them therefore
   does not prove the gate is cc-based in the way the claim implies.
2. **The two attention-backend refusals are the same `raise` in the same function**
   (`cuda.py:417`), with the backend name substituted; they are one gate, not two.
3. **The bfloat16 message ships its own workaround** (`--dtype=half`), which means the cell
   is a configuration error rather than a capability wall — srv1 runs the identical model in
   float16 in every other cell of the sweep.
**Also unchanged from my 2026-08-25 entry:** srv1 refused **four more** cells on the linear
backend axis (`exllama`, `torch`, `machete`, `cutlass`) that the claim does not count. I did
not re-run those; the claim's "six" is a floor.
**Command:**
```bash
# /tmp/vv.sh keeps the FULL log: docker logs vvcell > /tmp/vlogs/<cell>.log
B15=Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ
BASE="--max-model-len 8192 --gpu-memory-utilization 0.85 --max-num-seqs 16 --enforce-eager"
/tmp/vv.sh V7-dtype-bfloat16  $B15 $BASE --dtype bfloat16
/tmp/vv.sh V7-kv-fp8          $B15 $BASE --kv-cache-dtype fp8         # and fp8_e5m2, fp8_e4m3
/tmp/vv.sh V7-attn-FLASH_ATTN $B15 $BASE --attention-backend FLASH_ATTN   # and FLASHINFER
# launch line matches the sweep's exactly:
# docker run -d --name vvcell --runtime=nvidia --gpus all -v $HOME/.cache/huggingface:/root/.cache/huggingface \
#   -p 8000:8000 --ipc=host -e VLLM_SERVER_DEV_MODE=1 -e FLASHINFER_DISABLE_VERSION_CHECK=1 \
#   vllm/vllm-openai:v0.26.0 <model> --port 8000 <flags>
```
**Output** (extraction over the six kept logs):
```
=== V7-dtype-bfloat16.log  (151 lines)
ValueError: Bfloat16 is only supported on GPUs with compute capability of at least 8.0. Your
  NVIDIA GeForce GTX 1660 SUPER GPU has compute capability 7.5. ...
=== V7-kv-fp8.log / V7-kv-fp8_e5m2.log / V7-kv-fp8_e4m3.log  (236/235/236 lines)
ValueError: FP8 KV cache is not supported by the Triton attention backend on NVIDIA GeForce
  GTX 1660 SUPER (compute capability 7.5); native FP8 (fp8e4nv) requires SM89+. ...
=== V7-attn-FLASH_ATTN.log / V7-attn-FLASHINFER.log  (245/244 lines)
ValueError: Selected backend AttentionBackendEnum.<NAME> is not valid for this configuration.
  Reason: ['compute capability not supported']
  File "/usr/local/lib/python3.12/dist-packages/vllm/platforms/cuda.py", line 417, in get_attn_backend_cls
```
This also **confirms V2 by a different route**: the refusals are per-feature capability gates
in `platforms/cuda.py` and `v1/attention/backends/triton_attn.py`, not a blanket
compute-capability gate on CUDA-graph capture — nothing in these six logs mentions graphs.
**Bears on:** `records/evidence/2026-08-24-config-sweep/README.md:75-80` and
`srv1-1.5B.jsonl` (the six cells whose stored `launch.log` is the truncated generic tail)

### V8 — [V] verified — SUPERSEDES the 2026-08-25 [P] entry. `torch.OutOfMemoryError` is real and now quoted.
**Claim:** srv1 cannot serve dense 7B AWQ under vLLM at all: `torch.OutOfMemoryError` at
`--gpu-memory-utilization 0.85/0.90/0.95`, eager and not.
**Verdict:** **Verified.** One fresh launch at the record's own middle cell
(`--max-model-len 512 --gpu-memory-utilization 0.90 --max-num-seqs 32`, no `--enforce-eager`)
fails at 48 s with, verbatim:
```
torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 518.00 MiB. GPU 0 has a total
capacity of 5.61 GiB of which 151.88 MiB is free. Process 114566 has 5.46 GiB memory in use.
Of the allocated memory 5.29 GiB is allocated by PyTorch, and 76.48 MiB is reserved by
PyTorch but unallocated. ...
```
The exception the claim names is exactly the exception raised. The record's own four cells
never showed it only because the harness truncated to 25 lines (I confirmed on 2026-08-25
that the string appears nowhere in `srv1-7B.jsonl`).
**What the full log adds — the failure is not where anyone assumed.** It is not the KV cache
and not the profiling run; it is **AWQ dequantization at load time**:
```
File "/usr/local/lib/python3.12/dist-packages/vllm/model_executor/layers/quantization/auto_awq.py", line 119, in _convert_awq_to_standard_format
  unpacked = (qw.unsqueeze(-1) >> shifts) & mask  # (K, N_packed, pack_factor)
torch.OutOfMemoryError: ... Tried to allocate 518.00 MiB ...
```
vLLM 0.26.0 **unpacks the 4-bit AWQ checkpoint into a standard format on the card**, and the
unpacked intermediate is what does not fit. So "srv1 cannot serve dense 7B AWQ" is right, but
the reason is a *dequantization buffer*, not the model plus its KV cache — 5.29 GiB was
already resident when a 518 MiB temporary tipped it over. That is why lowering
`--gpu-memory-utilization` does not help across 0.85/0.90/0.95: the utilisation knob caps the
KV budget, and this allocation is upstream of it. It also means the cell is not evidence about
the *served* footprint of a 7B AWQ model on a 6 GB card, which is how §5 of the offload record
reads it.
**Command:**
```bash
/tmp/vv.sh V8-7B-util0.90 Qwen/Qwen2.5-Coder-7B-Instruct-AWQ \
  --max-model-len 512 --gpu-memory-utilization 0.90 --max-num-seqs 32
```
**Output:**
```
V8-7B-util0.90 RESULT=exited start_seconds=48 vram=1   FULL_LOG_LINES=176
```
**Caveat kept from 2026-08-25:** the claim says "eager and not", but the record tried eager at
only one utilisation (0.95) and I re-ran only the 0.90 no-eager cell, so "at 0.85/0.90/0.95,
eager and not" is still six cells asserted from four measured plus one of mine.
**Bears on:** `records/evidence/2026-08-24-config-sweep/srv1-7B.jsonl` and
`README.md:138-141`; `records/evidence/2026-08-25-moe-expert-offload/README.md` §5 (dense table)

### L19 (srv1 arm) — [V] verified, and the sign flip that made me falsify it on 2026-08-25 does not exist — SUPERSEDES the 2026-08-25 [F] entry
**Claim:** srv1 (28 CPU layers) gains **3.9%** from `-t 5` to `-t 6`.
**Verdict:** **Verified in direction and understated in size: +8.1%, not +3.9%. And the
opposing −3.1% reading in the repo does not reproduce — at that cell the two thread counts
are a dead tie.** Nine reloads, the two thread counts interleaved at both `--n-cpu-moe`
settings the repo disagrees about:

| cell | `-t 5` (each reload) | `-t 6` (each reload) | t6 vs t5 | record |
|---|---|---|---|---|
| **35B-A3B IQ3_XXS, ncmoe 28**, `-c 4096 -fa on` | 30.80 / 31.00 → **30.90** | 33.31 / 33.48 → **33.40** | **+8.1%** | +3.9% |
| **qwen3-coder-30b Q4_K_M, ncmoe 40**, `-c 4096 -fa on` | 25.83/25.50/25.45/25.16/25.49 → **25.49** | 25.53 / 25.57 → **25.55** | **+0.24%** | **−3.1%** |

+8.1% is 3.1x the 2.6% reload bar (M5) — solidly real. +0.24% is a tenth of the bar — a tie
by any reading. **There is no negative reading anywhere in nine reloads.** The repo's
`t=6 -> 25.01` at ncmoe 40 (`raw-postswap-squeeze-concurrency.txt:73`) sits 2.1% below my
five `-t 5` takes and 2.2% below my two `-t 6` takes; it is a single sample, and re-measured
twice the same cell comes back level.
**So my 2026-08-25 [F] was wrong, and wrong for an instructive reason.** I falsified L19 on
the grounds that three repo readings disagreed in sign and that all three had to be real
because the repeatability bar was 0.77%. Both halves of that argument fail: 0.77% was the
*steady-state* bar, not the *across-reload* bar (2.6%, see M5), and under the correct bar the
−3.1% row is a single unreplicated sample that does not survive re-measurement. **The lesson
is the one M5 states**: a corpus of single-pass cells cannot support sign claims about
few-percent effects, and reconciling its internal disagreements by declaring them all real is
the wrong move — the right move is to re-run them.
**What the claim still over-reaches on:** the general form ("threads matter in proportion to
layers on the CPU") predicts a *larger* gain at ncmoe 40 (40 CPU layers) than at ncmoe 28 (28
CPU layers). My data show the opposite — +8.1% at 28 layers, 0.0% at 40. The two rows are
also different models and different quants, so the corpus has never run the clean contrast
that would test the stated mechanism. Verified as a fact about the shipped 35B cell; not
established as a rule.
**Also worth recording:** the `-t 6` gain at ncmoe 28 shows up in **prefill too** (pp 41.6/41.4
vs 37.7/37.5 tok/s, +10.5%) and shortens TTFT (0.265 vs 0.293 s). It is a CPU-side effect
across the board, not a decode-only one.
**Command:**
```bash
ssh srv1 'python3 /tmp/vc.py \
 "L19-35B-nm28-t5-a|/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf|-ngl 99 --n-cpu-moe 28 -t 5 -c 4096 -fa on|1" \
 "L19-35B-nm28-t6-a|...-t 6...|1" "L19-35B-nm28-t5-b|...-t 5...|1" "L19-35B-nm28-t6-b|...-t 6...|1" \
 "L19-30b-nm40-t6-a|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 6 -c 4096 -fa on|1" \
 "L19-30b-nm40-t5-e|...-t 5...|1" "L19-30b-nm40-t6-b|...-t 6...|1"'
```
**Output:**
```
L19-35B-nm28-t5-a  vram=5500  dec_p50=30.80  pp=37.7  ttft=0.292
L19-35B-nm28-t6-a  vram=5502  dec_p50=33.31  pp=41.6  ttft=0.264
L19-35B-nm28-t5-b  vram=5502  dec_p50=31.00  pp=37.5  ttft=0.293
L19-35B-nm28-t6-b  vram=5502  dec_p50=33.48  pp=41.4  ttft=0.266
L19-30b-nm40-t6-a  vram=4420  dec_p50=25.53  pp=35.8
L19-30b-nm40-t5-e  vram=4420  dec_p50=25.49  pp=34.2
L19-30b-nm40-t6-b  vram=4420  dec_p50=25.57  pp=35.9
```
The `-t 6` ncmoe-28 figure (33.31 / 33.48) reproduces the shipped cell's recorded 33.28 to
within 0.6%, and my own 2026-08-25 reading of 33.35 through the running `llama-sweep` to
within 0.4% — so the instrument, the rig and the record agree on that cell across two days
and three measurement paths.
**Bears on:** `records/measurements/serving-sweep-2026-08-25/README.md:67-70`;
`records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt:73`
(the `t=6 -> 25.01` row, which does not reproduce); `moe README.md:83-86`

### L20 — [V] verified, and the collapse is worse than recorded — SUPERSEDES the 2026-08-25 log-derived entry
**Claim:** llama.cpp's threadpool spin-waits, so oversubscribing cores collapses throughput
far past the oversubscription ratio (srv1: two models at `-t 5` each on 6 cores = 14x slower
than solo).
**Verdict:** **Verified by direct measurement, and the collapse is 15–18x, not 14x.** Two
different expert-offloaded MoE models, both live, both generating 475 tokens at once:

| `-t` each | threads on 6 cores | A solo (30b, ncmoe 48) | B solo (dsc-v2-16b, ncmoe 27) | A conc | B conc | collapse |
|---|---|---|---|---|---|---|
| **5** | 10 (1.67x oversubscribed) | **22.58** | **19.43** | **1.291** | **1.290** | **A 17.5x / B 15.1x** |
| **3** | 6 (exactly saturated) | **20.19** | **17.44** | **13.10** | **12.50** | **A 1.54x / B 1.40x** |

At `-t 5` a **1.67x** oversubscription costs **16.3x** aggregate (41.99 → 2.58 combined
tok/s) — the collapse is **9.8x worse than the oversubscription ratio**, which is the claim's
whole point and is if anything understated by the record's 14x. The single concurrent request
pair took **368.6 s of wall clock**; the same pair at `-t 3` took **38.5 s**.
At `-t 3` the combined aggregate is **25.60 tok/s**, which beats either model alone — so the
record's "co-residency is worth having, but only at `-t 3`" holds. (The record's combined
figure is 28.25; mine is 9% lower, and my solo figures are 2–5 tok/s below the record's too,
so the whole cell reads slightly slow today rather than the ratio being different.)
**Two things the direct run shows that the log could not:**
1. **The two models collapse to the *same* rate** — 1.2906 and 1.2896 tok/s, a 0.08%
   difference between a 30B and a 16B model with different offload settings. Under
   spin-wait oversubscription the throughput is set by the scheduler, not by the model. That
   is about as clean a signature of the mechanism as one could ask for.
2. **A resident-but-idle co-tenant costs nothing measurable.** With B loaded and idle,
   A reads 22.58 tok/s; the penalty appears only when both are *generating*. So the
   16% of six cores an idle llama-server burns (my 2026-08-25 reading, reconfirmed today at
   `%Cpu(s): 16.1 us` with two servers resident) is not what causes the collapse —
   oversubscription during decode is.
**Command:**
```bash
ssh srv1 'python3 /tmp/vco.py 5; python3 /tmp/vco.py 3'
# each: docker run two llama.cpp b10481 servers on ports 8091/8092 —
#   A: -m /models/qwen3-coder-30b.gguf        -ngl 99 --n-cpu-moe 48 -t <T> -c 4096 -fa on
#   B: -m /models/deepseek-coder-v2-16b.gguf  -ngl 99 --n-cpu-moe 27 -t <T> -c 4096 -fa on
# then one 475-token request to A alone, one to B alone, then both at once in two threads.
```
**Output:**
```
## L20/L21  -t 5 each
A(qwen3-coder-30b ncmoe48) ready=True load_s=39.6 vram=1484
B(deepseek-coder-v2-16b ncmoe27) ready=True load_s=30.5
BOTH_RESIDENT vram=3466 MiB
SOLO_B t=5 dec=19.4288  (A idle-resident)
SOLO_A t=5 dec=22.5761  (B idle-resident)
CONC  t=5 A_dec=1.29061  B_dec=1.28957  wall=368.6  loadavg=['9.99','7.85','4.52']
## L20/L21  -t 3 each
SOLO_B t=3 dec=17.4442   SOLO_A t=3 dec=20.1894
CONC  t=3 A_dec=13.0972  B_dec=12.4991  wall=38.5   loadavg=['4.25','5.34','4.14']
```
**One measurement artefact to note for anyone reusing this driver:** the *first* request after
a container load reads low (A's first-ever request at `-t 5` gave 17.97 tok/s against 22.58 on
its second), because it pays kernel warm-up. Every figure in the table above is a
second-or-later request; the record's solo figures may not be.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:229-243` and
`raw-postswap-squeeze-concurrency.txt:158-164`

### L21 — [V] verified — SUPERSEDES the 2026-08-25 log-derived entry
**Claim:** Two different expert-offloaded MoE models co-reside on srv1 in **2,702 MiB** of
6,144, both healthy.
**Verdict:** **Co-residency verified live — but at `-c 4096` each it costs 3,466 MiB, not
2,702.** Both servers loaded, both passed `/health`, both answered a 475-token generation:
`qwen3-coder-30b` at `--n-cpu-moe 48` = **1,484 MiB** (record 1,274) and
`deepseek-coder-v2-16b` at `--n-cpu-moe 27` bringing the pair to **3,466 MiB** (record 2,702),
leaving 2.6 GB free on the 6,144 MiB card. The 764 MiB difference is the KV cache: I gave both
`-c 4096` to match every other cell in this verification, and the record does not state what
`-c` its co-residency pair carried. **The claim's shape is right and its headroom conclusion
is right; its specific MiB figure is not reproducible without the missing `-c`.**
**Read it with L20 attached, as before:** "both healthy" is a statement about *residency*, not
about *service*. At `-t 5` each both are healthy and both run at 1.29 tok/s — a 16x aggregate
collapse. Only the `-t 3` pairing (25.60 tok/s combined) is a configuration anyone would ship.
**Command / Output:** as L20 above —
```
BOTH_RESIDENT vram=3466 MiB   (docker ps: vA, vB)
A: qwen3-coder-30b       --n-cpu-moe 48 -c 4096 -> 1,484 MiB, /health 200, 475 tokens served
B: deepseek-coder-v2-16b --n-cpu-moe 27 -c 4096 -> pair 3,466 MiB, /health 200, 475 tokens served
```
Both GGUFs are the ones the record names, still on srv1 at
`/home/adaramir/ggufs/{qwen3-coder-30b.gguf, deepseek-coder-v2-16b.gguf}`.
**Bears on:** `records/evidence/2026-08-25-moe-expert-offload/README.md:229-233` and
`raw-postswap-squeeze-concurrency.txt:152-157`

---

## Rig restored, 2026-08-26

- **`llama-sweep` is back up and healthy.** It was restarted with `docker start llama-sweep`
  rather than a fresh `docker run`, which preserves the original container (created
  2026-08-25T17:30:13Z), its image, its argv, its bind and its `restart: no` policy exactly —
  strictly more faithful than re-creating it, and it avoids destroying the original record.
  ```bash
  ssh srv1 'docker start llama-sweep'
  ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"'
  ["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on","--host","0.0.0.0","--port","8080"]
  Image=ghcr.io/ggml-org/llama.cpp:server-cuda-b10481  Restart=no
  Ports={"8080/tcp":[{"HostIp":"","HostPort":"8080"}]}  Binds=["/home/adaramir/ggufs:/models"]
  ```
  `/health` returns 200, `/props` reports `total_slots 4`, and a live generation returns
  `'\n    return a+b\n\ndef sub(a,b):\n    return a-b'` at **31.99 tok/s**. Card reads
  **5,502 of 6,144 MiB** against the 5,558 MiB recorded when the previous crew arrived; my own
  fresh launches of the identical argv also read 5,500–5,502 (L19), so 5,502 is this cell's
  footprint and the earlier 5,558 included ~56 MiB of another client.
- **ollama untouched:** `is-active` = `inactive`, `is-enabled` = `enabled` — as found.
- **Every container I started is gone.** `docker ps -a` shows only `llama-sweep` (up) plus the
  two pre-existing exited containers `mcgyvr-vllm` and `vllm-nemotron-4b` that were already
  there. `vcell`, `vvcell`, `vA`, `vB` were all `docker rm -f`'d by their drivers' `finally`
  blocks.
- **Every temp file removed:** `/tmp/vc.py`, `/tmp/vv.sh`, `/tmp/vco.py`, `/tmp/v7.sh`,
  `/tmp/vtriad`, `/tmp/vtriad.c`, `/tmp/vout_*.txt`, `/tmp/vlogs/` — `ls /tmp/v*` returns
  "No such file or directory". The pre-existing `/tmp/llama-sweep-spec.json` was left alone.
- No package installed, no host setting changed, no systemd unit written, no `drop_caches`.
