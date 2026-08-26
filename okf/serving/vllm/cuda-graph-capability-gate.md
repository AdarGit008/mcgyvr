---
type: Finding
title: "vLLM 0.26.0 has no compute-capability gate on graph capture"
id: claim-V2
description: "Claim V2 of the 2026-08-25 serving report: partial."
aliases: ["claim V2", "V2"]
tags: ["serving", "verdict:partial", "engine:vllm", "cuda-graphs", "source"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/evidence/2026-08-24-config-sweep/README.md:62-65"
---

# V2 — vLLM 0.26.0 has no compute-capability gate on graph capture

**Claim as written.** vLLM 0.26.0 has NO compute-capability gate on CUDA graph capture; docs/features/README.md lists CUDA graph as supported on Turing; the only forced-eager paths are ROCm encoder-decoder and 8-bit bitsandbytes.

**Standing verdict: PARTIAL.**

## Evidence — srv1 [partial]

(a) **No capability gate on graph capture — VERIFIED.** Zero lines in the whole installed package pair `capability` with `graph`/`eager`; the cudagraph files carry no capability check at all. (b) **Turing supported in the matrix — VERIFIED** (upstream v0.26.0). (c) **"only two forced-eager paths" — FALSE.** There is a **third** engine-set `enforce_eager = True`, and the claim also misses that cudagraph is disabled by a *different* mechanism (`cudagraph_mode = CUDAGraphMode.NONE`) in at least six more places.

```bash
ssh srv1 'docker run --rm --entrypoint bash vllm/vllm-openai:v0.26.0 -c \
  "cd /usr/local/lib/python3.12/dist-packages/vllm && grep -rn \"capability\" --include=*.py . | grep -i \"graph\\|eager\""'
```

```
(exit 1 — zero matches)
```

```
/usr/local/lib/python3.12/dist-packages/vllm/config/model.py:1147        _verify_cuda_graph()  ROCm encoder-decoder   [claimed]
/usr/local/lib/python3.12/dist-packages/vllm/config/model.py:1175        _verify_bnb_config()  load_in_8bit           [claimed]
/usr/local/lib/python3.12/dist-packages/vllm/config/speculative.py:699   deepseek_v32 MTP  "# FIXME(luccafong): cudagraph with v32 MTP is not supported"   [MISSED]
```

Bears on: `records/evidence/2026-08-24-config-sweep/README.md:62-65` · https://raw.githubusercontent.com/vllm-project/vllm/v0.26.0/docs/features/README.md

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
