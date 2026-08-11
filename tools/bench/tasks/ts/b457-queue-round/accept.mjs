import assert from "node:assert/strict";
import { servedBy, queueRound } from "./solution.ts";

assert.equal(servedBy(["a", "b"], 0), "a", "the first turn");
assert.equal(servedBy(["a", "b"], 2), "a", "the queue comes round");
assert.deepEqual(queueRound(["a", "b"], 3), ["a", "b", "a"], "past the end and round");
assert.deepEqual(queueRound(["a", "b"], 2), ["a", "b"], "exactly one pass");
assert.deepEqual(queueRound(["a"], 0), [], "no turns at all");
assert.throws(() => queueRound([], 1), Error, "an empty queue is rejected");
console.log("ok");
