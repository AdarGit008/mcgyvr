import assert from "node:assert/strict";
import { stepBack } from "./solution.ts";

assert.equal(stepBack("FFB"), 2, "the peak is before the step back");
assert.equal(stepBack("BBB"), 0, "never forward, never past zero");
assert.equal(stepBack("FBFBFF"), 2, "the peak comes at the end");
assert.equal(stepBack(""), 0, "no moves at all");
assert.equal(stepBack("FxF"), 2, "an unknown letter is ignored");
assert.equal(stepBack("BFF"), 1, "the walk climbs back out of a hole");
console.log("ok");
