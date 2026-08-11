import assert from "node:assert/strict";
import { rankOf, rankAll } from "./solution.ts";

assert.equal(rankOf(5, [5, 3]), 1, "nothing stands above it");
assert.equal(rankOf(3, [5, 3]), 2, "one score stands above it");
assert.deepEqual(rankAll([5, 5, 3]), [1, 1, 3], "the tie shares a rank");
assert.deepEqual(rankAll([3, 5]), [2, 1], "in the order given");
assert.deepEqual(rankAll([]), [], "no scores at all");
assert.deepEqual(rankAll([7]), [1], "one score leads");
assert.deepEqual(rankAll([4, 4, 4]), [1, 1, 1], "everyone ties");
console.log("ok");
