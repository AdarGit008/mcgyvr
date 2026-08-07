import assert from "node:assert/strict";
import { hazardDetour } from "./solution.ts";

const open = [
  [0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0],
];
assert.equal(hazardDetour(open, [0, 0], [4, 4]), 8, "open grid walks straight");
const centre = [
  [0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0],
  [0, 0, 1, 0, 0],
  [0, 0, 0, 0, 0],
  [0, 0, 0, 0, 0],
];
assert.equal(
  hazardDetour(centre, [2, 0], [2, 4]),
  8,
  "detours around the hazard and its four neighbours",
);
assert.equal(
  hazardDetour([[0, 0, 0, 0], [0, 1, 0, 0]], [0, 0], [0, 3]),
  -1,
  "a hazard below the corridor closes it",
);
assert.equal(
  hazardDetour([[0, 1], [0, 0]], [0, 0], [1, 0]),
  -1,
  "a start beside a hazard is unsafe",
);
assert.equal(hazardDetour([[0, 0], [0, 0]], [1, 1], [1, 1]), 0, "start equals goal");
assert.equal(
  hazardDetour([[0, 1], [0, 0]], [0, 0], [0, 0]),
  -1,
  "an unsafe cell is -1 even as both start and goal",
);
assert.equal(hazardDetour([[0, 0, 0]], [0, 0], [0, 2]), 2, "strip with no hazards");
assert.throws(() => hazardDetour([], [0, 0], [0, 0]), Error, "empty grid rejected");
assert.throws(
  () => hazardDetour([[0, 0], [0]], [0, 0], [0, 1]),
  Error,
  "ragged grid rejected",
);
assert.throws(
  () => hazardDetour([[0, 2]], [0, 0], [0, 1]),
  Error,
  "bad cell rejected",
);
assert.throws(
  () => hazardDetour([[0, 0]], [5, 0], [0, 1]),
  Error,
  "out-of-bounds start rejected",
);
assert.throws(
  () => hazardDetour([[0, 0]], [0, 0], [0, -1]),
  Error,
  "out-of-bounds goal rejected",
);
console.log("ok");
