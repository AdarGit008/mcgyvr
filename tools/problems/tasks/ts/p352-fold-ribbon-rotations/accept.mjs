import assert from "node:assert/strict";
import { foldRibbonRotations } from "./solution.ts";

assert.deepEqual(
  foldRibbonRotations("banana"),
  { line: "annb|aa", home: 4 },
  "the stated banana example",
);
assert.deepEqual(
  foldRibbonRotations("a"),
  { line: "a|", home: 1 },
  "a single letter",
);
assert.deepEqual(
  foldRibbonRotations("ribbon"),
  { line: "nibrob|", home: 6 },
  "the glued ribbon can seat last",
);
assert.deepEqual(
  foldRibbonRotations("abab"),
  { line: "bb|aa", home: 2 },
  "a repeating ribbon",
);
assert.deepEqual(
  foldRibbonRotations("sea shell"),
  { line: "laeshsle| ", home: 8 },
  "the space ranks under every letter",
);
assert.deepEqual(
  foldRibbonRotations("zab"),
  { line: "bza|", home: 3 },
  "the marker must rank ahead of z",
);
assert.equal(
  foldRibbonRotations("mississippi").line,
  "ipssm|pissii",
  "only the closing symbols are joined",
);
assert.throws(
  () => foldRibbonRotations(17),
  Error,
  "a ribbon that is not a string is thrown out",
);
assert.throws(
  () => foldRibbonRotations(""),
  Error,
  "an empty ribbon is thrown out",
);
assert.throws(
  () => foldRibbonRotations("ba|na"),
  Error,
  "a ribbon already carrying the marker is thrown out",
);
assert.throws(
  () => foldRibbonRotations("Banana"),
  Error,
  "an uppercase symbol is thrown out",
);
assert.throws(
  () => foldRibbonRotations("one-two"),
  Error,
  "punctuation is thrown out",
);
console.log("ok");
