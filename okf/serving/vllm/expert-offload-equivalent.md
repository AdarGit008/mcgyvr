---
type: Finding
title: "Whether vLLM has an expert-offload knob"
id: claim-V10
description: "Claim V10 of the 2026-08-25 serving report: falsified."
aliases: ["claim V10", "V10"]
tags: ["serving", "verdict:falsified", "engine:vllm", "moe", "placement"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:16:17Z }
sources:
  - resource: "records/evidence/2026-08-25-moe-expert-offload/README.md:180-181"
---

# V10 — Whether vLLM has an expert-offload knob

**Claim as written.** vLLM has no --n-cpu-moe equivalent, so a MoE larger than the card is not a vLLM workload.

**Standing verdict: FALSIFIED.**

## Evidence — srv1 [falsified]

**False on both halves.** `n_cpu_moe` does not appear in the package, but vLLM 0.26.0 ships **six** weight-offload flags, and one of them selects tensors **by parameter-name segment with expert FFN as its own documented example**:
`--cpu-offload-gb` + **`--cpu-offload-params`** — `vllm/config/offload.py:34-44`: *"The set of parameter name segments to target for CPU offloading… For parameter name `mlp.experts.w2_weight`: `experts` or `experts.w2_weight` will match."* So `--cpu-offload-gb 20 --cpu-offload-params experts` **is** an expert-FFN offload. `--offload-backend prefetch` with `--offload-group-size` / `--offload-num-in-group` / `--offload-prefetch-step` / `--offload-params` (`offload.py:53-77`) is the closer structural analogue to `--n-cpu-moe`: deterministic per-layer selection plus async H2D prefetch.

```bash
ssh srv1 'docker run --rm --entrypoint bash vllm/vllm-openai:v0.26.0 -c \
  "cd /usr/local/lib/python3.12/dist-packages/vllm && grep -rn \"n_cpu_moe\|n-cpu-moe\" --include=*.py . ; sed -n 30,80p config/offload.py"'
```

```
(zero hits for n_cpu_moe)
config/offload.py:34-44  cpu_offload_params: "The set of parameter name segments to target for CPU
  offloading... For parameter name `mlp.experts.w2_weight`: `experts` or `experts.w2_weight` will match."
config/offload.py:53-77  offload_backend={uva,prefetch}, offload_group_size, offload_num_in_group,
  offload_prefetch_step, offload_params   ("group_size=8, num_in_group=2 offloads layers 6,7,14,15,22,23,...")
```

Bears on: `records/evidence/2026-08-25-moe-expert-offload/README.md:180-181`

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
