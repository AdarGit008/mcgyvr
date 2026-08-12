import assert from "node:assert/strict";
import { sealCode } from "./solution.ts";

assert.equal(sealCode("7"), "7L", "a single digit is sealed");
assert.equal(sealCode("0"), "0E", "a zero code is sealed");
assert.equal(sealCode("A"), "AO", "a single letter is sealed");
assert.equal(sealCode("AB"), "ABN", "the worked example holds");
assert.equal(sealCode("BA"), "BAO", "the same characters in the other order seal differently");
assert.equal(sealCode("Z9"), "Z9Z", "the highest worths wrap under the modulus");
assert.equal(sealCode("DOCK31"), "DOCK31R", "a longer mixed code is sealed");
assert.throws(() => sealCode(42), Error, "a non-string code is rejected");
assert.throws(() => sealCode(""), Error, "an empty code is rejected");
assert.throws(() => sealCode("dock"), Error, "a lowercase letter is rejected");
assert.throws(() => sealCode("A-1"), Error, "a character outside digits and capitals is rejected");
console.log("ok");
