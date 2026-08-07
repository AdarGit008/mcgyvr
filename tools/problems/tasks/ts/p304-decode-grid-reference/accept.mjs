import assert from "node:assert/strict";
import { decodeGridReference } from "./solution.ts";

assert.deepEqual(decodeGridReference("AA"), [0, 0], "AA is the origin square");
assert.deepEqual(
  decodeGridReference("BA"),
  [100000, 0],
  "the first capital walks east",
);
assert.deepEqual(
  decodeGridReference("AB"),
  [0, 100000],
  "the second capital walks north",
);
assert.deepEqual(
  decodeGridReference("VV"),
  [1900000, 1900000],
  "V by V is the far north-east square",
);
assert.deepEqual(
  decodeGridReference("AA00"),
  [0, 0],
  "a pair of noughts stays in the corner",
);
assert.deepEqual(
  decodeGridReference("AA51"),
  [50000, 10000],
  "one figure per axis cuts the square into tenths",
);
assert.deepEqual(
  decodeGridReference("KM1234"),
  [912000, 1134000],
  "two figures per axis inside square KM",
);
assert.deepEqual(
  decodeGridReference("AA1234567890"),
  [12345, 67890],
  "five figures per axis resolves to the metre",
);
assert.deepEqual(
  decodeGridReference("VV9999999999"),
  [1999999, 1999999],
  "the finest box in the far corner",
);
assert.throws(
  () => decodeGridReference(42),
  Error,
  "a number is not a reference",
);
assert.throws(() => decodeGridReference("A"), Error, "one capital is too few");
assert.throws(
  () => decodeGridReference("IA"),
  Error,
  "I was struck out of the alphabet",
);
assert.throws(
  () => decodeGridReference("AO"),
  Error,
  "O was struck out of the alphabet",
);
assert.throws(
  () => decodeGridReference("aa"),
  Error,
  "lower case is not a capital",
);
assert.throws(
  () => decodeGridReference("AA1"),
  Error,
  "an odd count of figures cannot split",
);
assert.throws(
  () => decodeGridReference("AA123456789012"),
  Error,
  "twelve figures overshoot the projection",
);
assert.throws(
  () => decodeGridReference("AA 12"),
  Error,
  "a space is not a decimal figure",
);
console.log("ok");
