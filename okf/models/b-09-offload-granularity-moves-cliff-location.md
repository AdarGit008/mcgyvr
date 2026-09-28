---
type: Concept
title: Offload granularity moves the cliff location, not the ceiling
description: Expert-level keeps hot attention resident, only cold experts spill.
tags: [local-ai, hardware]
---

# Offload granularity moves the cliff location, not the ceiling

Offload granularity moves the *location* of the cliff, not the ceiling.
Expert-level offload (`--n-cpu-moe`) keeps hot attention resident and spills
only cold experts; layer-level offload (lowering `-ngl`) spills attention with
them.
→ `okf/config/llama.cpp.md` `--n-cpu-moe`, `-ngl`
