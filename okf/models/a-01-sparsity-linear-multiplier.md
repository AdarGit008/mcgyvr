---
type: Concept
title: Sparsity is a linear metric multiplier
description: The eval metric collapses to (BW/bpp) × (total/active) × (1/union_factor) — sparsity is a linear multiplier.
tags: [local-ai, models]
---

# Sparsity is a linear metric multiplier

Decode is bounded by memory bandwidth over bytes read per token, so the metric
collapses to `(BW / bpp) × (total/active) × (1/union_factor)` — sparsity is a
*linear* multiplier. Compute `total/active` from the header's expert count and
top-k before comparing two checkpoints; at equal bytes per parameter the sparser
one reads fewer bytes per token.
→ `okf/must-read/touching-models.md`
