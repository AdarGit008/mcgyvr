import assert from "node:assert/strict";
import { ridgeRow } from "./solution.ts";

assert.equal(ridgeRow([3, 1, 2], 1), "###", "the ground row is solid across the transect");
assert.equal(ridgeRow([3, 1, 2], 2), "#.#", "a middle row shows only the taller stations");
assert.equal(ridgeRow([3, 1, 2], 3), "#..", "the top row keeps only the summit");
assert.equal(ridgeRow([3, 1, 2], 4), "...", "a level above the ridge is all dots");
assert.equal(ridgeRow([0, 2], 1), ".#", "a zero-elevation station never marks");
assert.equal(ridgeRow([], 1), "", "no stations gives the empty row");
assert.equal(ridgeRow([5], 5), "#", "an elevation exactly at the level marks");
assert.throws(() => ridgeRow(42, 1), Error, "a non-list is rejected");
assert.throws(() => ridgeRow([-1], 1), Error, "a negative elevation is rejected");
assert.throws(() => ridgeRow([1.5], 1), Error, "a fractional elevation is rejected");
assert.throws(() => ridgeRow([2], 0), Error, "a zero level is rejected");
console.log("ok");
