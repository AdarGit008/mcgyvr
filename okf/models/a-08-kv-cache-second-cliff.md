---
type: Concept
title: KV cache is computable and a second cliff trigger
description: KV = Σ over the caching layers of (k_elems + v_elems) × bytes per element × tokens, each layer's width from the header via kv_bytes — a second, independent cliff.
tags: [local-ai, models]
---

# KV cache is computable and a second cliff trigger

**Data point.** KV cache is fully computable — per layer, `(k_elems + v_elems) × bytes per element × tokens`, summed over the layers the header declares as caching; `kv_bytes` in `src/mcgyvr/serving/vramfit.py` reads each layer's width from the header, and one width for every layer is 5× wrong on deepseek2 — and it's a *second*, independent cliff trigger (context, not weights).
