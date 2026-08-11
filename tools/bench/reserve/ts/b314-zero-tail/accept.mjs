import assert from "node:assert/strict";
import { zeroTail } from "./solution.ts";

assert.equal(zeroTail(1200), 2, "two zeros at the end");
assert.equal(zeroTail(5), 0, "no zeros at all");
assert.equal(zeroTail(0), 1, "zero counts as one");
assert.equal(zeroTail(100000), 5, "a long tail");
assert.equal(zeroTail(101), 0, "an inner zero does not count");
assert.equal(zeroTail(10), 1, "one zero");
console.log("ok");
