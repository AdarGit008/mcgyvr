---
type: Concept
title: Active experts are per-layer, not per-model
description: num_experts_per_tok is per layer; active experts/token = per-tok × layers.
tags: [local-ai, models]
---

# Active experts are per-layer, not per-model

**Data point.** `num_experts_per_tok` is *per layer* — active experts/token = per-tok × layers (Qwen3-Next: 10 × 48 = 480, not 10).
