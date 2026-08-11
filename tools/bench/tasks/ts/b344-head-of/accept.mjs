import assert from "node:assert/strict";
import { headOf } from "./solution.ts";

assert.deepEqual(headOf(["a", "b", "c"], 2), ["a", "b"], "the first two");
assert.deepEqual(headOf(["a", "b"], 5), ["a", "b"], "more than the list holds");
assert.deepEqual(headOf(["a", "b"], 0), [], "none asked for");
assert.deepEqual(headOf([], 3), [], "an empty list");
assert.deepEqual(headOf(["a"], 1), ["a"], "the only entry");
assert.deepEqual(headOf(["p", "q", "r"], 1), ["p"], "just the head");
console.log("ok");
