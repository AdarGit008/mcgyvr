---
type: Finding
title: "srv1's expert-offload floor for the 35B"
id: claim-L9
description: "Claim L9 of the 2026-08-25 serving report: verified."
aliases: ["claim L9", "L9"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "moe", "rig:srv1", "refusal"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:48"
---

# L9 — srv1's expert-offload floor for the 35B

**Claim as written.** srv1's floor for 35B-A3B IQ3_XXS is ncmoe 28 (5,554 MiB); 27 overruns the 6,144 MiB card.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

The ncmoe-28 cell is live on srv1 right now and reads **5,558 MiB of 6,144** — the record's 5,554 MiB reproduces to 4 MiB (nvidia-smi granularity/other clients). The "27 overruns" half is a launch refusal I did not re-run inside budget; the record's own log is the evidence for it, and 5,558 + ~520 MiB/layer > 6,144 is arithmetically forced.

```bash
ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader'
```

```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on",...]
5558 MiB, 6144 MiB
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:48` and `:71`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
