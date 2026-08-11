import assert from "node:assert/strict";
import { trimZeros } from "./solution.ts";

assert.equal(trimZeros("007"), "7", "the padding goes");
assert.equal(trimZeros("0"), "0", "a lone zero stays");
assert.equal(trimZeros("000"), "0", "one digit is always left");
assert.equal(trimZeros("-0042"), "-42", "the sign stays in front");
assert.equal(trimZeros("12x"), "12x", "not a number, untouched");
assert.equal(trimZeros(""), "", "empty text is not a number");
assert.equal(trimZeros("1200"), "1200", "inner zeros are not leading");
console.log("ok");
