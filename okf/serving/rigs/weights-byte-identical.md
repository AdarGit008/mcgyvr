---
type: Finding
title: "Model weights are byte-identical across rigs"
id: claim-H4
description: "Claim H4 of the 2026-08-25 serving report: verified."
aliases: ["claim H4", "H4"]
tags: ["serving", "verdict:verified", "rig:srv1", "rig:srv2", "reproducibility"]
status: stable
verified: { by: human:adar, at: 2026-08-26T04:17:00Z }
sources:
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md:43"
  - resource: "records/measurements/serving-sweep-2026-08-25/README.md"
---

# H4 — Model weights are byte-identical across rigs

**Claim as written.** Weights are byte-identical across rigs: Qwen3.6-35B-A3B-UD-IQ3_XXS 9c964e657212fea1…, Qwen2.5-Coder-7B-IQ4_XS f7eff217195ff980…, qwen3-coder-30b Q4_K_M 1194192cf2a187eb… (18,556,688,736 B).

**Standing verdict: VERIFIED.**

## Evidence — srv1, srv1 arm; the "across rigs" half is the srv2 crew's [verified]

All three srv1 digests and the one quoted size match to the digit. Full digests recorded here so the srv2 crew has something to compare against, not just a prefix.

```bash
ssh srv1 'for f in Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf qwen3-coder-30b.gguf; do
            printf "%s  %s  " "$(stat -c %s /home/adaramir/ggufs/$f)" "$f"; sha256sum /home/adaramir/ggufs/$f | cut -d" " -f1; done'
```

```
13211155424  Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf        9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe
 4218473248  Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf  f7eff217195ff98092353ab2a101882e5a756513d6080d6fdd6bcae2f21831ac
18556688736  qwen3-coder-30b.gguf                   1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md:43` and `rig-reality-2026-08-25.md` ("Are the two hosts serving the same weights?")

## Evidence — srv2, srv2 arm [verified]

All three prefixes reproduce on srv2, and the 30B blob's size is exactly
18,556,688,736 B. (Byte-identity *across* rigs needs the srv1 crew's half; srv2's side is exact.)

```bash
ssh srv2 'sha256sum /home/adaramir/ggufs/*.gguf /usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a
          stat -c "%s %n" /usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb... /home/adaramir/ggufs/*.gguf'
```

```
f7eff217195ff98092353ab2a101882e5a756513d6080d6fdd6bcae2f21831ac  Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf
9c964e657212fea1f24905dd7b0a89b82fd807d19fab0b41da14251b07b88fbe  Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a  .../blobs/sha256-1194192cf2a187eb...
18556688736 /usr/share/ollama/.ollama/models/blobs/sha256-1194192cf2a187eb...
 4218473248 /home/adaramir/ggufs/Qwen2.5-Coder-7B-Instruct-IQ4_XS.gguf
13211155424 /home/adaramir/ggufs/Qwen3.6-35B-A3B-UD-IQ3_XXS.gguf
```

Bears on: `records/measurements/serving-sweep-2026-08-25/README.md` ("The two winners" table)

---

Register: `records/evidence/2026-08-26-claim-verification/CLAIMS.md` · Findings: `records/evidence/2026-08-26-claim-verification/srv1-findings.md`, `records/evidence/2026-08-26-claim-verification/srv2-findings.md` · Report: `records/evidence/2026-08-26-claim-verification/REPORT.md`
