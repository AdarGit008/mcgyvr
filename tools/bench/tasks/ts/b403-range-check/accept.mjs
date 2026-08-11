import assert from "node:assert/strict";
import { rangeCheck } from "./solution.ts";

assert.equal(rangeCheck([1, 2], 1, 3), true, "everything is inside");
assert.equal(rangeCheck([0, 2], 1, 3), false, "one reading falls short");
assert.equal(rangeCheck([4], 1, 3), false, "one reading overshoots");
assert.equal(rangeCheck([], 1, 3), true, "no readings fall outside anything");
assert.equal(rangeCheck([1, 3], 1, 3), true, "the bounds are included");
assert.throws(() => rangeCheck([], 5, 1), Error, "an upside-down range is rejected");
console.log("ok");
