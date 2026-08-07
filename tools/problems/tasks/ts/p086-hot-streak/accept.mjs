import assert from "node:assert/strict";
import { hotStreak } from "./solution.ts";

assert.deepEqual(hotStreak([1, 5, 6, 2, 7, 8, 9], 4), [4, 3], "later longer streak wins");
assert.deepEqual(hotStreak([5, 6, 1, 7, 8], 4), [0, 2], "a length tie goes to the earlier streak");
assert.deepEqual(hotStreak([9, 9], 1), [0, 2], "the whole list can be one streak");
assert.deepEqual(hotStreak([1, 2], 5), [-1, 0], "no game clears the bar");
assert.deepEqual(hotStreak([4, 4], 4), [-1, 0], "matching the bar exactly does not clear it");
assert.deepEqual(hotStreak([1, 9, 9, 9], 5), [1, 3], "a streak may run to the end");
assert.deepEqual(hotStreak([10], 2), [0, 1], "a single clearing game is a streak of one");
assert.deepEqual(hotStreak([], 0), [-1, 0], "no games at all");
assert.deepEqual(hotStreak([-2, -1, -8], -5), [0, 2], "a negative bar works the same way");
console.log("ok");
