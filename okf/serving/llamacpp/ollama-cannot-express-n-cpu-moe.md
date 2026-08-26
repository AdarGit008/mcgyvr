---
type: Finding
title: "ollama cannot express expert offload"
id: claim-L4
description: "Claim L4 of the 2026-08-25 serving report: verified."
aliases: ["claim L4", "L4"]
tags: ["serving", "verdict:verified", "engine:ollama", "moe", "placement"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:39-40"
---

# L4 — ollama cannot express expert offload

**Claim as written.** ollama cannot express --n-cpu-moe; it splits whole layers only (upstream ollama/ollama#11772).

**Standing verdict: VERIFIED.**

## Evidence — srv1 [verified]

Verified on the mechanism. ollama's only placement knob is `num_gpu`, a **layer count** (`api/types.go:589-594`, default `-1` = dynamic), and its llama.cpp launcher emits exactly one placement argument: `-ngl <NumGPU>` (`llm/llama_server.go:404-410`). **Citation correction:** #11772 is a *feature request* ("use cpu to offload moe weights to reduce the VRAM usage", opened 2025-08-07, still open) — it is demand-side evidence, not a statement of incapacity. The sharper citation is `llm/llama_server.go:404-410` plus PR #12333 (`num_moe_offload`, opened 2025-09-18, **unmerged**, with maintainer `jessegross` noting "generally we are not adding new features to the old llama engine").

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:39-40` · https://github.com/ollama/ollama/issues/11772 · https://github.com/ollama/ollama/pull/12333

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
