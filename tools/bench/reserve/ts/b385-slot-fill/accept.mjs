import assert from "node:assert/strict";
import { slotFill } from "./solution.ts";

assert.deepEqual(slotFill(["a"], 3), ["a", "", ""], "the spare slots stay empty");
assert.deepEqual(slotFill(["a", "b"], 2), ["a", "b"], "the board is exactly filled");
assert.deepEqual(slotFill(["a", "b", "c"], 2), ["a", "b"], "the spare label is left off");
assert.deepEqual(slotFill([], 2), ["", ""], "an empty board of two slots");
assert.deepEqual(slotFill(["a"], 1), ["a"], "one slot, one label");
assert.throws(() => slotFill([""], 2), Error, "an empty label is rejected");
console.log("ok");
