// A JavaScript/TypeScript lint config: `recommended` from eslint and
// typescript-eslint, nothing else.
//
// mcgyvr does not read this file: its gate runs eslint with the config of the
// repository it judges. The product no longer installs eslint (`package.json`
// pins prettier only). The file stays because the lab's bench stages it into
// every workspace it scores (mcgyvr-lab `tools/bench/score.py`), and the lab
// must supply eslint, @eslint/js and typescript-eslint to load it.

import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "node_modules/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
