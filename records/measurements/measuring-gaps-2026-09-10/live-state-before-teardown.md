# Live rig state before measuring-gaps teardown — captured 2026-09-10

**The plan's preflight assumed both rigs were already torn down. They were not.**
This file is the exact state to restore after the run. It matches
`records/plans/handoff.md` "Live state, as left" — the flexibility campaign's
production ladders were still up when this run began.

## srv1 — GTX 1660 SUPER, 6,144 MiB total, 5,110 MiB used

Running (compose project `mcgyvr`):

| container | image | status |
|---|---|---|
| `mcgyvr-srv1-Qwen3.6-35B-A3B-UD-IQ3_XXS-8080` | `llamacpp:b10644-L3` | Up 2 hours |

Exited (leftovers, not live): `mcgyvr-lcpp` (Exited 255), `vllm-nemotron-4b` (Exited 1).

Live compose is `~/.mcgyvr/config/compose.srv1.yml` — service
`Qwen3.6-35B-A3B-UD-IQ3_XXS-8080`, model
`/home/adaramir/models/moe/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf`, flags
`--n-cpu-moe 30 --parallel 2 --port 8080 -b 512 -c 16384 -fa on -ngl 99 -t 6
-ub 512 --chat-template-kwargs '{"enable_thinking":false}'`,
`LLAMA_ARG_HOST 0.0.0.0`, `network_mode host`, `restart unless-stopped`,
volumes `/home/adaramir/models/moe` (ro ×2).

## srv2 — RTX 3060, 12,288 MiB total, 9,445 MiB used

Running (compose project `mcgyvr`):

| container | image | status |
|---|---|---|
| `mcgyvr-srv2-Qwen-Qwen2.5-Coder-3B-Instruct-AWQ-8001` | `vllm/vllm-openai@sha256:ffb2d59b…` | Up ~1 hour |
| `mcgyvr-srv2-Qwen-Qwen2.5-Coder-7B-Instruct-AWQ-8002` | `vllm/vllm-openai@sha256:ffb2d59b…` | Up ~1 hour |

Exited (leftovers): `vllm-7b-coder` (Exited 0), `vllm-nemotron-30b` (Exited 0),
`vllm-nemotron-4b` (Exited 1).

Live compose is `~/.mcgyvr/config/compose.srv2.yml` — the 3B+7B vLLM pair,
`depends_on: service_started`, 3B at port 8001 / util 0.26, 7B at port 8002 /
util 0.72, `--max-model-len 4096 --max-num-seqs 8`, `HF_HUB_OFFLINE 1`,
`ipc: host`, `network_mode host`, `restart unless-stopped`.

## Restoration

`mcgyvr serve up` (or the door's equivalent) against
`~/.mcgyvr/config/compose.srv1.yml` and `compose.srv2.yml` restores exactly the
above. Idle baselines to verify after teardown: srv1 17 MiB, srv2 1 MiB.
