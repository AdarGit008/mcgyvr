import assert from "node:assert/strict";
import { stepsOn, holeFind } from "./solution.ts";

assert.deepEqual(stepsOn(1, 3), [1, 2, 3], "three numbers from one");
assert.deepEqual(stepsOn(5, 0), [], "no numbers at all");
assert.equal(holeFind([1, 3], 1, 3), 2, "the missing number");
assert.equal(holeFind([1, 2, 3], 1, 3), 0, "nothing is missing");
assert.equal(holeFind([], 1, 2), 1, "everything is missing");
assert.equal(holeFind([2, 3], 1, 3), 1, "the first is missing");
console.log("ok");
