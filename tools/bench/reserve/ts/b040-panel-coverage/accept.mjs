import assert from "node:assert/strict";
import { panelCoverage } from "./solution.ts";

assert.deepEqual(
  panelCoverage([]),
  { union: 0, overlap: 0, deepest: 0, perimeter: 0, bounds: null },
  "no panels yields all zeros and null bounds",
);
assert.deepEqual(
  panelCoverage([[0, 0, 3, 2]]),
  { union: 6, overlap: 0, deepest: 1, perimeter: 10, bounds: [0, 0, 3, 2] },
  "a single panel is its own report",
);
assert.deepEqual(
  panelCoverage([[0, 0, 1, 1], [2, 2, 3, 3]]),
  { union: 2, overlap: 0, deepest: 1, perimeter: 8, bounds: [0, 0, 3, 3] },
  "disjoint panels add areas and perimeters",
);
assert.deepEqual(
  panelCoverage([[0, 0, 2, 2], [2, 0, 4, 2]]),
  { union: 8, overlap: 0, deepest: 1, perimeter: 12, bounds: [0, 0, 4, 2] },
  "touching panels share a seam, not ground or boundary",
);
assert.deepEqual(
  panelCoverage([[0, 0, 2, 2], [1, 1, 3, 3]]),
  { union: 7, overlap: 1, deepest: 2, perimeter: 12, bounds: [0, 0, 3, 3] },
  "two panels sharing one unit of ground",
);
assert.deepEqual(
  panelCoverage([[0, 0, 4, 4], [1, 1, 2, 2]]),
  { union: 16, overlap: 1, deepest: 2, perimeter: 16, bounds: [0, 0, 4, 4] },
  "a contained panel adds overlap but no union or boundary",
);
assert.deepEqual(
  panelCoverage([[0, 0, 2, 1], [0, 0, 2, 1]]),
  { union: 2, overlap: 2, deepest: 2, perimeter: 6, bounds: [0, 0, 2, 1] },
  "identical panels overlap over their whole area",
);
assert.deepEqual(
  panelCoverage([[0, 0, 2, 2], [1, 0, 3, 2], [0, 1, 2, 3]]),
  { union: 8, overlap: 3, deepest: 3, perimeter: 12, bounds: [0, 0, 3, 3] },
  "three panels stacking over a common core",
);
assert.deepEqual(
  panelCoverage([[0, 0, 2, 1], [1, 0, 3, 1], [2, 0, 4, 1]]),
  { union: 4, overlap: 2, deepest: 2, perimeter: 10, bounds: [0, 0, 4, 1] },
  "a chain overlaps pairwise but never stacks three deep",
);
assert.deepEqual(
  panelCoverage([[-2, -2, 1, 1], [-1, -1, 2, 2]]),
  { union: 14, overlap: 4, deepest: 2, perimeter: 16, bounds: [-2, -2, 2, 2] },
  "negative coordinates measure the same way",
);
assert.deepEqual(
  panelCoverage([[0, -3, 1, 3], [-3, 0, 3, 1]]),
  { union: 11, overlap: 1, deepest: 2, perimeter: 24, bounds: [-3, -3, 3, 3] },
  "a cross keeps every arm's boundary",
);
assert.deepEqual(
  panelCoverage([[0, 0, 2, 2], [0, 0, 2, 2], [0, 0, 2, 2]]),
  { union: 4, overlap: 4, deepest: 3, perimeter: 8, bounds: [0, 0, 2, 2] },
  "a triple stack reads three deep",
);
assert.throws(() => panelCoverage("x"), Error, "non-list panels is rejected");
assert.throws(
  () => panelCoverage([[0, 0, 1]]),
  Error,
  "a three-item panel is rejected",
);
assert.throws(
  () => panelCoverage([[0, 0, 1.5, 1]]),
  Error,
  "a fractional coordinate is rejected",
);
assert.throws(
  () => panelCoverage([[0, "0", 1, 1]]),
  Error,
  "a string coordinate is rejected",
);
assert.throws(
  () => panelCoverage([[2, 0, 1, 1]]),
  Error,
  "reversed x edges are rejected",
);
assert.throws(
  () => panelCoverage([[1, 0, 1, 2]]),
  Error,
  "a zero-width panel is rejected",
);
assert.throws(
  () => panelCoverage([[0, 3, 2, 1]]),
  Error,
  "reversed y edges are rejected",
);
console.log("ok");
