import assert from "node:assert/strict";
import { replayBuffer } from "./solution.ts";

assert.deepEqual(replayBuffer(["add:a", "add:b", "take"], 2), { held: ["b"], taken: ["a"] }, "a take removes the oldest entry");
assert.deepEqual(replayBuffer([], 3), { held: [], taken: [] }, "no operations leave an empty result");
assert.deepEqual(replayBuffer(["add:a", "take", "add:b", "add:c"], 2), { held: ["b", "c"], taken: ["a"] }, "interleaved adds and takes");
assert.deepEqual(replayBuffer(["add:x", "add:y", "take", "add:z"], 2), { held: ["y", "z"], taken: ["x"] }, "a take frees a slot");
assert.throws(() => replayBuffer(["add:a", "add:b", "add:c"], 2), Error, "an add on a full buffer is an error");
assert.throws(() => replayBuffer(["take"], 1), Error, "a take on an empty buffer is an error");
assert.throws(() => replayBuffer(["drop:a"], 1), Error, "an unknown operation is an error");
assert.throws(() => replayBuffer([], 0), Error, "zero capacity is rejected");
assert.throws(() => replayBuffer([], 2.5), Error, "fractional capacity is rejected");
console.log("ok");
