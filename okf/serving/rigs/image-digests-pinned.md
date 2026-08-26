---
type: Finding
title: "Serving image digests are identical on both rigs"
id: claim-H3
description: "Claim H3 of the 2026-08-25 serving report: verified."
aliases: ["claim H3", "H3"]
tags: ["serving", "verdict:verified", "rig:srv1", "rig:srv2", "reproducibility"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-engine-sweep/"
  - resource: "records/evidence/2026-08-24-engine-sweep/README.md"
---

# H3 — Serving image digests are identical on both rigs

**Claim as written.** Both rigs hold identical image digests: llama.cpp server-cuda-b10481 = sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce; vllm/vllm-openai:v0.26.0 = sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52.

**Standing verdict: VERIFIED.**

## Evidence — srv1, srv1 arm [verified]

Both digests match on srv1, to the full 64 hex chars. (The srv2 half of "both rigs identical" is the srv2 crew's.) Note v0.26.0 and `latest` are the SAME image id on srv1 (ffb2d59b1c05).

```bash
ssh srv1 'docker images --digests'
```

```
ghcr.io/ggml-org/llama.cpp   server-cuda-b10481  sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce  b2497f8834f5
vllm/vllm-openai             v0.26.0             sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52  ffb2d59b1c05
vllm/vllm-openai             latest              sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52  ffb2d59b1c05
```

Bears on: `records/evidence/2026-08-24-engine-sweep/`

## Evidence — srv2, srv2 arm [verified]

Both digests match to the character on srv2. (The "both rigs identical" half is the srv1 crew's.)

```bash
ssh srv2 'docker images --digests'
```

```
ghcr.io/ggml-org/llama.cpp  server-cuda-b10481  sha256:b2497f8834f5ecb4e38530f6bf2734b8e0be107ff48e4720145911c86930f2ce
vllm/vllm-openai            v0.26.0             sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52
```

Bears on: `records/evidence/2026-08-24-engine-sweep/README.md`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
