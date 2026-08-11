import assert from "node:assert/strict";
import { heldDown, limitMap } from "./solution.ts";

assert.equal(heldDown(9, 5), 5, "brought down to the ceiling");
assert.equal(heldDown(2, 5), 2, "already under it");
assert.deepEqual(limitMap({ a: 9, b: 2 }, 5), { a: 5, b: 2 }, "only the high one moves");
assert.deepEqual(limitMap({}, 5), {}, "an empty store");
assert.deepEqual(limitMap({ a: 5 }, 5), { a: 5 }, "a value on the ceiling stays");
assert.deepEqual(limitMap({ a: 9, b: 8 }, 5), { a: 5, b: 5 }, "everything comes down");
console.log("ok");
