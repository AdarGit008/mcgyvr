// The project's JavaScript/TypeScript lint standard.
//
// The decision of record is ADR-0025 — this file binds the *gate*, not just the
// bench, and the rule set moves in step with `[tool.ruff.lint] select`. Read it
// before widening or narrowing anything here: changing the bar re-bases every
// JavaScript rate measured under it.
//
// This is the JS half of what `[tool.ruff.lint] select` is for Python, and it
// exists because the gate had no such standard: `src/mcgyvr/gate/adapters/
// javascript.py` shells to eslint, eslint 9 requires a flat config, and there
// was none anywhere in the repository. Its own error handling then scored the
// failure as "inconclusive" — which is no findings, which is a pass. The JS
// lint rung has therefore never rejected anything, in production or on a rig.
//
// **Why `recommended` and not `strict` or `stylistic`.** The Python side selects
// a moderate, correctness-leaning set — E, F, W, I, N, UP, B, SIM, RUF — and
// deliberately not the whole catalogue. `recommended` is that shape for this
// language: real defects and dead code, not house style. The two arms of the
// bench are paired, so a bar that is materially harsher on one side would show
// up as a language effect that is really a rule-selection effect.
//
// **What is not linted, and why.** `tools/baseline/` is a vendored, hash-pinned
// tree (REC-06) — linting it invites edits that break the pin. The task corpora
// are instrument material: their contents are fixed by digest in their
// admission manifests, and a formatter run there does not tidy anything, it
// invalidates a pin. These mirror `extend-exclude` in `pyproject.toml`.
//
// The bench copies this file into each scored workspace (`tools/bench/score.py`)
// so a candidate is judged by the project's bar rather than by whatever eslint
// falls back to when it finds no configuration.

import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "tools/baseline/**",
      "records/evidence/**",
      "tools/bundle/tasks/**",
      "tools/bundle/python/tasks/**",
      // Retired by #240 and released for training, but historical run
      // manifests still pin these digests — a formatter pass here does not
      // tidy anything, it breaks the resume of every run that used them.
      // ruff has no equivalent entry because the corpus is TypeScript: this
      // is the exclusion eslint needs and ruff never did.
      "tools/breadth/tasks/**",
      "tools/problems/tasks/**",
      "tools/bench/tasks/**",
      "tools/bench/reserve/**",
      "node_modules/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
