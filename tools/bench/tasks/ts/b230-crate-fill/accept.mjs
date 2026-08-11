import assert from "node:assert/strict";
import { crateFill, crateTotal } from "./solution.ts";

assert.deepEqual(crateFill(7, 3), [3, 2, 2], "the leftover leads");
assert.deepEqual(crateFill(6, 3), [2, 2, 2], "an even split");
assert.deepEqual(crateFill(2, 5), [1, 1, 0, 0, 0], "more crates than items");
assert.deepEqual(crateFill(5, 0), [], "zero crates hold nothing");
assert.equal(crateTotal([3, 2, 2]), 7, "the sizes add back up");
assert.equal(crateTotal([]), 0, "nothing sums to nothing");
console.log("ok");
