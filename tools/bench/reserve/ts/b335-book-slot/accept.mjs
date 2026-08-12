import assert from "node:assert/strict";
import { slotFree, freeSlots } from "./solution.ts";

assert.equal(slotFree(1, [2]), true, "an unbooked slot is free");
assert.equal(slotFree(2, [2]), false, "a booked slot is not");
assert.deepEqual(freeSlots(3, [2]), [1, 3], "the booked one is skipped");
assert.deepEqual(freeSlots(3, []), [1, 2, 3], "nothing is booked");
assert.deepEqual(freeSlots(0, []), [], "there are no slots");
assert.deepEqual(freeSlots(2, [1, 2]), [], "everything is booked");
console.log("ok");
