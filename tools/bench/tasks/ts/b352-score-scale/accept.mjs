import assert from "node:assert/strict";
import { scoreScale } from "./solution.ts";

assert.equal(scoreScale(5, 10, 100), 50, "half of one total is half of another");
assert.equal(scoreScale(10, 10, 100), 100, "full marks stay full");
assert.equal(scoreScale(0, 10, 100), 0, "no marks stay none");
assert.equal(scoreScale(11, 10, 100), 100, "a mark over the total is held back");
assert.equal(scoreScale(5, 0, 100), 0, "nothing to scale from");
assert.equal(scoreScale(1, 3, 10), 3, "rounded down");
console.log("ok");
