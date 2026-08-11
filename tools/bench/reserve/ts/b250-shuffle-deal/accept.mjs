import assert from "node:assert/strict";
import { shuffleDeal, dealCounts } from "./solution.ts";

assert.deepEqual(
  shuffleDeal(["a", "b", "c", "d"], 2),
  [["a", "c"], ["b", "d"]],
  "cards alternate round the table",
);
assert.deepEqual(shuffleDeal(["a"], 2), [["a"], []], "one card, one hand short");
assert.deepEqual(shuffleDeal([], 2), [[], []], "empty hands are still dealt");
assert.deepEqual(shuffleDeal(["a", "b"], 0), [], "no hands, nothing dealt");
assert.deepEqual(dealCounts([["a", "c"], ["b"]]), [2, 1], "the sizes of each hand");
assert.deepEqual(dealCounts([]), [], "no hands to count");
console.log("ok");
