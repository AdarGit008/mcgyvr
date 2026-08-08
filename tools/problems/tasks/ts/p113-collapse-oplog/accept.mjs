import assert from "node:assert/strict";
import { collapseOplog } from "./solution.ts";

assert.deepEqual(collapseOplog([]), [], "empty log stays empty");
assert.deepEqual(
  collapseOplog([["set", "a", 1]]),
  [["set", "a", 1]],
  "single record kept"
);
assert.deepEqual(
  collapseOplog([["set", "a", 1], ["set", "a", 9]]),
  [["set", "a", 9]],
  "the later set wins"
);
assert.deepEqual(
  collapseOplog([["set", "a", 1], ["drop", "a"]]),
  [["drop", "a"]],
  "a drop after a set wins"
);
assert.deepEqual(
  collapseOplog([["drop", "a"], ["set", "a", 3]]),
  [["set", "a", 3]],
  "a set after a drop wins"
);
assert.deepEqual(
  collapseOplog([["set", "b", 2], ["set", "a", 1]]),
  [["set", "a", 1], ["set", "b", 2]],
  "output is sorted by key"
);
assert.deepEqual(
  collapseOplog([
    ["set", "b", 1],
    ["drop", "c"],
    ["set", "b", 4],
    ["set", "c", 8],
    ["drop", "b"],
  ]),
  [["drop", "b"], ["set", "c", 8]],
  "mixed keys each keep their final record"
);
assert.throws(() => collapseOplog([["swap", "a", 1]]), Error, "unknown kind");
assert.throws(() => collapseOplog([["set", 7, 1]]), Error, "non-string key");
assert.throws(
  () => collapseOplog([["set", "a", "x"]]),
  Error,
  "non-integer value"
);
console.log("ok");
