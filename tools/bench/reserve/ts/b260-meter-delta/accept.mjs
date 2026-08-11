import assert from "node:assert/strict";
import { meterDelta } from "./solution.ts";

assert.equal(meterDelta(10, 25, 100), 15, "a plain climb");
assert.equal(meterDelta(90, 10, 100), 20, "the meter wrapped");
assert.equal(meterDelta(5, 5, 100), 0, "the meter did not move");
assert.equal(meterDelta(0, 99, 100), 99, "the whole span but the ceiling");
assert.throws(() => meterDelta(100, 5, 100), Error, "the earlier reading is too big");
assert.throws(() => meterDelta(5, 150, 100), Error, "the later reading is too big");
console.log("ok");
