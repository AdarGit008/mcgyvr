import assert from "node:assert/strict";
import { checkDigit } from "./solution.ts";

assert.equal(checkDigit("123"), 4, "six needs four more");
assert.equal(checkDigit("0"), 0, "zero is already a multiple");
assert.equal(checkDigit("55"), 0, "ten is already a multiple");
assert.equal(checkDigit("999"), 3, "twenty-seven needs three");
assert.equal(checkDigit(""), 0, "no digits need nothing");
assert.throws(() => checkDigit("12a"), Error, "a letter is rejected");
console.log("ok");
