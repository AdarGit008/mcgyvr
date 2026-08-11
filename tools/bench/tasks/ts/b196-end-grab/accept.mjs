import assert from "node:assert/strict";
import { endGrab } from "./solution.ts";

assert.deepEqual(endGrab([]), { first: 0, second: 0, taken: [] }, "an empty row is already cleared");
assert.deepEqual(endGrab([7]), { first: 7, second: 0, taken: [7] }, "the opening player takes the only card");
assert.deepEqual(endGrab([1, 5, 3]), { first: 4, second: 5, taken: [3, 5, 1] }, "each turn grabs the larger end");
assert.deepEqual(endGrab([4, 9, 4]), { first: 8, second: 9, taken: [4, 9, 4] }, "ends carrying the same number go to the left card");
assert.deepEqual(endGrab([2, 2, 2, 2]), { first: 4, second: 4, taken: [2, 2, 2, 2] }, "a row of equal cards clears left to right");
assert.deepEqual(endGrab([3, 1, 4, 1, 5]), { first: 7, second: 7, taken: [5, 3, 1, 4, 1] }, "a longer row alternates down to the last card");
console.log("ok");
