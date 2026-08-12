import assert from "node:assert/strict";
import { soakRun } from "./solution.ts";

assert.equal(soakRun([1, 5, 6, 2, 7], 4), 2, "the longest of two stretches");
assert.equal(soakRun([5, 5, 5], 4), 3, "the whole run is wet");
assert.equal(soakRun([1, 2], 4), 0, "never reaches the floor");
assert.equal(soakRun([], 4), 0, "no readings at all");
assert.equal(soakRun([4, 4], 4), 2, "sitting exactly on the floor counts");
assert.equal(soakRun([9, 1, 9, 9], 4), 2, "a later stretch wins");
console.log("ok");
