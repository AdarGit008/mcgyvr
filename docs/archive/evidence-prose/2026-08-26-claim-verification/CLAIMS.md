# Claims register — the 2026-08-25 serving report
Every claim below is asserted by the report built from records/measurements/serving-sweep-2026-08-25/,
records/evidence/2026-08-25-moe-expert-offload/ (+ width-sweep/), 2026-08-24-engine-sweep/,
2026-08-24-config-sweep/, 2026-08-24-knob-surface/, 2026-08-24-ramp-tokens/, 2026-08-23-cross-rig/.

Status legend: [ ] untested · [V] verified · [F] falsified · [P] partial · [U] untestable here (say why)
Every result needs: verdict, the command or code snippet that produced it, and the repo path or URL it bears on.

## H — hardware and environment
- [ ] H1  srv1 is a GTX 1660 SUPER, 6144 MiB, compute capability 7.5, driver 580.173.02, 48 GB RAM.
- [ ] H2  srv2 is an RTX 3060, 12288 MiB, cc 8.6, driver 595.84, 16 GB RAM dual-channel (post-swap).
- [ ] H3  Both rigs hold identical image digests: llama.cpp server-cuda-b10481 = sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce; vllm/vllm-openai:v0.26.0 = sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52.
- [ ] H4  Weights are byte-identical across rigs: Qwen3.6-35B-A3B-UD-IQ3_XXS 9c964e657212fea1…, Qwen2.5-Coder-7B-IQ4_XS f7eff217195ff980…, qwen3-coder-30b Q4_K_M 1194192cf2a187eb… (18,556,688,736 B).
- [ ] H5  STREAM triad bandwidth: srv1 26.8 GB/s, srv2 23.8 GB/s post-swap (was 13.3 pre-swap).

## L — llama.cpp (image ghcr.io/ggml-org/llama.cpp:server-cuda-b10481)
- [ ] L1  b10481's default slot count is 4: with no --parallel/-np, /props reports total_slots 4.
- [ ] L2  -c is a TOTAL divided across slots (-np 4 -c 4096 yields n_ctx_slot 1024; -np 16 -c 4096 yields 256).
- [ ] L3  --n-cpu-moe N keeps attention, KV cache and embeddings on the card and puts the expert FFN weights of N layers in system RAM.
- [ ] L4  ollama cannot express --n-cpu-moe; it splits whole layers only (upstream ollama/ollama#11772).
- [ ] L5  The --n-cpu-moe curve is NOT monotone at the edge: on srv1, ncmoe 37 (26.34) is slower than 38 (26.83) while still loading; 36 refuses.
- [ ] L6  --no-mmap is +63% on srv2 (16 GB host) and -12..-18% on srv1 (48 GB host) — same flag, opposite sign.
- [ ] L7  KV-cache q8_0 at -c 4096 across 4 slots frees only ~36 MiB and costs ~1.6 tok/s.
- [ ] L8  ollama's gpt-oss-20b blob will not load in b10481: "unknown model architecture: 'gptoss'".
- [ ] L9  srv1's floor for 35B-A3B IQ3_XXS is ncmoe 28 (5,554 MiB); 27 overruns the 6,144 MiB card.
- [ ] L10 srv1's TTFT is 5.5-6.0 s across EVERY configuration tried; srv2's is 0.67 s. No ncmoe or -t setting moves it.
- [ ] L11 srv2, 35B-A3B IQ3_XXS, --n-cpu-moe 25, -c = np x 1024: 44.9 tok/s at np=1 rises to 254.5 at np=32/n=32 (5.67x); p50 59.7 s at np32/n32 vs 94.8 s at np16/n16.
- [ ] L12 srv1, 7B IQ4_XS: width peaks at 8 slots (128.4); 16 slots is SLOWER (106.3); 32 slots refuses with CUDA OOM.
- [ ] L13 srv1's KV budget is the PRODUCT np x ctx_slot ~ 16K tokens: np32x1024 and np8x4096 both OOM, np16x1024 loads at 4,852 MiB.
- [ ] L14 Context buys nothing: srv2 35B at np=8, 1024 -> 8192 tokens/slot costs 1,126 MiB and loses 0.6% throughput.
- [ ] L15 srv1, 1.5B Q4_K_M, -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on: 446.6-448.9 agg tok/s at n=32.
- [ ] L16 srv2, 1.5B Q4_K_M, -np 128 -c 131072 -no-kvu -b 2048 -ub 2048 -fa on: 1,396.4 agg tok/s at n=128.
- [ ] L17 srv2, 7B Q4_K_M, -np 32 -c 32768 -b 1024 -ub 1024 -fa on: 726.2 agg tok/s at n=32.
- [ ] L18 A smaller quant of a bigger model beats a bigger quant of a smaller one: 35B-A3B IQ3_XXS (13.21 GB) 67.04 tok/s vs 30B-A3B Q4_K_M (18.56 GB) 44.84 on srv2.
- [ ] L19 Threads matter in proportion to layers on the CPU: srv2 (4 CPU layers) flat from -t 10 to -t 20; srv1 (28 CPU layers) gains 3.9% from -t 5 to -t 6. Under ncmoe 48 srv2 is flat past 4 threads (16 of 20 contribute nothing).
- [ ] L20 llama.cpp's threadpool spin-waits, so oversubscribing cores collapses throughput far past the oversubscription ratio (srv1: two models at -t 5 each on 6 cores = 14x slower than solo).
- [ ] L21 Two different expert-offloaded MoE models co-reside on srv1 in 2,702 MiB of 6,144, both healthy.
- [ ] L22 The single-stream S1 column of serving-sweep-2026-08-25 is a property of its named configuration and does NOT depend on -np.

## V — vLLM (image vllm/vllm-openai:v0.26.0)
- [ ] V1  --enforce-eager costs srv2 5.02x (2,601.7 vs 518.2 agg; 181.7 vs 36.2 at n=1) and srv1 0.1% (293.6 vs 293.3).
- [ ] V2  vLLM 0.26.0 has NO compute-capability gate on CUDA graph capture; docs/features/README.md lists CUDA graph as supported on Turing; the only forced-eager paths are ROCm encoder-decoder and 8-bit bitsandbytes.
- [ ] V3  srv1 responds to exactly ONE axis of twenty: 25 cells across compile, graphs, perf mode, scheduler, dtype, KV dtype, block size, prefix caching, chunked prefill, cascade attention, stream interval, watermark, attention backend and linear backend all land inside a 2.8% band (164-168 tok/s).
- [ ] V4  srv1's vLLM ceiling is ~293-294 agg tok/s and is NOT context-bound: -max-model-len 4096/2048/1024/512 all return 293.3-293.4 at seqs 128.
- [ ] V5  srv2's best vLLM cell is no-eager + --max-model-len 1024 + --max-num-seqs 256 + --kv-cache-dtype fp8 = 6,445.1 agg tok/s at n=256.
- [ ] V6  fp8 KV does nothing at n=16 (558, indistinguishable from baseline) and wins at n=256 (6,445 vs 6,088): it halves bytes per token rather than speeding a kernel up.
- [ ] V7  srv1 (cc 7.5) refuses --dtype bfloat16, --kv-cache-dtype fp8/fp8_e5m2/fp8_e4m3, --attention-backend FLASH_ATTN and FLASHINFER, each with the engine's own capability message. srv2 accepts all six.
- [ ] V8  srv1 cannot serve dense 7B AWQ under vLLM at all: torch.OutOfMemoryError at --gpu-memory-utilization 0.85/0.90/0.95, eager and not.
- [ ] V9  The image declares 275 flags, 250 with a printed default, 31 with a choice set. The config sweep tried 20 of them; 255 are untried.
- [ ] V10 vLLM has no --n-cpu-moe equivalent, so a MoE larger than the card is not a vLLM workload.
- [ ] V11 vLLM's --max-model-len is a CEILING that reserves nothing (allocates per token used) — the opposite of llama.cpp's -c.
- [ ] V12 Speculative decoding (n-gram) loses at every concurrency tested.
- [ ] V13 vLLM reproduces across srv2's 32GB->16GB RAM change (6,562.0 vs 6,445.1/6,452.2/6,480.6; 1,617.2 vs 1,604.7): a model resident on the card never touches system RAM in the decode path.
- [ ] V14 Four independent takes of srv2's best 1.5B cell agree within +/-1.8% (6,445.1 / 6,452.2 / 6,480.6 / 6,562.0).

## M — methodological claims the report makes about its own evidence
- [ ] M1  Every `tasks/h @8` figure in serving-sweep-2026-08-25 is void: 8 concurrent requests against llama.cpp's default 4 slots is 4 served and 4 queued, so the figure is not a property of the configuration.
- [ ] M2  The two "legal cross-host contrasts" (1.95x on 35B, 1.32x on 7B) are confounded: srv2 carried --no-mmap in every cell and srv1 in none, and that flag alone is worth +63%/-12..-18%.
- [ ] M3  "Expert offload does not batch" is a statement about -np 4, not about expert offload: at 32 slots a comparable MoE reaches 5.67x rather than 2.06x.
- [ ] M4  Decode under expert offload is memory-bandwidth-bound: on srv2, turbo off->on (2.8->5.2 GHz) moves decode under 3% while prefill gains 11%; package power peaked at 40.0 W against a 65 W cap, so power was never binding.
- [ ] M5  Run-to-run spread: srv2 repeats within 0.2%; srv1 varies 5-10%, so an srv1 gap under ~10% is a tie.
- [ ] M6  Nothing in this corpus scores quality: every rate is tokens produced, not tokens worth keeping. No task passed or failed.
- [ ] M7  On srv1 the engine choice is worth ~1.5x at the same model and concurrency: llama-server 446.6-448.9 vs vLLM 229.7 at n=32 (1.5B).
- [ ] M8  A cgroup --memory cap does not simulate a smaller machine when the file is already in the host page cache (the invalid docker --memory=15g cell).
