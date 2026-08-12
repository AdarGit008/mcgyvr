import assert from "node:assert/strict";
import { changePct } from "./solution.ts";

assert.equal(changePct(10, 15), 50, "half again as much");
assert.equal(changePct(10, 5), -50, "half as much");
assert.equal(changePct(10, 10), 0, "no change at all");
assert.equal(changePct(0, 5), 0, "nothing to change from");
assert.equal(changePct(10, 0), -100, "everything gone");
assert.equal(changePct(10, 13), 30, "a smaller rise");
console.log("ok");
