---
type: Finding
title: "Single-stream rate does not depend on slot count"
id: claim-L22
description: "Claim L22 of the 2026-08-25 serving report: partial."
aliases: ["claim L22", "L22"]
tags: ["serving", "verdict:partial", "engine:llamacpp", "throughput"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:164-165"
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
---

# L22 — Single-stream rate does not depend on slot count

**Claim as written.** The single-stream S1 column of serving-sweep-2026-08-25 is a property of its named configuration and does NOT depend on -np.

**Standing verdict: PARTIAL.**

## Evidence — srv1, srv1 arm, from the width sweep's own srv1 cells [verified]

Verified on srv1 data. The width sweep varied `-np` from 1 to 16 at fixed model/flags and read n=1 each time: srv1 7B IQ4_XS gives **54.5 / 54.3 / 54.2 / 54.1** at np 1/4/8/16 — a 0.7% spread, an order of magnitude inside srv1's own run-to-run behaviour (M5). srv1 35B-A3B at ncmoe 35 gives **29.1 / 28.4 / 29.3 / 29.3** at np 1/4/8/16 — 3.1%, also a tie. So the S1 column survives the `-np` correction that voids the `tasks/h @8` column; a single stream uses one slot regardless of how many exist.

```bash
sed -n '/### srv1, 7B IQ4_XS/,/^$/p' records/evidence/2026-08-25-moe-expert-offload/width-sweep/README.md
```

```
| -np | -c     | VRAM  | n=1  |
| 1   | 1,024  | 4,012 | 54.5 |
| 4   | 4,096  | 4,180 | 54.3 |
| 8   | 8,192  | 4,404 | 54.2 |
| 16  | 16,384 | 4,852 | 54.1 |
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:164-165`

## Evidence — srv2 [partial]

The S1 value itself reproduces at the named configuration (**67.47** against 67.04),
so the column is a real measurement of its argv. But the *independence from `-np`* is **not
established at the precision the column implies**, and the record's own data argues against it:
the srv2 35B width sweep's n=1 column reads 44.7 / 44.4 / **40.0** / 44.8 / 44.9 at np =
1/4/8/16/32 — a 12% spread, with np=8 an 11% outlier. My own reload-to-reload spread on that
same cell is 5.2% (M5). So S1 is `-np`-independent only to within roughly +/-5-12%, which is
larger than several of the differences the S1 column is used to argue about.

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md` ("What survives", final line)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
