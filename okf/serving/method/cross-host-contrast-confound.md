---
type: Finding
title: "The cross-host contrasts and their confound"
id: claim-M2
description: "Claim M2 of the 2026-08-25 serving report: partial."
aliases: ["claim M2", "M2"]
tags: ["serving", "verdict:partial", "method", "defect", "rig:srv1", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:90-103"
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
---

# M2 — The cross-host contrasts and their confound

**Claim as written.** The two "legal cross-host contrasts" (1.95x on 35B, 1.32x on 7B) are confounded: srv2 carried --no-mmap in every cell and srv1 in none, and that flag alone is worth +63%/-12..-18%.

**Standing verdict: PARTIAL.**

## Evidence — srv1 [verified]

Verified on three independent legs. (1) The argv are on the record and differ in the flag: srv1's winner is `-ngl 99 --n-cpu-moe 28 -t 6 -c 4096 -fa on` and srv2's is the same **plus `--no-mmap`** — and I confirmed srv1's live argv contains no `--no-mmap` today. (2) The flag's srv1 cost is -12..-18% (L6, verified). (3) The flag's srv2 gain is +63% (srv2 crew's arm). The contrast also folds in a **thread-count difference** (`-t 6` vs `-t 10/20`) and a **`--n-cpu-moe` difference** (28 vs 4), so `--no-mmap` is not even the only confound — the pair differs on at least four axes, not the "host and flags" the record names. What survives untouched is the byte-identity of the weights (H4) and the build identity.

```bash
ssh srv1 'docker inspect llama-sweep --format "{{json .Config.Cmd}}"'
sed -n '44p' records/measurements/serving-sweep-2026-08-25/README.md
```

```
["-m","/models/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf","-ngl","99","--n-cpu-moe","28","-t","6","-c","4096","-fa","on",...]   # no --no-mmap
| argv | `-ngl 99 --n-cpu-moe 28 -t 6 -c 4096 -fa on` | `-ngl 99 --n-cpu-moe 4 -t 10 -c 4096 -fa on --no-mmap` |
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:90-103` and `:146-150`

## Evidence — srv2, srv2 arm [partial]

The **existence** of the confound is verified — srv2's winner argv does carry
`--no-mmap` (`docker inspect llama-sweep` above, and every srv2 cell in the sweep's `cells/`).
The **magnitude** is falsified on srv2's side: at the record's own cell for that figure the flag
is worth **+2.1% cold / +5.0% warm**, not +63% (see L6). A 2-5% flag cannot account for a 1.95x
cross-host ratio, so the correction's arithmetic ("the 1.95x and 1.32x ratios fold host, thread
count and `--no-mmap` together") overstates the `--no-mmap` term by roughly an order of magnitude.
The srv1 side of the flag (-12..-18%) is the srv1 crew's to check.

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md` (CORRECTION §3)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
