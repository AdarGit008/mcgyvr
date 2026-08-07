import assert from "node:assert/strict";
import { squashJournal } from "./solution.ts";

assert.deepEqual(squashJournal([]), [], "empty journal squashes to empty");
assert.deepEqual(
  squashJournal([["put", "a", 1], ["put", "b", 2]]),
  [["put", "a", 1], ["put", "b", 2]],
  "independent puts survive in order"
);
assert.deepEqual(
  squashJournal([["put", "a", 1], ["put", "a", 5]]),
  [["put", "a", 5]],
  "overwrite keeps only the final value"
);
assert.deepEqual(
  squashJournal([["put", "a", 1], ["del", "a"]]),
  [],
  "put then del cancels out"
);
assert.deepEqual(
  squashJournal([["put", "a", 7], ["ren", "a", "b"], ["ren", "b", "c"]]),
  [["put", "c", 7]],
  "a rename chain collapses to one put of the final name"
);
assert.deepEqual(
  squashJournal([["put", "a", 1], ["put", "b", 2], ["put", "a", 3]]),
  [["put", "b", 2], ["put", "a", 3]],
  "ordering follows the establishing put, not first appearance"
);
assert.deepEqual(
  squashJournal([["put", "x", 4], ["put", "y", 9], ["del", "x"], ["ren", "y", "x"]]),
  [["put", "x", 9]],
  "rename after delete reuses the freed name"
);
assert.deepEqual(
  squashJournal([["put", "a", 1], ["ren", "a", "b"], ["put", "b", 2]]),
  [["put", "b", 2]],
  "overwriting a renamed key re-establishes it"
);
assert.deepEqual(
  squashJournal([
    ["put", "a", 1],
    ["put", "b", 2],
    ["ren", "a", "t"],
    ["ren", "b", "a"],
    ["ren", "t", "b"],
  ]),
  [["put", "b", 1], ["put", "a", 2]],
  "a swap through a temporary keeps establishing order"
);
assert.throws(() => squashJournal([["del", "a"]]), Error, "del of absent key");
assert.throws(
  () => squashJournal([["ren", "a", "b"]]),
  Error,
  "ren of absent source"
);
assert.throws(
  () => squashJournal([["put", "a", 1], ["put", "b", 2], ["ren", "a", "b"]]),
  Error,
  "ren onto existing destination"
);
assert.throws(() => squashJournal([["zap", "a"]]), Error, "unknown operation");
assert.throws(() => squashJournal([["put", "", 1]]), Error, "empty key");
assert.throws(() => squashJournal([["put", "a", 0]]), Error, "zero value");
assert.throws(() => squashJournal([["put", "a", 1.5]]), Error, "fractional value");
console.log("ok");
