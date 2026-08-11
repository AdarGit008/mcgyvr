import assert from "node:assert/strict";
import { stackPop } from "./solution.ts";

assert.deepEqual(stackPop(["a", "b", "take"]), ["a"], "the last on comes off first");
assert.deepEqual(stackPop(["a", "b"]), ["a", "b"], "orders that only put on");
assert.deepEqual(stackPop(["a", "take", "b"]), ["b"], "taking then putting on again");
assert.deepEqual(stackPop(["a", "take"]), [], "the pile is emptied");
assert.deepEqual(stackPop([]), [], "no orders at all");
assert.throws(() => stackPop(["take"]), Error, "taking from an empty pile is rejected");
assert.throws(() => stackPop(["a", "take", "take"]), Error, "taking one time too many is rejected");
console.log("ok");
