import assert from "node:assert/strict";
import { compareRemitLines } from "./solution.ts";

const ours = [["INV-1", 1000], ["INV-2", 2500], ["INV-3", -400]];
const theirs = [["INV-2", 2500], ["INV-3", -450], ["INV-9", 700]];

assert.deepEqual(
  compareRemitLines(ours, theirs),
  { agreed: ["INV-2"], queried: ["INV-3"], ourSide: ["INV-1"], theirSide: ["INV-9"] },
  "one of each outcome",
);
assert.deepEqual(
  compareRemitLines([], []),
  { agreed: [], queried: [], ourSide: [], theirSide: [] },
  "two empty advices agree on nothing",
);
assert.deepEqual(
  compareRemitLines(ours, []),
  { agreed: [], queried: [], ourSide: ["INV-1", "INV-2", "INV-3"], theirSide: [] },
  "an empty counterparty advice leaves everything on our side",
);
assert.deepEqual(
  compareRemitLines([], theirs),
  { agreed: [], queried: [], ourSide: [], theirSide: ["INV-2", "INV-3", "INV-9"] },
  "an empty advice of ours leaves everything on theirs",
);
assert.deepEqual(
  compareRemitLines([["c", 0], ["a", 0]], [["a", 0], ["c", 1]]),
  { agreed: ["a"], queried: ["c"], ourSide: [], theirSide: [] },
  "zero is an amount like any other and the lists come back sorted",
);
assert.deepEqual(
  compareRemitLines([["x", -5]], [["x", 5]]),
  { agreed: [], queried: ["x"], ourSide: [], theirSide: [] },
  "the same size with the opposite sign is queried",
);
assert.deepEqual(
  compareRemitLines([["z", 12], ["y", 12], ["w", 3]], [["w", 4], ["y", 12]]),
  { agreed: ["y"], queried: ["w"], ourSide: ["z"], theirSide: [] },
  "several lines split across the four buckets",
);

assert.throws(() => compareRemitLines([["a", 1], ["a", 2]], []), Error, "a repeated label is rejected");
assert.throws(() => compareRemitLines([["", 1]], []), Error, "an empty label is rejected");
assert.throws(() => compareRemitLines([[7, 1]], []), Error, "a non-string label is rejected");
assert.throws(() => compareRemitLines([["a", 1.5]], []), Error, "a fractional amount is rejected");
assert.throws(() => compareRemitLines([["a", 1, 2]], []), Error, "a three-entry line is rejected");
assert.throws(() => compareRemitLines([["a"]], []), Error, "a one-entry line is rejected");
assert.throws(() => compareRemitLines("a", []), Error, "a string advice is rejected");
console.log("ok");
