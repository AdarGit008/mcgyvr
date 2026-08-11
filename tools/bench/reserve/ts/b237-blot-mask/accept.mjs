import assert from "node:assert/strict";
import { blotMask } from "./solution.ts";

assert.equal(blotMask("ABCD1234"), "****1234", "the tail stays readable");
assert.equal(blotMask("ABCDE"), "*BCDE", "one character masked");
assert.equal(blotMask("ABCD"), "ABCD", "exactly four is untouched");
assert.equal(blotMask("AB"), "AB", "shorter than four is untouched");
assert.equal(blotMask(""), "", "an empty code is untouched");
assert.equal(blotMask("1234567890"), "******7890", "a long code");
console.log("ok");
