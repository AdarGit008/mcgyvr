---
type: Finding
title: "The tasks/h figures measured a slot default, not a configuration"
id: claim-M1
description: "Claim M1 of the 2026-08-25 serving report: partial."
aliases: ["claim M1", "M1"]
tags: ["serving", "verdict:partial", "method", "defect"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:127-133"
---

# M1 — The tasks/h figures measured a slot default, not a configuration

**Claim as written.** Every `tasks/h @8` figure in serving-sweep-2026-08-25 is void: 8 concurrent requests against llama.cpp's default 4 slots is 4 served and 4 queued, so the figure is not a property of the configuration.

**Standing verdict: PARTIAL.**

## Evidence — srv1 [partial]

The **mechanism is verified directly**: I fired 8 concurrent completions at the live default-slot server while polling `/slots` every 500 ms. `total_slots` stayed 4 and the number of slots with `is_processing:true` never exceeded **4** for the whole 109.7 s burst — exactly 4 served, 4 queued. What does *not* follow is "void": 4 slots was part of the configuration as run (it is the build default, and the record states `total_slots: 4` for every cell). The figure is a real property of *that* configuration; what it is not is a property of the model+flags independent of slot count. The record's own correction says the milder thing ("read every `tasks/h @8` column as tasks/h at 8 requests against 4 slots"), and that is the defensible version.

```bash
# /slots polled at 2 Hz during 8 concurrent POST /completion (n_predict 160)
ssh srv1 'python3 /tmp/verify_probe1.py 8080'
```

```
BURST8 wall=109.7s total_tokens=1280 agg=11.7 tok/s tasks/h=262
BURST8 slots_total=4 max_simultaneously_processing=4
slot samples (total,busy): [(4,0),(4,1),(4,4),(4,4),(4,4),(4,4),(4,4),(4,4), ...]   # never (4,5+)
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:127-133`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
