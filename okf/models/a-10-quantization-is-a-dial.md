---
type: Concept
title: Quantization is a dial, not a tax
description: Bits-per-parameter moves the cliff line itself; take the real figure from the tensor table, never from the quant name.
tags: [local-ai, models]
---

# Quantization is a dial, not a tax

Quantization is a *dial*, not a tax — bits-per-parameter moves
the cliff line itself, so a deeper quant does not merely shrink a model, it
relocates the capacity boundary the model is judged against. **Do not estimate
bits-per-parameter from the quant name, or from file size over parameter
count.** The name is nominal, the mixes are heterogeneous, and both shortcuts
have been wrong here in the direction that admits a placement which then does
not fit. Sum the tensor table for the real figure.
→ `okf/must-read/touching-models.md`
