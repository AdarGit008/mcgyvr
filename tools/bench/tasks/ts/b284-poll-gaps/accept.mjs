import assert from "node:assert/strict";
import { pollGaps } from "./solution.ts";

assert.deepEqual(pollGaps([1, 2, 4]), [3], "one minute missed");
assert.deepEqual(pollGaps([1, 2, 3]), [], "an unbroken run");
assert.deepEqual(pollGaps([5, 9]), [6, 7, 8], "a long silence");
assert.deepEqual(pollGaps([7]), [], "one run reports nothing");
assert.deepEqual(pollGaps([]), [], "no runs at all");
assert.deepEqual(pollGaps([2, 5, 6, 9]), [3, 4, 7, 8], "two silences in order");
console.log("ok");
