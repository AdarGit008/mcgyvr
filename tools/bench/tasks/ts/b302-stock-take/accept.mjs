import assert from "node:assert/strict";
import { unitPrice } from "./solution.ts";

assert.equal(unitPrice(1000, 4), 250, "an exact division");
assert.equal(unitPrice(999, 4), 249, "rounded down");
assert.equal(unitPrice(100, 3), 33, "a third, rounded down");
assert.equal(unitPrice(0, 5), 0, "nothing costs nothing each");
assert.equal(unitPrice(7, 7), 1, "one each");
assert.throws(() => unitPrice(100, 0), Error, "a count of zero is rejected");
console.log("ok");
