import assert from "node:assert/strict";
import { shareOut } from "./solution.ts";

assert.deepEqual(shareOut(10, 3), [4, 3, 3], "the leftover goes to the earliest part");
assert.deepEqual(shareOut(9, 3), [3, 3, 3], "the amount breaks evenly");
assert.deepEqual(shareOut(2, 5), [1, 1, 0, 0, 0], "fewer to hand out than parts");
assert.deepEqual(shareOut(7, 1), [7], "a single part takes it all");
assert.deepEqual(shareOut(0, 2), [0, 0], "an amount of nothing");
assert.throws(() => shareOut(5, 0), Error, "a count of parts below one is rejected");
console.log("ok");
