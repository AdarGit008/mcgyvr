import assert from "node:assert/strict";
import { hopWindowSums } from "./solution.ts";

assert.deepEqual(hopWindowSums([1, 2, 3, 4, 5], 3, 2), [6, 12], "overlapping hop");
assert.deepEqual(hopWindowSums([1, 2, 3, 4], 2, 2), [3, 7], "tumbling windows");
assert.deepEqual(hopWindowSums([1, 2, 3], 1, 1), [1, 2, 3], "unit windows");
assert.deepEqual(hopWindowSums([5, 5, 5], 3, 5), [15], "single full window");
assert.deepEqual(hopWindowSums([2, 4, 6, 8], 2, 3), [6], "partial tail discarded");
assert.deepEqual(hopWindowSums([], 2, 1), [], "empty input");
assert.deepEqual(hopWindowSums([1, 2], 3, 1), [], "window larger than list");
assert.throws(() => hopWindowSums([1, 2], 0, 1), Error, "zero size is rejected");
assert.throws(() => hopWindowSums([1, 2], 2, 0), Error, "zero hop is rejected");
assert.throws(() => hopWindowSums([1, 2], 1.5, 1), Error, "fractional size is rejected");
assert.throws(() => hopWindowSums("12", 1, 1), Error, "non-list input is rejected");
assert.throws(() => hopWindowSums([1, "x"], 1, 1), Error, "non-integer element is rejected");
console.log("ok");
