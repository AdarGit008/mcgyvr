import assert from "node:assert/strict";
import { crossUp } from "./solution.ts";

assert.equal(crossUp([1, 5], 3), 1, "one crossing upward");
assert.equal(crossUp([5, 1], 3), 0, "a fall is not a crossing");
assert.equal(crossUp([1, 5, 1, 5], 3), 2, "two crossings");
assert.equal(crossUp([], 3), 0, "no readings at all");
assert.equal(crossUp([3, 3], 3), 0, "sitting on the level is not crossing it");
assert.equal(crossUp([1, 3], 3), 1, "reaching the level counts");
console.log("ok");
