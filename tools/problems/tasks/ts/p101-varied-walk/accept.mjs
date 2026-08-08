import assert from "node:assert/strict";
import { variedLabelWalk } from "./solution.ts";

assert.equal(
  variedLabelWalk([["s", "a", "x"], ["a", "g", "y"]], "s", "g"),
  2,
  "two differently labeled edges chain",
);
assert.equal(
  variedLabelWalk([["s", "a", "x"], ["a", "g", "x"]], "s", "g"),
  -1,
  "a repeated label in a row is forbidden",
);
assert.equal(
  variedLabelWalk(
    [["s", "a", "r"], ["a", "g", "r"], ["a", "b", "g"], ["b", "a", "b"]],
    "s",
    "g",
  ),
  4,
  "the only lawful walk leaves a and comes back under another label",
);
assert.equal(
  variedLabelWalk([["s", "a", "x"], ["s", "a", "y"], ["a", "g", "x"]], "s", "g"),
  2,
  "parallel edges with different labels are distinct arrivals",
);
assert.equal(
  variedLabelWalk([["s", "a", "x"], ["a", "g", "y"], ["s", "g", "z"]], "s", "g"),
  1,
  "a direct edge wins",
);
assert.equal(variedLabelWalk([["s", "a", "x"]], "s", "s"), 0, "equal endpoints need no walk");
assert.equal(
  variedLabelWalk([["s", "a", "x"], ["g", "b", "y"]], "s", "g"),
  -1,
  "a goal with no way in stays unreached",
);
assert.throws(() => variedLabelWalk([["s", "a"]], "s", "a"), Error, "a two-part edge is rejected");
assert.throws(() => variedLabelWalk([["s", "a", ""]], "s", "a"), Error, "an empty label is rejected");
assert.throws(() => variedLabelWalk([["s", "a", "x"]], "z", "a"), Error, "an unknown start is rejected");
assert.throws(() => variedLabelWalk([["s", "a", "x"]], "s", "z"), Error, "an unknown goal is rejected");
console.log("ok");
