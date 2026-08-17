// The project's JavaScript/TypeScript **format** bar, stated rather than inherited.
//
// The decision of record is ADR-0035, and #262 is why this file exists. Until
// it did, `eslint.config.mjs` declared the lint half of the JS/TS bar and
// nothing at all declared the format half: prettier ran on its built-in
// defaults, in the gate and in every bench workspace, and no manifest said so.
// The Python arm's formatter reads `[tool.ruff.format]` out of a `pyproject.toml`
// the bench renders from this repository's own settings — so one arm applied a
// declared style and the other applied whatever its release shipped with.
//
// **Every value here is prettier 3.9.6's own default, verbatim.** That is the
// point and not a shortcut. #262 is out of scope for changing either bar
// ("changing either rule set to make the counts closer"), so writing the
// defaults down changes what is measured by exactly nothing today, and changes
// what happens tomorrow: a default that moves in prettier 4 moves the bar under
// every rate measured against it, silently, and this file stops that. Verified
// by formatting all 257 `bench-ts` reference solutions with and without it —
// 257 of 257 byte-identical.
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
// ADR-0025 decided that the two arms' rule *sets* mirror each other in shape
// rather than in content, and narrowing an 8-column difference after 32,601
// scored candidates would re-base every JS/TS format rate on the disk for a
// cosmetic gain. It is a real asymmetry, it is now written down, and
// `identity.bar_material` puts it in the manifest so a reader of a ts/py
// contrast sees it.
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
