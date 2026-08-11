import assert from "node:assert/strict";
import { batchEnds } from "./solution.ts";

assert.deepEqual(batchEnds(6, 2), [1, 3, 5], "three full batches");
assert.deepEqual(batchEnds(7, 2), [1, 3, 5], "the part-batch is left out");
assert.deepEqual(batchEnds(1, 2), [], "not even one full batch");
assert.deepEqual(batchEnds(0, 2), [], "nothing to batch");
assert.deepEqual(batchEnds(3, 3), [2], "exactly one batch");
assert.deepEqual(batchEnds(4, 1), [0, 1, 2, 3], "a batch of one");
console.log("ok");
