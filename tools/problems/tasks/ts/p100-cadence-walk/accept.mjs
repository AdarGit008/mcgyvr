import assert from "node:assert/strict";
import { labelCadenceWalk } from "./solution.ts";

assert.equal(
  labelCadenceWalk([["s", "a", "red"], ["a", "g", "blue"]], ["red", "blue"], "s", "g"),
  2,
  "a two-edge walk matches the cadence once",
);
assert.equal(
  labelCadenceWalk([["s", "a", "r"], ["a", "b", "b"], ["b", "g", "r"]], ["r", "b"], "s", "g"),
  3,
  "the cadence wraps around past its last label",
);
assert.equal(
  labelCadenceWalk(
    [["s", "a", "r"], ["a", "s", "b"], ["s", "a", "g"], ["a", "g", "r"]],
    ["r", "b", "g"],
    "s",
    "g",
  ),
  4,
  "the walk may pass through a node twice at different cadence positions",
);
assert.equal(
  labelCadenceWalk([["s", "a", "r"], ["a", "g", "b"]], ["r", "b", "g"], "s", "g"),
  2,
  "the walk may end before the cadence completes a lap",
);
assert.equal(
  labelCadenceWalk([["s", "a", "b"]], ["r"], "s", "a"),
  -1,
  "no edge carries the opening label",
);
assert.equal(labelCadenceWalk([["s", "a", "r"]], ["r"], "s", "s"), 0, "equal endpoints walk nowhere");
assert.throws(() => labelCadenceWalk([["s", "a", "r"]], [], "s", "a"), Error, "an empty cadence is rejected");
assert.throws(() => labelCadenceWalk([["s", "a", "r"]], ["r", ""], "s", "a"), Error, "an empty cadence entry is rejected");
assert.throws(() => labelCadenceWalk([["s", "a"]], ["r"], "s", "a"), Error, "a two-part edge is rejected");
assert.throws(() => labelCadenceWalk([["s", "a", ""]], ["r"], "s", "a"), Error, "an empty edge label is rejected");
assert.throws(() => labelCadenceWalk([["s", "a", "r"]], ["r"], "z", "a"), Error, "an unknown start is rejected");
assert.throws(() => labelCadenceWalk([["s", "a", "r"]], ["r"], "s", "z"), Error, "an unknown goal is rejected");
console.log("ok");
