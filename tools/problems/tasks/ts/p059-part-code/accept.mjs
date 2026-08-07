import assert from "node:assert/strict";
import { normalizePartCode } from "./solution.ts";

assert.equal(
  normalizePartCode("000000000"),
  "0000-0000-0",
  "the zero code verifies and gains its hyphens",
);
assert.equal(
  normalizePartCode("aaaa aaaa k"),
  "AAAA-AAAA-K",
  "lowercase with spaces cleans, uppercases and verifies",
);
assert.equal(
  normalizePartCode("1B2C3D4E8"),
  "1B2C-3D4E-8",
  "mixed digits and letters weigh out to 8",
);
assert.equal(
  normalizePartCode("1b2c-3d4e-8"),
  "1B2C-3D4E-8",
  "hyphens anywhere are discarded before verification",
);
assert.equal(
  normalizePartCode("0000-0000-0"),
  "0000-0000-0",
  "canonical input comes back canonical",
);
assert.equal(
  normalizePartCode("zzzzzzzzy"),
  "ZZZZ-ZZZZ-Y",
  "the top letter value folds to Y",
);
assert.throws(
  () => normalizePartCode("1B2C3D4E9"),
  Error,
  "a wrong check character is rejected",
);
assert.throws(
  () => normalizePartCode("1B2C3D4E"),
  Error,
  "eight cleaned characters are rejected",
);
assert.throws(
  () => normalizePartCode("1B2C3D4E88"),
  Error,
  "ten cleaned characters are rejected",
);
assert.throws(
  () => normalizePartCode("1B2C_3D4E-8"),
  Error,
  "an underscore is rejected",
);
assert.throws(() => normalizePartCode(42), Error, "a number is rejected");
console.log("ok");
