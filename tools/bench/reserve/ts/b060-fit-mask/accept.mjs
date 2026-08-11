import assert from "node:assert/strict";
import { fitMask } from "./solution.ts";

assert.equal(fitMask("AA-99", "ab-12"), "AB-12", "letters uppercase, digits keep");
assert.equal(fitMask("(999) AA", "(407) pq"), "(407) PQ", "literals pass through");
assert.equal(fitMask("9A9A", "1x2Y"), "1X2Y", "alternating slots fit in place");
assert.throws(() => fitMask("AA", "abc"), Error, "a text longer than its mask");
assert.throws(() => fitMask("A-9", "a_7"), Error, "a literal slot must match");
assert.throws(() => fitMask("AA", "a1"), Error, "a digit cannot fill a letter slot");
assert.throws(() => fitMask("99", "4x"), Error, "a letter cannot fill a digit slot");
assert.throws(() => fitMask("", ""), Error, "an empty mask is rejected");
assert.throws(() => fitMask("AA", 42), Error, "a non-string text is rejected");
console.log("ok");
