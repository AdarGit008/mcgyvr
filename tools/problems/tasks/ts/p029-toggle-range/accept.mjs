import assert from "node:assert/strict";
import { toggleRange } from "./solution.ts";

assert.equal(toggleRange(0, 0, 3), 15, "positions 0..3 of zero become 1111");
assert.equal(toggleRange(10, 1, 2), 12, "middle bits invert");
assert.equal(toggleRange(5, 0, 0), 4, "single-bit range flips exactly one bit");
assert.equal(toggleRange(0, 29, 29), 536870912, "topmost allowed bit flips");
assert.equal(toggleRange(1023, 0, 9), 0, "full range of set bits clears them");
assert.equal(toggleRange(0, 0, 29), 1073741823, "whole 30-bit span inverts");
assert.equal(
  toggleRange(toggleRange(777, 3, 17), 3, 17),
  777,
  "toggling twice restores the value",
);
assert.throws(() => toggleRange(1, 3, 2), Error, "lo above hi is rejected");
assert.throws(() => toggleRange(1, 0, 30), Error, "position 30 is rejected");
assert.throws(() => toggleRange(1, -1, 3), Error, "negative position is rejected");
assert.throws(() => toggleRange(-1, 0, 3), Error, "negative value is rejected");
assert.throws(() => toggleRange(2 ** 30, 0, 3), Error, "value at 2**30 is rejected");
assert.throws(() => toggleRange(1.5, 0, 3), Error, "fractional value is rejected");
console.log("ok");
