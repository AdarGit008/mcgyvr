// Prettier's defaults for JS/TS, written down: every value below is the
// default of the prettier `package-lock.json` pins (`npx prettier
// --support-info`), stated so a later prettier cannot move it silently.
//
// mcgyvr does not read this file: its gate runs prettier with the config of
// the repository it judges, and the one product test that runs the pinned
// prettier (`tests/test_fix_outcomes_and_argv.py`) formats a file outside this
// checkout. The file stays because the lab's bench stages it into every
// workspace it scores (mcgyvr-lab `tools/bench/score.py`).

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
