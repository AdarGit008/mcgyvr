---
record: session/1
lane: 252
agent: adar
started: 2026-08-14
---

## Did

**Surveyed the field for portable code and reusable evidence, and recorded it as
`docs/portable-code-prior-art-2026-08-14.md`.** Ten scouts: three reading this
repository, seven reading others. Every external repository was cloned and read
at source rather than summarised from documentation, because the question was
what could actually be lifted.

The survey answered a narrower question than it was given. The brief was "what
code can we port"; the answer is **almost none, because every component already
exists.** Nothing in `src/` supplies the `attempt` callable to `route.climb()`
or `escalate()`, `decompose`'s `Proposer` has no default binding, and
`parse_reply()`'s output is never written to a file anywhere in the package. The
only end-to-end loop in the tree is `tools/bench/score.py`. So the portable
assets are the few missing executors, algorithms that raise the floor inside
components we already have, and corpora — not subsystems.

**The four highest-value findings are defects here, not code elsewhere.** Each
was reproduced by running it:

- `ruff check --fix && ruff format` short-circuits. The check exits 1 whenever
  any unfixable lint remains, and F821 is ubiquitous in worker output, so the
  normalisation #246 measured at +13.7pp is skipped on exactly the replies that
  need it. `--exit-zero` on the check, and `ruff format` first as the
  parseability gate.
- `worker/reply.py:100` rejects spaces and colons in a fence info string, so
  ` ```python:sol.py ` is refused **and misdiagnosed as `unterminated-fence`** —
  the code the module documents as the signature of a truncated reply. #17
  attributed all 47 measured refusals to a mis-sized cap; that diagnosis is
  contaminated by an unknown amount.
- `scope.py:109` compiles `**/` to `(?:.*/)?` once per occurrence and never
  collapses the run. Twelve repeats against a non-matching path exceeds 60s.
  Contracts are attacker-authored, so this hangs the gate at load. Six further
  defects beyond it, all passing `tests/test_scope.py` 80/80 today.
- `mypy --strict` passes a file annotated entirely with `Any`, exit 0.
  `--disallow-any-explicit` is the minimum addition, and the checker must run
  together with the acceptance file or `-> object` passes too. That settles
  #211's open question.

**Two structural findings.** The deterministic tier has **0/998** representation
in the problem pool — four of nine catalogue types start on `deterministic` and
every pool problem is `function_implementation` or `bug_fix` — so #81's
floor-raiser-by-elimination argument cannot be measured as the corpus stands.
And a shipped context-window table is *structurally* unable to be right:
measured on srv2, served context is 4,096 against a trained 32,768 for
`qwen2.5-coder:1.5b` and 262,144 for `nemotron-3-nano:4b`, because Ollama picks
the window from available VRAM at startup and llama.cpp divides it across slots.

**Three contradictions are recorded unresolved** rather than smoothed over, in
§6: whether a narrower tool surface helps at the floor (three shipped codebases
say yes; the SWE-bench archive inverts at 32B), whether interface design or
trajectory SFT is what moves small models (published evidence says SFT, which
bears on #221), and decomposition — where the literature supports smaller units
of work while arguing against a small model generating its own structure, which
is what `decompose.py` already assumes.

Documentation only. No source, schema, corpus or measurement changed.

## Left open

The four defects are recorded as findings, not fixed. Each wants its own issue
and its own lane; three of them (the `&&`, the fence class, the ReDoS) are
small, unblocked and independently testable, and the fourth belongs to #211.

The survey also names two measurements nobody has published that this rig could
make: a batched-versus-serial wall-clock for N draws on one consumer GPU, which
is the only real cost term left in #119; and a pass-rate delta between backends
running the same quantized weights, which bears on the empty `bounds: []` in
`tools/bench/reproducibility.json`.

next: file the four defect issues, starting with the `&&` short-circuit — it is
the cheapest and it silently degrades a result we have already banked.
