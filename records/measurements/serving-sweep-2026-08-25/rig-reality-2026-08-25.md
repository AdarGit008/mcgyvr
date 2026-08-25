# rig-reality-2026-08-25

Second rig contact, seven days after `rig-reality.md` (2026-08-18). That file is a record of the
review as conducted and is not amended here (ADR-0036 clause 4); this one records what the rigs
are on **2026-08-25** and names, with evidence, the four places where ADR-0024, the identity
surface and `tools/breadth/measure.py` now disagree with the machines they describe.

Contact was by ssh (authorised for this pass; `rig-reality.md` recorded "did not ssh per
instructions") plus HTTP against the serving port. Read-only throughout: no service started or
stopped, no file on either host written, no model pulled.

## verdicts

### Q: Is ollama still serving on :11434 with the builds ADR-0024 clause 3 makes run identity (srv1 0.32.4, srv2 0.32.5)?
VERDICT: REFUTED
EVIDENCE: `systemctl is-active ollama` -> `inactive` on both hosts (`is-enabled` -> `enabled`, so it is stopped, not removed). A `/dev/tcp/127.0.0.1/11434` connect test is refused on both. `ollama --version` prints `Warning: could not connect to a running Ollama instance` and `client version is 0.32.15` on both — the client is also three patch versions past the 0.32.4/0.32.5 pair confirmed live on 2026-08-18. No ollama build is serving anything on either host.

### Q: What is serving models on each host now?
VERDICT: llama.cpp server in Docker, on :8080, identical build on both hosts.
EVIDENCE: `docker ps` -> container `llama-moe`, image `ghcr.io/ggml-org/llama.cpp:server-cuda-b10481`, `0.0.0.0:8080->8080/tcp`, status healthy. `GET /props` -> `build_info: b10481-25ae3a9b3` on both. argv from `/proc/<pid>/cmdline`: srv1 `llama-server -m /models/qwen3-coder-30b.gguf -ngl 99 --n-cpu-moe 38 -t 5 -c 4096 -fa on --alias qwen3-coder-30b --host 0.0.0.0 --port 8080`; srv2 the same but `-m /models/sha256-1194192cf2a1… --n-cpu-moe 20 -t 20 --no-mmap`. Docker mounts: srv1 `/home/adaramir/ggufs -> /models`; srv2 `/usr/share/ollama/.ollama/models/blobs -> /models` — llama.cpp reading ollama's blob store directly, with ollama itself down.

### Q: Are the two hosts serving the same weights?
VERDICT: CONFIRMED — byte-identical.
EVIDENCE: `sha256sum /home/adaramir/ggufs/qwen3-coder-30b.gguf` on srv1 = `1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a`. srv2 serves `/models/sha256-1194192cf2a187eb…`, and `sha256sum` inside its container returns that same digest for that blob (an ollama blob's filename is its own sha256; verified rather than assumed). Both files are 18,556,688,736 bytes. Same weights, same build, differing only in host and flags — the first cross-host contrast available on this project that satisfies ADR-0024's comparability rule on every axis except the two it would be isolating.

### Q: Does ADR-0024's rig table (:33-36) match the hardware?
VERDICT: REFUTED on the RAM row, both hosts. CONFIRMED on GPU and CPU.
EVIDENCE: `nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap`: srv1 = GTX 1660 SUPER, 6144 MiB, driver 580.173.02, cc 7.5; srv2 = RTX 3060, 12288 MiB, driver 595.84, cc 8.6 — matches ADR-0024:33. `nproc` = 6 / 20, consistent with i5-9600K 6c/6t and i9-10900F 10c/20t at :34. `dmidecode -t memory`: **srv1 = 16 GB in ChannelA-DIMM1 + 32 GB in ChannelB-DIMM1 = 48 GB @ 3200 MT/s** (a mismatched pair, so only the paired 32 GB interleaves); **srv2 = 8 GB in ChannelA-DIMM0 + 8 GB in ChannelB-DIMM0 = 16 GB @ 2667 MT/s** — one DIMM per channel, i.e. **dual** channel. ADR-0024:35 records both hosts as "32 GB" and srv2's as "single channel @ 2933". srv2 has half the recorded RAM and the opposite channel configuration. `free -g`: srv1 45 total / 43 available; srv2 15 total / **6 available**.

### Q: Does `--n-cpu-moe` run a 30B-A3B MoE on both cards, and at what rate?
VERDICT: CONFIRMED.
EVIDENCE: `POST /completion`, `n_predict: 160`, `temperature: 0`, `cache_prompt: false`, identical prompt, warm (second call of two). **srv2: 44.96 tok/s decode**, 95.5 tok/s prompt, 11,286 MiB VRAM, 7.66 GB RSS. **srv1: 27.07 tok/s decode**, 51.0 tok/s prompt, 5,116 MiB VRAM, 18.87 GB RSS. The cold first call on srv1 measured 13.99 tok/s — a ~1.9x cold-start penalty that any sweep must warm past before recording. At these flags srv2 is 1.66x srv1 on byte-identical weights and an identical build.

### Q: Does llama.cpp serve concurrent requests without an explicit `--parallel` flag?
VERDICT: CONFIRMED — 4 slots by default, ~2x aggregate.
EVIDENCE: `GET /slots` on srv2 returns 4 slots although neither argv passes `--parallel`. Six concurrent `POST /completion` calls (120 tokens each, identical prompt, `cache_prompt: false`): 720 tokens in 7.8 s wall = **92.01 tok/s aggregate** against 44.96 tok/s single-stream. Per-request decode rates split 29.0 / 39.1 across the six — four served concurrently, two queued behind them.

### Q: Is vLLM present, and does the "vLLM cannot run MoE FP8 on Ampere" limitation still hold?
VERDICT: UNVERIFIABLE on this rig; the claim's basis is outdated.
EVIDENCE: srv1 has **vllm 0.26.0** (`~/.local/lib/python3.14/site-packages/vllm`); srv2 has none (`import vllm` fails, `pip list` shows nothing). The installed 0.26.0 ships `model_executor/layers/fused_moe/experts/marlin_moe.py` and `model_executor/layers/fused_moe/oracle/fp8.py`, the latter containing `Fp8MoeBackend.MARLIN`, `prepare_fp8_moe_layer_for_marlin` and `select_fp8_moe_backend` — a Marlin FP8 MoE path exists, where the Triton-only limitation (vllm-project/vllm#17579, 2025) said none could. Whether it enables on sm_86 cannot be settled here: the only Ampere card is srv2, which has no vLLM, and srv1's card is Turing sm_75.

### Q: What models are on each host now?
VERDICT: materially changed since 2026-08-18; srv1 is no longer the small-model host.
EVIDENCE: srv1 `/home/adaramir/ggufs`, 5 files, 57.3 GB: `Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf` 4,218,473,248 B and `Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf` 13,211,155,424 B (both dated **2026-08-25**), `deepseek-coder-v2-16b.gguf` 8,905,109,984 B, `gpt-oss-20b.gguf` 13,793,422,144 B, `qwen3-coder-30b.gguf` 18,556,688,736 B. ADR-0024:36 records srv1 as holding "≤ 7B (largest blob 4.7 GB)"; it now holds a 18.6 GB blob and is serving it. srv2 keeps its ollama blob store — 12 blobs over 1 GB, largest 36,282,685,440 B — but nothing serves it except the single blob llama.cpp has open.

### Q: Would `serving_build()` record the new stack's build?
VERDICT: REFUTED — it records `None`, silently.
EVIDENCE: `tools/breadth/measure.py:861-882` probes `endpoint + "/api/version"` and returns `None` on any exception, by design ("an endpoint that does not answer `/api/version` … is one whose build is unknown"). llama.cpp's server has no `/api/version`; it publishes the build at `GET /props` as `build_info` (`b10481-25ae3a9b3`, verified above). So every run against the current stack records `serving_build: null`. `BOUND_MATCH` (`tools/bench/identity.py:283`) includes `serving_build`, so two runs served by *different unknown* builds compare equal on that field — the exact failure ADR-0024 exists to prevent, re-entering through the null.

## new_findings
- **The stack under the whole instrument changed and nothing in the tree knows.** `probe_model`, the 9-key `/api/show` surface, `/api/tags`, ADR-0033's model-group path and `serving_build()` all address ollama on :11434, which is stopped on both hosts. The discharge recorded in `rig-reality.md` ("first rig contact confirms the code") was true on 2026-08-18 and describes a service that is no longer running.
- **ADR-0024's central inference is built on a wrong number.** Its :38-42 argument turns on srv2's memory being slower than srv1's, and dismisses bandwidth because "that figure only matters once a model spills to CPU". Both premises now fail: srv2 is 16 GB dual-channel 2667, not 32 GB single-channel 2933; and under `--n-cpu-moe` the model *always* spills to CPU by design, so RAM is on the critical path of every token. The conclusion (srv2 is the faster host) survives — measured 1.66x — but for the opposite reason from the one recorded: srv2 wins on 20 threads against 5 and on holding 33 of 48 MoE layers in VRAM, not on memory.
- **srv2's binding constraint flipped from VRAM to RAM.** ADR-0024:38 says "the binding constraint is VRAM, not memory bandwidth". srv2 has 6 GB of 15 GB RAM available and runs `--no-mmap`, which forces the offloaded experts resident; that, not the 12 GB card, is what sets its `--n-cpu-moe 20` floor. srv1 has 43 GB available and is the host with room to trade layers against RAM.
- **srv1's assigned role is inverted in practice.** ADR-0024 clause 2 makes srv1 "capacity … 1.5B and 3B sweeps for throughput". srv1 is currently serving an 18.6 GB 30B-A3B MoE at 27.07 tok/s and holds a 13.2 GB Qwen3.6-35B-A3B and a 4.2 GB Qwen2.5-Coder-7B IQ4_XS pulled the same day.
- **Concurrency is already available and unmeasured.** Four slots by default, 2.05x aggregate at six in flight, on a stack no manifest describes. `concurrency` is a declared identity field (`identity.py:152`) sitting at `AWAITING_PROBE_SET` (`:243`); the rig now has a value for it.
- **A legal cross-host contrast exists for the first time.** Byte-identical weights (`1194192cf2a1…`), identical build (`b10481-25ae3a9b3`), same context and decode settings. Whatever ADR-0024 clause 2 decides about comparing rates across hosts, the technical objection it was written against does not apply to this pair.

## plan_input
- **Nothing measured against :8080 is a measurement until `serving_build` has a writer for it.** The smallest correct fix is to fall back to `GET /props -> build_info` when `/api/version` is absent, and to record the server's argv — `--n-cpu-moe`, `-t`, `-c`, `-fa`, `--no-mmap` all move the rate and none is currently recorded anywhere. Until then, sweep output is notes.
- **The dispatch path already exists.** `src/mcgyvr/runner.py:444` serves `/v1/chat/completions`, and `tools/bundle/measure.py:583-592` records that vLLM and llama.cpp offer it on the same port. llama.cpp's server does implement it, so a sweep against :8080 needs the OpenAI-compat runner, not new transport code. CAV-01's `/api/generate` caveat (`runner.py:99`) is moot here — there is no `/api/generate` to get wrong.
- **ADR-0024 needs a dated correction, not a rewrite** (ADR-0036 clause 4): the RAM row is wrong for both hosts, clause 3's build identity has no live referent, and clause 2's role assignment no longer describes what srv1 runs. Its clause 1 (srv2 is the measurement rig) is *not* contradicted by anything here — srv2 is still the faster host on identical weights.
- **Figures a plan may cite from this file**: srv2 44.96 tok/s / srv1 27.07 tok/s single-stream on `1194192cf2a1…` at build `b10481-25ae3a9b3`; srv2 92.01 tok/s aggregate at 6 in flight over 4 slots; VRAM 11,286 / 5,116 MiB; RSS 7.66 / 18.87 GB; RAM available 6 / 43 GB; cold-start penalty ~1.9x on srv1.
- **Do not re-derive the model inventory from `/api/tags`.** It answers nothing while ollama is down. The inventory above came from the Docker mount source on each host (`/home/adaramir/ggufs`, `/usr/share/ollama/.ollama/models/blobs`) with sizes and sha256 from the filesystem.
