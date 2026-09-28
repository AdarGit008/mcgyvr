// The project's JavaScript/TypeScript **format** bar, stated rather than inherited.
//
// `eslint.config.mjs` declares the lint half of the JS/TS bar and this file the
// format half, as `[tool.ruff.format]` in `pyproject.toml` does for the Python
// arm.
//
// **Every value here is the default of the prettier `package-lock.json` pins,
// verbatim.** Writing the defaults down changes nothing that is measured; it
// stops a default that moves in a later prettier from silently moving the bar
// under every rate measured against it.
//
// Reproduce the defaults with `npx prettier --support-info`. The options left
// out are the ones that cannot reach a `.ts` file: the HTML/Vue pair
// (`htmlWhitespaceSensitivity`, `vueIndentScriptAndStyle`), the pragma trio
// (`requirePragma`, `insertPragma`, `checkIgnorePragma`), and `plugins`, which
// is empty because loading one would make the bar depend on a package
// `package-lock.json` does not pin here.
//
// **Why the numbers do not match the Python arm's.** `printWidth` is 80 and
// `[tool.ruff] line-length` is 88. They are not reconciled here, deliberately:
// the two arms' rule *sets* mirror each other in shape rather than in content,
// and narrowing the difference would re-base every JS/TS format rate on the
// disk for a cosmetic gain. `identity.bar_material` puts the asymmetry in the
// manifest so a reader of a ts/py contrast sees it.
//
// The bench copies this file into each scored workspace
// (`tools/bench/score.py:stage_config`), so a candidate is judged by the
// project's declared style rather than by whatever prettier falls back to when
// it finds no configuration.

export default {
  // --- global ---------------------------------------------------------------
  printWidth: 80,
  tabWidth: 2,
  useTabs: false,
  endOfLine: "lf",
  embeddedLanguageFormatting: "auto",

  // --- common ---------------------------------------------------------------
  bracketSpacing: true,
  bracketSameLine: false,
  objectWrap: "preserve",
  proseWrap: "preserve",
  singleAttributePerLine: false,

  // --- javascript / typescript ----------------------------------------------
  semi: true,
  singleQuote: false,
  jsxSingleQuote: false,
  quoteProps: "as-needed",
  trailingComma: "all",
  arrowParens: "always",
  experimentalTernaries: false,
  experimentalOperatorPosition: "end",
};
