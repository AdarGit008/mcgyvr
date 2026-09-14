# fleet-setup srv1 measurements — 2026-09-13

Raw dev-run outputs for the srv1 half of the fleet stamping. Read
`fleet-setup/REPORT-srv1.md` for the pinned numbers; `fleet-setup/evidence-srv1.json`
is the lock-shaped evidence, and `fleet-setup/digests-srv1.json` the identities.

| file | what |
|---|---|
| `raw/maxctx-32768.json` | a-solo/srv1 sweep at `-c 32768`: decode, prefill, card, mem, restarts |
| `raw/maxctx-65536-oom.log` | the `-c 65536` attempt — GPU OOM (`cudaMalloc failed`) |
| `raw/deepseek-bsmall.json` | b-small/srv1: deepseek ncmoe 19 width 2 `-c 8192` |
| `raw/35b-bbig.json` | b-big/srv1: Qwen3.6 ncmoe 30 width 2 `-c 16384` |
| `raw/context-maxctx.json` | CUDA context probe, maxctx launch (RS-corrected: 98.38 MiB) |
| `raw/context-deepseek-35bb.json` | context probes: deepseek 87.22 MiB, 35b_b 95.57 MiB |
| `raw/moves-cold.json` | the two switch moves, page cache dropped (cold) |
| `raw/moves.json` | the two switch moves, warm page cache |
| `harness_llama.py` | decode+prefill+card harness (starts container, does NOT tear down) |
| `measure_context.py` | CUDA context probe (parses model/KV/compute buffers; add RS for Qwen3.6) |
| `measure_move.py` | switch-move timer (stop source, start target cold, downtime + wake) |

Overhead per combination = CUDA context (measured) + driver reserve (399 MiB,
`nvidia-smi memory.reserved`, idle). Contexts are per model (C14): Qwen3.6
98.38 MiB (np 1) / 95.57 (np 2), deepseek 87.22 MiB.

Rig left idle: card 1 MiB used / 5745 free / 399 reserved, no containers, swap 0.
