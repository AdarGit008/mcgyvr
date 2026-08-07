import assert from "node:assert/strict";
import { countStripTilings } from "./solution.ts";

assert.equal(countStripTilings(0), 1, "empty strip has the empty covering");
assert.equal(countStripTilings(1), 1, "one column takes one upright domino");
assert.equal(countStripTilings(2), 3, "two columns: two uprights, two flats, or a square");
assert.equal(countStripTilings(3), 5, "three columns");
assert.equal(countStripTilings(4), 11, "four columns");
assert.equal(countStripTilings(5), 21, "five columns");
assert.equal(countStripTilings(7), 85, "seven columns");
assert.equal(countStripTilings(12), 2731, "twelve columns");
assert.equal(countStripTilings(20), 699051, "twenty columns");
assert.equal(countStripTilings(40), 733007751851, "forty columns needs better than blind recursion");
assert.throws(() => countStripTilings(-1), Error, "negative width rejected");
assert.throws(() => countStripTilings(2.5), Error, "fractional width rejected");
console.log("ok");
