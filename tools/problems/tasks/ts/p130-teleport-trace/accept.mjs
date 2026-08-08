import assert from "node:assert/strict";
import { traceTeleports } from "./solution.ts";

assert.deepEqual(traceTeleports([1, 2, 3, 1], 0), [1, 3, 1], "one ride to a 3-circuit");
assert.deepEqual(traceTeleports([1, 2, 3, 1], 2), [0, 3, 2], "starting on the circuit");
assert.deepEqual(traceTeleports([0], 0), [0, 1, 0], "a pad wired to itself");
assert.deepEqual(traceTeleports([1, 1], 0), [1, 1, 1], "tail into a self-wired pad");
assert.deepEqual(traceTeleports([3, 0, 1, 2], 0), [0, 4, 0], "the whole hall circles");
assert.deepEqual(traceTeleports([1, 2, 0, 2], 3), [1, 3, 2], "side pad feeds the ring");
assert.throws(() => traceTeleports([], 0), Error, "empty hall is rejected");
assert.throws(() => traceTeleports([2], 0), Error, "destination outside the hall");
assert.throws(() => traceTeleports([0, 1], 5), Error, "start outside the hall");
console.log("ok");
