import assert from "node:assert/strict";
import { driestWindow } from "./solution.ts";

assert.equal(driestWindow([4], 1), 0, "a single day names index zero");
assert.equal(driestWindow([3, 1, 4, 1, 5], 1), 1, "width one finds the smallest reading, earliest on a tie");
assert.equal(driestWindow([4, 2, 0, 3], 2), 1, "the driest two-day stretch starts at index one");
assert.equal(driestWindow([2, 2, 2, 2], 3), 0, "an all-tie record keeps the earliest start");
assert.equal(driestWindow([9, 1, 1, 9], 4), 0, "width equal to the record names the whole record");
assert.equal(driestWindow([0, 6, 0, 6, 0], 3), 0, "a later equal stretch does not displace the earliest");
assert.throws(() => driestWindow("wet", 2), Error, "a rain argument that is not a list is rejected");
assert.throws(() => driestWindow([1, 2.5, 3], 2), Error, "a fractional reading is rejected");
assert.throws(() => driestWindow([1, -2, 3], 2), Error, "a negative reading is rejected");
assert.throws(() => driestWindow([1, 2, 3], 0), Error, "a zero width is rejected");
assert.throws(() => driestWindow([1, 2, 3], 4), Error, "a width larger than the record is rejected");
console.log("ok");
