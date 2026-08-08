import assert from "node:assert/strict";
import { sortPostalItems } from "./solution.ts";

const frame = [
  { name: "one", depot: "QNR", low: 0, high: 199 },
  { name: "two", depot: "QNR", low: 100, high: 499 },
  { name: "three", depot: "BLT", low: 0, high: 999 },
];

assert.deepEqual(
  sortPostalItems(["QNR-150"], frame),
  ["one"],
  "the earliest claiming bin wins, not the tightest",
);
assert.deepEqual(
  sortPostalItems(["QNR-300", "BLT-000", "BLT-999"], frame),
  ["two", "three", "three"],
  "later bins and the ends of a range",
);
assert.deepEqual(
  sortPostalItems(["QNR-700", "ZZZ-001"], frame),
  ["HOLD", "HOLD"],
  "a well-formed code no bin claims is held",
);
assert.deepEqual(
  sortPostalItems(["blt-001", "QNR150", "QNR-1500", "", "QNR-15"], frame),
  ["BAD", "BAD", "BAD", "BAD", "BAD"],
  "broken grammar never reaches the frame",
);
assert.deepEqual(
  sortPostalItems(["QNR-199", "QNR-200", "QNR-499", "QNR-500"], frame),
  ["one", "two", "two", "HOLD"],
  "range edges either side of the boundary",
);
assert.deepEqual(sortPostalItems([], frame), [], "an empty sack sorts to nothing");
assert.deepEqual(
  sortPostalItems(["BLT-042"], [{ name: "solo", depot: "BLT", low: 42, high: 42 }]),
  ["solo"],
  "a range of one walk",
);

assert.throws(() => sortPostalItems(["BLT-000"], []), Error, "an empty frame");
assert.throws(
  () =>
    sortPostalItems(
      ["BLT-000"],
      [
        { name: "x", depot: "BLT", low: 0, high: 9 },
        { name: "x", depot: "QNR", low: 0, high: 9 },
      ],
    ),
  Error,
  "repeated bin name",
);
assert.throws(
  () => sortPostalItems(["BLT-000"], [{ name: "HOLD", depot: "BLT", low: 0, high: 9 }]),
  Error,
  "a bin named for a mark",
);
assert.throws(
  () => sortPostalItems(["BLT-000"], [{ name: "x", depot: "Blt", low: 0, high: 9 }]),
  Error,
  "a depot that is not three capitals",
);
assert.throws(
  () => sortPostalItems(["BLT-000"], [{ name: "x", depot: "BLT", low: 9, high: 4 }]),
  Error,
  "low above high",
);
assert.throws(
  () => sortPostalItems(["BLT-000"], [{ name: "x", depot: "BLT", low: 0, high: 1000 }]),
  Error,
  "a walk beyond 999",
);
assert.throws(() => sortPostalItems([7], frame), Error, "a code that is not a string");
assert.throws(() => sortPostalItems("BLT-000", frame), Error, "codes is not a list");
console.log("ok");
