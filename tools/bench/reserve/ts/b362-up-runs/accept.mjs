import assert from "node:assert/strict";
import { upRuns } from "./solution.ts";

assert.equal(upRuns([1, 2, 3]), 3, "the whole list rises");
assert.equal(upRuns([3, 2, 1]), 1, "nothing rises");
assert.equal(upRuns([1, 5, 2, 3, 4]), 3, "the later run is longer");
assert.equal(upRuns([]), 0, "no readings at all");
assert.equal(upRuns([7]), 1, "one reading is a run of one");
assert.equal(upRuns([1, 1, 2]), 2, "a flat step breaks the run");
console.log("ok");
