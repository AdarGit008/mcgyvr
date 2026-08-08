import assert from "node:assert/strict";
import { shelfCount } from "./solution.ts";

assert.deepEqual(shelfCount([]), [0, 0], "empty entry list");
assert.deepEqual(
  shelfCount([["add", 5], ["take", 2]]),
  [3, 0],
  "add then take within stock",
);
assert.deepEqual(
  shelfCount([["add", 2], ["take", 5]]),
  [2, 1],
  "oversized take is skipped and tallied, count untouched",
);
assert.deepEqual(
  shelfCount([["take", 1]]),
  [0, 1],
  "taking from an empty shelf is skipped",
);
assert.deepEqual(
  shelfCount([["add", 4], ["take", 4]]),
  [0, 0],
  "taking exactly the stock is applied",
);
assert.deepEqual(
  shelfCount([["add", 9], ["fix", 3], ["take", 2]]),
  [1, 0],
  "fix overwrites the running count",
);
assert.deepEqual(
  shelfCount([["take", 2], ["add", 1], ["take", 3], ["take", 1]]),
  [0, 2],
  "each skipped take is tallied",
);
assert.throws(() => shelfCount([["drop", 1]]), Error, "unknown kind is rejected");
assert.throws(() => shelfCount([["add", -2]]), Error, "negative amount is rejected");
assert.throws(
  () => shelfCount([["add", 1.5]]),
  Error,
  "fractional amount is rejected",
);
assert.throws(
  () => shelfCount([["take", "3"]]),
  Error,
  "non-numeric amount is rejected",
);
console.log("ok");
