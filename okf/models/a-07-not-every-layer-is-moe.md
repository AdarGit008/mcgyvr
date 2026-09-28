---
type: Concept
title: Not every layer is MoE
description: first_k_dense_replace / mlp_only_layers keep some layers dense; read the expert-bearing blocks from the tensor table.
tags: [local-ai, models]
---

# Not every layer is MoE

Not every layer is MoE — `first_k_dense_replace` / `mlp_only_layers` keep some
layers dense, and other families are MoE throughout. Read the expert-bearing
blocks from the tensor table; never assume they equal the layer count.
→ `okf/config/llama.cpp.md` `--n-cpu-moe` for what that does to N
