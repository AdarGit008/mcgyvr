import assert from "node:assert/strict";
import { applyCyclePower } from "./solution.ts";

assert.deepEqual(
  applyCyclePower([1, 0, 3, 4, 2], 0),
  [0, 1, 2, 3, 4],
  "zero rounds leaves every plug alone",
);
assert.deepEqual(
  applyCyclePower([1, 0, 3, 4, 2], 1),
  [1, 0, 3, 4, 2],
  "one round is the panel itself",
);
assert.deepEqual(
  applyCyclePower([1, 0, 3, 4, 2], 2),
  [0, 1, 4, 2, 3],
  "two rounds settles the pair and turns the triple",
);
assert.deepEqual(
  applyCyclePower([1, 0, 3, 4, 2], 5),
  [1, 0, 4, 2, 3],
  "five rounds slides each ring by its own remainder",
);
assert.deepEqual(
  applyCyclePower([1, 0, 3, 4, 2], 6),
  [0, 1, 2, 3, 4],
  "six rounds is a whole number of turns for both rings",
);
assert.deepEqual(
  applyCyclePower([1, 2, 3, 0, 5, 4], 6),
  [2, 3, 0, 1, 4, 5],
  "a four-ring and a two-ring reduce differently",
);
assert.deepEqual(
  applyCyclePower([0, 1, 2], 100),
  [0, 1, 2],
  "a panel that moves nothing stays put",
);
assert.deepEqual(applyCyclePower([0], 9), [0], "a one-slot panel");
assert.throws(() => applyCyclePower("panel", 1), Error, "a non-list panel is rejected");
assert.throws(() => applyCyclePower([], 1), Error, "an empty panel is rejected");
assert.throws(() => applyCyclePower([0.5], 1), Error, "a fractional entry is rejected");
assert.throws(() => applyCyclePower([null, 0], 1), Error, "a non-number entry is rejected");
assert.throws(() => applyCyclePower([2, 0], 1), Error, "a slot the panel lacks is rejected");
assert.throws(() => applyCyclePower([1, 1], 1), Error, "a slot named twice is rejected");
assert.throws(() => applyCyclePower([0, 1], -1), Error, "a negative round count is rejected");
assert.throws(() => applyCyclePower([0, 1], 1.5), Error, "a fractional round count is rejected");
assert.throws(() => applyCyclePower([0, 1], "3"), Error, "a non-number round count is rejected");
console.log("ok");
