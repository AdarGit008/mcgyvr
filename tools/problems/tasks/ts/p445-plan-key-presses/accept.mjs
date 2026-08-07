import assert from "node:assert/strict";
import { planKeyPresses } from "./solution.ts";

const phone = [" ", "", "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"];
const tiny = ["_", "", "AB", "CD", "EF", "", "", "", "", ""];

assert.equal(
  planKeyPresses("HELLO", phone),
  "4433555.555666",
  "a repeated key is parted by a full stop",
);
assert.equal(planKeyPresses("MOON", phone), "6.666.666.66", "four characters on one key");
assert.equal(planKeyPresses("H H", phone), "44044", "a different key needs no separator");
assert.equal(planKeyPresses("Z", phone), "9999", "the last character of a key");
assert.equal(planKeyPresses("S", phone), "7777", "a four-character key");
assert.equal(planKeyPresses("BAD", tiny), "22.233", "a layout of the caller's own");
assert.equal(planKeyPresses("_", tiny), "0", "key 0 carries one character");
assert.equal(planKeyPresses("FEED", tiny), "44.4.433", "three stretches on one key then another");

assert.throws(() => planKeyPresses("", phone), Error, "empty text is refused");
assert.throws(() => planKeyPresses(9, phone), Error, "text that is not a string is refused");
assert.throws(() => planKeyPresses("HI", phone.slice(0, 9)), Error, "nine keys are refused");
assert.throws(() => planKeyPresses("HI", "not a layout"), Error, "a layout that is not a list is refused");
assert.throws(
  () => planKeyPresses("HI", [" ", "", "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", 9]),
  Error,
  "a key that is not a string is refused",
);
assert.throws(() => planKeyPresses("HI!", phone), Error, "a character on no key is refused");
assert.throws(() => planKeyPresses("G", tiny), Error, "a smaller layout refuses what it never listed");
assert.throws(
  () => planKeyPresses("A", [" ", "", "ABC", "DEA", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"]),
  Error,
  "a character listed on two keys is refused",
);
assert.throws(
  () => planKeyPresses("A", [" ", "", "ABA", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"]),
  Error,
  "a character listed twice on one key is refused",
);
console.log("ok");
