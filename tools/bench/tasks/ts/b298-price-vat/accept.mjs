import assert from "node:assert/strict";
import { grossPrice } from "./solution.ts";

assert.equal(grossPrice(1000, 20), 1200, "a fifth is added");
assert.equal(grossPrice(999, 20), 1198, "the tax is rounded down");
assert.equal(grossPrice(500, 0), 500, "no rate, no change");
assert.equal(grossPrice(0, 20), 0, "nothing is taxed as nothing");
assert.equal(grossPrice(333, 10), 366, "a tenth, rounded down");
assert.equal(grossPrice(100, 100), 200, "a rate of a hundred doubles it");
console.log("ok");
