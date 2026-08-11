import assert from "node:assert/strict";
import { billSplit } from "./solution.ts";

assert.deepEqual(billSplit(100, 4), [25, 25, 25, 25], "an even bill");
assert.deepEqual(billSplit(101, 4), [26, 25, 25, 25], "the first takes the penny");
assert.deepEqual(billSplit(10, 3), [4, 3, 3], "two pennies over");
assert.deepEqual(billSplit(5, 1), [5], "one diner pays it all");
assert.deepEqual(billSplit(0, 2), [0, 0], "nothing to pay");
assert.deepEqual(billSplit(7, 2), [4, 3], "an odd bill between two");
console.log("ok");
