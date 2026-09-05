---
type: Concept
title: KV cache is computable and a second cliff trigger
description: KV = 2 × layers × kv_heads × head_dim × 2B × tokens — a second, independent cliff.
tags: [local-ai, models]
---

# KV cache is computable and a second cliff trigger

**Data point.** KV cache is fully computable — `2 × layers × kv_heads × head_dim × 2B × tokens` — and it's a *second*, independent cliff trigger (context, not weights).
