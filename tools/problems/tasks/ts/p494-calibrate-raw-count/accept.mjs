import assert from "node:assert/strict";
import { calibrateRawCount } from "./solution.ts";

assert.equal(calibrateRawCount([[0, 0], [100, 500]], 50), "250", "the midpoint of one segment");
assert.equal(calibrateRawCount([[0, 0], [100, 500]], 25), "125", "a quarter of the way along");
assert.equal(calibrateRawCount([[0, 0], [100, 500]], 0), "0", "the opening breakpoint itself");
assert.equal(calibrateRawCount([[0, 0], [100, 500]], 100), "500", "the closing breakpoint itself");
assert.equal(calibrateRawCount([[0, 0], [3, 1]], 1), "1/3", "a third stays a fraction");
assert.equal(calibrateRawCount([[0, 0], [3, 1]], 2), "2/3", "two thirds stays a fraction");
assert.equal(calibrateRawCount([[0, 0], [3, 1]], -5), "0", "a count under the table clamps low");
assert.equal(calibrateRawCount([[0, 0], [3, 1]], 10), "1", "a count over the table clamps high");
assert.equal(calibrateRawCount([[10, -4], [14, 6]], 11), "-3/2", "a negative fraction carries its sign");
assert.equal(calibrateRawCount([[10, -4], [14, 6]], 12), "1", "a fraction that reduces to a whole");
assert.equal(calibrateRawCount([[10, -4], [14, 6]], 13), "7/2", "the fraction is put in lowest terms");
assert.equal(calibrateRawCount([[0, 10], [5, 10], [9, 2]], 3), "10", "a flat segment holds its reading");
assert.equal(calibrateRawCount([[0, 10], [5, 10], [9, 2]], 6), "8", "the second segment is picked");
assert.equal(calibrateRawCount([[0, 10], [5, 10], [9, 2]], 7), "6", "a falling segment reads down");
assert.equal(calibrateRawCount([[0, -3], [6, 3]], 3), "0", "a crossing of nought reads as plain 0");

assert.throws(() => calibrateRawCount("rows", 1), Error, "the table must be a list");
assert.throws(() => calibrateRawCount([[0, 0]], 1), Error, "one row is not enough");
assert.throws(() => calibrateRawCount([[0, 0, 0], [5, 5]], 1), Error, "a three-entry row is refused");
assert.throws(() => calibrateRawCount([[0, 0], [5, 1.5]], 1), Error, "a fractional entry is refused");
assert.throws(() => calibrateRawCount([[0, 0], [0, 5]], 0), Error, "repeated counts are refused");
assert.throws(() => calibrateRawCount([[9, 0], [2, 5]], 4), Error, "falling counts are refused");
assert.throws(() => calibrateRawCount([[0, 0], [5, 1]], 2.5), Error, "a fractional raw count is refused");
assert.throws(() => calibrateRawCount([[0, 0], [5, 1]], 9000000), Error, "a raw count beyond a million is refused");
assert.throws(() => calibrateRawCount([[0, 0], [5, 4000000]], 2), Error, "a reading beyond a million is refused");
console.log("ok");
