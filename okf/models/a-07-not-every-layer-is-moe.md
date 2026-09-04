---
type: Concept
title: Not every layer is MoE
description: first_k_dense_replace / mlp_only_layers keep early layers dense.
tags: [local-ai, models]
---

# Not every layer is MoE

**Data point.** Not every layer is MoE — `first_k_dense_replace` / `mlp_only_layers` keep early layers dense. gpt-oss/GLM keep layer 0 dense; Qwen3-235B is `mlp_only_layers=[]` (all-MoE).
