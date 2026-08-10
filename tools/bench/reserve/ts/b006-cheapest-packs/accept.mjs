import assert from "node:assert/strict";
import { cheapestPacks } from "./solution.ts";

assert.equal(cheapestPacks(6, [[3, 2]]), 4, "one pack size bought twice");
assert.equal(cheapestPacks(6, [[4, 3], [3, 2]]), 4, "two small packs beat the big pack");
assert.equal(cheapestPacks(10, [[4, 4], [3, 2]]), 8, "mixed pack sizes fill exactly");
assert.equal(cheapestPacks(0, [[5, 3]]), 0, "an order of zero costs nothing");
assert.equal(cheapestPacks(7, [[7, 9], [3, 2], [4, 3]]), 5, "a combination undercuts the exact pack");
assert.equal(cheapestPacks(5, [[2, 1]]), -1, "an unfillable order yields -1");
assert.equal(cheapestPacks(9, [[3, 0]]), 0, "free packs cost nothing");
assert.throws(() => cheapestPacks(-1, [[2, 1]]), Error, "negative order is rejected");
assert.throws(() => cheapestPacks(2.5, [[2, 1]]), Error, "fractional order is rejected");
assert.throws(() => cheapestPacks(4, []), Error, "empty pack list is rejected");
assert.throws(() => cheapestPacks(4, [[0, 1]]), Error, "zero pack size is rejected");
assert.throws(() => cheapestPacks(4, [[2, -1]]), Error, "negative pack price is rejected");
console.log("ok");
