---
type: Finding
title: "Two expert-offloaded MoE models co-reside on srv1"
id: claim-L21
description: "Claim L21 of the 2026-08-25 serving report: verified."
aliases: ["claim L21", "L21"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "moe", "co-residency", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:229-233"
---

# L21 — Two expert-offloaded MoE models co-reside on srv1

**Claim as written.** Two different expert-offloaded MoE models co-reside on srv1 in 2,702 MiB of 6,144, both healthy.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified] *(superseded below)*

The raw log records `qwen3-coder:30b` at `--n-cpu-moe 48` = 1,274 MiB and `deepseek-coder-v2:16b` at `--n-cpu-moe 27` = 1,424 MiB, summing to **2,702 MiB of 6,144** with both serving. Both GGUFs are still on srv1 (`deepseek-coder-v2-16b.gguf` 8,905,109,984 B, `qwen3-coder-30b.gguf` 18,556,688,736 B), so the cell is reproducible. **Read it with L20 attached:** "both healthy" is only true at `-t 3` each; at `-t 5` each they are both alive and both 14x slower, which is a *worse* outcome than not co-residing.

```
sed -n '152,157p' records/evidence/2026-08-25-moe-expert-offload/raw-postswap-squeeze-concurrency.txt
```

## Evidence — srv1 [verified]

**Co-residency verified live — but at `-c 4096` each it costs 3,466 MiB, not
2,702.** Both servers loaded, both passed `/health`, both answered a 475-token generation:
`qwen3-coder-30b` at `--n-cpu-moe 48` = **1,484 MiB** (record 1,274) and
`deepseek-coder-v2-16b` at `--n-cpu-moe 27` bringing the pair to **3,466 MiB** (record 2,702),
leaving 2.6 GB free on the 6,144 MiB card. The 764 MiB difference is the KV cache: I gave both
`-c 4096` to match every other cell in this verification, and the record does not state what
`-c` its co-residency pair carried. **The claim's shape is right and its headroom conclusion
is right; its specific MiB figure is not reproducible without the missing `-c`.**

```bash
BOTH_RESIDENT vram=3466 MiB   (docker ps: vA, vB)
A: qwen3-coder-30b       --n-cpu-moe 48 -c 4096 -> 1,484 MiB, /health 200, 475 tokens served
B: deepseek-coder-v2-16b --n-cpu-moe 27 -c 4096 -> pair 3,466 MiB, /health 200, 475 tokens served
```

```
  ssh srv1 'docker start llama-sweep'
  ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"'
  ["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on","--host","0.0.0.0","--port","8080"]
  Image=ghcr.io/ggml-org/llama.cpp:server-cuda-b10481  Restart=no
  Ports={"8080/tcp":[{"HostIp":"","HostPort":"8080"}]}  Binds=["/home/adaramir/ggufs:/models"]
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:229-233` and
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

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
