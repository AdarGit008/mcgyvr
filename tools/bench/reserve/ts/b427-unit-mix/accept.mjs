import assert from "node:assert/strict";
import { unitMix } from "./solution.ts";

assert.deepEqual(unitMix(1, 7, 4), [2, 3], "the parts carry into a unit");
assert.deepEqual(unitMix(0, 3, 4), [0, 3], "nothing to carry");
assert.deepEqual(unitMix(2, 8, 4), [4, 0], "the parts carry exactly");
assert.deepEqual(unitMix(0, 0, 4), [0, 0], "nothing at all");
assert.deepEqual(unitMix(1, 4, 4), [2, 0], "one unit's worth of parts");
assert.throws(() => unitMix(1, 1, 0), Error, "a unit of no parts is rejected");
console.log("ok");
