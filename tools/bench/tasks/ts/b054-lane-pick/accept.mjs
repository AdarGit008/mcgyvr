import assert from "node:assert/strict";
import { pickLane } from "./solution.ts";

assert.equal(pickLane([4, 2, 7], []), 1, "the shortest queue wins");
assert.equal(pickLane([3, 1, 1], []), 1, "a tie goes to the lowest index");
assert.equal(pickLane([0, 5, 2], [0]), 2, "a closed first lane is never picked");
assert.equal(pickLane([4, 1, 3], [1]), 2, "a closed shortest lane is skipped");
assert.equal(pickLane([2], []), 0, "a single open lane is picked");
assert.throws(() => pickLane([], []), Error, "empty queues are rejected");
assert.throws(() => pickLane([1, 2], [0, 1]), Error, "all lanes closed is rejected");
assert.throws(() => pickLane([1, -2], []), Error, "a negative length is rejected");
assert.throws(() => pickLane([1, 2], [5]), Error, "an out-of-range closed index is rejected");
console.log("ok");
