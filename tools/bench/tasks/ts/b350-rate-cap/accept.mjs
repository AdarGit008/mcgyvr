import assert from "node:assert/strict";
import { rateCap } from "./solution.ts";

assert.equal(rateCap(1000, 10, 50), 1050, "the cap bites");
assert.equal(rateCap(1000, 10, 500), 1100, "the cap is out of reach");
assert.equal(rateCap(1000, 0, 50), 1000, "no rate, no rise");
assert.equal(rateCap(0, 10, 50), 0, "nothing to raise");
assert.equal(rateCap(100, 10, 10), 110, "the rise lands exactly on the cap");
assert.equal(rateCap(999, 10, 1000), 1098, "the rise is rounded down");
console.log("ok");
