---
type: Concept
title: Active experts are per-layer, not per-model
description: Experts-per-token is per layer; active experts per token = per-token count × expert-bearing layers.
tags: [local-ai, models]
---

# Active experts are per-layer, not per-model

The header's experts-per-token (`expert_used_count`, `num_experts_per_tok`) is
*per layer*: active experts per token = per-token count × expert-bearing layers,
not the per-token count. Multiply before sizing bytes read per token, and take
the expert-bearing layer count from the tensor table, not from the layer count.
