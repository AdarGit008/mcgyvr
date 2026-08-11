import assert from "node:assert/strict";
import { splitLength } from "./solution.ts";

assert.equal(splitLength(0), "0mm", "zero length reads 0mm");
assert.equal(splitLength(7), "7mm", "millimetres alone");
assert.equal(splitLength(30), "3cm", "an exact count of centimetres");
assert.equal(splitLength(1000), "1m", "an exact metre");
assert.equal(splitLength(999), "99cm 9mm", "just under a metre");
assert.equal(splitLength(1005), "1m 5mm", "a zero-count unit is skipped");
assert.equal(splitLength(1234), "1m 23cm 4mm", "all three units appear");
assert.equal(splitLength(123456), "123m 45cm 6mm", "large lengths carve the same way");
assert.throws(() => splitLength(2.5), Error, "a fractional length is rejected");
assert.throws(() => splitLength("5"), Error, "a string length is rejected");
assert.throws(() => splitLength(true), Error, "a boolean length is rejected");
assert.throws(() => splitLength(-1), Error, "a negative length is rejected");
console.log("ok");
