---
type: Finding
title: "Nothing in the serving corpus scores quality"
id: claim-M6
description: "Claim M6 of the 2026-08-25 serving report: verified."
aliases: ["claim M6", "M6"]
tags: ["serving", "verdict:verified", "method", "scope"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:114"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:268-269"
---

# M6 — Nothing in the serving corpus scores quality

**Claim as written.** Nothing in this corpus scores quality: every rate is tokens produced, not tokens worth keeping. No task passed or failed.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified by reading every driver that produced a number. None of `sweep.py`, `drivers/*.py`, `width-sweep/lcpsweep.py` or `probe_np.sh` contains a single `assert`, comparison to a reference, or call to a task's `accept.py` — a grep for `assert|correct|accept|expected|pass_|fail_|unittest|pytest` across all of them returns **nothing**. Every cell posts one fixed prompt at `temperature: 0` with `ignore_eos`/`n_predict` forcing a fixed length, and records `timings.predicted_per_second`. The reply text is never read.

```bash
grep -rniE "assert|correct|accept|expected|pass_|fail_|unittest|pytest" \
  records/measurements/serving-sweep-2026-08-25/sweep.py \
  records/evidence/2026-08-25-moe-expert-offload/drivers/ \
  records/evidence/2026-08-25-moe-expert-offload/width-sweep/lcpsweep.py
# (no output)
sed -n '117,118p' records/measurements/serving-sweep-2026-08-25/sweep.py
```

```
        rec["score_S1"] = round(rec["S1_tok_s"] * cell["params_b"])
        rec["score_S8"] = round(rec["S8_tok_s"] * cell["params_b"])
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:114` and `records/evidence/2026-08-25-moe-expert-offload/README.md:268-269`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
