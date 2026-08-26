---
type: Finding
title: "Time to first token, per rig"
id: claim-L10
description: "Claim L10 of the 2026-08-25 serving report: partial."
aliases: ["claim L10", "L10"]
tags: ["serving", "verdict:partial", "engine:llamacpp", "latency", "rig:srv1", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:46"
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
---

# L10 — Time to first token, per rig

**Claim as written.** srv1's TTFT is 5.5-6.0 s across EVERY configuration tried; srv2's is 0.67 s. No ncmoe or -t setting moves it.

**Standing verdict: PARTIAL.**

## Evidence — srv1, srv1 arm [verified]

srv1 arm reproduces. Five fresh `POST /completion` calls on the shipped winner (ncmoe 28, -t 6, 550-token prompt, `cache_prompt:false`) give TTFT **5.56 / 5.60 / 5.94 / 6.39** s, prefill 86-99 tok/s. The 5.5-6.0 band holds; the one 6.39 s sample coincided with CPU contention from another process (see M5). The "no setting moves it" half is an over-generalisation from the configs tried, not something a single re-run can verify — TTFT here is 550 tokens / ~95 tok/s prefill, i.e. it is set by prefill rate, and prefill IS bandwidth/CPU-bound under 28 offloaded layers.

```bash
ssh srv1 'python3 /tmp/verify_probe1.py 8080'   # 550-token corpus contract prompt, n_predict 160, temperature 0
```

```
rep0 tg=32.35 tok/s  prompt_n=550 ttft=5.94s  pp=92.5 tok/s
rep1 tg=33.48 tok/s  prompt_n=550 ttft=5.56s  pp=98.9 tok/s
rep2 tg=31.39 tok/s  prompt_n=550 ttft=5.60s  pp=98.3 tok/s
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:46` and `:73-77`

## Evidence — srv2, srv2 arm [partial]

srv2's sub-second TTFT is confirmed on every cell measured here, but I cannot confirm
the specific **0.67 s** because that figure was taken with the sweep's 527-token corpus prompt and
every cell here used the short 10-token prompt. Measured TTFT (`prompt_ms`) on the short prompt:

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md` ("The two winners" table, TTFT row)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
