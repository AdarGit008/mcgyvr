import assert from "node:assert/strict";
import { hexGroups } from "./solution.ts";

assert.equal(hexGroups([10], 4), "0a", "one byte renders two digits");
assert.equal(hexGroups([0, 255], 2), "00ff", "zero pads and the top byte fits");
assert.equal(hexGroups([10, 255, 3], 2), "0aff 03", "a short last group stands alone");
assert.equal(hexGroups([10, 255, 3], 1), "0a ff 03", "width one spaces every byte");
assert.equal(hexGroups([1, 2, 3], 8), "010203", "width past the end makes one group");
assert.equal(hexGroups([], 4), "", "no bytes yield the empty string");
assert.throws(() => hexGroups("ff", 2), Error, "non-list is rejected");
assert.throws(() => hexGroups([256], 2), Error, "a byte past 255 is rejected");
assert.throws(() => hexGroups([2.5], 2), Error, "a fractional byte is rejected");
assert.throws(() => hexGroups([10], 0), Error, "zero width is rejected");
console.log("ok");
