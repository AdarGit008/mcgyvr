import assert from "node:assert/strict";
import { sumRange } from "./solution.ts";

assert.equal(sumRange(1, 3), 6, "one to three");
assert.equal(sumRange(5, 5), 5, "the same number twice");
assert.equal(sumRange(4, 2), 0, "the first stands above the second");
assert.equal(sumRange(0, 0), 0, "nothing to nothing");
assert.equal(sumRange(1, 10), 55, "one to ten");
assert.equal(sumRange(2, 3), 5, "two to three");
console.log("ok");
