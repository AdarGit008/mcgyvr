import assert from "node:assert/strict";
import { sealSerial } from "./solution.ts";

assert.equal(sealSerial("00000000"), "000000000", "all zeros seal with 0");
assert.equal(sealSerial("12345678"), "123456787", "ascending digits seal with 7");
assert.equal(sealSerial("99999999"), "999999992", "all nines seal with 2");
assert.equal(
  sealSerial("70000000"),
  "70000000K",
  "a remainder of ten seals as the letter K",
);
assert.equal(
  sealSerial("00000001"),
  "000000017",
  "the eighth position carries weight 7",
);
assert.equal(sealSerial("10203040"), "102030405", "interleaved zeros");
assert.throws(() => sealSerial("1234567"), Error, "seven digits are rejected");
assert.throws(() => sealSerial("123456789"), Error, "nine digits are rejected");
assert.throws(() => sealSerial("1234567a"), Error, "a letter is rejected");
assert.throws(() => sealSerial("1234 567"), Error, "a space is rejected");
assert.throws(() => sealSerial(12345678), Error, "a number is rejected");
console.log("ok");
