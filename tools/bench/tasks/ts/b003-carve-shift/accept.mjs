import assert from "node:assert/strict";
import { carveShift } from "./solution.ts";

assert.deepEqual(carveShift(0, 10, 4, 2, 1), [[0, 4], [6, 10]], "two stretches");
assert.deepEqual(carveShift(5, 8, 10, 3, 1), [[5, 8]], "shift shorter than span");
assert.deepEqual(carveShift(0, 7, 4, 2, 2), [[0, 4]], "short tail is dropped");
assert.deepEqual(
  carveShift(0, 9, 4, 2, 3),
  [[0, 4], [6, 9]],
  "tail of exactly least units is kept",
);
assert.deepEqual(
  carveShift(0, 12, 4, 2, 1),
  [[0, 4], [6, 10]],
  "a rest may swallow the end of the shift",
);
assert.deepEqual(
  carveShift(-6, 3, 5, 1, 2),
  [[-6, -1], [0, 3]],
  "negative bounds",
);
assert.throws(() => carveShift(0, 10, 2.5, 1, 1), Error, "fractional span");
assert.throws(() => carveShift(0, 10, 4, 0, 1), Error, "rest below one");
assert.throws(() => carveShift(3, 3, 1, 1, 1), Error, "empty shift is rejected");
assert.throws(() => carveShift(5, 2, 1, 1, 1), Error, "reversed shift is rejected");
assert.throws(() => carveShift(0, 10, 0, 1, 1), Error, "span below one");
assert.throws(() => carveShift(0, 10, 3, 1, 4), Error, "least above span");
console.log("ok");
