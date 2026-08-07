import assert from "node:assert/strict";
import { spanConflicts } from "./solution.ts";

assert.deepEqual(spanConflicts([]), [], "no annotations");
assert.deepEqual(
  spanConflicts([[0, 4, "loc"], [4, 8, "org"]]),
  [],
  "touching annotations with different labels never conflict",
);
assert.deepEqual(
  spanConflicts([[0, 5, "loc"], [3, 8, "org"]]),
  [[0, 1]],
  "overlap across labels is a conflict",
);
assert.deepEqual(
  spanConflicts([[0, 5, "loc"], [3, 8, "loc"]]),
  [],
  "same-label overlap is layering, not a conflict",
);
assert.deepEqual(
  spanConflicts([[2, 9, "a"], [3, 5, "b"]]),
  [[0, 1]],
  "containment across labels is a conflict",
);
assert.deepEqual(
  spanConflicts([[0, 10, "a"], [1, 3, "b"], [5, 7, "c"], [12, 14, "b"]]),
  [[0, 1], [0, 2]],
  "pairs use original indices in lexicographic order",
);
assert.deepEqual(
  spanConflicts([[6, 8, "x"], [0, 7, "y"], [7, 9, "y"]]),
  [[0, 1], [0, 2]],
  "an unsorted input still reports i below j",
);
assert.throws(() => spanConflicts([[5, 5, "a"]]), Error, "empty span is rejected");
assert.throws(
  () => spanConflicts([[1.5, 3, "a"]]),
  Error,
  "non-integer bound is rejected",
);
assert.throws(() => spanConflicts([[0, 3, ""]]), Error, "empty label is rejected");
console.log("ok");
