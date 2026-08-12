import assert from "node:assert/strict";
import { partCheck } from "./solution.ts";

assert.equal(partCheck(10, [5, 5], 0), true, "an exact match");
assert.equal(partCheck(10, [5, 4], 0), false, "one short with no tolerance");
assert.equal(partCheck(10, [5, 4], 1), true, "one short within tolerance");
assert.equal(partCheck(0, [], 0), true, "nothing matches nothing");
assert.equal(partCheck(1, [], 0), false, "nothing does not match one");
assert.equal(partCheck(10, [11], 1), true, "one over is within tolerance too");
console.log("ok");
