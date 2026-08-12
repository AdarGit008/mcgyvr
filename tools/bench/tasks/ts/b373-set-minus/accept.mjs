import assert from "node:assert/strict";
import { setMinus } from "./solution.ts";

assert.deepEqual(setMinus(["a", "b", "c"], ["b"]), ["a", "c"], "one entry removed");
assert.deepEqual(setMinus(["a", "a"], ["b"]), ["a", "a"], "repeats are kept");
assert.deepEqual(setMinus(["a"], ["a"]), [], "everything is removed");
assert.deepEqual(setMinus([], ["a"]), [], "nothing to remove from");
assert.deepEqual(setMinus(["a", "b"], []), ["a", "b"], "nothing to remove");
assert.deepEqual(setMinus(["b", "a", "b"], ["a"]), ["b", "b"], "order is kept");
console.log("ok");
