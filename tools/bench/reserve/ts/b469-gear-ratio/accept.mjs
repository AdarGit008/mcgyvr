import assert from "node:assert/strict";
import { gearRatio } from "./solution.ts";

assert.equal(gearRatio(4, 6), "2:3", "a shared amount of two");
assert.equal(gearRatio(9, 3), "3:1", "the second divides the first");
assert.equal(gearRatio(5, 7), "5:7", "nothing is shared");
assert.equal(gearRatio(12, 12), "1:1", "the two counts match");
assert.equal(gearRatio(0, 4), "0:1", "a first count of nothing");
assert.equal(gearRatio(100, 75), "4:3", "a larger pair");
assert.throws(() => gearRatio(3, 0), Error, "a second count of nothing is rejected");
console.log("ok");
