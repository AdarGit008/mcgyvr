import assert from "node:assert/strict";
import { mergeLedgers } from "./solution.ts";

assert.deepEqual(
  mergeLedgers([["a", 100]], [["a", 120]], [["a", 90]]),
  [["a", 110]],
  "both sides' deltas apply",
);
assert.deepEqual(
  mergeLedgers([["a", 100]], [["a", 100]], [["a", 70]]),
  [["a", 70]],
  "one side's edit carries",
);
assert.deepEqual(
  mergeLedgers([["a", 100]], [["a", 100]], [["a", 100]]),
  [["a", 100]],
  "untouched account keeps its value",
);
assert.deepEqual(
  mergeLedgers([["a", 50]], [["a", 0]], [["a", 10]]),
  [["a", -40]],
  "joint withdrawals may overdraw",
);
assert.deepEqual(mergeLedgers([], [["n", 25]], []), [["n", 25]], "added by ours");
assert.deepEqual(mergeLedgers([], [], [["p", 8]]), [["p", 8]], "added by theirs");
assert.deepEqual(
  mergeLedgers([], [["n", 25]], [["n", 30]]),
  [["n", 55]],
  "added by both sums the two values",
);
assert.deepEqual(
  mergeLedgers([["a", 40]], [], [["a", 40]]),
  [],
  "deletion beside an untouched copy holds",
);
assert.deepEqual(
  mergeLedgers([["a", 40]], [], [["a", 45]]),
  [["a", 45]],
  "an edit outlives the other side's deletion",
);
assert.deepEqual(mergeLedgers([["a", 40]], [], []), [], "dropped by both stays gone");
assert.deepEqual(
  mergeLedgers(
    [["b", 10], ["a", 5]],
    [["b", 12], ["a", 5], ["c", 3]],
    [["b", 10], ["a", 8]],
  ),
  [["a", 8], ["b", 12], ["c", 3]],
  "merged ledger comes back sorted by account",
);
assert.deepEqual(mergeLedgers([], [], []), [], "three empty ledgers merge to nothing");
assert.throws(() => mergeLedgers("cash", [], []), Error, "non-list ledger");
assert.throws(() => mergeLedgers([["", 1]], [], []), Error, "empty account name");
assert.throws(() => mergeLedgers([], [["a", 1.5]], []), Error, "fractional cents");
assert.throws(() => mergeLedgers([], [], [["a", 1, 2]]), Error, "three-item entry");
assert.throws(() => mergeLedgers([["a", 1], ["a", 2]], [], []), Error, "repeated account");
console.log("ok");
