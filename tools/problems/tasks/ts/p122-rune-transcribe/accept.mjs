import assert from "node:assert/strict";
import { transcribeRunes } from "./solution.ts";

assert.equal(
  transcribeRunes("khora", [["kh", "q"], ["o", "au"]]),
  "qaura",
  "basic pairs",
);
assert.equal(
  transcribeRunes("schule", [["s", "z"], ["sch", "x"]]),
  "zchule",
  "table order beats pattern length",
);
assert.equal(
  transcribeRunes("aaa", [["a", "ab"]]),
  "ababab",
  "outputs are not rescanned",
);
assert.equal(
  transcribeRunes("aaa", [["aa", "X"]]),
  "Xa",
  "a match consumes its whole span",
);
assert.equal(
  transcribeRunes("brim", [["zz", "q"]]),
  "brim",
  "no rule fires anywhere",
);
assert.equal(transcribeRunes("keel", []), "keel", "empty table is identity");
assert.equal(
  transcribeRunes("ab", [["abc", "Z"]]),
  "ab",
  "pattern must fit before the end",
);
assert.equal(transcribeRunes("", [["a", "b"]]), "", "empty source");
assert.throws(
  () => transcribeRunes("x", [["", "y"]]),
  Error,
  "empty pattern is rejected",
);
assert.throws(
  () => transcribeRunes("", [["", "y"]]),
  Error,
  "empty pattern rejected even on empty source",
);
console.log("ok");
