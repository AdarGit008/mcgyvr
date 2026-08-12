import assert from "node:assert/strict";
import { rangeText, spanList } from "./solution.ts";

assert.equal(rangeText(1, 3), "1-3", "a run of several");
assert.equal(rangeText(5, 5), "5", "a run of one");
assert.deepEqual(spanList([1, 2, 3]), ["1-3"], "one unbroken run");
assert.deepEqual(spanList([1, 2, 4]), ["1-2", "4"], "a break makes two runs");
assert.deepEqual(spanList([]), [], "no numbers, no runs");
assert.deepEqual(spanList([7]), ["7"], "a single number");
assert.deepEqual(spanList([1, 3, 5]), ["1", "3", "5"], "nothing is consecutive");
console.log("ok");
