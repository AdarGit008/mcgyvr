import assert from "node:assert/strict";
import { lapBest } from "./solution.ts";

assert.equal(lapBest([90, 0, 88]), 88, "an uncompleted lap is ignored");
assert.equal(lapBest([90, 88]), 88, "the quicker of two");
assert.equal(lapBest([0, 0]), 0, "nothing was completed");
assert.equal(lapBest([]), 0, "no laps at all");
assert.equal(lapBest([77]), 77, "a single lap");
assert.equal(lapBest([0, 95, 0, 93]), 93, "zeros scattered through");
console.log("ok");
