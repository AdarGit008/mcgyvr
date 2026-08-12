import assert from "node:assert/strict";
import { keepIndex, dropEvery } from "./solution.ts";

assert.equal(keepIndex(1, 2), true, "the first place survives");
assert.equal(keepIndex(2, 2), false, "the second is dropped");
assert.deepEqual(dropEvery(["a", "b", "c", "d"], 2), ["a", "c"], "every second goes");
assert.deepEqual(dropEvery(["a", "b", "c"], 3), ["a", "b"], "every third goes");
assert.deepEqual(dropEvery([], 2), [], "nothing to drop from");
assert.deepEqual(dropEvery(["a"], 5), ["a"], "the count never comes round");
console.log("ok");
