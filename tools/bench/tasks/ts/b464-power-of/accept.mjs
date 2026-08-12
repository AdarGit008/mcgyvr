import assert from "node:assert/strict";
import { powerOf } from "./solution.ts";

assert.equal(powerOf(2, 3), 8, "two cubed");
assert.equal(powerOf(5, 0), 1, "a power of nothing gives one");
assert.equal(powerOf(2, 1), 2, "a power of one gives the base");
assert.equal(powerOf(0, 3), 0, "nothing to any power is nothing");
assert.equal(powerOf(1, 10), 1, "one to any power is one");
assert.throws(() => powerOf(2, -1), Error, "a negative power is rejected");
console.log("ok");
