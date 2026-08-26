---
type: Finding
title: "srv1's vLLM throughput ceiling"
id: claim-V4
description: "Claim V4 of the 2026-08-25 serving report: verified."
aliases: ["claim V4", "V4"]
tags: ["serving", "verdict:verified", "engine:vllm", "throughput", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:46-50"
---

# V4 — srv1's vLLM throughput ceiling

**Claim as written.** srv1's vLLM ceiling is ~293-294 agg tok/s and is NOT context-bound: -max-model-len 4096/2048/1024/512 all return 293.3-293.4 at seqs 128.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified in the cell records to four significant figures — 293.3 / 293.3 / 293.3 / 293.4 for len 4096 / 2048 / 1024 / 512 at `--max-num-seqs 128`, and the stage-2 crossings top out at 294.7. Not re-run on the rig: four vLLM launches would have cost ~12 min of a 60-min budget for a figure whose four independent cells already agree to 0.03%.

```bash
python3 -c '
import json
for f in ["records/evidence/2026-08-24-config-sweep/srv1-1.5B.jsonl","records/evidence/2026-08-24-config-sweep/srv1-1.5B-stage2.jsonl"]:
 for l in open(f):
  r=json.loads(l)
  if r.get("launch",{}).get("ok") and ("len" in r["cell"]): print(r["cell"], r["max_agg_tok_s"], "@n", r["max_at_n"])'
```

```
len4096-seqs128 293.3 @n 128 | len2048-seqs128 293.3 @n 128
len1024-seqs128 293.3 @n 128 | len512-seqs128  293.4 @n 128
s2-noeager-len1024-seqs256 294.2 | s2-noeager-len512-seqs256 294.7 | s2-noeager-opt3-len1024-seqs256 294.7
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:46-50`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
