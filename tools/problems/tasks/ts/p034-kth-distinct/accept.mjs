import assert from "node:assert/strict";
import { kthDistinct } from "./solution.ts";

assert.equal(kthDistinct([7, 3, 3, 9], 1), 3, "rank one after collapsing");
assert.equal(kthDistinct([7, 3, 3, 9], 2), 7, "rank two skips the duplicate");
assert.equal(kthDistinct([7, 3, 3, 9], 3), 9, "top rank");
assert.equal(kthDistinct([5], 1), 5, "single element");
assert.equal(kthDistinct([4, 4, 4, 4], 1), 4, "all duplicates collapse to one");
assert.equal(kthDistinct([10, -2, 0, -2, 10, 6], 2), 0, "unsorted with negatives");
assert.equal(kthDistinct([100, 20, 300], 3), 300, "largest distinct value");
assert.throws(() => kthDistinct([7, 3, 3, 9], 4), Error, "rank past distinct count is rejected");
assert.throws(() => kthDistinct([1, 2], 0), Error, "zero rank is rejected");
assert.throws(() => kthDistinct([1, 2], 1.5), Error, "fractional rank is rejected");
assert.throws(() => kthDistinct([], 1), Error, "empty input is rejected");
assert.throws(() => kthDistinct([1, "b"], 1), Error, "non-integer element is rejected");
console.log("ok");
