import assert from "node:assert/strict";
import { holdQueue } from "./solution.ts";

assert.deepEqual(holdQueue(["a", "b", "c"], 2), ["b", "c"], "the longest wait goes");
assert.deepEqual(holdQueue(["a"], 2), ["a"], "under the limit");
assert.deepEqual(holdQueue([], 3), [], "nobody called");
assert.deepEqual(holdQueue(["a", "b", "c", "d"], 1), ["d"], "only the newest survives");
assert.deepEqual(holdQueue(["a", "b"], 5), ["a", "b"], "a roomy limit");
assert.throws(() => holdQueue([], 0), Error, "a limit of zero is rejected");
console.log("ok");
