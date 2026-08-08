import assert from "node:assert/strict";
import { nameKettleHands } from "./solution.ts";

assert.deepEqual(
  nameKettleHands([["g1", "h2", "j3", "k4"]]),
  { names: ["kiln-run"], totals: [10] },
  "four running heats across four flues",
);
assert.deepEqual(
  nameKettleHands([["g1", "g5", "h2", "h8"]]),
  { names: ["double-flue"], totals: [16] },
  "two flues covering two cards each",
);
assert.deepEqual(
  nameKettleHands([["g1", "h2", "j4", "g7"]]),
  { names: ["banked"], totals: [14] },
  "heats adding to a multiple of seven",
);
assert.deepEqual(
  nameKettleHands([["g1", "h3", "j4", "k8"]]),
  { names: ["draught"], totals: [16] },
  "a spread of six or more",
);
assert.deepEqual(
  nameKettleHands([["g1", "h2", "j3", "k6"]]),
  { names: ["cold"], totals: [12] },
  "a hand no line fits",
);
assert.deepEqual(
  nameKettleHands([["g1", "h1", "j3", "k4"]]),
  { names: ["cold"], totals: [9] },
  "a repeated heat is not a run",
);
assert.deepEqual(
  nameKettleHands([["g2", "h2", "j5", "k5"]]),
  { names: ["banked"], totals: [14] },
  "two repeated heats three apart fall through to banked",
);
assert.deepEqual(
  nameKettleHands([["g1", "g2", "g3", "h4"]]),
  { names: ["cold"], totals: [10] },
  "two flues split three and one are no double-flue",
);
assert.deepEqual(
  nameKettleHands([
    ["g1", "h2", "j3", "k4"],
    ["g2", "h2", "j5", "k5"],
    ["g1", "h1", "j3", "k4"],
  ]),
  { names: ["kiln-run", "banked", "cold"], totals: [10, 14, 9] },
  "several hands keep the order they arrived in",
);
assert.throws(() => nameKettleHands("hands"), Error, "a non-list argument is rejected");
assert.throws(() => nameKettleHands([]), Error, "an empty list of hands is rejected");
assert.throws(
  () => nameKettleHands([["g1", "h2", "j3"]]),
  Error,
  "a hand of three cards is rejected",
);
assert.throws(() => nameKettleHands(["g1h2"]), Error, "a hand that is not a list is rejected");
assert.throws(
  () => nameKettleHands([["g1", "h2", "j3", "k9"]]),
  Error,
  "a heat of nine is rejected",
);
assert.throws(
  () => nameKettleHands([["g1", "h2", "j3", "z4"]]),
  Error,
  "an unknown flue letter is rejected",
);
assert.throws(
  () => nameKettleHands([["g1", "g1", "h2", "j3"]]),
  Error,
  "a card written twice is rejected",
);
assert.throws(
  () => nameKettleHands([["g1", "h2", "j3", 4]]),
  Error,
  "a card that is not a string is rejected",
);
console.log("ok");
