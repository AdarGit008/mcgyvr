import assert from "node:assert/strict";
import { wireText, wireValue } from "./solution.ts";

assert.equal(wireValue("cargo"), "s5:cargo", "a text leaf");
assert.equal(wireValue(""), "s0:", "empty text still carries its length");
assert.equal(wireValue(-32), "n-32;", "a negative whole number");
assert.equal(wireValue([]), "[]", "the empty list");
assert.equal(wireValue(["ab", 4]), "[s2:abn4;]", "a mixed flat list");
assert.equal(wireValue([1, ["x", []], "yz"]), "[n1;[s1:x[]]s2:yz]", "nesting");
assert.equal(wireText("a:b"), "s3:a:b", "the leaf helper renders alone");
assert.throws(() => wireValue(true), Error, "a boolean is rejected");
assert.throws(() => wireValue(1.5), Error, "a fractional number is rejected");
assert.throws(() => wireValue(null), Error, "null is rejected");
assert.throws(() => wireValue({ a: 1 }), Error, "a plain object is rejected");
assert.throws(() => wireValue("two\nlines"), Error, "a newline in text is rejected");
console.log("ok");
