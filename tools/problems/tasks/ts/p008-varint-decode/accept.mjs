import assert from "node:assert/strict";
import { decodeVarints } from "./solution.ts";

assert.deepEqual(decodeVarints([]), [], "empty input decodes to nothing");
assert.deepEqual(decodeVarints([0]), [0], "single zero byte");
assert.deepEqual(decodeVarints([1, 127]), [1, 127], "two one-byte varints");
assert.deepEqual(decodeVarints([150, 1]), [150], "continuation bit spans bytes");
assert.deepEqual(
  decodeVarints([5, 150, 1, 0]),
  [5, 150, 0],
  "mixed lengths back to back",
);
assert.deepEqual(decodeVarints([172, 2]), [300], "seven-bit groups accumulate");
assert.deepEqual(decodeVarints([255, 255, 3]), [65535], "sixteen-bit maximum");
assert.deepEqual(decodeVarints([128, 128, 128, 1]), [2097152], "four-byte varint");
assert.throws(() => decodeVarints([128]), Error, "lone continuation byte");
assert.throws(() => decodeVarints([150]), Error, "truncated after high bit");
assert.throws(() => decodeVarints([1, 128]), Error, "truncated at list end");
assert.throws(() => decodeVarints([128, 0]), Error, "overlong encoding of zero");
assert.throws(() => decodeVarints([256]), Error, "byte above 255 is rejected");
assert.throws(() => decodeVarints([-1]), Error, "negative byte is rejected");
assert.throws(() => decodeVarints([1.5]), Error, "fractional byte is rejected");
assert.throws(() => decodeVarints("bytes"), Error, "non-list is rejected");
console.log("ok");
