import assert from "node:assert/strict";
import { romanToInt } from "./solution.ts";

assert.equal(romanToInt("I"), 1, "smallest value");
assert.equal(romanToInt("III"), 3, "simple repetition");
assert.equal(romanToInt("IV"), 4, "subtractive IV");
assert.equal(romanToInt("IX"), 9, "subtractive IX");
assert.equal(romanToInt("XIV"), 14, "mixed additive and subtractive");
assert.equal(romanToInt("XL"), 40, "subtractive XL");
assert.equal(romanToInt("XCIX"), 99, "canonical 99");
assert.equal(romanToInt("CDXLIV"), 444, "all subtractive digits");
assert.equal(romanToInt("MCMXCIV"), 1994, "classic 1994");
assert.equal(romanToInt("MMMCMXCIX"), 3999, "largest value");
assert.equal(romanToInt("DLV"), 555, "half symbols");

assert.throws(() => romanToInt("IIII"), Error, "IIII is not canonical");
assert.throws(() => romanToInt("IC"), Error, "IC is not a valid subtractive pair");
assert.throws(() => romanToInt("VX"), Error, "VX is invalid");
assert.throws(() => romanToInt("XXXX"), Error, "XXXX is not canonical");
assert.throws(() => romanToInt("MMMM"), Error, "4000 is out of range");
assert.throws(() => romanToInt("VV"), Error, "VV is not canonical");
assert.throws(() => romanToInt(""), Error, "empty string throws");
assert.throws(() => romanToInt("xiv"), Error, "lowercase is invalid");
assert.throws(() => romanToInt("XIVA"), Error, "foreign character throws");
assert.throws(() => romanToInt(14), Error, "non-string throws");
