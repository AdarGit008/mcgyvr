// The project's JavaScript/TypeScript lint standard.
//
// This file binds the *gate*, not just the bench, and the rule set moves in
// step with `[tool.ruff.lint] select`: changing the bar re-bases every
// JavaScript rate measured under it.
//
// This is the JS half of what `[tool.ruff.lint] select` is for Python:
// `src/mcgyvr/gate/adapters/javascript.py` shells to eslint, and eslint 9
// requires a flat config.
//
// **Why `recommended` and not `strict` or `stylistic`.** The Python side selects
// a moderate, correctness-leaning set — E, F, W, I, N, UP, B, SIM, RUF — and
// deliberately not the whole catalogue. `recommended` is that shape for this
// language: real defects and dead code, not house style. The two arms of the
// bench are paired, so a bar that is materially harsher on one side would show
// up as a language effect that is really a rule-selection effect.
//

import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "records/evidence/**",
      "tools/bundle/tasks/**",
      "tools/bundle/python/tasks/**",
      // Historical run manifests pin these digests — a formatter pass here does not
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
