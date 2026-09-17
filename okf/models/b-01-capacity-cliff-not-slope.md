---
type: Concept
title: Capacity boundary is a cliff, not a slope
description: A small VRAM overflow costs a large multiple of speed — a discontinuity, not a graceful slope.
tags: [local-ai, hardware]
---

# Capacity boundary is a cliff, not a slope

The capacity boundary is a *cliff*, not a slope — a small VRAM overflow costs a
large multiple of speed, not a proportional one. Size to stay under it with the
margin stated; do not plan on degrading gracefully past it.
