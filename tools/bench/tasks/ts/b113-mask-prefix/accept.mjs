import assert from "node:assert/strict";
import { maskFromPrefix, prefixFromMask } from "./solution.ts";

assert.equal(maskFromPrefix(0), "0.0.0.0", "no ones renders all zeros");
assert.equal(maskFromPrefix(20), "255.255.240.0", "a mid-octet prefix renders");
assert.throws(() => maskFromPrefix(33), Error, "a prefix past 32 is rejected");
assert.equal(prefixFromMask("0.0.0.0"), 0, "all zeros reads back as 0");
assert.equal(prefixFromMask("255.255.240.0"), 20, "a mid-octet mask reads back");
assert.equal(prefixFromMask("255.255.255.255"), 32, "all ones reads back as 32");
assert.equal(prefixFromMask(maskFromPrefix(11)), 11, "the two directions agree");
assert.throws(() => prefixFromMask(7), Error, "a non-string mask is rejected");
assert.throws(
  () => prefixFromMask("255.255.240"),
  Error,
  "three fields are rejected",
);
assert.throws(
  () => prefixFromMask("255.x.0.0"),
  Error,
  "a non-digit field is rejected",
);
assert.throws(
  () => prefixFromMask("255.040.0.0"),
  Error,
  "a leading zero is rejected",
);
assert.throws(
  () => prefixFromMask("256.0.0.0"),
  Error,
  "an octet past 255 is rejected",
);
assert.throws(
  () => prefixFromMask("255.0.255.0"),
  Error,
  "a bit run broken across octets is rejected",
);
assert.throws(
  () => prefixFromMask("250.0.0.0"),
  Error,
  "a bit run broken inside an octet is rejected",
);
console.log("ok");
