---
type: Finding
title: "Run-to-run spread, per rig and per engine"
id: claim-M5
description: "Claim M5 of the 2026-08-25 serving report: falsified."
aliases: ["claim M5", "M5"]
tags: ["serving", "verdict:falsified", "method", "noise", "rig:srv1", "rig:srv2"]
status: stable
verified: { by: human:adar, at: 2026-08-25T21:47:56Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:264-267"
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md"
  - resource: "width-sweep/README.md"
---

# M5 — Run-to-run spread, per rig and per engine

**Claim as written.** Run-to-run spread: srv2 repeats within 0.2%; srv1 varies 5-10%, so an srv1 gap under ~10% is a tie.

**Standing verdict: FALSIFIED.**

## Evidence — srv1 [falsified] *(superseded below)*

**On a quiet srv1, twelve consecutive single-stream repeats of the shipped winner agree within 0.77%** — 33.22 to 33.48 tok/s, no outliers, TTFT 5.56-5.63 s. That is the same order as srv2's quoted 0.2%, not 5-10%. I also reproduced the 5-10%-and-worse behaviour twice, and **isolated its cause: CPU contention, not the rig**. When one CPU-only research container of mine was also running on srv1's 6 cores, the same cell produced a 4x collapse — a single sample at **7.58 tok/s** against a 33.44 median (77% "spread"), plus 31.7-tok/s samples. srv1 offloads 28 of 48 expert-FFN layers to 6 cores at `-t 6`, so it has **zero spare core** and any co-tenant lands directly on the decode path.

```bash
ssh srv1 'docker ps --format "{{.Names}}"; python3 /tmp/verify_m5b.py'   # 12 x POST /completion, n_predict 160, temp 0, cache_prompt false
```

```
llama-sweep                      <- sole container; quiet box
t+  10.3s slot=0 tg=  33.48 ttft=5.56
t+  20.7s slot=0 tg=  33.22 ttft=5.60
t+  31.1s slot=0 tg=  33.44 ttft=5.60
...
t+ 124.5s slot=0 tg=  33.35 ttft=5.63
median=33.35 n_good=12 good-spread=0.77%  outliers=[]
```

```
docker ps: ['wonderful_moser', 'llama-sweep']
rep0 tg=33.53   rep1 tg=33.50   rep2 tg=7.62(!)   rep3 tg=33.54   rep4 tg=31.68   rep5 tg=31.90
S1 median=32.70  min=7.62 max=33.54  full-spread=79.3%
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:264-267` and `records/measurements/serving-sweep-2026-08-25/README.md` (every srv1 comparison that invokes the 10% tie rule)

## Evidence — srv1, srv1 across-reload arm [falsified]

**Both the record's 5–10% and my own earlier 0.77% are the wrong bar, for
different reasons.** Four *cold container reloads* of one identical llama.cpp cell, run
back to back by one driver, read **25.83 / 25.50 / 25.45 / 25.16 tok/s** — a **2.6% span**
(mean 25.49, sd 0.26 = 1.0%). VRAM was 4,420 MiB on all four, so the resolved config was
identical every time.
So the correct srv1 bar has **two levels**, and the corpus conflates them:
- *steady-state*, repeated requests against one already-loaded server: **0.77%** (my
  2026-08-25 measurement, 12 repeats) — this is what the record's own "3 reps, 0.04% spread"
  at ncmoe 37 measures too, and it is the weakest form of repeatability.
- *across reloads*, which is what every configuration contrast in this corpus actually is:
  **2.6%** on srv1. (The srv2 crew's matching figure is 5.2%.)
The record's 5–10% is too loose on srv1 by 2–4x and would call real 3–5% effects ties;
the 0.77% figure is too tight by 3.4x and would call reload noise a result.

```bash
ssh srv1 'python3 /tmp/vc.py \
 "M5-30b-nm40-t5-take1|/models/qwen3-coder-30b.gguf|-ngl 99 --n-cpu-moe 40 -t 5 -c 4096 -fa on|1" ...take2 ...take3 ...take4'
```

```
M5-30b-nm40-t5-take1 READY load_s=21.2 vram=4420   dec_p50=25.83  ttft=0.495  loadavg 0.16
M5-30b-nm40-t5-take2 READY load_s=3.0  vram=4420   dec_p50=25.50  ttft=0.291  loadavg 1.44
M5-30b-nm40-t5-take3 READY load_s=3.0  vram=4420   dec_p50=25.45  ttft=0.288  loadavg 2.48
M5-30b-nm40-t5-take4 READY load_s=3.0  vram=4420   dec_p50=25.16  ttft=0.291  loadavg 3.48
(top, containers torn down: %Cpu(s): 1.5 us, 98.5 id — the loadavg column is decay, not a co-tenant)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` ("Bounds on all of
the above"); `records/measurements/serving-sweep-2026-08-25/README.md` wherever it calls an
srv1 gap under 10% a tie.

## Evidence — srv2, srv2 arm [verified] *(superseded below)*

Two independently loaded takes of the identical vLLM cell differ by **0.03%**
at n=256 (6,600.6 vs 6,602.5), 0.27% at n=16, 0.20% at n=1. The 0.2% figure is right for the
aggregate at high concurrency; at low n the spread is at the stated bound rather than inside it.
Note this is *repeatability of a reload*, which is the stronger form.

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` ("Bounds on all of the above")

## Evidence — srv2, srv2 arm [falsified] *(superseded below)*

True of vLLM (0.03% at n=256 across two cold loads) and **false of llama.cpp**.
Two cold loads of the identical llama.cpp cell, run minutes apart by the same driver, read

```bash
ssh srv2 'python3 /tmp/lcells.py \
  "L11-np1|...|-ngl 99 -np 1 -c 1024 --n-cpu-moe 25 -fa on|1" \
  ... \
  "M5-L11-np1-take2|...|-ngl 99 -np 1 -c 1024 --n-cpu-moe 25 -fa on|1"'
```

```
L11-np1            n=1 agg=44.5 decode_tok_s_p50=45.34  (vram=6069)
M5-L11-np1-take2   n=1 agg=42.2 decode_tok_s_p50=42.98  (vram=6069)
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md` ("Bounds on all of the
above"); `width-sweep/README.md` §1 table, n=1 column

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
