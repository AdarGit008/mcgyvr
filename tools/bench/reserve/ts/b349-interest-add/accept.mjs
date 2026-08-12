import assert from "node:assert/strict";
import { interestAdd } from "./solution.ts";

assert.equal(interestAdd(1000, 5, 2), 1100, "two years at five percent");
assert.equal(interestAdd(1000, 5, 0), 1000, "no years, no interest");
assert.equal(interestAdd(100, 3, 1), 103, "one year at three percent");
assert.equal(interestAdd(0, 10, 5), 0, "nothing earns nothing");
assert.equal(interestAdd(999, 1, 1), 1008, "the interest is rounded down");
assert.equal(interestAdd(200, 50, 1), 300, "half again in a year");
console.log("ok");
