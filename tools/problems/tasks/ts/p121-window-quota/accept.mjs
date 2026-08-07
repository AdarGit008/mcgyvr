import assert from "node:assert/strict";
import { windowQuota } from "./solution.ts";

assert.deepEqual(windowQuota(2, 10, []), [], "no calls, no labels");
assert.deepEqual(
  windowQuota(2, 10, [[0, "a"], [1, "a"], [2, "a"]]),
  ["ok", "ok", "over"],
  "the third call in a frame is turned away"
);
assert.deepEqual(
  windowQuota(2, 10, [[0, "a"], [1, "a"], [2, "b"], [3, "b"], [4, "a"]]),
  ["ok", "ok", "ok", "ok", "over"],
  "names are metered separately"
);
assert.deepEqual(
  windowQuota(2, 10, [[8, "a"], [9, "a"], [10, "a"]]),
  ["ok", "ok", "ok"],
  "tick 10 opens a fresh frame"
);
assert.deepEqual(
  windowQuota(1, 5, [[0, "a"], [4, "a"], [5, "a"], [9, "a"], [10, "a"]]),
  ["ok", "over", "ok", "over", "ok"],
  "limit one resets at every frame edge"
);
assert.deepEqual(
  windowQuota(1, 3, [[2, "a"], [2, "a"], [3, "b"], [3, "b"]]),
  ["ok", "over", "ok", "over"],
  "equal times share a frame"
);
assert.throws(() => windowQuota(0, 10, []), Error, "zero limit");
assert.throws(() => windowQuota(2, 0, []), Error, "zero width");
assert.throws(() => windowQuota(2, 10, [[0, ""]]), Error, "empty name");
assert.throws(() => windowQuota(2, 10, [[-1, "a"]]), Error, "negative time");
assert.throws(() => windowQuota(2, 10, [[0.5, "a"]]), Error, "fractional time");
assert.throws(
  () => windowQuota(2, 10, [[5, "a"], [4, "a"]]),
  Error,
  "time earlier than its predecessor"
);
console.log("ok");
