import assert from "node:assert/strict";
import { anyOver, windowAny } from "./solution.ts";

assert.equal(anyOver([1, 5], 3), true, "one reading stands above");
assert.equal(anyOver([1, 2], 3), false, "none stands above");
assert.deepEqual(windowAny([1, 5, 1], 2, 3), [true, true], "the high reading is in both");
assert.deepEqual(windowAny([1, 1, 1], 2, 3), [false, false], "no run holds one");
assert.deepEqual(windowAny([], 2, 3), [], "no readings at all");
assert.deepEqual(windowAny([5, 1, 1], 2, 3), [true, false], "only the first run");
console.log("ok");
