import assert from "node:assert/strict";
import { firstOver } from "./solution.ts";

assert.equal(firstOver([1, 7, 9], 3), 7, "the reading, not its place");
assert.equal(firstOver([9], 3), 9, "the first reading is already over");
assert.equal(firstOver([1, 2], 3), 0, "nothing stands above");
assert.equal(firstOver([], 3), 0, "no readings at all");
assert.equal(firstOver([3, 4], 3), 4, "a reading on the level is not over it");
assert.equal(firstOver([1, 1, 5], 3), 5, "the third reading");
console.log("ok");
