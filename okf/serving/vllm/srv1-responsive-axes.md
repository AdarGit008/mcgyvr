---
type: Finding
title: "How many configuration axes move srv1"
id: claim-V3
description: "Claim V3 of the 2026-08-25 serving report: falsified."
aliases: ["claim V3", "V3"]
tags: ["serving", "verdict:falsified", "engine:vllm", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:16:17Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:43-50"
---

# V3 — How many configuration axes move srv1

**Claim as written.** srv1 responds to exactly ONE axis of twenty: 25 cells across compile, graphs, perf mode, scheduler, dtype, KV dtype, block size, prefix caching, chunked prefill, cascade attention, stream interval, watermark, attention backend and linear backend all land inside a 2.8% band (164-168 tok/s).

**Standing verdict: FALSIFIED.**

## Evidence — srv1 [falsified]

**False on the record's own data.** Of the 26 non-concurrency stage-1 cells that launched on srv1, **22** land in 164-168; **four do not**, and three of them are far outside — and they sit on axes the claim names by name:
- `async-sched-off` (**scheduler**) = **153.5** (-6.6% vs baseline 164.3)
- `attn-FLEX_ATTENTION` (**attention backend**) = **116.3** (-29%)
- `linear-triton` (**linear backend**) = **124.4** (-24%)
- `opt-level-3` = 168.1, marginally above the stated band.
So srv1 responds to *four* named axes, not one; three of them respond **downward**. The defensible restatement is "concurrency is the only axis that moves srv1 **up**; several others can move it sharply down." The cell count is also off: 22 in band, not 25.

```bash
python3 -c '
import json
d=[json.loads(l) for l in open("records/evidence/2026-08-24-config-sweep/srv1-1.5B.jsonl")]
for r in d:
  if r.get("launch",{}).get("ok") and r["axis"]!="concurrency": print(r["axis"], r["cell"], r["max_agg_tok_s"])'
```

```
scheduler          async-sched-off       153.5
attention-backend  attn-FLEX_ATTENTION   116.3
linear-backend     linear-triton         124.4
opt-level          opt-level-3           168.1
(22 others: 164.3 - 167.9)
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:43-50`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
