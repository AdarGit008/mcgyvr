---
type: Concept
title: Union amortization depends on expert count, not batch size
description: Batching shares expert reads only when the expert count is small; with many experts coverage stays nearly linear. Compute it, do not assume a factor.
tags: [local-ai, models]
---

# Union amortization depends on expert count, not batch size

Batching amortizes expert reads only when the expert count is
small. With a handful of experts a batch reaches near-full coverage quickly, so
the union factor collapses and batching buys a lot; with several hundred
experts, coverage stays nearly linear in batch size and batching shares almost
nothing. **Compute the distinct-expert count rather than assuming a sharing
factor** — for `N` experts, batch `n` and top-`k`,
`distinct = N·(1−(1−1/N)^(n·k))` — and read the union factor off that, at the
width you actually intend to serve.
