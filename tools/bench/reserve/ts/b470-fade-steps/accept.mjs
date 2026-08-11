import assert from "node:assert/strict";
import { fadeSteps } from "./solution.ts";

assert.deepEqual(fadeSteps(8), [8, 4, 2, 1], "a level that halves evenly");
assert.deepEqual(fadeSteps(5), [5, 2, 1], "a part below a whole is dropped");
assert.deepEqual(fadeSteps(7), [7, 3, 1], "an odd level all the way down");
assert.deepEqual(fadeSteps(20), [20, 10, 5, 2, 1], "a longer run");
assert.deepEqual(fadeSteps(1), [1], "a level of one");
assert.deepEqual(fadeSteps(0), [], "nothing to begin with");
console.log("ok");
