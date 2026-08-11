import assert from "node:assert/strict";
import { vatBack } from "./solution.ts";

assert.equal(vatBack(1200, 20), 1000, "a fifth comes back off");
assert.equal(vatBack(1000, 0), 1000, "no rate, no change");
assert.equal(vatBack(110, 10), 100, "a tenth comes back off");
assert.equal(vatBack(0, 20), 0, "nothing is taxed as nothing");
assert.equal(vatBack(1000, 20), 833, "rounded down");
assert.equal(vatBack(100, 100), 50, "a rate of a hundred halves it");
console.log("ok");
