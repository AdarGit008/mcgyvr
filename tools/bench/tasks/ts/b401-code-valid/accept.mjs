import assert from "node:assert/strict";
import { codeValid } from "./solution.ts";

assert.equal(codeValid("AB12", 4), true, "the right length and charset");
assert.equal(codeValid("ab12", 4), false, "small letters are not allowed");
assert.equal(codeValid("AB1", 4), false, "too short");
assert.equal(codeValid("AB-2", 4), false, "a dash is not allowed");
assert.equal(codeValid("", 1), false, "an empty code is never the right length");
assert.throws(() => codeValid("A", 0), Error, "a length of zero is rejected");
console.log("ok");
