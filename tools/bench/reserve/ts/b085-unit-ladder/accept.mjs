import assert from "node:assert/strict";
import { ladderConvert } from "./solution.ts";

const LADDER = [["cup", "tbsp", 16], ["tbsp", "tsp", 3]];

assert.equal(ladderConvert(LADDER, 2, "cup", "tbsp"), 32, "one hop downward multiplies");
assert.equal(
  ladderConvert(LADDER, 1, "cup", "tsp"),
  48,
  "a downward conversion crosses the whole ladder",
);
assert.equal(ladderConvert(LADDER, 96, "tsp", "cup"), 2, "an exact upward conversion divides");
assert.equal(ladderConvert(LADDER, 7, "tbsp", "tbsp"), 7, "same unit returns the amount");
assert.equal(ladderConvert(LADDER, 0, "tsp", "cup"), 0, "zero converts to zero");
assert.equal(
  ladderConvert([["tbsp", "tsp", 3], ["gal", "cup", 16], ["cup", "tbsp", 16]], 1, "gal", "tsp"),
  768,
  "rule order does not matter",
);
assert.throws(() => ladderConvert(LADDER, -1, "cup", "tsp"), Error, "negative amount is rejected");
assert.throws(
  () => ladderConvert([["pack", "piece", 1]], 1, "pack", "piece"),
  Error,
  "a factor below two is rejected",
);
assert.throws(
  () => ladderConvert([["case", "box", 2], ["case", "tray", 3]], 1, "case", "box"),
  Error,
  "a unit on the bigger side of two rules is rejected",
);
assert.throws(
  () => ladderConvert([["case", "box", 2], ["pallet", "crate", 3]], 1, "case", "box"),
  Error,
  "disconnected rules are rejected",
);
assert.throws(() => ladderConvert(LADDER, 1, "cup", "oz"), Error, "an unknown unit is rejected");
assert.throws(
  () => ladderConvert(LADDER, 5, "tsp", "tbsp"),
  Error,
  "an inexact upward conversion is rejected",
);
console.log("ok");
