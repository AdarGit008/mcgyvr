import assert from "node:assert/strict";
import { carryAdd } from "./solution.ts";

assert.deepEqual(carryAdd([1, 2], [3, 4]), [4, 6], "no place carries");
assert.deepEqual(carryAdd([5], [5]), [1, 0], "a carry opens a new place");
assert.deepEqual(carryAdd([9, 9], [1]), [1, 0, 0], "a carry runs the whole way");
assert.deepEqual(carryAdd([1, 0, 0], [2]), [1, 0, 2], "runs of unlike length");
assert.deepEqual(carryAdd([0], [0]), [0], "two figures of nothing");
assert.deepEqual(carryAdd([], []), [], "two runs holding nothing");
console.log("ok");
