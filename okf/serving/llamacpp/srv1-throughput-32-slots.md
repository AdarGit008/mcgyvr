---
type: Finding
title: "srv1 llama-server throughput at 32 slots"
id: claim-L15
description: "Claim L15 of the 2026-08-25 serving report: verified."
aliases: ["claim L15", "L15"]
tags: ["serving", "verdict:verified", "engine:llamacpp", "throughput", "rig:srv1"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-engine-sweep/README.md:83-84"
  - resource: "records/evidence/2026-08-24-engine-sweep/README.md:83"
  - resource: "records/headers/2026-08-24-engine-default-r2.json:63"
---

# L15 — srv1 llama-server throughput at 32 slots

**Claim as written.** srv1, 1.5B Q4_K_M, -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on: 446.6-448.9 agg tok/s at n=32.

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified against two independent takes of the same cell: B1-1 first pass **446.64** (p50 33.99 s) and its re-take R1 **448.92** (p50 33.76 s) — 0.5% apart, both `cap_frac 1.0` (every request produced all 475 tokens, so the aggregate is not an EOS artefact) and `fail 0`. The config is internally consistent with L2: `-c 32768` over `-np 32` with `-no-kvu` is 1,024 tokens/slot.

```bash
grep -n "B1-1 n=32\|R1 n=32" records/evidence/2026-08-24-engine-sweep/srv1.log
```

```
20:32:55   B1-1 n=32   446.64 tok/s  p50 33.993s  cap_frac 1.0  fail 0
20:36:38   R1 n=32     448.92 tok/s  p50 33.764s  cap_frac 1.0  fail 0
```

Bears on: `records/evidence/2026-08-24-engine-sweep/README.md:83-84`

## Evidence — srv1 [verified]

**439.69 agg tok/s at n=32 — 1.5% below the bottom of the recorded band, i.e.
inside the 2.6% across-reload bar (M5), so it reproduces.** 32 of 32 requests completed,
none failed, 475 tokens each, wall 34.57 s against the record's 33.99 s.
Same GGUF blob the engine sweep used
(`sha256-29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104`, the
`qwen2.5-coder:1.5b` ollama blob), same argv including `--metrics --slots -sps 0
--no-context-shift`, one cold container reload.

```bash
ssh srv1 'python3 /tmp/vc.py \
 "L15-1.5B-np32-c32768|/blobs/sha256-29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104|\
-ngl 99 -np 32 -c 32768 -no-kvu -b 1024 -ub 1024 -fa on --metrics --slots -sps 0 --no-context-shift|32"'
```

```
L15-1.5B-np32-c32768 READY load_s=3.0 vram=2044 loadavg=['0.90','1.53','1.17']
L15-1.5B-np32-c32768 RESULT {"n": 32, "agg": 439.69, "dec_p50": 13.94, "ttft_p50": 0.49,
                             "pp_p50": 20.4, "ok": 32, "fail": 0, "wall": 34.57}
```

Bears on: `records/evidence/2026-08-24-engine-sweep/README.md:83` (cell B1-1) and
`records/headers/2026-08-24-engine-default-r2.json:63`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
