import assert from "node:assert/strict";
import { bestRatePath } from "./solution.ts";

assert.deepEqual(
  bestRatePath([["USD", "EUR", 900000]], 1000, "USD", "EUR"),
  { amount: 900, path: ["USD", "EUR"] },
  "a single quote is the only run"
);

assert.deepEqual(
  bestRatePath(
    [
      ["USD", "EUR", 900000],
      ["EUR", "GBP", 900000],
      ["USD", "GBP", 800000],
    ],
    1000,
    "USD",
    "GBP"
  ),
  { amount: 810, path: ["USD", "EUR", "GBP"] },
  "a detour can beat the direct quote"
);

assert.deepEqual(
  bestRatePath(
    [
      ["A", "B", 500000],
      ["B", "C", 2000000],
      ["A", "C", 1000000],
    ],
    7,
    "A",
    "C"
  ),
  { amount: 7, path: ["A", "C"] },
  "the discard at each hop is what separates the two runs"
);

assert.deepEqual(
  bestRatePath(
    [
      ["A", "B", 1000000],
      ["B", "C", 1000000],
      ["A", "C", 1000000],
    ],
    500,
    "A",
    "C"
  ),
  { amount: 500, path: ["A", "C"] },
  "equal amounts break toward the shorter run"
);

assert.deepEqual(
  bestRatePath(
    [
      ["A", "M", 1000000],
      ["M", "Z", 1000000],
      ["A", "N", 1000000],
      ["N", "Z", 1000000],
    ],
    100,
    "A",
    "Z"
  ),
  { amount: 100, path: ["A", "M", "Z"] },
  "equal amounts and equal lengths break on the codes"
);

assert.deepEqual(
  bestRatePath(
    [
      ["A", "B", 400000],
      ["B", "C", 5000000],
      ["A", "C", 900000],
    ],
    1,
    "A",
    "C"
  ),
  { amount: 0, path: ["A", "C"] },
  "a run may arrive at nothing and still be the best one"
);

assert.deepEqual(
  bestRatePath(
    [
      ["JPY", "USD", 6000],
      ["USD", "CHF", 890000],
      ["JPY", "CHF", 5000],
    ],
    1000000,
    "JPY",
    "CHF"
  ),
  { amount: 5340, path: ["JPY", "USD", "CHF"] },
  "a three-code chain over a thin direct quote"
);

assert.throws(
  () => bestRatePath([], 10, "A", "B"),
  Error,
  "an empty quote list is rejected"
);
assert.throws(
  () => bestRatePath([["A", "B"]], 10, "A", "B"),
  Error,
  "a two-element quote is rejected"
);
assert.throws(
  () => bestRatePath([["A", "", 100]], 10, "A", "B"),
  Error,
  "an empty code is rejected"
);
assert.throws(
  () => bestRatePath([["A", "A", 100]], 10, "A", "B"),
  Error,
  "a quote naming one code twice is rejected"
);
assert.throws(
  () => bestRatePath([["A", "B", 0]], 10, "A", "B"),
  Error,
  "a micro rate of zero is rejected"
);
assert.throws(
  () =>
    bestRatePath(
      [
        ["A", "B", 100],
        ["A", "B", 200],
      ],
      10,
      "A",
      "B"
    ),
  Error,
  "the same ordered pair quoted twice is rejected"
);
assert.throws(
  () => bestRatePath([["A", "B", 100]], 0, "A", "B"),
  Error,
  "an amount of zero is rejected"
);
assert.throws(
  () => bestRatePath([["A", "B", 100]], 10, "A", "A"),
  Error,
  "source and destination alike are rejected"
);
assert.throws(
  () => bestRatePath([["A", "B", 100]], 10, "A", "Q"),
  Error,
  "a code no quote names is rejected"
);
assert.throws(
  () => bestRatePath([["A", "B", 100]], 10, "B", "A"),
  Error,
  "a quote's direction cannot be run backwards"
);

console.log("ok");
