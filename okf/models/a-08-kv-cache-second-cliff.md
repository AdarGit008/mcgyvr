---
type: Concept
title: KV cache is computable and a second cliff trigger
description: KV = Σ over the caching layers of (k_elems + v_elems) × bytes per element × tokens, each layer's width from the header — a second, independent cliff.
tags: [local-ai, models]
---

# KV cache is computable and a second cliff trigger

KV cache is fully computable — per layer,
`(k_elems + v_elems) × bytes per element × tokens`, summed over the layers the
header declares as caching. One width applied to every layer is wrong by a large
factor on architectures with compressed or interval caching. It is a *second*,
independent cliff trigger (context, not weights): raising `-c` or `--parallel`
can fire it with the weights untouched, and a smaller KV dtype (`-ctk` / `-ctv`)
moves it back.
→ `okf/must-read/touching-rigs.md`
