import assert from "node:assert/strict";
import { slotHits } from "./solution.ts";

assert.equal(slotHits([], 4), 0, "empty stream scores no hits");
assert.equal(slotHits([7, 7, 7], 4), 2, "repeats hit after the first miss");
assert.equal(slotHits([1, 5, 1], 4), 0, "colliding keys keep evicting each other");
assert.equal(slotHits([0, 1, 2, 0, 1, 2], 4), 3, "keys in distinct slots hit on return");
assert.equal(slotHits([-3, -3], 4), 1, "a negative key holds its slot");
assert.equal(slotHits([-3, 1, -3], 4), 0, "key -3 shares slot 1 with key 1");
assert.equal(slotHits([4, 4], 1), 1, "a single-slot cache still hits");
assert.throws(() => slotHits([1], 0), Error, "zero slots is rejected");
assert.throws(() => slotHits([1], 2.5), Error, "fractional slot count is rejected");
assert.throws(() => slotHits([1.5], 4), Error, "fractional key is rejected");
console.log("ok");
