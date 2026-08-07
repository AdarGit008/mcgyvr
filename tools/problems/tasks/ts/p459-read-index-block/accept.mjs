import assert from "node:assert/strict";
import { readIndexBlock } from "./solution.ts";

assert.deepEqual(readIndexBlock([0]), [], "a block promising nothing yields nothing");
assert.deepEqual(
  readIndexBlock([1, 2, 97, 98, 0, 16, 1, 0]),
  [["ab", 16, 256]],
  "one entry with a two-byte name",
);
assert.deepEqual(
  readIndexBlock([2, 1, 97, 0, 0, 0, 5, 3, 98, 50, 122, 0, 5, 2, 1]),
  [["a", 0, 5], ["b2z", 5, 513]],
  "two entries of unequal name width follow one another",
);
assert.deepEqual(
  readIndexBlock([1, 4, 108, 111, 103, 57, 255, 255, 255, 255]),
  [["log9", 65535, 65535]],
  "an offset and a length that fill their two bytes",
);
assert.deepEqual(
  readIndexBlock([1, 1, 122, 0, 0, 0, 0]),
  [["z", 0, 0]],
  "an entry of no length at the very front",
);
assert.deepEqual(
  readIndexBlock([3, 1, 97, 0, 1, 0, 1, 1, 98, 0, 2, 0, 1, 1, 99, 0, 3, 0, 1]),
  [["a", 1, 1], ["b", 2, 1], ["c", 3, 1]],
  "three single-letter entries in rising order",
);

assert.throws(() => readIndexBlock(7), Error, "an argument that is not a list is refused");
assert.throws(() => readIndexBlock([]), Error, "a block with not even a count is refused");
assert.throws(() => readIndexBlock([1, 2, 97, 98, 0, 16, 1]), Error, "a block ending inside an entry is refused");
assert.throws(() => readIndexBlock([2, 1, 97, 0, 0, 0, 5]), Error, "a promised entry that never arrives is refused");
assert.throws(() => readIndexBlock([1, 0, 0, 0, 0, 0]), Error, "a name of no bytes is refused");
assert.throws(() => readIndexBlock([1, 1, 65, 0, 0, 0, 0]), Error, "a capital letter in a name is refused");
assert.throws(() => readIndexBlock([1, 1, 45, 0, 0, 0, 0]), Error, "a dash in a name is refused");
assert.throws(
  () => readIndexBlock([2, 1, 98, 0, 0, 0, 1, 1, 97, 0, 1, 0, 1]),
  Error,
  "entries out of rising name order are refused",
);
assert.throws(
  () => readIndexBlock([2, 1, 97, 0, 0, 0, 1, 1, 97, 0, 1, 0, 1]),
  Error,
  "one name appearing twice is refused",
);
assert.throws(() => readIndexBlock([0, 9]), Error, "a byte past the last entry is refused");
assert.throws(() => readIndexBlock([1, 1, 97, 0, 0, 0, 0, 4]), Error, "a stray tail byte is refused");
assert.throws(() => readIndexBlock([0.5]), Error, "a fractional byte is refused");
assert.throws(() => readIndexBlock([256]), Error, "a byte above 255 is refused");
assert.throws(() => readIndexBlock([-3]), Error, "a byte below nought is refused");
console.log("ok");
