import assert from "node:assert/strict";
import { countBack } from "./solution.ts";

assert.deepEqual(countBack(3), [3, 2, 1], "down to one and no further");
assert.deepEqual(countBack(1), [1], "a start of one");
assert.deepEqual(countBack(0), [], "a start of zero counts nothing");
assert.deepEqual(countBack(-2), [], "a start below zero counts nothing");
assert.deepEqual(countBack(5), [5, 4, 3, 2, 1], "a longer count");
assert.deepEqual(countBack(2), [2, 1], "a short one");
console.log("ok");
