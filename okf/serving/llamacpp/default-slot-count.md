---
type: Finding
title: "llama.cpp b10481 defaults to 4 slots"
id: claim-L1
description: "Claim L1 of the 2026-08-25 serving report: verified."
aliases: ["claim L1", "L1"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "concurrency"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: ".verify/CLAIMS.md"
  - resource: "records/evidence/2026-08-24-knob-surface/"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/width-sweep/np-semantics-probe.txt"
---

# L1 — llama.cpp b10481 defaults to 4 slots

**Claim as written.** b10481's default slot count is 4: with no --parallel/-np, /props reports total_slots 4.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified on a live b10481 server launched with no -np/--parallel: `"total_slots":4`, and the startup line says `n_slots = 4`.

```bash
ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"; curl -s localhost:8080/props | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[\"total_slots\"], d[\"default_generation_settings\"][\"n_ctx\"])"'
```

```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on","--host","0.0.0.0","--port","8080"]
"total_slots":4        n_ctx 4096
docker logs: srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'
```

Bears on: `.verify/CLAIMS.md` L1 / `records/evidence/2026-08-24-knob-surface/`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
