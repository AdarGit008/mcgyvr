import assert from "node:assert/strict";
import { weighIn } from "./solution.ts";

assert.deepEqual(weighIn(2500), [2, 500], "two kilos and a half");
assert.deepEqual(weighIn(999), [0, 999], "under a kilo");
assert.deepEqual(weighIn(1000), [1, 0], "exactly a kilo");
assert.deepEqual(weighIn(0), [0, 0], "nothing weighs nothing");
assert.deepEqual(weighIn(12345), [12, 345], "a heavier load");
assert.throws(() => weighIn(-1), Error, "a negative weight is rejected");
console.log("ok");
