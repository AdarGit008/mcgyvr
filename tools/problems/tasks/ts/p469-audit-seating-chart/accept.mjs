import assert from "node:assert/strict";
import { auditSeatingChart } from "./solution.ts";

const chart = [
  ["ana", "ben", ""],
  ["cal", "", "dot"],
];

assert.deepEqual(
  auditSeatingChart(
    chart,
    [
      ["ana", "ben"],
      ["ben", "dot"],
    ],
    [
      ["ana", "cal"],
      ["cal", "dot"],
    ],
  ),
  ["split:ben-dot", "touching:ana-cal"],
  "wanted ties come first, then the banned ones",
);

assert.deepEqual(
  auditSeatingChart(chart, [["ana", "ben"]], [["cal", "dot"]]),
  [],
  "a chart that breaks nothing puts out nothing",
);

assert.deepEqual(
  auditSeatingChart(chart, [["dot", "ben"]], []),
  ["split:ben-dot"],
  "the names are joined with the earlier one alphabetically first",
);

assert.deepEqual(
  auditSeatingChart(chart, [["ana", "cal"]], []),
  [],
  "sitting one band apart in the same column counts as next to",
);

assert.deepEqual(
  auditSeatingChart(chart, [["ana", "dot"]], [["ana", "dot"]]),
  ["split:ana-dot"],
  "cells meeting only at a corner are not next to one another",
);

assert.deepEqual(
  auditSeatingChart([["one", "", "two"]], [], [["one", "two"]]),
  [],
  "a blank place between two names keeps them apart",
);

assert.deepEqual(
  auditSeatingChart(
    [
      ["p", "q"],
      ["r", "s"],
    ],
    [
      ["p", "s"],
      ["q", "r"],
    ],
    [
      ["p", "q"],
      ["r", "s"],
      ["p", "r"],
    ],
  ),
  ["split:p-s", "split:q-r", "touching:p-q", "touching:r-s", "touching:p-r"],
  "every finding is reported, each list in its own order",
);

assert.throws(() => auditSeatingChart([], [], []), Error, "an empty chart");
assert.throws(
  () => auditSeatingChart([["a", "b"], ["c"]], [], []),
  Error,
  "bands of differing length are rejected",
);
assert.throws(
  () => auditSeatingChart([["a", 7]], [], []),
  Error,
  "a cell that is not a string is rejected",
);
assert.throws(
  () => auditSeatingChart([["a", "a"]], [], []),
  Error,
  "a name written twice is rejected",
);
assert.throws(
  () => auditSeatingChart([["a", "b"]], [["a", "zz"]], []),
  Error,
  "a tie naming somebody absent is rejected",
);
assert.throws(
  () => auditSeatingChart([["a", "b"]], [["a", "a"]], []),
  Error,
  "a tie naming one person twice is rejected",
);
assert.throws(
  () => auditSeatingChart([["a", "b"]], [["a", "b", "c"]], []),
  Error,
  "a tie of three names is rejected",
);
assert.throws(
  () => auditSeatingChart([["a", "b"]], "nope", []),
  Error,
  "a list of ties that is not a list is rejected",
);
console.log("ok");
