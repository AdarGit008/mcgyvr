import assert from "node:assert/strict";
import { radixValue } from "./solution.ts";

assert.equal(radixValue("2#1011"), 11, "a binary literal is decoded");
assert.equal(radixValue("16#ff"), 255, "letter digits carry their worths");
assert.equal(radixValue("10#0"), 0, "a lone zero is zero");
assert.equal(radixValue("2#0011"), 3, "leading zeros are legal");
assert.equal(radixValue("13#c0"), 156, "an uncommon base folds the same way");
assert.throws(() => radixValue(42), Error, "a non-string literal is rejected");
assert.throws(() => radixValue("1011"), Error, "a literal without a hash mark is rejected");
assert.throws(() => radixValue("17#0"), Error, "a base above 16 is rejected");
assert.throws(() => radixValue("2#"), Error, "an empty digit part is rejected");
assert.throws(() => radixValue("2#102"), Error, "a digit at or above the base is rejected");
assert.throws(() => radixValue("16#FF"), Error, "an uppercase digit is rejected");
console.log("ok");
