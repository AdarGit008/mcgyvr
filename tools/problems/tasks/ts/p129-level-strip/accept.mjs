import assert from "node:assert/strict";
import { levelStrip } from "./solution.ts";

assert.equal(levelStrip([0, 1, 2, 3], 0, 8, ".:*#"), "..::", "lower bands floor down");
assert.equal(levelStrip([4, 5, 6, 7], 0, 8, ".:*#"), "**##", "upper bands floor down");
assert.equal(levelStrip([-5], 0, 8, ".:*#"), ".", "below the span clamps dimmest");
assert.equal(levelStrip([8, 99], 0, 8, ".:*#"), "##", "at or beyond high clamps brightest");
assert.equal(levelStrip([10, 12, 13], 10, 14, "ab"), "abb", "a nonzero low shifts the bands");
assert.equal(levelStrip([], 0, 8, ".:*#"), "", "no readings, empty strip");
assert.equal(levelStrip([3, -9, 42], 5, 6, "o"), "ooo", "one-character ramp absorbs everything");
assert.throws(() => levelStrip([1], 0, 8, ""), Error, "empty ramp is rejected");
assert.throws(() => levelStrip([1], 5, 5, ".:*#"), Error, "flat span is rejected");
assert.throws(() => levelStrip([1], 9, 2, ".:*#"), Error, "inverted span is rejected");
console.log("ok");
