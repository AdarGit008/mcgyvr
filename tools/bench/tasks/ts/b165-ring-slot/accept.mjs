import assert from "node:assert/strict";
import { ringSlot } from "./solution.ts";

assert.equal(ringSlot(8, 3, 0), 0, "before wrapping the oldest sits in slot 0");
assert.equal(ringSlot(8, 3, 2), 2, "before wrapping rank k sits in slot k");
assert.equal(ringSlot(4, 4, 3), 3, "an exactly full recorder has not wrapped");
assert.equal(ringSlot(4, 6, 0), 2, "after wrapping the oldest survivor moved up");
assert.equal(ringSlot(4, 6, 3), 1, "the newest survivor sits before the oldest slot");
assert.equal(ringSlot(3, 10, 1), 2, "a long run keeps wrapping around");
assert.throws(() => ringSlot(0, 3, 0), Error, "a zero capacity is rejected");
assert.throws(() => ringSlot(4, -1, 0), Error, "negative writes are rejected");
assert.throws(() => ringSlot(4, 4, 1.5), Error, "a fractional rank is rejected");
assert.throws(() => ringSlot(4, 6, 4), Error, "a rank past the survivors is rejected");
assert.throws(() => ringSlot(5, 0, 0), Error, "an empty recorder has no survivors");
console.log("ok");
