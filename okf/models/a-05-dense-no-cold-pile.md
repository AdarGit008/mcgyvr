---
type: Concept
title: Dense models have no cold pile
description: Dense = 1:1 ratio = no cold pile; offload degenerates to whole-layer tail, uniformly slow.
tags: [local-ai, models]
---

# Dense models have no cold pile

Dense = 1:1 ratio = *no cold pile at all*. The only offload left is lowering
`-ngl`, which spills whole layers and is uniformly slow. MoE's offload value is
the cold pile, not the routing.
→ `okf/config/llama.cpp.md` `--n-cpu-moe`
