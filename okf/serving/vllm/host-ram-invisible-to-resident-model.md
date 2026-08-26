---
type: Finding
title: "Host RAM is invisible to a card-resident model"
id: claim-V13
description: "Claim V13 of the 2026-08-25 serving report: partial."
aliases: ["claim V13", "V13"]
tags: ["serving", "verdict:partial", "engine:vllm", "memory"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md"
---

# V13 — Host RAM is invisible to a card-resident model

**Claim as written.** vLLM reproduces across srv2's 32GB->16GB RAM change (6,562.0 vs 6,445.1/6,452.2/6,480.6; 1,617.2 vs 1,604.7): a model resident on the card never touches system RAM in the decode path.

**Standing verdict: PARTIAL.**

## Evidence — srv2 [partial]

The 1.5B half is verified twice over on the post-swap 16 GB host — 6,600.6 and
6,602.5, inside the pre-swap band. The 7B half (1,617.2 vs 1,604.7) was **not re-run**: it
needs a separate ~4 min model load and the budget went to V1/V5/V6 and the llama.cpp contrasts.
The mechanism is independently supported here: at `--gpu-memory-utilization 0.85` the engine's
own startup line accounts for **all** of weights, activation and KV on the device
(1.1 GiB weights + 0.45 GiB activation + 8.29 GiB KV), with nothing host-resident in the
decode path.

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` §5

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
