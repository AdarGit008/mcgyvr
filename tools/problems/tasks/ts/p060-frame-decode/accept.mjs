import assert from "node:assert/strict";
import { decodeFrames } from "./solution.ts";

assert.deepEqual(decodeFrames([]), [], "an empty stream holds no frames");
assert.deepEqual(
  decodeFrames([0, 3, 1, 2, 3, 0]),
  [[1, 2, 3]],
  "a single frame with a correct XOR trailer",
);
assert.deepEqual(
  decodeFrames([0, 0, 0, 0, 2, 5, 9, 12]),
  [[], [5, 9]],
  "a zero-length frame followed by a two-byte frame",
);
const bigPayload = Array(258).fill(7);
assert.deepEqual(
  decodeFrames([1, 2, ...bigPayload, 0]),
  [bigPayload],
  "the header is big-endian: 0x0102 is 258, not 513",
);
assert.throws(
  () => decodeFrames([0, 1, 5, 4]),
  Error,
  "a wrong trailer is rejected",
);
assert.throws(() => decodeFrames([0]), Error, "a lone header byte is rejected");
assert.throws(
  () => decodeFrames([0, 5, 1, 2]),
  Error,
  "a stream ending inside a payload is rejected",
);
assert.throws(
  () => decodeFrames([0, 2, 1, 2]),
  Error,
  "a frame missing its trailer is rejected",
);
assert.throws(
  () => decodeFrames([0, 0, 0, 9]),
  Error,
  "trailing garbage after a good frame is rejected",
);
assert.throws(() => decodeFrames([0, 1, 256, 0]), Error, "256 is not a byte");
assert.throws(() => decodeFrames([0, 1, -1, 255]), Error, "-1 is not a byte");
assert.throws(() => decodeFrames([0, 1, 1.5, 0]), Error, "a fraction is not a byte");
console.log("ok");
