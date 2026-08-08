import assert from "node:assert/strict";
import { serpentinePickOrder } from "./solution.ts";

const pick = (sku, aisle, bay) => ({ sku, aisle, bay });

assert.deepEqual(serpentinePickOrder([]), [], "nothing to grab");
assert.deepEqual(serpentinePickOrder([pick("a", 1, 4)]), ["a"], "a lone pick");
assert.deepEqual(
  serpentinePickOrder([pick("a", 1, 9), pick("b", 1, 2), pick("c", 1, 5)]),
  ["b", "c", "a"],
  "an odd aisle climbs the bays"
);
assert.deepEqual(
  serpentinePickOrder([pick("a", 2, 9), pick("b", 2, 2), pick("c", 2, 5)]),
  ["a", "c", "b"],
  "an even aisle descends the bays"
);
assert.deepEqual(
  serpentinePickOrder([pick("x", 3, 1), pick("y", 2, 1), pick("z", 1, 1)]),
  ["z", "y", "x"],
  "aisles are worked in ascending order"
);
assert.deepEqual(
  serpentinePickOrder([
    pick("p", 1, 2),
    pick("q", 2, 3),
    pick("r", 1, 7),
    pick("s", 2, 8),
  ]),
  ["p", "r", "s", "q"],
  "the walk turns at the end of each aisle"
);
assert.deepEqual(
  serpentinePickOrder([pick("late", 4, 5), pick("early", 4, 5)]),
  ["late", "early"],
  "a shared bay keeps the listed order"
);
assert.deepEqual(
  serpentinePickOrder([
    pick("m", 6, 1),
    pick("n", 5, 3),
    pick("o", 6, 4),
    pick("p", 5, 1),
  ]),
  ["p", "n", "o", "m"],
  "two aisles of opposite parity"
);

assert.throws(
  () => serpentinePickOrder("nope"),
  Error,
  "a pick list that is not a list is rejected"
);
assert.throws(
  () => serpentinePickOrder([[1, 2]]),
  Error,
  "a pick that is not a mapping is rejected"
);
assert.throws(
  () => serpentinePickOrder([{ aisle: 1, bay: 1 }]),
  Error,
  "a missing sku is rejected"
);
assert.throws(
  () => serpentinePickOrder([pick("", 1, 1)]),
  Error,
  "an empty sku is rejected"
);
assert.throws(
  () => serpentinePickOrder([pick("a", 1, 1), pick("a", 2, 2)]),
  Error,
  "a repeated sku is rejected"
);
assert.throws(
  () => serpentinePickOrder([pick("a", 0, 1)]),
  Error,
  "aisle zero is rejected"
);
assert.throws(
  () => serpentinePickOrder([pick("a", 1, -2)]),
  Error,
  "a negative bay is rejected"
);

console.log("ok");
