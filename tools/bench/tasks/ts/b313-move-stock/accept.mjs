import assert from "node:assert/strict";
import { moveStock } from "./solution.ts";

assert.equal(moveStock(10, [5, -3]), 12, "in then out");
assert.equal(moveStock(10, [-20]), 0, "a removal cannot go below zero");
assert.equal(moveStock(0, []), 0, "nothing happens");
assert.equal(moveStock(5, [-2, -2, -2]), 0, "the floor holds part way");
assert.equal(moveStock(0, [3]), 3, "a delivery into an empty store");
assert.equal(moveStock(2, [-5, 4]), 4, "the floor resets what follows");
console.log("ok");
