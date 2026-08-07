import assert from "node:assert/strict";
import { turnCostRoute } from "./solution.ts";

assert.equal(turnCostRoute([[0]], 1, 1), 0, "single cell costs nothing");
assert.equal(turnCostRoute([[0, 0, 0]], 2, 5), 4, "straight strip has no turns");
assert.equal(
  turnCostRoute([[0, 0, 0], [0, 0, 0], [0, 0, 0]], 1, 10),
  14,
  "open 3x3 pays for exactly one turn",
);
assert.equal(
  turnCostRoute(
    [[0, 0, 0, 0, 0], [0, 1, 0, 1, 0], [0, 1, 0, 1, 0], [0, 0, 0, 0, 0]],
    1,
    10,
  ),
  17,
  "prefers the single-turn route among equally short ones",
);
const maze = [
  [0, 1, 0, 0, 0, 0, 0],
  [0, 0, 0, 1, 0, 1, 0],
  [0, 1, 0, 0, 1, 0, 0],
  [0, 0, 1, 0, 0, 0, 0],
  [1, 0, 0, 0, 0, 1, 0],
];
assert.equal(turnCostRoute(maze, 1, 7), 40, "a longer route with fewer turns wins");
assert.equal(turnCostRoute(maze, 1, 0), 10, "free turns reduce to fewest moves");
assert.equal(turnCostRoute([[0, 1], [1, 0]], 1, 1), -1, "walled off is -1");
assert.equal(turnCostRoute([[1, 0], [0, 0]], 1, 1), -1, "walled start is -1");
assert.throws(() => turnCostRoute([[0, 0], [0]], 1, 1), Error, "ragged grid rejected");
assert.throws(() => turnCostRoute([[0, 2], [0, 0]], 1, 1), Error, "bad cell rejected");
assert.throws(() => turnCostRoute([], 1, 1), Error, "empty grid rejected");
assert.throws(() => turnCostRoute([[0, 0]], 0, 1), Error, "zero step cost rejected");
assert.throws(() => turnCostRoute([[0, 0]], 1, -1), Error, "negative turn cost rejected");
assert.throws(() => turnCostRoute([[0, 0]], 1.5, 1), Error, "fractional step cost rejected");
console.log("ok");
