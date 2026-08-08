import assert from "node:assert/strict";
import { rangeAlgebra } from "./solution.ts";

assert.deepEqual(
  rangeAlgebra([[0, 3]], [[3, 6]], "union"),
  [[0, 6]],
  "touching pieces fuse across operands",
);
assert.deepEqual(
  rangeAlgebra([[8, 12], [1, 4]], [[3, 9]], "union"),
  [[1, 12]],
  "union bridges through the middle",
);
assert.deepEqual(
  rangeAlgebra([[5, 9], [0, 2]], [], "union"),
  [[0, 2], [5, 9]],
  "union with an empty operand canonicalises the other",
);
assert.deepEqual(
  rangeAlgebra([[0, 10]], [[2, 4], [6, 8]], "intersect"),
  [[2, 4], [6, 8]],
  "intersection keeps only the shared integers",
);
assert.deepEqual(
  rangeAlgebra([[0, 3]], [[3, 6]], "intersect"),
  [],
  "touching sets share nothing",
);
assert.deepEqual(
  rangeAlgebra([[0, 5], [4, 9]], [[3, 7]], "intersect"),
  [[3, 7]],
  "overlap inside one operand is flattened first",
);
assert.deepEqual(
  rangeAlgebra([[0, 10]], [[3, 5]], "subtract"),
  [[0, 3], [5, 10]],
  "subtracting the middle splits a piece",
);
assert.deepEqual(
  rangeAlgebra([[2, 6]], [[0, 10]], "subtract"),
  [],
  "subtracting a superset leaves nothing",
);
assert.deepEqual(
  rangeAlgebra([[1, 4], [6, 9]], [[3, 7]], "subtract"),
  [[1, 3], [7, 9]],
  "subtraction clips both sides",
);
assert.deepEqual(
  rangeAlgebra([[0, 4]], [[4, 8]], "subtract"),
  [[0, 4]],
  "a touching subtrahend removes nothing",
);
assert.throws(() => rangeAlgebra([], [], "xor"), Error, "unknown op is rejected");
assert.throws(
  () => rangeAlgebra([[3, 3]], [], "union"),
  Error,
  "an empty interval is rejected",
);
assert.throws(
  () => rangeAlgebra([[5, 2]], [], "union"),
  Error,
  "a backwards interval is rejected",
);
assert.throws(
  () => rangeAlgebra([[0, 1.5]], [], "union"),
  Error,
  "a fractional endpoint is rejected",
);
assert.throws(
  () => rangeAlgebra([[0, 1, 2]], [], "union"),
  Error,
  "a triple is rejected",
);
console.log("ok");
