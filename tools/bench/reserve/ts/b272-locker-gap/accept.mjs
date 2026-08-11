import assert from "node:assert/strict";
import { lockerGap } from "./solution.ts";

assert.equal(lockerGap([1, 2, 4]), 3, "the hole in the middle");
assert.equal(lockerGap([3, 1, 2]), 4, "order does not matter");
assert.equal(lockerGap([2, 2, 3]), 1, "the first is free");
assert.equal(lockerGap([]), 1, "nothing in use");
assert.equal(lockerGap([1, 1, 1]), 2, "repeats count once");
assert.equal(lockerGap([5]), 1, "a lone high locker");
assert.equal(lockerGap([1, 2, 3]), 4, "past the highest");
console.log("ok");
