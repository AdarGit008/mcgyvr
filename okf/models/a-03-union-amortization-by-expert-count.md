---
type: Concept
title: Union amortization depends on expert count, not batch size
description: Few experts reach full coverage by n=4; many experts stay ~linear; distinct = N·(1−(1−1/N)^(n·k)).
tags: [local-ai, models]
---

# Union amortization depends on expert count, not batch size

**Data point.** Few experts (Mixtral 8) reach full coverage by n=4 (union_factor ≈ 0.44); many experts (512) stay ~linear (≈ 0.93 at n=8) — batching barely shares anything. Tool: `distinct = N·(1−(1−1/N)^(n·k))`.
