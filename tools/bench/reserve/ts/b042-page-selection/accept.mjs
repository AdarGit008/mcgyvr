import assert from "node:assert/strict";
import { expandSelection, readSpan } from "./solution.ts";

assert.deepEqual(readSpan("4-6"), [4, 6], "a dashed piece keeps both ends");
assert.deepEqual(expandSelection("3"), [3], "one page expands to itself");
assert.deepEqual(expandSelection("1-3,7,10-12"), [1, 2, 3, 7, 10, 11, 12], "spans and lone pages mix");
assert.deepEqual(expandSelection("4,5-6"), [4, 5, 6], "touching pieces are allowed");
assert.throws(() => expandSelection(""), Error, "an empty selection is rejected");
assert.throws(() => expandSelection("5-2"), Error, "a backwards span is rejected");
assert.throws(() => expandSelection("1-4,3-6"), Error, "an overlapping piece is rejected");
assert.throws(() => expandSelection("2,,5"), Error, "an empty piece is rejected");
assert.throws(() => expandSelection(7), Error, "a non-string selection is rejected");
console.log("ok");
