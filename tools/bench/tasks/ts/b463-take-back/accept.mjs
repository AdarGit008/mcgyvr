import assert from "node:assert/strict";
import { takeBack } from "./solution.ts";

assert.equal(takeBack([1, 2, 3], 3), 1, "the last entry alone reaches it");
assert.equal(takeBack([1, 2, 3], 5), 2, "two from the end");
assert.equal(takeBack([1, 2, 3], 99), -1, "the whole list never reaches it");
assert.equal(takeBack([], 1), -1, "an empty list");
assert.equal(takeBack([5], 5), 1, "one entry exactly reaches it");
assert.equal(takeBack([1, 1, 1], 2), 2, "two of three");
console.log("ok");
