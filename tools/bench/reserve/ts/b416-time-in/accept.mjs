import assert from "node:assert/strict";
import { timeIn } from "./solution.ts";

assert.equal(timeIn(600, 540, 660), true, "inside an ordinary window");
assert.equal(timeIn(500, 540, 660), false, "before it opens");
assert.equal(timeIn(660, 540, 660), false, "the closing minute is outside");
assert.equal(timeIn(30, 1380, 60), true, "after midnight in a window that wraps");
assert.equal(timeIn(1400, 1380, 60), true, "before midnight in the same window");
assert.equal(timeIn(600, 1380, 60), false, "the middle of the day is outside it");
console.log("ok");
