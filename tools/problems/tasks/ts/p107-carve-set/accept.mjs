import assert from "node:assert/strict";
import { carveSet } from "./solution.ts";

assert.deepEqual(carveSet([]), [], "no instructions");
assert.deepEqual(carveSet([["add", 2, 6]]), [[2, 6]], "a single add");
assert.deepEqual(
  carveSet([["add", 0, 3], ["add", 3, 5]]),
  [[0, 5]],
  "touching adds fuse",
);
assert.deepEqual(
  carveSet([["add", 0, 4], ["add", 8, 12], ["add", 2, 9]]),
  [[0, 12]],
  "an add can weld separate pieces",
);
assert.deepEqual(
  carveSet([["add", 0, 10], ["cut", 3, 6]]),
  [[0, 3], [6, 10]],
  "a cut through the middle leaves two pieces",
);
assert.deepEqual(
  carveSet([["add", 0, 10], ["cut", 3, 6], ["add", 3, 6]]),
  [[0, 10]],
  "re-adding the cut welds the stretch back",
);
assert.deepEqual(
  carveSet([["add", 2, 5], ["cut", 0, 9]]),
  [],
  "cutting everything empties the set",
);
assert.deepEqual(
  carveSet([["add", 2, 5], ["cut", 5, 9], ["cut", 0, 2]]),
  [[2, 5]],
  "cuts outside the held range change nothing",
);
assert.deepEqual(
  carveSet([["cut", 1, 3], ["add", 4, 6]]),
  [[4, 6]],
  "cutting from the empty set is allowed",
);
assert.throws(() => carveSet([["del", 0, 2]]), Error, "unknown verb is rejected");
assert.throws(
  () => carveSet([["add", 0, 0]]),
  Error,
  "an empty range is rejected",
);
assert.throws(
  () => carveSet([["add", 4, 1]]),
  Error,
  "a backwards range is rejected",
);
assert.throws(
  () => carveSet([["cut", 0, 2.5]]),
  Error,
  "a fractional bound is rejected",
);
console.log("ok");
