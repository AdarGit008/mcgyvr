---
type: Concept
title: Shared/routed expert split is a resident-vs-offload boundary
description: n_shared_experts marks the always-hot part vs the cold, offloadable part.
tags: [local-ai, models]
---

# Shared/routed expert split is a resident-vs-offload boundary

The shared/routed expert split (`n_shared_experts`) *is* a resident-vs-offload
boundary, not an inference detail. Shared experts (`ffn_*_shexp`) are not among
the tensors the expert-offload flags move, so budget them as card-resident at
every N.
→ `okf/config/llama.cpp.md` `--n-cpu-moe`
