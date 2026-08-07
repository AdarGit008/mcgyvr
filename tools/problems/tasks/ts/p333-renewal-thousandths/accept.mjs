import assert from "node:assert/strict";
import { renewalThousandths } from "./solution.ts";

assert.deepEqual(
  renewalThousandths([["red", 8, [8, 6, 4, 1]]]),
  [["red", [1000, 750, 500, 125]]],
  "every cycle is measured against the forming seats",
);

assert.deepEqual(
  renewalThousandths([["blue", 16, [1]]]),
  [["blue", [63]]],
  "an exact half rounds upward",
);

assert.deepEqual(
  renewalThousandths([["gray", 3, [2, 1]]]),
  [["gray", [667, 333]]],
  "thirds round to the nearest whole thousandth",
);

assert.deepEqual(
  renewalThousandths([["flat", 40, [40, 40, 40]]]),
  [["flat", [1000, 1000, 1000]]],
  "a squad that keeps every seat reads full strength",
);

assert.deepEqual(
  renewalThousandths([["gone", 4, [2, 0, 0]]]),
  [["gone", [500, 0, 0]]],
  "an empty cycle reads zero and does not poison the ones after it",
);

assert.deepEqual(
  renewalThousandths([
    ["one", 5, []],
    ["two", 7, [7]],
  ]),
  [
    ["one", []],
    ["two", [1000]],
  ],
  "squads keep the order given and an empty run gives an empty strength list",
);

assert.deepEqual(renewalThousandths([]), [], "no squads gives no rows");

assert.throws(
  () =>
    renewalThousandths([
      ["red", 4, [1]],
      ["red", 4, [1]],
    ]),
  Error,
  "a repeated squad name is rejected",
);
assert.throws(
  () => renewalThousandths([["red", 4, [5]]]),
  Error,
  "a tally above the forming seats is rejected",
);
assert.throws(
  () => renewalThousandths([["red", 4, [2, 3]]]),
  Error,
  "a tally that climbs is rejected",
);
assert.throws(
  () => renewalThousandths([["red", 0, [0]]]),
  Error,
  "zero forming seats is rejected",
);
assert.throws(
  () => renewalThousandths([["red", 4, [1.5]]]),
  Error,
  "a fractional tally is rejected",
);
assert.throws(
  () => renewalThousandths([["", 4, [1]]]),
  Error,
  "an empty squad name is rejected",
);
assert.throws(
  () => renewalThousandths([["red", 4]]),
  Error,
  "a squad that is not a triple is rejected",
);
assert.throws(
  () => renewalThousandths("red"),
  Error,
  "a non-list argument is rejected",
);
console.log("ok");
