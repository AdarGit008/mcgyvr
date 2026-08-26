---
type: Finding
title: "A smaller quant of a bigger model wins"
id: claim-L18
description: "Claim L18 of the 2026-08-25 serving report: verified."
aliases: ["claim L18", "L18"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "quantisation", "moe"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
---

# L18 — A smaller quant of a bigger model wins

**Claim as written.** A smaller quant of a bigger model beats a bigger quant of a smaller one: 35B-A3B IQ3_XXS (13.21 GB) 67.04 tok/s vs 30B-A3B Q4_K_M (18.56 GB) 44.84 on srv2.

**Standing verdict: VERIFIED.**

## Evidence — srv2 [verified]

Both sides reproduce within 1%. 35B-A3B IQ3_XXS at the recorded winner argv reads

```bash
# 35B side: the rig's own winner configuration, single 160-token completion after a warm-up
ssh srv2 'curl -s http://localhost:8080/completion -d "{\"prompt\":\"Write a Python function that merges two sorted lists.\",\"n_predict\":160,\"temperature\":0,\"cache_prompt\":false}" | python3 -c "import json,sys; t=json.load(sys.stdin)[\"timings\"]; print(t[\"predicted_per_second\"], t[\"prompt_per_second\"], t[\"prompt_ms\"])"'
```

```
S1_decode 67.47   prefill_tok_s 111.8   ttft_s 0.089     # argv: -ngl 99 --n-cpu-moe 4 -t 10 -c 4096 -fa on --no-mmap
L6-nommap n=1 decode_tok_s_p50=44.82                     # argv: -ngl 99 --n-cpu-moe 20 -t 10 -c 4096 -fa on --no-mmap
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md` ("Findings", 2nd bullet)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
