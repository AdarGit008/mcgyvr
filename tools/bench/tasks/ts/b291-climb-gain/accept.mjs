import assert from "node:assert/strict";
import { legGain, climbGain } from "./solution.ts";

assert.equal(legGain(10, 15), 5, "a rise is a gain");
assert.equal(legGain(15, 10), 0, "a fall gains nothing");
assert.equal(legGain(4, 4), 0, "level ground gains nothing");
assert.equal(climbGain([1, 4, 9]), 8, "two rises add up");
assert.equal(climbGain([9, 2, 6]), 4, "only the rise counts");
assert.equal(climbGain([5, 5, 5]), 0, "a flat walk");
assert.equal(climbGain([7]), 0, "one height is not a leg");
assert.equal(climbGain([]), 0, "no heights, no gain");
console.log("ok");
