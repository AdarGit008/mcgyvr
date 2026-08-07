import assert from "node:assert/strict";
import { stepDropReport } from "./solution.ts";

assert.deepEqual(
  stepDropReport(
    [
      ["kept", 30],
      ["seen", 200],
      ["tried", 80],
    ],
    ["seen", "tried", "kept"],
  ),
  [
    { step: "seen", count: 200, lost: 0, share: 100 },
    { step: "tried", count: 80, lost: 120, share: 40 },
    { step: "kept", count: 30, lost: 50, share: 15 },
  ],
  "shuffled tallies are reported top to bottom",
);
assert.deepEqual(
  stepDropReport(
    [
      ["a", 3],
      ["b", 1],
    ],
    ["a", "b"],
  ),
  [
    { step: "a", count: 3, lost: 0, share: 100 },
    { step: "b", count: 1, lost: 2, share: 33 },
  ],
  "a third of the top rounds down to 33",
);
assert.deepEqual(
  stepDropReport(
    [
      ["a", 7],
      ["b", 7],
    ],
    ["a", "b"],
  ),
  [
    { step: "a", count: 7, lost: 0, share: 100 },
    { step: "b", count: 7, lost: 0, share: 100 },
  ],
  "a step that sheds nobody keeps the whole share",
);
assert.deepEqual(
  stepDropReport(
    [
      ["a", 0],
      ["b", 0],
    ],
    ["a", "b"],
  ),
  [
    { step: "a", count: 0, lost: 0, share: 0 },
    { step: "b", count: 0, lost: 0, share: 0 },
  ],
  "an empty top makes every share zero",
);
assert.deepEqual(
  stepDropReport(
    [
      ["a", 5],
      ["b", 0],
    ],
    ["a", "b"],
  ),
  [
    { step: "a", count: 5, lost: 0, share: 100 },
    { step: "b", count: 0, lost: 5, share: 0 },
  ],
  "a step nobody reaches sheds all of them",
);
assert.deepEqual(
  stepDropReport([["a", 9]], ["a"]),
  [{ step: "a", count: 9, lost: 0, share: 100 }],
  "one step is the whole report",
);

assert.throws(
  () => stepDropReport([["a", 7], ["b", 8]], ["a", "b"]),
  Error,
  "a step gathering more than the one above it is rejected",
);
assert.throws(
  () => stepDropReport([["a", 7], ["z", 1]], ["a", "b"]),
  Error,
  "a tally the order does not name is rejected",
);
assert.throws(
  () => stepDropReport([["a", 7]], ["a", "b"]),
  Error,
  "a step with no tally is rejected",
);
assert.throws(
  () => stepDropReport([["a", 7], ["a", 5]], ["a"]),
  Error,
  "a step tallied twice is rejected",
);
assert.throws(
  () => stepDropReport([["a", -1]], ["a"]),
  Error,
  "a negative count is rejected",
);
assert.throws(
  () => stepDropReport([["a", 1.5]], ["a"]),
  Error,
  "a fractional count is rejected",
);
assert.throws(() => stepDropReport([["a", 1]], []), Error, "an empty order is rejected");
assert.throws(
  () => stepDropReport([["a", 1]], ["a", "a"]),
  Error,
  "an order naming one step twice is rejected",
);
assert.throws(
  () => stepDropReport("tallies", ["a"]),
  Error,
  "tallies that are not a list are rejected",
);
assert.throws(
  () => stepDropReport([["a", 1, 2]], ["a"]),
  Error,
  "a tally of three items is rejected",
);
console.log("ok");
