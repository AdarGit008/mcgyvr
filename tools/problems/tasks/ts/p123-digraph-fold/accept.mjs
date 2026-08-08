import assert from "node:assert/strict";
import { foldDigraphs } from "./solution.ts";

assert.equal(
  foldDigraphs("ab", [["a", "b"], ["b", "c"]]),
  "bc",
  "one pair's output never feeds another pair",
);
assert.equal(
  foldDigraphs("chip", [["c", "k"], ["ch", "x"]]),
  "xip",
  "the widest pattern wins regardless of table order",
);
assert.equal(
  foldDigraphs("aaa", [["a", "1"], ["aa", "2"]]),
  "21",
  "widest match at every position",
);
assert.equal(foldDigraphs("sos", [["s", "ss"]]), "ssoss", "emitted output is final");
assert.equal(
  foldDigraphs("x", [["x", "1"], ["x", "2"]]),
  "1",
  "width tie goes to the earlier pair",
);
assert.equal(foldDigraphs("mud", [["zz", "q"]]), "mud", "unclaimed positions copy");
assert.equal(foldDigraphs("", [["a", "b"]]), "", "empty text");
assert.equal(foldDigraphs("th", [["th", "h"]]), "h", "output may echo a pattern");
assert.throws(
  () => foldDigraphs("x", [["", "y"]]),
  Error,
  "empty pattern is rejected",
);
console.log("ok");
