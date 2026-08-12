import assert from "node:assert/strict";
import { halfLife } from "./solution.ts";

assert.equal(halfLife(100, 1), 50, "one clean halving");
assert.equal(halfLife(7, 1), 3, "the fraction is discarded");
assert.equal(halfLife(7, 2), 1, "and again");
assert.equal(halfLife(100, 0), 100, "no steps, no change");
assert.equal(halfLife(0, 5), 0, "nothing halves to nothing");
assert.equal(halfLife(1, 3), 0, "one falls to nothing and stays");
console.log("ok");
