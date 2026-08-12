import assert from "node:assert/strict";
import { toggleRun } from "./solution.ts";

assert.equal(toggleRun(["on"]), true, "switched on");
assert.equal(toggleRun(["on", "off"]), false, "on then off");
assert.equal(toggleRun(["flip"]), true, "flipped from off");
assert.equal(toggleRun(["flip", "flip"]), false, "flipped back");
assert.equal(toggleRun([]), false, "no instructions leaves it off");
assert.equal(toggleRun(["on", "x", "flip"]), false, "an unknown step is ignored");
console.log("ok");
