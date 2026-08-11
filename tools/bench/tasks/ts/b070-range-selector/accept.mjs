import assert from "node:assert/strict";
import { selectorHits } from "./solution.ts";

assert.equal(selectorHits([8, 12, 40, 41], "10-40"), 2, "one range");
assert.equal(selectorHits([3, 8, 22, 25], "1-5,20-30"), 3, "several terms");
assert.equal(selectorHits([15], "10-20,15"), 1, "overlapping terms count a value once");
assert.equal(selectorHits([10, 40], "10-40"), 2, "range ends are inclusive");
assert.equal(selectorHits([], "5"), 0, "no values");
assert.throws(() => selectorHits(["9"], "9"), Error, "non-integer value is rejected");
assert.throws(() => selectorHits([1], ""), Error, "empty selector is rejected");
assert.throws(() => selectorHits([1], "3,,9"), Error, "empty term is rejected");
assert.throws(() => selectorHits([1], "9-4"), Error, "reversed range is rejected");
console.log("ok");
