import assert from "node:assert/strict";
import { activityFloatTable } from "./solution.ts";

assert.deepEqual(
  activityFloatTable([
    { name: "a", days: 3, after: [] },
    { name: "b", days: 2, after: ["a"] },
    { name: "c", days: 4, after: ["a"] },
    { name: "d", days: 1, after: ["b", "c"] },
  ]),
  ["a 0 0 0", "b 3 5 2", "c 3 3 0", "d 7 7 0"],
  "a fork and a join, with slack on the short arm",
);
assert.deepEqual(
  activityFloatTable([{ name: "solo", days: 5, after: [] }]),
  ["solo 0 0 0"],
  "one activity alone",
);
assert.deepEqual(
  activityFloatTable([
    { name: "x", days: 2, after: [] },
    { name: "y", days: 5, after: [] },
  ]),
  ["x 0 3 3", "y 0 0 0"],
  "two activities with nothing between them",
);
assert.deepEqual(
  activityFloatTable([
    { name: "zip", days: 1, after: [] },
    { name: "arc", days: 2, after: ["zip"] },
    { name: "mid", days: 3, after: ["arc"] },
  ]),
  ["arc 1 1 0", "mid 3 3 0", "zip 0 0 0"],
  "a chain reported in name order, not plan order",
);
assert.deepEqual(
  activityFloatTable([
    { name: "p", days: 1, after: [] },
    { name: "q", days: 1, after: ["p"] },
    { name: "r", days: 6, after: ["p"] },
    { name: "s", days: 1, after: ["q", "r"] },
  ]),
  ["p 0 0 0", "q 1 6 5", "r 1 1 0", "s 7 7 0"],
  "a wide diamond gives one arm five days of slack",
);
assert.throws(() => activityFloatTable("a"), Error, "not a list");
assert.throws(() => activityFloatTable([]), Error, "an empty plan");
assert.throws(() => activityFloatTable(["a"]), Error, "an entry that is not a mapping");
assert.throws(
  () => activityFloatTable([{ name: "", days: 1, after: [] }]),
  Error,
  "an empty name",
);
assert.throws(
  () => activityFloatTable([
    { name: "a", days: 1, after: [] },
    { name: "a", days: 2, after: [] },
  ]),
  Error,
  "two entries share a name",
);
assert.throws(
  () => activityFloatTable([{ name: "a", days: 0, after: [] }]),
  Error,
  "zero days",
);
assert.throws(
  () => activityFloatTable([{ name: "a", days: 1.5, after: [] }]),
  Error,
  "a fractional day count",
);
assert.throws(
  () => activityFloatTable([{ name: "a", days: 1, after: "b" }]),
  Error,
  "an after list that is not a list",
);
assert.throws(
  () => activityFloatTable([{ name: "a", days: 1, after: ["ghost"] }]),
  Error,
  "an after entry naming nothing",
);
assert.throws(
  () => activityFloatTable([{ name: "a", days: 1, after: ["a"] }]),
  Error,
  "an activity waiting on itself",
);
assert.throws(
  () => activityFloatTable([
    { name: "a", days: 1, after: ["b"] },
    { name: "b", days: 1, after: ["a"] },
  ]),
  Error,
  "a loop",
);
console.log("ok");
