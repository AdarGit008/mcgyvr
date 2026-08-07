import assert from "node:assert/strict";
import { readVaultHeader } from "./solution.ts";

assert.deepEqual(
  readVaultHeader([86, 76, 84, 1, 0, 0, 0]),
  { version: 1, size: 0, sealed: false, packed: false, stamp: 0 },
  "an old-edition header with no body at all",
);
assert.deepEqual(
  readVaultHeader([86, 76, 84, 1, 0, 3, 1, 9, 9, 9]),
  { version: 1, size: 3, sealed: true, packed: false, stamp: 0 },
  "the low flag reads as sealed",
);
assert.deepEqual(
  readVaultHeader([86, 76, 84, 1, 0, 1, 2, 7]),
  { version: 1, size: 1, sealed: false, packed: true, stamp: 0 },
  "the next flag reads as packed",
);
assert.deepEqual(
  readVaultHeader([86, 76, 84, 1, 0, 0, 3]),
  { version: 1, size: 0, sealed: true, packed: true, stamp: 0 },
  "both flags may stand together",
);
assert.deepEqual(
  readVaultHeader([86, 76, 84, 2, 0, 2, 0, 0, 0, 1, 44, 5, 6]),
  { version: 2, size: 2, sealed: false, packed: false, stamp: 300 },
  "the new edition carries a four-byte stamp",
);
assert.deepEqual(
  readVaultHeader([86, 76, 84, 2, 1, 0, 3, 255, 255, 255, 255].concat(Array(256).fill(0))),
  { version: 2, size: 256, sealed: true, packed: true, stamp: 4294967295 },
  "a size and a stamp that fill their fields",
);

assert.throws(() => readVaultHeader("VLT"), Error, "an argument that is not a list is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 0, 256]), Error, "a value above 255 is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 0, -1]), Error, "a value below nought is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 0, 1.5]), Error, "a fractional value is refused");
assert.throws(() => readVaultHeader([86, 76]), Error, "a run too short for the marker is refused");
assert.throws(() => readVaultHeader([86, 76, 85, 1, 0, 0, 0]), Error, "the wrong marker is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 3, 0, 0, 0]), Error, "an edition the reader does not know is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 0]), Error, "an old header cut short is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 2, 0, 0, 0, 0, 0, 0]), Error, "a new header cut short is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 0, 4]), Error, "a flag the reader does not know is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 0, 128]), Error, "the top flag bit is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 3, 0, 9, 9]), Error, "a body shorter than declared is refused");
assert.throws(() => readVaultHeader([86, 76, 84, 1, 0, 1, 0, 9, 9]), Error, "a body longer than declared is refused");
assert.throws(
  () => readVaultHeader([86, 76, 84, 2, 0, 1, 0, 0, 0, 0, 0]),
  Error,
  "a new-edition body missing altogether is refused",
);
console.log("ok");
