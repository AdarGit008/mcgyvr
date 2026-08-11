import assert from "node:assert/strict";
import { unpackFrame } from "./solution.ts";

assert.deepEqual(unpackFrame([0, 0]), [], "a zero-reading frame is header and trailer");
assert.deepEqual(unpackFrame([1, 150, 1, 152]), [150], "a two-byte varint decodes");
assert.deepEqual(
  unpackFrame([2, 0, 172, 2, 176]),
  [0, 300],
  "two readings come back in order",
);
assert.deepEqual(
  unpackFrame([1, 128, 1, 130]),
  [128],
  "the first two-byte value has a zero low group",
);
assert.deepEqual(unpackFrame([1, 127, 128]), [127], "the largest one-byte value");
assert.deepEqual(
  unpackFrame([1, 255, 255, 255, 255, 127, 124]),
  [34359738367],
  "a five-byte varint carries 35 bits",
);
assert.throws(() => unpackFrame("frame"), Error, "a non-list is rejected");
assert.throws(() => unpackFrame([256]), Error, "a byte past 255 is rejected");
assert.throws(() => unpackFrame([]), Error, "an empty frame has no header");
assert.throws(() => unpackFrame([1, 150]), Error, "a frame ending inside a varint");
assert.throws(() => unpackFrame([1, 5]), Error, "a frame with no room for a trailer");
assert.throws(() => unpackFrame([0, 0, 9]), Error, "bytes after the trailer");
assert.throws(() => unpackFrame([1, 150, 0, 151]), Error, "a wasted final zero byte");
assert.throws(
  () => unpackFrame([1, 255, 255, 255, 255, 255, 1, 0]),
  Error,
  "a six-byte varint is rejected",
);
assert.throws(() => unpackFrame([1, 5, 7]), Error, "a trailer that misses the sum");
console.log("ok");
