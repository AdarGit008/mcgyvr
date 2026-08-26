---
type: Finding
title: "What engine choice is worth on srv1"
id: claim-M7
description: "Claim M7 of the 2026-08-25 serving report: falsified."
aliases: ["claim M7", "M7"]
tags: ["serving", "verdict:falsified", "method", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:16:17Z }
sources:
  - resource: "records/evidence/2026-08-24-engine-sweep/README.md:83-84"
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:20"
---

# M7 — What engine choice is worth on srv1

**Claim as written.** On srv1 the engine choice is worth ~1.5x at the same model and concurrency: llama-server 446.6-448.9 vs vLLM 229.7 at n=32 (1.5B).

**Standing verdict: FALSIFIED.**

## Evidence — srv1 [falsified]

The two numbers are correctly quoted from the record, but **446.6 / 229.7 = 1.94x and 448.9 / 229.7 = 1.95x — not ~1.5x.** The 1.5x figure comes from a *different* pairing: srv1's best vLLM cell is 293.6-294.7, and 446.6 / 293.6 = 1.52x — but that vLLM cell runs at n=128/n=256, so the "same concurrency" qualifier fails. As written the claim mixes the n=32 numerator with the n=128 denominator's ratio. **Restate as either "1.94x at matched n=32" or "1.5x against srv1's best vLLM configuration at its own best concurrency" — not both.**

```bash
grep -n "E1-1 \| B1-1 \| R1 " records/evidence/2026-08-24-engine-sweep/README.md
```

```
| E1-1 | vLLM         | 1.5B AWQ     | no-eager, len 1024, seqs 64, f16 KV | 44.2 | 27.5 | 107.0 | 229.7 |
| B1-1 | llama-server | 1.5B Q4_K_M  | -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on | 151.8 | 235.0 | 373.2 | 446.6 |
| R1   | llama-server | 1.5B Q4_K_M  | re-take of B1-1, better-of-two   | 152.2 | 236.6 | 370.3 | 448.9 |
python3 -c "print(446.6/229.7, 448.9/229.7, 446.6/293.6)"  ->  1.9442 1.9542 1.5211
```

Bears on: `records/evidence/2026-08-24-engine-sweep/README.md:83-84` and `records/evidence/2026-08-24-config-sweep/README.md:20`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
