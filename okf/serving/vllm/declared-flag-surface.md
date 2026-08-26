---
type: Finding
title: "The declared vLLM flag surface, and how much was tried"
id: claim-V9
description: "Claim V9 of the 2026-08-25 serving report: partial."
aliases: ["claim V9", "V9"]
tags: ["serving", "verdict:partial", "engine:vllm", "coverage"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:3-7"
---

# V9 — The declared vLLM flag surface, and how much was tried

**Claim as written.** The image declares 275 flags, 250 with a printed default, 31 with a choice set. The config sweep tried 20 of them; 255 are untried.

**Standing verdict: PARTIAL.**

## Evidence — srv1 [partial]

**275 ✓ and 250 ✓** reproduce to the digit. **31 ✗** — no counting rule tried yields 31; the measurement is **32** actions carrying an argparse `choices` set / **33** flags printing a `{a,b,c}` metavar / **37** including 4 Literal-style `['a','b']` metavars. `Possible choices:` appears 0 times in the output. Two gotchas that make this hard to reproduce and are worth recording: `vllm serve --help` **fails on a CPU-only box** in this image (`RuntimeError: Failed to infer device type`, `vllm/config/device.py:56`), and `--help` alone prints only a *group index* — the full listing needs **`--help=all`** (`vllm/utils/argparse_utils.py:169-183`).

```
# inside the image, with a sitecustomize shim stamping device_type="cpu" onto UnspecifiedPlatform
vllm serve --help=all 2>/dev/null > /tmp/H
sed -n '/^options:/,$p' /tmp/H > /tmp/B
grep -oE '^  --[a-z0-9][a-z0-9-]*' /tmp/B | tr -d ' ' | sort -u | grep -cv '^--no-'   # 274 long flags (+ -h/--help = 275)
grep -c '(default:' /tmp/B                                                            # 250
grep -cE '^  --[a-z0-9-]+ \{' /tmp/B                                                  # 33
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:3-7`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
