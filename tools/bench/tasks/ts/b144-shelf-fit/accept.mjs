import assert from "node:assert/strict";
import { shelfFit } from "./solution.ts";

assert.equal(shelfFit([], 50), 0, "no books shelves nothing");
assert.equal(shelfFit([20], 50), 1, "a single book fits");
assert.equal(shelfFit([60], 50), 0, "a first book too wide shelves nothing");
assert.equal(shelfFit([20, 30], 50), 2, "an exact fill is allowed");
assert.equal(shelfFit([20, 31, 5], 50), 1, "shelving stops at the first misfit even when a later book would fit");
assert.equal(shelfFit([10, 10, 10, 10], 35), 3, "shelving stops when the shelf runs out");
assert.equal(shelfFit([5, 5], 0), 0, "a zero-width shelf holds nothing");
assert.throws(() => shelfFit(42, 50), Error, "a non-list is rejected");
assert.throws(() => shelfFit([20, 0], 50), Error, "a zero spine width anywhere is rejected");
assert.throws(() => shelfFit([2.5], 50), Error, "a fractional spine width is rejected");
assert.throws(() => shelfFit([20], -1), Error, "a negative shelf width is rejected");
console.log("ok");
